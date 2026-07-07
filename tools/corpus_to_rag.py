"""corpus_to_rag.py — FP-034 -> FP-035: exporta o corpus.jsonl de variantes
julgadas num shape INGERIVEL pelos dois RAGs existentes.

- RAG #1 (reference_db): 1 linha `kind=judged_variant` por variante via
  `_upsert` (idempotente por slug=variant/<id>; gate_verdicts em JSON-texto
  {"gate": "PASS"} consultavel pelo LIKE do `query(gate_pass=...)`).
  curation_status='candidate' SEMPRE — candidato != canonico, promocao a golden
  e' decisao humana fora daqui.
- RAG #2 (project_memory_db): materializa uma LISTA json (estrategia 'json' do
  indexador: 1 chunk por item, titulo do id) que o CHAMADOR grava num
  corpus-root SCRATCH em `.ai_bridge/research/judged_variants.json` (glob ja
  existente em SOURCES) e indexa com `cmd_index --corpus-root <scratch>` —
  NUNCA no .ai_bridge real.

Leitura last-wins por variant_id (o corpus e' append-only; um upgrade de visao
appenda um registro superseding). Sem clock: created_at vem do registro
(mtime-derivado no sweep). FP-034 PRODUZ; FP-035 INDEXA/CONSULTA.

Uso:
    python -m tools.corpus_to_rag --corpus runs/variant_sweep/run1/corpus.jsonl \\
        [--reference-db <db>] [--memory-out <scratch>/.ai_bridge/research/judged_variants.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tools.jsonl_io import read_jsonl


def _last_wins(corpus_path: Path) -> list[dict]:
    by_id: dict = {}
    for rec in read_jsonl(Path(corpus_path)):
        vid = rec.get("variant_id")
        if vid:
            by_id[vid] = rec
    return list(by_id.values())


def export_reference_rows(corpus_path: Path) -> list[tuple[dict, list[str]]]:
    """corpus.jsonl -> [(row 18-colunas do reference_db._upsert, tags)]."""
    rows: list[tuple[dict, list[str]]] = []
    for rec in _last_wins(corpus_path):
        vid = rec["variant_id"]
        params = rec.get("params") or {}
        gates = (rec.get("geometry") or {}).get("deterministic_gates") or {}
        render = rec.get("render_refs") or {}
        row = {
            "slug": f"variant/{vid}",
            "kind": "judged_variant",
            "path": render.get("iso") or "",
            "room": None,
            "theme": params.get("theme") or "warm_compact",
            "style": params.get("style") or "baseline",
            "sub_element": "variant",
            "category": None,
            "intent": (f"variante julgada {vid} "
                       f"(layout_seed={params.get('layout_seed')}, "
                       f"layout_source={params.get('layout_source')})"),
            "source": "variant_sweep",
            "source_url": None,
            "sha256": render.get("sha256"),
            "curation_status": "candidate",  # NUNCA golden: candidato != canonico
            "gate_verdicts": json.dumps(gates, ensure_ascii=False) if gates else None,
            "linked_skp": None,
            "sidecar": Path(corpus_path).as_posix(),
            "notes": rec.get("verdict"),
            "created_at": rec.get("created_at"),
        }
        tags = [t for t in (rec.get("plant"),
                            (rec.get("verdict") or "").lower(),
                            f"seed{params.get('layout_seed')}") if t]
        rows.append((row, tags))
    return rows


def ingest_reference(corpus_path: Path, db_path: Path | None = None) -> int:
    """Upsert das linhas exportadas no reference_db (RAG #1). Idempotente por
    slug (ON CONFLICT UPDATE); _upsert nao comita -> commit explicito aqui."""
    from tools import reference_db as rdb
    if db_path is not None:
        rdb.DB_PATH = Path(db_path)
        rdb.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = rdb.connect()
    rdb.init(con)
    rows = export_reference_rows(corpus_path)
    for row, tags in rows:
        rdb._upsert(con, row, tags)
    con.commit()
    con.close()
    return len(rows)


def export_memory_json(corpus_path: Path, out_json: Path) -> int:
    """Materializa a lista ingerivel pelo project_memory_db (RAG #2, estrategia
    'json': lista -> 1 chunk/item, titulo de 'id'). O chamador aponta o
    cmd_index pro corpus-root SCRATCH que contem este arquivo."""
    items = []
    for rec in _last_wins(corpus_path):
        params = rec.get("params") or {}
        items.append({
            "id": rec["variant_id"],
            "title": rec["variant_id"],
            "verdict": rec.get("verdict"),
            "params": params,
            "gates": (rec.get("geometry") or {}).get("deterministic_gates") or {},
            "render": (rec.get("render_refs") or {}).get("iso"),
            # objeto {value,label} INTEIRO: o rotulo machine_provisional e' o
            # marcador de honestidade e viaja junto com a nota (spec FP-034)
            "machine_score": rec.get("machine_score"),
            "created_at": rec.get("created_at"),
        })
    out_json = Path(out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(items, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    return len(items)


def main(argv=None) -> int:
    for _stream in (sys.stdout, sys.stderr):  # console Windows cp1252 -> UTF-8
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="FP-034 -> FP-035: corpus julgado -> RAGs")
    ap.add_argument("--corpus", type=Path, required=True)
    ap.add_argument("--reference-db", type=Path, default=None,
                    help="SQLite do reference_db (default: o DB_PATH do modulo)")
    ap.add_argument("--memory-out", type=Path, default=None,
                    help="json de saida p/ o corpus-root SCRATCH do project_memory_db")
    a = ap.parse_args(argv)
    if not Path(a.corpus).is_file():
        print(f"corpus inexistente: {a.corpus}", file=sys.stderr)
        return 1
    done = {}
    if a.reference_db is not None or a.memory_out is None:
        done["reference_db"] = ingest_reference(a.corpus, a.reference_db)
    if a.memory_out is not None:
        done["memory_json"] = export_memory_json(a.corpus, a.memory_out)
    print(json.dumps({"corpus": str(a.corpus), **done}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
