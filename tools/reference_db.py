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
    python tools/reference_db.py stats
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


def _ingest_token(con, p: Path) -> int:
    d = json.loads(p.read_text("utf-8"))
    _upsert(con, {
        "slug": p.stem, "kind": "token", "path": _rel(p), "room": d.get("room"),
        "intent": d.get("intent") or d.get("description") or p.stem,
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
    a = ap.parse_args(argv)

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
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
