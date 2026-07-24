"""reference_db.py — índice SQLite das referências do reference_lab (REFERENCE_DB_DESIGN.md).

Mata a "pasta solta": em vez de abrir 50 PNGs sem metadado, consulta uma tabela por tema/
sub-elemento e lê só o que importa. Fonte da verdade continua nos arquivos; o .db é índice
DERIVADO e reconstruível (`rebuild`). Idempotente por sha256 do arquivo.

Uso:
    python tools/reference_db.py init
    python tools/reference_db.py ingest            # cards/tokens/themes (M1) + kitchen_angles (M3)
    python tools/reference_db.py rebuild           # drop + init + ingest
    python tools/reference_db.py query --room kitchen --theme black_wood_gold [--kind render]
    python tools/reference_db.py query --sub-element hero_render --json
    python tools/reference_db.py retrieve --room kitchen --style black_wood_gold [--budget medio] [--json]
    python tools/reference_db.py stats

FP-035: retrieve(room, style, budget) devolve um DesignSpecBundle.v1 ranqueado
(tokens curados de references/tokens/ + sinal de curadoria/gates do índice),
degradando honesto pra confidence LOW quando o corpus julgado do FP-034 está
ausente. Ver schemas/design_spec_bundle.schema.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "artifacts/reference_lab"
DB_PATH = LAB / "reference.db"
ANGLES = ROOT / "artifacts/planta_74/furnished/kitchen_angles"
TOKENS_DIR = ROOT / "references/tokens"     # tokens builder-consumíveis curados (FP-035)
FELIPE_ANTI = ROOT / "references/felipe/anti_patterns"  # refs anti do Felipe (por bucket)

SCHEMA = """
CREATE TABLE IF NOT EXISTS reference (
    id              INTEGER PRIMARY KEY,
    slug            TEXT UNIQUE NOT NULL,
    kind            TEXT NOT NULL,
    path            TEXT NOT NULL,
    room            TEXT,
    theme           TEXT,
    style           TEXT,
    sub_element     TEXT,
    category        TEXT,
    intent          TEXT,
    source          TEXT,
    source_url      TEXT,
    sha256          TEXT,
    curation_status TEXT,
    gate_verdicts   TEXT,
    linked_skp      TEXT,
    sidecar         TEXT,
    notes           TEXT,
    created_at      TEXT
);
CREATE TABLE IF NOT EXISTS tag (id INTEGER PRIMARY KEY, name TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS reference_tag (
    reference_id INTEGER, tag_id INTEGER, PRIMARY KEY (reference_id, tag_id)
);
CREATE INDEX IF NOT EXISTS ix_ref_room  ON reference(room);
CREATE INDEX IF NOT EXISTS ix_ref_theme ON reference(theme);
CREATE INDEX IF NOT EXISTS ix_ref_kind  ON reference(kind);
"""

THEME_WORDS = {
    "black_wood_gold": "black_wood_gold", "blackgold": "black_wood_gold", "bwg": "black_wood_gold",
    "dark_walnut": "dark_walnut", "walnut": "dark_walnut", "nogueira": "dark_walnut",
    "hotel_boutique": "hotel_boutique", "boutique": "industrial_boutique",
    "industrial": "industrial_boutique", "nero": "black_wood_gold",
    "warm_compact": "warm_compact", "clara": "warm_compact", "fendi": "warm_compact",
    "moody": "black_wood_gold",
}
SUBELEM_WORDS = {
    "hero": "hero_render", "elevacao": "elevation", "elevation": "elevation",
    "dollhouse": "full_room", "plano": "plan", "matriz": "montage", "montagem": "montage",
    "ab_": "montage", "backsplash": "backsplash", "floor": "floor", "piso": "floor",
    "variante": "variant", "golden": "hero_render", "premium": "hero_render", "stress": "variant",
    "angle": "detail", "ang_": "detail", "3q": "hero_render", "materials": "montage",
}
# intermediários do V-Ray e auxiliares que NÃO são referência consultável
SKIP_SUFFIX = (".denoiser.png", ".effectsResult.png")


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _mtime_iso(p: Path) -> str:
    # determinístico (não usa clock atual) — idempotente
    import datetime
    return datetime.datetime.fromtimestamp(
        p.stat().st_mtime, datetime.timezone.utc).strftime("%Y-%m-%d")


def _rel(p: Path) -> str:
    try:
        return p.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return p.as_posix()


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA)
    con.commit()


def _infer_from_name(name: str) -> tuple[str | None, str | None]:
    low = name.lower()
    theme = next((v for k, v in THEME_WORDS.items() if k in low), None)
    sub = next((v for k, v in SUBELEM_WORDS.items() if k in low), None)
    return theme, sub


def _upsert(con, row: dict, tags: list[str] | None = None) -> None:
    cols = ("slug", "kind", "path", "room", "theme", "style", "sub_element", "category",
            "intent", "source", "source_url", "sha256", "curation_status", "gate_verdicts",
            "linked_skp", "sidecar", "notes", "created_at")

    def _coerce(v):  # SQLite não aceita dict/list — serializa
        return json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v
    vals = [_coerce(row.get(c)) for c in cols]
    placeholders = ",".join("?" * len(cols))
    updates = ",".join(f"{c}=excluded.{c}" for c in cols if c != "slug")
    con.execute(
        f"INSERT INTO reference ({','.join(cols)}) VALUES ({placeholders}) "
        f"ON CONFLICT(slug) DO UPDATE SET {updates}", vals)
    ref_id = con.execute("SELECT id FROM reference WHERE slug=?", (row["slug"],)).fetchone()["id"]
    for t in tags or []:
        t = str(t).strip().lower()
        if not t:
            continue
        con.execute("INSERT OR IGNORE INTO tag(name) VALUES (?)", (t,))
        tag_id = con.execute("SELECT id FROM tag WHERE name=?", (t,)).fetchone()["id"]
        con.execute("INSERT OR IGNORE INTO reference_tag(reference_id, tag_id) VALUES (?,?)",
                    (ref_id, tag_id))


def _ingest_card(con, p: Path) -> int:
    d = json.loads(p.read_text("utf-8"))
    applies = d.get("applies_to") or []
    tokens = d.get("implementation_tokens") or {}
    _upsert(con, {
        "slug": d.get("card_id") or p.stem, "kind": "card", "path": _rel(p),
        "room": applies[0] if applies else None, "theme": None,
        "sub_element": None, "category": d.get("category"),
        "intent": (d.get("problem", "") + " -> " + d.get("design_move", "")).strip(" ->"),
        "source": "felipe_curated", "sha256": _sha(p),
        "curation_status": "approved", "sidecar": _rel(p), "created_at": _mtime_iso(p),
    }, tags=(tokens.get("parts") or []) + ([tokens.get("system")] if tokens.get("system") else []))
    return 1


def _ingest_theme(con, p: Path) -> int:
    d = json.loads(p.read_text("utf-8"))
    name = d.get("theme") or d.get("name") or p.stem
    theme, _ = _infer_from_name(name + " " + p.stem)
    gates = d.get("gates") or d.get("gate_verdicts")
    _upsert(con, {
        "slug": p.stem, "kind": "theme_preset", "path": _rel(p),
        "room": "kitchen", "theme": theme or p.stem.lower(),
        "intent": d.get("description") or d.get("intent") or name,
        "source": "preset", "sha256": _sha(p),
        "curation_status": d.get("status") or "approved",
        "gate_verdicts": json.dumps(gates, ensure_ascii=False) if gates else None,
        "created_at": _mtime_iso(p),
    })
    return 1


def _ingest_token(con, p: Path, default_room: str | None = None) -> int:
    d = json.loads(p.read_text("utf-8"))
    _upsert(con, {
        "slug": p.stem, "kind": "token", "path": _rel(p),
        "room": d.get("room") or default_room,
        "intent": d.get("intent") or d.get("rule") or d.get("title")
        or d.get("description") or p.stem,
        "category": d.get("category"), "source": "token", "sha256": _sha(p),
        "curation_status": "approved", "created_at": _mtime_iso(p),
    })
    return 1


def _ingest_render(con, p: Path) -> int:
    theme, sub = _infer_from_name(p.name)
    status = "golden" if ("hero" in p.name.lower() and "final" in p.name.lower()) else "candidate"
    _upsert(con, {
        "slug": p.stem, "kind": "render", "path": _rel(p), "room": "kitchen",
        "theme": theme, "sub_element": sub or "render", "source": "generated_vray",
        "sha256": _sha(p), "curation_status": status, "created_at": _mtime_iso(p),
    })
    return 1


def ingest(con: sqlite3.Connection) -> dict:
    counts = {"card": 0, "theme_preset": 0, "token": 0, "render": 0}
    for p in sorted(LAB.glob("**/cards/*.json")):
        counts["card"] += _ingest_card(con, p)
    for p in sorted(LAB.glob("**/THEME*.json")) + sorted(LAB.glob("themes/*.json")):
        counts["theme_preset"] += _ingest_theme(con, p)
    for p in sorted(LAB.glob("**/tokens/*.json")):
        counts["token"] += _ingest_token(con, p)
    if TOKENS_DIR.is_dir():  # FP-035: tokens builder-consumíveis curados (cozinha)
        for p in sorted(TOKENS_DIR.glob("*.json")):
            counts["token"] += _ingest_token(con, p, default_room="kitchen")
    if ANGLES.is_dir():  # M3: mata a pasta solta
        for p in sorted(ANGLES.glob("*.png")):
            if p.name.endswith(SKIP_SUFFIX):
                continue
            counts["render"] += _ingest_render(con, p)
    con.commit()
    return counts


def query(con, *, room=None, theme=None, kind=None, sub_element=None, tag=None,
          curation=None, gate_pass=None) -> list[sqlite3.Row]:
    sql = "SELECT DISTINCT r.* FROM reference r"
    where, params = [], []
    if tag:
        sql += (" JOIN reference_tag rt ON rt.reference_id=r.id"
                " JOIN tag t ON t.id=rt.tag_id")
        where.append("t.name=?")
        params.append(tag.lower())
    for col, val in (("room", room), ("theme", theme), ("kind", kind),
                     ("sub_element", sub_element), ("curation_status", curation)):
        if val:
            where.append(f"r.{col}=?")
            params.append(val)
    if gate_pass:
        where.append("r.gate_verdicts LIKE ?")
        params.append(f'%"{gate_pass}"%PASS%')
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY r.kind, r.slug"
    return con.execute(sql, params).fetchall()


# ---------------------------------------------------------------------------
# FP-035 — retrieve(): room/style/budget -> DesignSpecBundle.v1 (faceted+ranked).
#
# LÊ o disco (references/tokens/*.json) + o índice SQLite (cards/theme_presets/
# judged_variants) e devolve um bundle RANQUEADO. Colapsa sinônimos via
# reference_grammar (não duplica vocabulário). DEGRADA HONESTO: sem corpus julgado
# do FP-034 -> confidence LOW baseado só em facets+gates, nunca ranking fabricado.
# Determinístico (sem clock/random; ordena por chave estável). query() fica intacta.
# ---------------------------------------------------------------------------

BUNDLE_SCHEMA_VERSION = "design_spec_bundle.v1"

# palavra de custo (1ª token do cost_relative em prosa) -> nível ordinal.
_COST_LEVEL = {"baixo": 1, "baixo-médio": 2, "médio": 3, "médio-alto": 4, "alto": 5}
# alvo de budget (arg) -> nível ordinal (aceita pt e en).
_BUDGET_LEVEL = {
    "baixo": 1, "low": 1, "econ": 1, "economico": 1,
    "medio": 3, "médio": 3, "mid": 3, "medium": 3,
    "alto": 5, "high": 5, "premium": 5,
}
# papéis de paleta reconhecidos nos params dos tokens (chave *_rgb -> papel).
_PALETTE_RGB_SUFFIX = "_rgb"


def _cost_level(cost_relative: str | None) -> int | None:
    """Nível ordinal do custo a partir da 1ª palavra da prosa cost_relative."""
    if not cost_relative:
        return None
    head = str(cost_relative).strip().lower().split()[0].strip(",.;:()")
    return _COST_LEVEL.get(head)


def _budget_fit(cost_level: int | None, budget: str | None) -> int:
    """+1 se o custo do token cabe no budget alvo; -1 se estoura; 0 sem info."""
    if budget is None or cost_level is None:
        return 0
    target = _BUDGET_LEVEL.get(str(budget).strip().lower())
    if target is None:
        return 0
    return 1 if cost_level <= target else -1


def _canon_token_name(name: str):
    """Colapsa sinônimo -> nome canônico via reference_grammar (reuso, sem duplicar)."""
    try:
        from tools import reference_grammar as rg
        return rg._canon(name)
    except Exception:  # noqa: BLE001 — grammar ausente não deve derrubar retrieve
        return name


def _load_disk_tokens(room: str) -> list[dict]:
    """Lê references/tokens/*.json (builder-consumíveis). Room é implícito
    (cozinha) — estes tokens não têm campo 'room'. Filtra por room quando o
    token declara um; senão trata como do cômodo-alvo (kitchen)."""
    out: list[dict] = []
    if not TOKENS_DIR.is_dir():
        return out
    for p in sorted(TOKENS_DIR.glob("*.json")):
        try:
            d = json.loads(p.read_text("utf-8"))
        except Exception:  # noqa: BLE001
            continue
        tok_room = (d.get("room") or "kitchen").strip().lower()
        if room and tok_room != room:
            continue
        out.append({
            "raw_name": d.get("name") or p.stem,
            "params": d.get("params") or {},
            "applies_to_kinds": d.get("applies_to_kinds") or [],
            "anti_pattern": d.get("anti_pattern"),
            "cost_relative": d.get("cost_relative"),
            "gate_refs": d.get("gate_refs") or [],
            "source_path": _rel(p),
            "curation_status": "approved",   # curado pelo Felipe (references/tokens)
            "gate_verdicts": None,
            "kind": "token",
        })
    return out


def _load_db_signal(con, room: str, theme: str | None) -> list[dict]:
    """Sinal de curadoria/gates do índice (cards/theme_presets/judged_variants).
    Só pra RANKING — NÃO vira token do bundle. Ausência = degradação honesta."""
    if con is None:
        return []
    out: list[dict] = []
    try:
        rows = query(con, room=room) if room else con.execute(
            "SELECT * FROM reference").fetchall()
    except sqlite3.Error:
        return []
    for r in rows:
        if r["kind"] == "token":
            continue  # tokens vêm do disco (fonte curada), não do índice
        gv = None
        if r["gate_verdicts"]:
            try:
                gv = json.loads(r["gate_verdicts"])
            except Exception:  # noqa: BLE001
                gv = None
        out.append({
            "slug": r["slug"], "kind": r["kind"],
            "theme": r["theme"], "curation_status": r["curation_status"],
            "gate_verdicts": gv, "source_path": r["path"],
        })
    return out


def _curation_weight(status: str | None) -> int:
    return {"main": 3, "golden": 3, "approved": 2, "candidate": 1, "anti": -5}.get(
        (status or "").strip().lower(), 0)


def _gate_pass_count(gv: dict | None) -> int:
    if not isinstance(gv, dict):
        return 0
    return sum(1 for v in gv.values() if str(v).upper() == "PASS")


def _load_felipe_anti(room: str, style: str | None) -> list[str]:
    """Refs anti do Felipe (references/felipe/anti_patterns/*.json). Bucket é por
    cômodo hoje só p/ sofá (sala); cozinha degrada honesto (lista vazia)."""
    out: list[str] = []
    if not FELIPE_ANTI.is_dir():
        return out
    for p in sorted(FELIPE_ANTI.glob("*.json")):
        try:
            d = json.loads(p.read_text("utf-8"))
        except Exception:  # noqa: BLE001
            continue
        avoid = d.get("avoid") or d.get("comment")
        if avoid:
            out.append(str(avoid).strip())
    return out


# style -> termos semânticos curados p/ a query de recall (determinístico, sem LLM).
# Chaveado pelo tema canônico (normalize_theme) p/ casar sinônimos de estilo.
_STYLE_QUERY_TERMS = {
    "black_wood_gold": "preto fosco madeira escura bronze champagne metal escuro",
    "dark_walnut": "nogueira madeira escura quente preto fosco inox grafite",
    "warm_compact": "off-white quente fendi carvalho claro compacto aconchegante led 2700k",
    "industrial_boutique": "concreto metal preto cru industrial madeira",
    "hotel_boutique": "luxo hoteleiro pedra madeira iluminação âmbar",
}


def build_retrieval_query(room: str, style: str | None, budget: str | None = None) -> str:
    """room/style -> texto de query semântica curado e DETERMINÍSTICO (sem LLM).
    Substitui o f-string fixo antigo; injeta a LINGUAGEM do estilo p/ o recall
    discriminar (o facet não carrega tema). budget NÃO entra (é sinal de ranking,
    não de semântica)."""
    room = (room or "").strip().lower()
    style_norm = normalize_theme(style)
    parts = [room, "marcenaria planejada"]
    terms = _STYLE_QUERY_TERMS.get(style_norm or "")
    if terms:
        parts.append(terms)
    elif style_norm:
        parts.append(str(style_norm).replace("_", " "))
    return " ".join(p for p in parts if p).strip()


def _rrf_fuse(faceted_ranked: list[dict], semantic_sources: list[str],
              k: int = 60) -> list[dict]:
    """Reciprocal Rank Fusion DETERMINÍSTICA de duas rank-lists. faceted_ranked =
    tokens na ordem faceted (posição = rank); semantic_sources = source_paths na
    ordem de cosine desc. Junta por source_path; termo ausente não contribui.
    Desempate estável por nome. semantic vazio -> ordem faceted preservada."""
    sem_rank = {src: i for i, src in enumerate(semantic_sources)}

    def _rrf(i: int, tok: dict) -> float:
        s = 1.0 / (k + i + 1)                       # rank faceted (1-indexed)
        sp = tok.get("source_path")
        if sp in sem_rank:
            s += 1.0 / (k + sem_rank[sp] + 1)       # rank semântico (1-indexed)
        return s

    return [tok for _, tok in sorted(
        enumerate(faceted_ranked),
        key=lambda it: (-_rrf(it[0], it[1]), it[1]["name"]))]


def _embed_recall_chunks(room: str, style_norm: str | None) -> tuple[list[dict], str | None, list[str]]:
    """FP-037 Camada 2 — recall semântico OPCIONAL via Qdrant+Ollama.

    Devolve (retrieved_chunks, corpus_version, notes). retrieved_chunks =
    [{source, chunk_id, confidence}] pros consumidores auditarem. DEGRADA HONESTO:
    Qdrant/Ollama off -> ([], corpus_version_ou_None, [nota_de_degradação]). NUNCA
    infla confidence; o vetor só melhora RECALL, os facets decidem o resto.

    Import LAZY do adapter (urllib puro) — o CI que só tem [dev] não toca infra.
    """
    notes: list[str] = []
    try:
        from tools import rag_embed_backend as reb
        from tools import rag_freshness as rf
    except Exception as e:  # noqa: BLE001 — módulo ausente não derruba retrieve
        notes.append(f"backend=embed indisponível (import): {e!r} -> faceted.")
        return [], None, notes

    con_fresh = None
    try:
        con_fresh = rf.connect()
        corpus_version = rf.current_corpus_version(con_fresh)
        if corpus_version is None:
            notes.append("backend=embed: índice de freshness vazio "
                         "(rode `reference_db reindex`) -> faceted.")
            return [], None, notes
        query_text = build_retrieval_query(room, style_norm)
        # source_type='token' -> recall token-scoped (senão os chunks-de-token
        # ficam esparsos no top_k do corpus inteiro e a fusão RRF colapsa).
        hits = reb.semantic_recall(query_text, corpus_version=corpus_version,
                                   top_k=12, source_type="token")
        retrieved = [{
            "source": h["payload"].get("source_path"),
            "chunk_id": h["chunk_id"],
            "confidence": round(h["score"], 4),
        } for h in hits]
        if not retrieved:
            notes.append("backend=embed: Qdrant vazio p/ o corpus atual "
                         "(reindex do Qdrant pendente) -> faceted mantém a decisão.")
        return retrieved, corpus_version, notes
    except reb.InfraUnavailable as e:  # Qdrant/Ollama off
        notes.append(f"backend=embed degradou p/ faceted: infra off ({e}). "
                     "confidence NÃO inflada.")
        cv = None
        if con_fresh is not None:
            try:
                cv = rf.current_corpus_version(con_fresh)
            except Exception:  # noqa: BLE001
                cv = None
        return [], cv, notes
    except Exception as e:  # noqa: BLE001 — qualquer erro -> faceted, honesto
        notes.append(f"backend=embed erro inesperado -> faceted: {e!r}")
        return [], None, notes
    finally:
        if con_fresh is not None:
            con_fresh.close()


def retrieve(room, style=None, budget=None, *, con=None, top_n=6,
             backend="faceted") -> dict:
    """room/style/budget -> DesignSpecBundle.v1 (faceted+ranked).

    Lê os tokens curados de references/tokens/ (fonte builder-consumível) e usa o
    índice SQLite (se existir) só como SINAL de curadoria/gates pro ranking.
    Colapsa sinônimos via reference_grammar. Ranking determinístico por
    (facet_match, curation_status, gate_pass, budget_fit) — desempate estável
    por nome. DEGRADA HONESTO: sem corpus julgado do FP-034 -> confidence LOW.

    NÃO fabrica ranking sem dado; o bundle é PROPOSTA (Felipe aprova); nunca
    emite veredito visual.

    FP-037: backend='embed' liga o recall semântico REAL (Qdrant+Ollama) por cima
    do faceted — o vetor melhora RECALL (retrieved_chunks auditáveis), os
    facets/gates continuam decidindo confidence. Infra off -> degrada pro faceted,
    loga, e a confidence NÃO infla. backend='faceted' (default) NUNCA toca infra.
    O bundle carrega SEMPRE rag_corpus_version + retrieved_chunks (aditivo/retrocompat).
    """
    room = (room or "").strip().lower()
    style_norm = normalize_theme(style)
    notes: list[str] = []
    rag_corpus_version: str | None = None
    retrieved_chunks: list[dict] = []
    if backend == "embed":
        retrieved_chunks, rag_corpus_version, embed_notes = _embed_recall_chunks(
            room, style_norm)
        notes.extend(embed_notes)
        backend = "embed"  # registra a INTENÇÃO; o ranking segue faceted (honesto)

    disk_tokens = _load_disk_tokens(room)
    db_signal = _load_db_signal(con, room, style_norm)

    # corpus julgado do FP-034 presente? (kind=judged_variant no índice)
    fp034_present = any(s["kind"] == "judged_variant" for s in db_signal)

    # ranking dos tokens (determinístico). facet_match: room casou (disk tokens já
    # filtrados por room) => 1; style casa se algum params/nome bate o tema — mas
    # os tokens curados não carregam theme, então facet de style não penaliza.
    def _score(tok: dict) -> tuple:
        cost_lvl = _cost_level(tok.get("cost_relative"))
        s = 3 * 1                                   # facet room match (já filtrado)
        s += 2 * _curation_weight(tok["curation_status"])
        s += 1 * 0                                  # tokens de disco não têm gate_verdicts
        s += _budget_fit(cost_lvl, budget)
        # desempate estável e determinístico: score desc, depois nome canônico asc
        return (s, )

    # colapsa sinônimo -> canônico e dedup por nome canônico (last-wins irrelevante:
    # tokens de disco têm nomes distintos; sinônimo só colapsa duplicata real).
    by_canon: dict[str, dict] = {}
    for tok in disk_tokens:
        canon = _canon_token_name(tok["raw_name"])
        tok = {**tok, "name": canon}
        if canon not in by_canon:
            by_canon[canon] = tok
    collapsed = list(by_canon.values())

    ranked = sorted(collapsed, key=lambda t: (-_score(t)[0], t["name"]))

    # FP-035 epic "ligar o embed": funde o recall semântico (antes DESCARTADO em
    # :467) no ranking via RRF. SÓ no caminho embed COM chunks reais -> o caminho
    # faceted / infra-off fica byte-idêntico (a fusão nem roda). Confidence segue
    # decidida por facets/gates — o cosine nunca a infla.
    if backend == "embed" and retrieved_chunks:
        sem_sources = [c["source"] for c in retrieved_chunks if c.get("source")]
        ranked = _rrf_fuse(ranked, sem_sources)

    tokens_out: list[dict] = []
    anti: list[str] = []
    hints: list[str] = []
    gate_refs: list[str] = []
    palette: dict = {}
    provenance: list[dict] = []
    seen_anti: set[str] = set()
    seen_gate: set[str] = set()

    for tok in ranked[:top_n]:
        tokens_out.append({
            "name": tok["name"],
            "builder_kinds": list(tok["applies_to_kinds"]),
            "params": tok["params"],
            "source_path": tok["source_path"],
            "cost_relative": tok.get("cost_relative"),
        })
        # anti-patterns (union, dedup, ordem de ranking preservada)
        ap = tok.get("anti_pattern")
        if ap and ap not in seen_anti:
            seen_anti.add(ap)
            anti.append(str(ap))
        # gate_refs (union dedup)
        for g in tok.get("gate_refs") or []:
            if g not in seen_gate:
                seen_gate.add(g)
                gate_refs.append(g)
        # layout_hints: campo 'position' dos params (LINGUAGEM, não coordenada)
        pos = tok["params"].get("position") if isinstance(tok["params"], dict) else None
        if pos:
            hints.append(f'{tok["name"]}: {pos}')
        # palette: chaves *_rgb dos params (papel = chave sem sufixo _rgb)
        if isinstance(tok["params"], dict):
            for k, v in tok["params"].items():
                if k.endswith(_PALETTE_RGB_SUFFIX):
                    palette.setdefault(k[: -len(_PALETTE_RGB_SUFFIX)], v)
        provenance.append({
            "source_path": tok["source_path"], "kind": "token",
            "curation_status": tok["curation_status"],
            "gate_verdicts": tok.get("gate_verdicts"),
        })

    # refs anti do Felipe (bucket por cômodo; cozinha degrada honesto)
    for a in _load_felipe_anti(room, style_norm):
        if a not in seen_anti:
            seen_anti.add(a)
            anti.append(a)

    # provenance dos sinais de DB considerados (honestidade de origem do ranking)
    for s in db_signal:
        provenance.append({
            "source_path": s["source_path"], "kind": s["kind"],
            "curation_status": s["curation_status"] or "candidate",
            "gate_verdicts": s["gate_verdicts"],
        })

    # confidence — honesto: sem corpus julgado FP-034 -> LOW (só facets+gates).
    if not tokens_out:
        confidence = "LOW"
        notes.append("nenhum token recuperado para o cômodo/estilo -> confidence LOW.")
    elif not fp034_present:
        confidence = "LOW"
        notes.append("corpus julgado FP-034 ausente -> ranking sem sinal de "
                     "curadoria julgada; confidence LOW (degradação honesta).")
    else:
        # FP-034 presente: HIGH se há gate PASS no sinal, senão MEDIUM.
        any_pass = any(_gate_pass_count(s["gate_verdicts"]) for s in db_signal)
        confidence = "HIGH" if any_pass else "MEDIUM"

    return {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "query": {"room": room, "style": style_norm, "budget": budget},
        "tokens": tokens_out,
        "palette": palette,
        "anti_patterns": anti,
        "layout_hints": hints,
        "gate_refs": gate_refs,
        "provenance": provenance,
        "confidence": confidence,
        "backend": backend,
        "notes": notes,
        # FP-037 (aditivo/retrocompat): resposta auditável — de qual geração do
        # corpus veio, e quais chunks o recall semântico trouxe (vazio no faceted
        # puro ou quando a infra está off; nunca infla confidence).
        "rag_corpus_version": rag_corpus_version,
        "retrieved_chunks": retrieved_chunks,
    }


def normalize_theme(style: str | None) -> str | None:
    """Colapsa um 'style' solto pro tema canônico do índice (THEME_WORDS)."""
    if not style:
        return None
    low = str(style).strip().lower()
    return THEME_WORDS.get(low) or next(
        (v for k, v in THEME_WORDS.items() if k in low), low)


def _print_rows(rows, as_json=False, paths_only=False) -> None:
    if paths_only:
        for r in rows:
            print(r["path"])
        return
    if as_json:
        print(json.dumps([dict(r) for r in rows], ensure_ascii=False, indent=2))
        return
    if not rows:
        print("(0 referências)")
        return
    print(f"{'slug':<38} {'kind':<14} {'theme':<18} {'sub_element':<13} intent")
    print("-" * 110)
    for r in rows:
        intent = (r["intent"] or "")[:46]
        print(f"{(r['slug'] or '')[:37]:<38} {(r['kind'] or ''):<14} "
              f"{(r['theme'] or '-'):<18} {(r['sub_element'] or '-'):<13} {intent}")
    print(f"\n{len(rows)} referência(s).")


def _cmd_reindex(a) -> int:
    """FP-037 `reindex`: source registry -> chunks (camada pura, sempre) e depois,
    se a infra estiver up e --no-embed não for passado, popula o Qdrant incremental.
    O clock real entra SÓ aqui (borda CLI) via now_iso; a lógica de biblioteca é
    determinística (recebe now_iso injetado)."""
    import datetime as _dt

    from tools import rag_freshness as rf

    now_iso = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    con = rf.connect()
    report = rf.reindex(con, now_iso=now_iso, rebuild=a.rebuild)

    qdrant_report = None
    if not a.no_embed:
        try:
            from tools import rag_embed_backend as reb
            if reb.infra_up():
                qdrant_report = reb.reindex_qdrant(
                    con, corpus_version=report["corpus_version"], now_iso=now_iso)
            else:
                report["note"] = ("Qdrant/Ollama off -> só a camada pura de "
                                  "freshness foi reindexada (embed pulado, honesto).")
        except reb.InfraUnavailable as e:  # noqa: F821 — reb pode não ter importado
            report["note"] = f"embed pulado (infra off): {e}"
        except Exception as e:  # noqa: BLE001
            report["note"] = f"embed pulado (erro): {e!r}"
    con.close()

    out = {"freshness": report, "qdrant": qdrant_report}
    if getattr(a, "json", False):
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(f"reindex freshness: corpus_version={report['corpus_version'][:12]} "
              f"docs={report['docs_active']} reused={report['chunks_reused']} "
              f"reindexed={report['chunks_reindexed']} "
              f"deactivated={report['chunks_deactivated']}")
        if qdrant_report:
            print(f"reindex qdrant: embedded={qdrant_report['embedded']} "
                  f"deleted={qdrant_report['deleted']}")
        if report.get("note"):
            print(f"  note: {report['note']}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Índice SQLite das referências (reference_lab).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    sub.add_parser("ingest")
    sub.add_parser("rebuild")
    sub.add_parser("stats")
    q = sub.add_parser("query")
    for opt in ("room", "theme", "kind", "sub-element", "tag", "curation", "gate-pass"):
        q.add_argument(f"--{opt}")
    q.add_argument("--json", action="store_true")
    q.add_argument("--paths", action="store_true")
    rt = sub.add_parser("retrieve", help="room/style/budget -> DesignSpecBundle.v1 (FP-035)")
    rt.add_argument("--room", required=True)
    rt.add_argument("--style")
    rt.add_argument("--budget")
    rt.add_argument("--top-n", type=int, default=6)
    rt.add_argument("--backend", default="faceted", choices=("faceted", "embed"))
    rt.add_argument("--json", action="store_true")
    rx = sub.add_parser("reindex", help="FP-037: source registry -> chunks + (opcional) Qdrant")
    rx.add_argument("--rebuild", action="store_true", help="dropa e reconstrói o índice de freshness")
    rx.add_argument("--no-embed", action="store_true",
                    help="só a camada pura (freshness); pula o embed no Qdrant")
    rx.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    if a.cmd == "reindex":
        return _cmd_reindex(a)

    LAB.mkdir(parents=True, exist_ok=True)
    if a.cmd == "rebuild" and DB_PATH.exists():
        DB_PATH.unlink()
    con = connect()
    init(con)
    if a.cmd in ("ingest", "rebuild"):
        counts = ingest(con)
        print("ingest:", ", ".join(f"{k}={v}" for k, v in counts.items()),
              f"| total={sum(counts.values())} -> {_rel(DB_PATH)}")
    elif a.cmd == "init":
        print(f"init -> {_rel(DB_PATH)}")
    elif a.cmd == "stats":
        for r in con.execute("SELECT kind, COUNT(*) n FROM reference GROUP BY kind ORDER BY n DESC"):
            print(f"  {r['kind']:<16} {r['n']}")
        total = con.execute("SELECT COUNT(*) n FROM reference").fetchone()["n"]
        print(f"  {'TOTAL':<16} {total}")
    elif a.cmd == "query":
        rows = query(con, room=a.room, theme=a.theme, kind=a.kind, sub_element=getattr(a, "sub_element"),
                     tag=a.tag, curation=a.curation, gate_pass=getattr(a, "gate_pass"))
        _print_rows(rows, as_json=a.json, paths_only=a.paths)
    elif a.cmd == "retrieve":
        bundle = retrieve(a.room, a.style, a.budget, con=con,
                          top_n=a.top_n, backend=a.backend)
        if a.json:
            print(json.dumps(bundle, ensure_ascii=False, indent=2))
        else:
            print(f"room={bundle['query']['room']} style={bundle['query']['style']} "
                  f"budget={bundle['query']['budget']} confidence={bundle['confidence']}")
            print(f"  tokens ({len(bundle['tokens'])}): "
                  + ", ".join(t["name"] for t in bundle["tokens"]))
            print(f"  anti_patterns: {len(bundle['anti_patterns'])} | "
                  f"layout_hints: {len(bundle['layout_hints'])} | "
                  f"gate_refs: {len(bundle['gate_refs'])}")
            for n in bundle["notes"]:
                print(f"  note: {n}")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
