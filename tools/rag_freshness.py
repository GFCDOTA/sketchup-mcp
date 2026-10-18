"""rag_freshness.py — FP-037: freshness, cache-invalidation e source-registry do RAG do arquiteto.

Camada PURA e DETERMINÍSTICA (roda SEMPRE no CI, zero infra externa). Responde a
UMA pergunta de honestidade: *o índice/contexto que o arquiteto vai consumir ainda
reflete a verdade das fontes?* Se a fonte mudou e o índice não, o contexto está
STALE — e contexto stale NÃO pode ser usado silenciosamente.

Peças:
  - source registry: as fontes CANÔNICAS de conhecimento (DNA do Felipe, tokens
    curados, design_rules, anti-patterns, consensus/semantic_zones da planta,
    learning patches). Cada uma vira um `document` com content_hash (sha256),
    document_version (= content_hash) e updated_at (mtime iso, determinístico).
  - chunking + chunk_hash: cada documento é fatiado; cada chunk tem chunk_hash
    (sha256 do conteúdo) — a UNIDADE de reindex incremental.
  - corpus_version: sha256 dos document_version de todos os documentos ATIVOS,
    ordenado. Muda quando QUALQUER fonte muda (add/edit/remove) e SÓ então.
  - reindex incremental: chunk com hash igual = reusa (não re-embeda); hash novo
    = reindexa; chunk sumido = is_active=false (soft-delete, histórico preservado).
  - freshness guard: rejeita chunk inativo / de corpus_version antigo; sinaliza
    stale quando o doc é mais novo que o índice. LOGA a degradação.
  - cache de resposta do arquiteto: chave inclui corpus_version -> mudou o corpus,
    cache antigo vira MISS por dependência (invalidação automática).

O estado mora em SQLite (`.ai_bridge/rag_freshness.db`), índice DERIVADO e
reconstruível (`reindex --rebuild`). As fontes continuam sendo a verdade.
stdlib only na camada pura (sqlite3/hashlib/json/pathlib). O embed real (Ollama)
e o vector store (Qdrant) são opcionais e vivem no adapter de reindex (backend
embed), sempre atrás de import lazy — o CI nunca depende deles.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / ".ai_bridge" / "rag_freshness.db"

# versão da CONFIG de retrieval — entra na chave do cache do arquiteto. Bump manual
# quando a lógica de retrieval/ranking muda de forma que invalida respostas cacheadas.
RETRIEVAL_CONFIG_VERSION = "fp037.v1"

log = logging.getLogger("rag_freshness")

# ---------------------------------------------------------------------------
# Source registry — fontes CANÔNICAS de conhecimento do arquiteto.
#
# (glob relativo à raiz do repo, source_type, estratégia de chunk). Só entra o
# que É conhecimento de DESIGN consumido pelo arquiteto; ruído operacional fica
# fora (mesma filosofia do project_memory_db.SOURCES, mas escopo = design corpus).
# Estratégia: md = por seção (heading) · whole = arquivo inteiro · json = por
# item/chave · token = 1 chunk por token curado (nome+rule+anti_pattern).
# ---------------------------------------------------------------------------
SOURCES: list[tuple[str, str, str]] = [
    (".claude/memory/felipe_style_dna.md",                          "style_dna",     "md"),
    ("references/tokens/*.json",                                     "token",         "token"),
    ("references/design_rules/felipe_visual_judge_rules.json",       "design_rule",   "json"),
    ("references/design_rules/furniture_rule_cards.json",            "design_rule",   "json"),
    ("references/felipe/anti_patterns/*.json",                       "anti_pattern",  "json"),
    # write-back do GOSTO do Felipe (taste_writeback): sem este glob o veredito
    # curado nunca muda o corpus_version nem entra no Qdrant (o "buraco central").
    ("references/felipe/verdicts/*.json",                            "human_verdict", "json"),
    ("fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json",
                                                                     "consensus",     "consensus"),
    ("fixtures/planta_74/semantic_zones.json",                       "semantic_zones", "json"),
    (".ai_bridge/learning_patches/*.json",                          "learning_patch", "json"),
]

MAX_CHARS = 4000
MIN_CHARS = 20

SCHEMA = """
CREATE TABLE IF NOT EXISTS document (
    document_id      TEXT PRIMARY KEY,
    source_path      TEXT NOT NULL,
    source_type      TEXT NOT NULL,
    content_hash     TEXT NOT NULL,
    document_version TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    is_active        INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS chunk (
    chunk_id         TEXT PRIMARY KEY,
    document_id      TEXT NOT NULL,
    document_version TEXT NOT NULL,
    chunk_index      INTEGER NOT NULL,
    title            TEXT,
    text             TEXT NOT NULL,
    chunk_hash       TEXT NOT NULL,
    corpus_version   TEXT NOT NULL,
    source_path      TEXT NOT NULL,
    source_type      TEXT NOT NULL,
    indexed_at       TEXT NOT NULL,
    is_active        INTEGER NOT NULL DEFAULT 1,
    embedded         INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_chunk_doc    ON chunk(document_id);
CREATE INDEX IF NOT EXISTS ix_chunk_active ON chunk(is_active);
CREATE TABLE IF NOT EXISTS arch_cache (
    cache_key      TEXT PRIMARY KEY,
    corpus_version TEXT NOT NULL,
    room_id        TEXT,
    style_profile  TEXT,
    response_json  TEXT NOT NULL,
    created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_cache_corpus ON arch_cache(corpus_version);
"""


# ---------------------------------------------------------------------------
# hashing determinístico
# ---------------------------------------------------------------------------
def _sha(s: str | bytes) -> str:
    b = s.encode("utf-8") if isinstance(s, str) else s
    return hashlib.sha256(b).hexdigest()


def _mtime_iso(p: Path) -> str:
    """mtime UTC ISO — determinístico (não usa clock atual)."""
    return _dt.datetime.fromtimestamp(
        p.stat().st_mtime, _dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def document_id_for(rel_path: str) -> str:
    """document_id estável = path relativo posix (uma fonte = um documento)."""
    return rel_path


# ---------------------------------------------------------------------------
# chunking por estratégia
# ---------------------------------------------------------------------------
_HEADING = "#"


def _pack(text: str, max_chars: int = MAX_CHARS) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    out: list[str] = []
    buf = ""
    for para in text.split("\n\n"):
        if not buf:
            buf = para
        elif len(buf) + len(para) + 2 <= max_chars:
            buf = f"{buf}\n\n{para}"
        else:
            out.append(buf)
            buf = para
        while len(buf) > max_chars:
            out.append(buf[:max_chars])
            buf = buf[max_chars:]
    if buf:
        out.append(buf)
    return out


def _chunks_md(text: str) -> list[tuple[str | None, str]]:
    sections: list[tuple[str | None, list[str]]] = []
    title: str | None = None
    buf: list[str] = []
    started = False
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(_HEADING) and stripped.lstrip("#").startswith(" "):
            if started or buf:
                sections.append((title, buf))
            title = line.lstrip("#").strip()
            buf = [line]
            started = True
        else:
            buf.append(line)
    if buf:
        sections.append((title, buf))
    out: list[tuple[str | None, str]] = []
    for t, lines in sections:
        sec = "\n".join(lines).strip()
        for piece in _pack(sec):
            if piece.strip():
                out.append((t, piece.strip()))
    return out


def _chunks_whole(text: str, stem: str) -> list[tuple[str | None, str]]:
    txt = text.strip()
    return [(stem, p.strip()) for p in _pack(txt) if p.strip()] if txt else []


def _chunks_token(text: str, stem: str) -> list[tuple[str | None, str]]:
    """Token curado -> 1 chunk semântico: nome + rule/title + anti_pattern + custo.
    Determinístico: ordena as chaves relevantes; NÃO serializa o dict inteiro
    (params numéricos ruidosos não ajudam o recall e inflam o chunk)."""
    try:
        d = json.loads(text)
    except json.JSONDecodeError:
        return _chunks_whole(text, stem)
    name = d.get("name") or stem
    parts = [f"token: {name}"]
    for key in ("title", "rule", "appearance", "anti_pattern", "cost_relative"):
        v = d.get(key)
        if v:
            parts.append(f"{key}: {v}")
    kinds = d.get("applies_to_kinds") or []
    if kinds:
        parts.append("applies_to_kinds: " + ", ".join(kinds))
    blob = "\n".join(parts).strip()
    return [(name, p) for p in _pack(blob) if p.strip()]


def _chunks_json(text: str, stem: str) -> list[tuple[str | None, str]]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    out: list[tuple[str | None, str]] = []

    def title_of(item: object, fallback: str) -> str:
        if isinstance(item, dict):
            for k in ("id", "name", "title", "rule_id", "card_id", "nivel"):
                if item.get(k):
                    return str(item[k])
        return fallback

    def emit_list(prefix: str, lst: list) -> None:
        for i, item in enumerate(lst):
            out.append((title_of(item, f"{prefix}[{i}]"),
                        json.dumps(item, ensure_ascii=False, sort_keys=True)))

    if isinstance(data, list):
        emit_list(stem, data)
    elif isinstance(data, dict):
        for key in sorted(data.keys()):  # ordem estável -> chunk_index determinístico
            val = data[key]
            if isinstance(val, list) and val:
                emit_list(key, val)
            else:
                out.append((key, f"{key}: {json.dumps(val, ensure_ascii=False, sort_keys=True)}"))
    else:
        out.append((stem, json.dumps(data, ensure_ascii=False, sort_keys=True)))
    packed: list[tuple[str | None, str]] = []
    for t, txt in out:
        for piece in _pack(txt):
            packed.append((t, piece))
    return packed


def _chunks_consensus(text: str, stem: str) -> list[tuple[str | None, str]]:
    """consensus da planta -> 1 chunk por ROOM (nome+área) + 1 por opening-set.
    Só o que é LINGUAGEM de layout consultável; não a geometria pt-a-pt inteira
    (que é ruído semântico). Determinístico: ordena por id."""
    try:
        d = json.loads(text)
    except json.JSONDecodeError:
        return []
    out: list[tuple[str | None, str]] = []
    rooms = d.get("rooms") or []
    for r in sorted(rooms, key=lambda x: str(x.get("id") or x.get("name") or "")):
        rid = r.get("id") or r.get("name") or "?"
        name = r.get("name") or "?"
        area = r.get("area_pts2")
        out.append((f"room:{rid}",
                    json.dumps({"id": rid, "name": name, "area_pts2": area},
                               ensure_ascii=False, sort_keys=True)))
    # bloco de contagem estrutural (muda se paredes/openings mudam) -> sinal de versão
    summary = {
        "n_rooms": len(rooms),
        "n_walls": len(d.get("walls") or []),
        "n_openings": len(d.get("openings") or []),
    }
    out.append(("consensus_summary",
                json.dumps(summary, ensure_ascii=False, sort_keys=True)))
    return out


def chunk_document(text: str, strategy: str, stem: str) -> list[tuple[str | None, str]]:
    if strategy == "md":
        return _chunks_md(text)
    if strategy == "token":
        return _chunks_token(text, stem)
    if strategy == "consensus":
        return _chunks_consensus(text, stem)
    if strategy == "json":
        return _chunks_json(text, stem)
    return _chunks_whole(text, stem)


# ---------------------------------------------------------------------------
# source registry — descobre os documentos ativos no disco
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SourceDoc:
    document_id: str
    source_path: str
    source_type: str
    strategy: str
    content_hash: str
    updated_at: str
    text: str

    @property
    def document_version(self) -> str:
        return self.content_hash


def discover_sources(root: Path = ROOT) -> list[SourceDoc]:
    """Varre o SOURCES e devolve os documentos que EXISTEM no disco, ordenados
    por document_id (determinístico). content_hash = sha256 do conteúdo bruto."""
    docs: dict[str, SourceDoc] = {}
    for pattern, stype, strat in SOURCES:
        for path in sorted(root.glob(pattern)):
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            try:
                raw = path.read_bytes()
            except OSError:
                continue
            text = raw.decode("utf-8", errors="replace")
            docs[rel] = SourceDoc(
                document_id=document_id_for(rel),
                source_path=rel,
                source_type=stype,
                strategy=strat,
                content_hash=_sha(raw),
                updated_at=_mtime_iso(path),
                text=text,
            )
    return [docs[k] for k in sorted(docs)]


def compute_corpus_version(docs: list[SourceDoc]) -> str:
    """corpus_version = sha256 dos document_version dos documentos ATIVOS, ORDENADO
    por document_id. Determinístico: mesma coleção -> mesmo hash; qualquer doc
    add/edit/remove -> hash diferente. Coleção vazia -> hash do vazio (estável)."""
    payload = "\n".join(f"{d.document_id}={d.document_version}"
                        for d in sorted(docs, key=lambda x: x.document_id))
    return _sha(payload)


# ---------------------------------------------------------------------------
# db
# ---------------------------------------------------------------------------
def connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    # lê DEFAULT_DB dinamicamente (não como default de arg) pra respeitar
    # monkeypatch do módulo em teste e override em runtime.
    p = Path(db_path if db_path is not None else DEFAULT_DB)
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def current_corpus_version(con: sqlite3.Connection) -> str | None:
    """corpus_version indexado (o mais recente entre os chunks ATIVOS). None se vazio."""
    row = con.execute(
        "SELECT corpus_version FROM chunk WHERE is_active=1 "
        "ORDER BY indexed_at DESC LIMIT 1").fetchone()
    return row["corpus_version"] if row else None


# ---------------------------------------------------------------------------
# reindex incremental (camada pura — sem embed)
#
# Compara o disco (discover_sources) com o índice. Por chunk:
#   hash igual  -> REUSA (não re-embeda; só re-carimba corpus_version)
#   hash novo   -> REINDEXA (embedded=0 -> o backend embed re-embeda)
#   sumido      -> is_active=false (soft-delete; histórico preservado)
# Documento sumido -> todos os chunks dele viram is_active=false.
# Retorna um relatório determinístico (contagens + corpus_version novo).
# ---------------------------------------------------------------------------
def reindex(con: sqlite3.Connection, *, root: Path = ROOT, now_iso: str,
            rebuild: bool = False) -> dict:
    """Reindex incremental determinístico. `now_iso` é INJETADO (sem clock real)
    -> testável e reproduzível. NÃO embeda (isso é do backend embed); marca
    embedded=0 nos chunks novos."""
    if rebuild:
        con.execute("DELETE FROM chunk")
        con.execute("DELETE FROM document")

    docs = discover_sources(root)
    corpus_version = compute_corpus_version(docs)
    active_doc_ids = {d.document_id for d in docs}

    report = {
        "corpus_version": corpus_version,
        "docs_active": len(docs),
        "chunks_reused": 0,
        "chunks_reindexed": 0,
        "chunks_deactivated": 0,
        "docs_deactivated": 0,
    }

    # documentos que sumiram do disco -> soft-delete (doc + chunks)
    known_doc_ids = {r["document_id"] for r in
                     con.execute("SELECT document_id FROM document WHERE is_active=1")}
    for gone in sorted(known_doc_ids - active_doc_ids):
        con.execute("UPDATE document SET is_active=0 WHERE document_id=?", (gone,))
        n = con.execute(
            "UPDATE chunk SET is_active=0 WHERE document_id=? AND is_active=1",
            (gone,)).rowcount
        report["docs_deactivated"] += 1
        report["chunks_deactivated"] += n
        log.info("reindex: documento removido -> soft-delete document_id=%s chunks=%d",
                 gone, n)

    for doc in docs:
        con.execute(
            "INSERT INTO document (document_id, source_path, source_type, "
            "content_hash, document_version, updated_at, is_active) "
            "VALUES (?,?,?,?,?,?,1) "
            "ON CONFLICT(document_id) DO UPDATE SET "
            "source_path=excluded.source_path, source_type=excluded.source_type, "
            "content_hash=excluded.content_hash, document_version=excluded.document_version, "
            "updated_at=excluded.updated_at, is_active=1",
            (doc.document_id, doc.source_path, doc.source_type,
             doc.content_hash, doc.document_version, doc.updated_at))

        stem = Path(doc.source_path).stem
        raw_chunks = chunk_document(doc.text, doc.strategy, stem)
        # chunk_id ESTÁVEL por (document_id, chunk_index) — sobrevive a edições do
        # conteúdo (o hash muda, o id não) -> permite comparar hash antigo vs novo.
        desired: dict[str, dict] = {}
        for idx, (title, text) in enumerate(raw_chunks):
            text = text.strip()
            if len(text) < MIN_CHARS:
                continue
            chunk_id = _sha(f"{doc.document_id}#{idx}")[:20]
            desired[chunk_id] = {
                "chunk_id": chunk_id, "chunk_index": idx, "title": title,
                "text": text, "chunk_hash": _sha(text),
            }

        existing = {r["chunk_id"]: r for r in con.execute(
            "SELECT chunk_id, chunk_hash, is_active, embedded FROM chunk "
            "WHERE document_id=?", (doc.document_id,))}

        # chunks que sumiram deste documento -> soft-delete
        for gone_cid in sorted(set(existing) - set(desired)):
            if existing[gone_cid]["is_active"]:
                con.execute("UPDATE chunk SET is_active=0 WHERE chunk_id=?", (gone_cid,))
                report["chunks_deactivated"] += 1

        for cid in sorted(desired):
            d = desired[cid]
            prev = existing.get(cid)
            if prev is not None and prev["chunk_hash"] == d["chunk_hash"]:
                # hash igual -> REUSA embedding; só re-carimba versão/atividade
                con.execute(
                    "UPDATE chunk SET corpus_version=?, document_version=?, "
                    "is_active=1, source_path=?, source_type=?, title=? "
                    "WHERE chunk_id=?",
                    (corpus_version, doc.document_version, doc.source_path,
                     doc.source_type, d["title"], cid))
                report["chunks_reused"] += 1
            else:
                # hash novo (ou chunk novo) -> REINDEXA; embedded=0 pro backend embed
                con.execute(
                    "INSERT INTO chunk (chunk_id, document_id, document_version, "
                    "chunk_index, title, text, chunk_hash, corpus_version, "
                    "source_path, source_type, indexed_at, is_active, embedded) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,1,0) "
                    "ON CONFLICT(chunk_id) DO UPDATE SET "
                    "document_version=excluded.document_version, "
                    "chunk_index=excluded.chunk_index, title=excluded.title, "
                    "text=excluded.text, chunk_hash=excluded.chunk_hash, "
                    "corpus_version=excluded.corpus_version, "
                    "source_path=excluded.source_path, source_type=excluded.source_type, "
                    "indexed_at=excluded.indexed_at, is_active=1, embedded=0",
                    (cid, doc.document_id, doc.document_version, d["chunk_index"],
                     d["title"], d["text"], d["chunk_hash"], corpus_version,
                     doc.source_path, doc.source_type, now_iso))
                report["chunks_reindexed"] += 1

    con.commit()
    log.info("reindex: corpus_version=%s docs=%d reused=%d reindexed=%d "
             "deactivated=%d", corpus_version[:12], report["docs_active"],
             report["chunks_reused"], report["chunks_reindexed"],
             report["chunks_deactivated"])
    return report


# ---------------------------------------------------------------------------
# freshness guard — o portão ANTES do arquiteto consumir contexto RAG
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class FreshnessResult:
    fresh_chunks: list[dict]
    rejected: list[dict]        # {chunk_id, reason}
    stale: list[dict]           # {chunk_id, document_id, reason} — doc mais novo que índice
    corpus_version: str | None

    @property
    def has_stale(self) -> bool:
        return bool(self.stale)


def active_chunks(con: sqlite3.Connection, corpus_version: str) -> list[dict]:
    """Chunks ATIVOS do corpus_version dado, ordenados por (document_id, chunk_index)."""
    rows = con.execute(
        "SELECT chunk_id, document_id, document_version, chunk_index, title, text, "
        "chunk_hash, corpus_version, source_path, source_type, indexed_at, embedded "
        "FROM chunk WHERE is_active=1 AND corpus_version=? "
        "ORDER BY document_id, chunk_index", (corpus_version,))
    return [dict(r) for r in rows]


def freshness_guard(con: sqlite3.Connection, candidate_chunks: list[dict], *,
                    root: Path = ROOT) -> FreshnessResult:
    """Filtra os chunks candidatos ANTES do arquiteto. Rejeita chunk se:
      - is_active == false (não consultável);
      - chunk.corpus_version != current_corpus_version (índice de outra geração).
    Sinaliza STALE (mas NÃO usa silenciosamente) se a fonte mudou depois do índice
    (document.updated_at > chunk.indexed_at) OU o content_hash do disco divergiu do
    indexado. Determinístico: usa mtime/hash do disco, sem clock atual.
    """
    current = current_corpus_version(con)
    # mapa document_id -> (updated_at no disco, content_hash no disco)
    disk = {d.document_id: d for d in discover_sources(root)}

    fresh: list[dict] = []
    rejected: list[dict] = []
    stale: list[dict] = []

    for ch in candidate_chunks:
        cid = ch.get("chunk_id")
        # atividade real do índice (o candidato pode ter sido passado stale de fora)
        row = con.execute(
            "SELECT is_active, corpus_version, indexed_at, document_version "
            "FROM chunk WHERE chunk_id=?", (cid,)).fetchone()
        if row is None or not row["is_active"]:
            rejected.append({"chunk_id": cid, "reason": "inactive"})
            log.info("freshness: REJEITADO chunk=%s motivo=inactive", cid)
            continue
        if current is not None and row["corpus_version"] != current:
            rejected.append({"chunk_id": cid, "reason": "stale_corpus_version"})
            log.info("freshness: REJEITADO chunk=%s motivo=stale_corpus_version "
                     "(chunk=%s current=%s)", cid, row["corpus_version"][:12],
                     current[:12])
            continue
        # chunk ativo e do corpus atual -> checa se a FONTE ficou mais nova que o índice
        doc = disk.get(ch.get("document_id"))
        if doc is not None:
            source_moved = doc.updated_at > row["indexed_at"]
            hash_diverged = doc.document_version != row["document_version"]
            if source_moved or hash_diverged:
                reason = "source_newer_than_index" if source_moved else "content_hash_diverged"
                stale.append({"chunk_id": cid, "document_id": ch.get("document_id"),
                              "reason": reason})
                log.warning("freshness: STALE chunk=%s doc=%s motivo=%s "
                            "(NÃO usado silenciosamente)", cid, ch.get("document_id"),
                            reason)
                continue
        fresh.append(ch)

    return FreshnessResult(fresh_chunks=fresh, rejected=rejected, stale=stale,
                           corpus_version=current)


# ---------------------------------------------------------------------------
# cache do arquiteto — chave dependente do corpus_version (invalidação automática)
# ---------------------------------------------------------------------------
def cache_key(*, query_hash: str, corpus_version: str, room_id: str | None,
              style_profile: str | None,
              retrieval_config_version: str = RETRIEVAL_CONFIG_VERSION) -> str:
    """sha256(query_hash + corpus_version + room_id + style_profile + config_version).
    corpus_version na chave => corpus mudou -> chave nova -> MISS automático no
    cache antigo (invalidação por dependência, sem varredura)."""
    payload = "|".join([
        query_hash or "", corpus_version or "", room_id or "",
        style_profile or "", retrieval_config_version or "",
    ])
    return _sha(payload)


def query_hash(query: str) -> str:
    return _sha(query or "")


def cache_get(con: sqlite3.Connection, key: str) -> dict | None:
    row = con.execute(
        "SELECT response_json, corpus_version FROM arch_cache WHERE cache_key=?",
        (key,)).fetchone()
    if row is None:
        log.info("cache: MISS key=%s motivo=absent", key[:12])
        return None
    current = current_corpus_version(con)
    if current is not None and row["corpus_version"] != current:
        # defesa-em-profundidade: mesmo colidindo a chave, corpus divergente = MISS
        log.info("cache: MISS key=%s motivo=corpus_version_mismatch", key[:12])
        return None
    log.info("cache: HIT key=%s", key[:12])
    return json.loads(row["response_json"])


def cache_put(con: sqlite3.Connection, key: str, *, corpus_version: str,
              room_id: str | None, style_profile: str | None,
              response: dict, now_iso: str) -> None:
    con.execute(
        "INSERT INTO arch_cache (cache_key, corpus_version, room_id, style_profile, "
        "response_json, created_at) VALUES (?,?,?,?,?,?) "
        "ON CONFLICT(cache_key) DO UPDATE SET "
        "corpus_version=excluded.corpus_version, response_json=excluded.response_json, "
        "created_at=excluded.created_at",
        (key, corpus_version, room_id, style_profile,
         json.dumps(response, ensure_ascii=False, sort_keys=True), now_iso))
    con.commit()
    log.info("cache: PUT key=%s corpus=%s", key[:12], corpus_version[:12])


def purge_stale_cache(con: sqlite3.Connection) -> int:
    """Remove entradas de cache cujo corpus_version não é mais o atual. Opcional
    (o cache_get já dá MISS por mismatch); mantém o .db enxuto. Retorna nº removido."""
    current = current_corpus_version(con)
    if current is None:
        return 0
    n = con.execute("DELETE FROM arch_cache WHERE corpus_version != ?",
                    (current,)).rowcount
    con.commit()
    if n:
        log.info("cache: purge de %d entradas de corpus antigo", n)
    return n
