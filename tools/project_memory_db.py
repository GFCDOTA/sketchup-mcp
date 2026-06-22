"""project_memory_db.py — RAG #2: memória de longo prazo do PROJETO ("cérebro do arquiteto").

Distinto de `reference_db.py` (RAG #1 = referências visuais de design). Aqui
indexamos o conhecimento ACUMULADO e espalhado do projeto — decisões, vereditos
de gate, lições (FP/LL), ciclos de design, marcos, ergonomia — para que os
agentes (arquiteto / PM / lead) consultem "o que já fizemos e aprendemos" por
BUSCA SEMÂNTICA, antes de decidir, em vez de depender do relay verbal do Felipe.

Stack local-first, ZERO infra nova:
  - embeddings: Ollama `nomic-embed-text` (768d) via urllib (sem `requests`)
  - store:      SQLite (`.ai_bridge/project_memory.db`), embedding em BLOB float32
  - busca:      cosseno em numpy (corpus pequeno) — sem sqlite-vec, sem Qdrant

Invariantes:
  - O `.db` é índice DERIVADO e reconstruível (`--rebuild`). Os arquivos-fonte
    continuam sendo a verdade.
  - RAG é CONSULTIVO: os gates determinísticos continuam decidindo. Esta base
    responde "o que já aconteceu?", nunca "está certo?".
  - Idempotente: rodar 2× = mesmo resultado (dedup por hash de conteúdo; só
    reembeda arquivo que mudou).

Uso:
    python tools/project_memory_db.py index  [--corpus-root <path>] [--rebuild]
    python tools/project_memory_db.py search "como julgamos a proporção do sofá?" [--k 6]
    python tools/project_memory_db.py stats
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = REPO_ROOT / ".ai_bridge" / "project_memory.db"

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "nomic-embed-text")

MAX_CHARS = 4000   # ~1000 tokens — folga p/ o contexto do nomic; evita truncar
MIN_CHARS = 30     # descarta migalha sem sinal

SCHEMA = """
CREATE TABLE IF NOT EXISTS chunk (
    id          TEXT PRIMARY KEY,
    source_path TEXT NOT NULL,
    source_type TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    title       TEXT,
    text        TEXT NOT NULL,
    text_hash   TEXT NOT NULL,
    dim         INTEGER NOT NULL,
    embedding   BLOB NOT NULL,
    created_at  TEXT
);
CREATE INDEX IF NOT EXISTS ix_chunk_source ON chunk(source_path);
CREATE INDEX IF NOT EXISTS ix_chunk_type   ON chunk(source_type);
"""

# (glob relativo ao corpus-root, source_type, estratégia de chunk)
# Estratégia: md = por seção (heading 1-3) · whole = arquivo inteiro · jsonl = 1
# objeto/linha · json = lista→por item / dict→por chave (ou lista interna).
# Deliberadamente FORA (ruído operacional sem valor semântico): audit heartbeat,
# noc/queue+actions, logs/events, questions/responses legados. Ver README.
SOURCES: list[tuple[str, str, str]] = [
    (".ai_bridge/HANDOFF.md",                       "handoff",  "md"),
    (".ai_bridge/interior_consult/HANDOFF.md",      "handoff",  "md"),
    (".ai_bridge/STUDIO_HANDOFF.md",                "handoff",  "md"),
    (".ai_bridge/fidelity/verdicts/*.md",           "verdict",  "whole"),
    (".ai_bridge/knowledge/*.md",                   "knowledge","md"),
    (".ai_bridge/lessons/*.md",                     "lesson",   "whole"),
    (".ai_bridge/ROOM_CYCLE_PLAN.md",               "plan",     "md"),
    (".ai_bridge/STUDIO_BACKLOG.md",                "plan",     "md"),
    (".ai_bridge/interior_consult/next_microtasks.md", "plan",  "md"),
    (".ai_bridge/interior_consult/cycles.jsonl",    "cycle",    "jsonl"),
    (".ai_bridge/interior_consult/answered/*.md",   "consult",  "whole"),
    (".ai_bridge/interior_consult/inbox/*answer*.md","consult", "whole"),
    (".ai_bridge/interior_feedback/approved/*.md",  "feedback", "whole"),
    (".ai_bridge/interior_feedback/corrections/*.md","feedback","whole"),
    (".ai_bridge/research/*.json",                  "research", "json"),
    (".ai_bridge/learning_patches/*.json",          "learning", "json"),
    (".ai_bridge/interior_cycles/*.json",           "cycle",    "json"),
    ("tools/claude_bridge/marcos.json",             "marco",    "json"),
]

_HEADING = re.compile(r"^#{1,3}\s+\S")


# ----------------------------------------------------------------------------- embed
def embed(text: str, *, timeout: int = 120) -> np.ndarray:
    """Embedding local via Ollama (urllib, sem requests). Levanta se vazio/offline."""
    payload = json.dumps({"model": EMBED_MODEL, "prompt": text}).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/embeddings", data=payload,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
        raise RuntimeError(
            f"Ollama embed falhou em {OLLAMA_URL} (modelo {EMBED_MODEL!r}): {e!r}. "
            f"Ollama está de pé? `ollama pull {EMBED_MODEL}` foi feito?"
        ) from e
    vec = body.get("embedding") or []
    if not vec:
        raise RuntimeError(f"embedding vazio p/ texto de {len(text)} chars")
    return np.asarray(vec, dtype=np.float32)


# ----------------------------------------------------------------------------- chunking
def _pack(text: str, max_chars: int = MAX_CHARS) -> list[str]:
    """Quebra texto longo em pedaços <= max_chars em fronteiras de parágrafo."""
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
        while len(buf) > max_chars:  # parágrafo gigante: corte duro
            out.append(buf[:max_chars])
            buf = buf[max_chars:]
    if buf:
        out.append(buf)
    return out


def _split_md(text: str) -> list[tuple[str | None, str]]:
    """Divide markdown por heading (nível 1-3). Cada seção = 1 chunk (sub-quebra se grande)."""
    sections: list[tuple[str | None, list[str]]] = []
    title: str | None = None
    buf: list[str] = []
    started = False
    for line in text.splitlines():
        if _HEADING.match(line):
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


def _chunks_whole(path: Path) -> list[tuple[str | None, str]]:
    txt = path.read_text("utf-8", errors="replace").strip()
    return [(path.stem, p.strip()) for p in _pack(txt) if p.strip()] if txt else []


def _chunks_md(path: Path) -> list[tuple[str | None, str]]:
    return _split_md(path.read_text("utf-8", errors="replace"))


def _chunks_jsonl(path: Path) -> list[tuple[str | None, str]]:
    out: list[tuple[str | None, str]] = []
    for i, line in enumerate(path.read_text("utf-8", errors="replace").splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        title = None
        if isinstance(obj, dict):
            for k in ("cycle_id", "id", "mt", "object_id", "kind"):
                if obj.get(k):
                    title = str(obj[k])
                    break
        out.append((title or f"[{i}]", json.dumps(obj, ensure_ascii=False)))
    return out


def _chunks_json(path: Path) -> list[tuple[str | None, str]]:
    try:
        data = json.loads(path.read_text("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return []
    out: list[tuple[str | None, str]] = []

    def title_of(item: object, fallback: str) -> str:
        if isinstance(item, dict):
            for k in ("id", "nivel", "titulo", "title", "cycle_id", "name"):
                if item.get(k):
                    return str(item[k])
        return fallback

    def emit_list(prefix: str, lst: list) -> None:
        for i, item in enumerate(lst):
            out.append((title_of(item, f"{prefix}[{i}]"),
                        json.dumps(item, ensure_ascii=False)))

    if isinstance(data, list):
        emit_list(path.stem, data)
    elif isinstance(data, dict):
        for key, val in data.items():
            if isinstance(val, list) and val:
                emit_list(key, val)
            else:
                out.append((key, f"{key}: {json.dumps(val, ensure_ascii=False)}"))
    else:
        out.append((path.stem, json.dumps(data, ensure_ascii=False)))
    # sub-quebra itens grandes
    packed: list[tuple[str | None, str]] = []
    for t, txt in out:
        for piece in _pack(txt):
            packed.append((t, piece))
    return packed


_DISPATCH = {"whole": _chunks_whole, "md": _chunks_md,
             "jsonl": _chunks_jsonl, "json": _chunks_json}


# ----------------------------------------------------------------------------- db
def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    con.executescript(SCHEMA)
    return con


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _mtime_iso(p: Path) -> str:
    return _dt.datetime.fromtimestamp(
        p.stat().st_mtime, _dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ----------------------------------------------------------------------------- commands
def cmd_index(args: argparse.Namespace) -> int:
    corpus = Path(args.corpus_root).resolve()
    db_path = Path(args.db).resolve()
    if not corpus.is_dir():
        print(f"corpus-root inexistente: {corpus}", file=sys.stderr)
        return 2
    con = connect(db_path)
    cur = con.cursor()
    if args.rebuild:
        cur.execute("DROP TABLE IF EXISTS chunk")
        con.executescript(SCHEMA)
        print("[rebuild] tabela chunk recriada")

    n_new = n_skip_files = n_files = 0
    for pattern, stype, strat in SOURCES:
        for path in sorted(corpus.glob(pattern)):
            if not path.is_file():
                continue
            n_files += 1
            rel = path.relative_to(corpus).as_posix()
            raw = _DISPATCH[strat](path)
            recs = []
            for idx, (title, text) in enumerate(raw):
                text = text.strip()
                if len(text) < MIN_CHARS:
                    continue
                cid = _sha(f"{rel}#{idx}#{text}")[:16]
                recs.append((cid, rel, stype, idx, title, text))
            if not recs:
                continue
            existing = {r[0] for r in cur.execute(
                "SELECT id FROM chunk WHERE source_path=?", (rel,))}
            if existing == {r[0] for r in recs}:
                n_skip_files += 1
                continue  # arquivo inalterado — não reembeda
            cur.execute("DELETE FROM chunk WHERE source_path=?", (rel,))
            created = _mtime_iso(path)
            for cid, rel_, stype_, idx, title, text in recs:
                emb = embed(f"[{stype_}] {title or ''}\n{text}")
                cur.execute(
                    "INSERT OR REPLACE INTO chunk "
                    "(id,source_path,source_type,chunk_index,title,text,text_hash,dim,embedding,created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (cid, rel_, stype_, idx, title, text, _sha(text),
                     int(emb.shape[0]), emb.tobytes(), created),
                )
                n_new += 1
            con.commit()
            print(f"  + {rel}  ({len(recs)} chunks)")
    print(f"\n[index] {n_files} arquivos | {n_new} chunks embedados | "
          f"{n_skip_files} arquivos inalterados (pulados)")
    print(f"[index] db: {db_path}")
    return 0


def _load_matrix(con: sqlite3.Connection):
    rows = con.execute(
        "SELECT id,source_path,source_type,title,text,embedding FROM chunk").fetchall()
    if not rows:
        return [], None
    mat = np.stack([np.frombuffer(r[5], dtype=np.float32) for r in rows])
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return rows, mat / norms


def cmd_search(args: argparse.Namespace) -> int:
    con = connect(Path(args.db).resolve())
    rows, mat = _load_matrix(con)
    if not rows:
        print("índice vazio — rode `index` primeiro", file=sys.stderr)
        return 1
    q = embed(args.query)
    q = q / (np.linalg.norm(q) or 1.0)
    sims = mat @ q
    top = np.argsort(-sims)[: args.k]
    print(f'busca: "{args.query}"   ({len(rows)} chunks no índice)\n')
    for rank, i in enumerate(top, 1):
        _id, src, stype, title, text, _ = rows[i]
        snippet = " ".join(text.split())[:240]
        head = f"#{rank}  score={sims[i]:.3f}  [{stype}]  {src}"
        print(head)
        if title:
            print(f"      title: {title}")
        print(f"      {snippet}\n")
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    db_path = Path(args.db).resolve()
    con = connect(db_path)
    total = con.execute("SELECT COUNT(*) FROM chunk").fetchone()[0]
    by_type = con.execute(
        "SELECT source_type, COUNT(*) FROM chunk GROUP BY source_type ORDER BY 2 DESC"
    ).fetchall()
    n_src = con.execute("SELECT COUNT(DISTINCT source_path) FROM chunk").fetchone()[0]
    size = db_path.stat().st_size if db_path.exists() else 0
    print(f"db:     {db_path}  ({size/1024:.0f} KB)")
    print(f"chunks: {total}   |   arquivos-fonte: {n_src}")
    for stype, n in by_type:
        print(f"  {stype:10s} {n}")
    return 0


def main(argv: list[str] | None = None) -> int:
    for _stream in (sys.stdout, sys.stderr):  # console Windows é cp1252; força UTF-8
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="RAG #2 — memória de projeto do arquiteto")
    ap.add_argument("--db", default=str(DEFAULT_DB), help="caminho do SQLite (default .ai_bridge/project_memory.db)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_idx = sub.add_parser("index", help="ingere o corpus (chunk + embed)")
    p_idx.add_argument("--corpus-root", default=str(REPO_ROOT),
                       help="raiz de onde LER os arquivos (default: raiz do repo)")
    p_idx.add_argument("--rebuild", action="store_true", help="dropa e reconstrói do zero")
    p_idx.set_defaults(func=cmd_index)

    p_search = sub.add_parser("search", help="busca semântica")
    p_search.add_argument("query")
    p_search.add_argument("--k", type=int, default=6)
    p_search.set_defaults(func=cmd_search)

    p_stats = sub.add_parser("stats", help="contagens do índice")
    p_stats.set_defaults(func=cmd_stats)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
