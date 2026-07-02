"""FP-034 -> FP-035 — ponte RAG: o corpus julgado vira linhas ingeriveis pelo
reference_db (upsert idempotente por slug, gate_verdicts consultavel) e pelo
project_memory_db (corpus-root SCRATCH; embed MOCKADO — Ollama off e' aceite
explicito). Hermetico: DBs em tmp_path, zero rede, zero clock."""
from __future__ import annotations

import inspect
import json
import sqlite3
from pathlib import Path

import numpy as np
import pytest

from tools import corpus_to_rag as ctr
from tools import project_memory_db as pmd
from tools import reference_db as rdb


def _record(vid: str, verdict: str, gates: dict) -> dict:
    return {
        "schema": "judged_variant/1.0.0", "run_id": "run1", "variant_id": vid,
        "created_at": "2026-07-01T12:00:00Z", "plant": "planta_74",
        "params": {"style": "industrial", "theme": "dark_walnut",
                   "layout_seed": 1, "layout_source": "template:estar_ancorado",
                   "pt_to_m": "0.0259"},
        "geometry": {"n_boxes": 10, "rooms": [], "deterministic_gates": gates},
        "render_refs": {"iso": f"{vid}/iso.png", "sha256": "ab" * 32,
                        "renderer": "su-free"},
        "visual_findings": None,
        "machine_score": {"value": None, "label": "machine_provisional"},
        "verdict": verdict, "human_verdict": None,
    }


@pytest.fixture
def corpus(tmp_path) -> Path:
    p = tmp_path / "corpus.jsonl"
    rows = [
        _record("planta_74__industrial__dark_walnut__L1", "CANDIDATE",
                {"geometry_sanity": "PASS", "furniture_overlap": "PASS"}),
        _record("planta_74__baseline__warm_compact__L0", "FAIL",
                {"geometry_sanity": "FAIL", "furniture_overlap": "FAIL"}),
    ]
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return p


def test_corpus_to_rag_output_is_ingestible_reference_db(monkeypatch, tmp_path,
                                                         corpus):
    monkeypatch.setattr(rdb, "DB_PATH", tmp_path / "reference.db")
    n = ctr.ingest_reference(corpus)
    assert n == 2
    con = rdb.connect()
    rows = rdb.query(con, kind="judged_variant")
    assert {r["slug"] for r in rows} == {
        "variant/planta_74__industrial__dark_walnut__L1",
        "variant/planta_74__baseline__warm_compact__L0"}
    by_slug = {r["slug"]: r for r in rows}
    cand = by_slug["variant/planta_74__industrial__dark_walnut__L1"]
    assert cand["curation_status"] == "candidate"   # NUNCA golden
    assert cand["theme"] == "dark_walnut" and cand["style"] == "industrial"
    assert cand["notes"] == "CANDIDATE"
    assert cand["created_at"] == "2026-07-01T12:00:00Z"
    # gate_verdicts em JSON-texto {"gate": "PASS"} -> consultavel pelo LIKE
    passing = rdb.query(con, kind="judged_variant", gate_pass="geometry_sanity")
    assert [r["slug"] for r in passing] == [
        "variant/planta_74__industrial__dark_walnut__L1"]
    # re-ingest idempotente (ON CONFLICT slug -> UPDATE, nao duplica)
    ctr.ingest_reference(corpus)
    total = con.execute("SELECT COUNT(*) n FROM reference").fetchone()["n"]
    assert total == 2
    con.close()


def test_corpus_to_rag_output_is_ingestible_project_memory_db(monkeypatch,
                                                              tmp_path, corpus):
    scratch = tmp_path / "corpus_root"
    out_json = scratch / ".ai_bridge" / "research" / "judged_variants.json"
    n = ctr.export_memory_json(corpus, out_json)
    assert n == 2
    items = json.loads(out_json.read_text("utf-8"))
    assert isinstance(items, list) and items[0]["id"].startswith("planta_74__")
    # embed MOCKADO por NOME (cmd_index/search chamam pmd.embed): Ollama-off ok
    monkeypatch.setattr(pmd, "embed",
                        lambda t, **kw: np.zeros(8, dtype=np.float32))
    db = tmp_path / "pm.db"
    rc = pmd.main(["--db", str(db), "index", "--corpus-root", str(scratch)])
    assert rc == 0
    con = sqlite3.connect(db)
    n_chunks = con.execute("SELECT COUNT(*) FROM chunk").fetchone()[0]
    con.close()
    assert n_chunks >= 2
    results = pmd.search("variante industrial dark_walnut", k=2, db_path=db)
    assert isinstance(results, list) and len(results) >= 1


def test_created_at_is_deterministic_no_clock():
    src = inspect.getsource(ctr)
    assert "datetime.now" not in src
    assert "time.time" not in src


def test_export_rows_shape_and_tags(corpus):
    rows = ctr.export_reference_rows(corpus)
    assert len(rows) == 2
    row, tags = rows[0]
    assert row["kind"] == "judged_variant"
    assert row["slug"].startswith("variant/")
    assert row["source"] == "variant_sweep"
    assert json.loads(row["gate_verdicts"])["geometry_sanity"] in (
        "PASS", "WARN", "FAIL")
    assert "planta_74" in tags
    assert any(t.startswith("seed") for t in tags)
    assert tags == [t.lower() for t in tags]
