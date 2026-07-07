"""FP-037 — wiring do freshness guard no architect_program (Camada 1, sem infra).

Prova que o arquiteto RECUSA contexto stale ANTES de consumir o RAG:
  - bundle sem retrieved_chunks (faceted puro) passa intacto (retrocompat);
  - chunk inativo é descartado do contexto;
  - chunk cuja fonte ficou mais nova que o índice vira STALE e não entra calado;
  - a nota de degradação viaja no bundle (honestidade).
Determinístico: DB e corpus em tmp_path, now_iso injetado, zero rede.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools import rag_freshness as rf
from tools.interior_studio import architect_program as ap

T0 = "2026-07-07T10:00:00Z"


def _write(root: Path, rel: str, content: str, mtime: float = 1_700_000_000) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    import os
    os.utime(p, (mtime, mtime))
    return p


@pytest.fixture
def indexed(tmp_path, monkeypatch):
    """Corpus fake indexado + rag_freshness apontando (DB + root) pro tmp_path.

    O guard em produção usa SEMPRE o mesmo root (ROOT do repo) do índice; aqui
    fixamos discover_sources no corpus fake pra manter essa consistência no teste.
    """
    root = tmp_path / "repo"
    _write(root, "references/tokens/hot_tower_niche.json", json.dumps({
        "name": "hot_tower_niche", "rule": "torre quente coluna piso-teto.",
        "anti_pattern": "forno embaixo do cooktop.", "applies_to_kinds": ["kc_niche_wood"]}))
    _write(root, "references/tokens/matte_black_cabinetry.json", json.dumps({
        "name": "matte_black_cabinetry", "rule": "marcenaria preta fosca.",
        "applies_to_kinds": ["kc_corpo"]}))
    db_path = tmp_path / "rag_freshness.db"
    con = rf.connect(db_path)
    rf.reindex(con, root=root, now_iso=T0)
    con.close()
    # o guard usa rf.connect()/discover_sources sem args -> aponta ambos pro tmp_path
    monkeypatch.setattr(rf, "DEFAULT_DB", db_path)
    _orig_discover = rf.discover_sources
    monkeypatch.setattr(rf, "discover_sources",
                        lambda r=root: _orig_discover(root))
    return root, db_path


def test_guard_noop_when_no_retrieved_chunks():
    # faceted puro: bundle sem retrieved_chunks -> intacto (retrocompat FP-035)
    bundle = {"tokens": [{"name": "x", "builder_kinds": []}], "confidence": "LOW"}
    out = ap.guard_bundle_freshness(bundle)
    assert out is bundle  # mesmo objeto, sem tocar


def test_guard_noop_on_none():
    assert ap.guard_bundle_freshness(None) is None


def test_guard_keeps_fresh_chunks(indexed):
    root, db_path = indexed
    con = rf.connect(db_path)
    cv = rf.current_corpus_version(con)
    chunks = rf.active_chunks(con, cv)
    con.close()
    bundle = {"tokens": [{"name": "hot_tower_niche", "builder_kinds": []}],
              "confidence": "LOW",
              "retrieved_chunks": [{"source": c["source_path"], "chunk_id": c["chunk_id"],
                                    "confidence": 0.9} for c in chunks]}
    out = ap.guard_bundle_freshness(bundle)
    assert len(out["retrieved_chunks"]) == len(chunks)  # todos frescos
    assert out["freshness"]["kept"] == len(chunks)
    assert not out["freshness"]["rejected"] and not out["freshness"]["stale"]


def test_guard_drops_inactive_chunk(indexed):
    root, db_path = indexed
    con = rf.connect(db_path)
    cv = rf.current_corpus_version(con)
    chunks = rf.active_chunks(con, cv)
    victim = chunks[0]
    con.execute("UPDATE chunk SET is_active=0 WHERE chunk_id=?", (victim["chunk_id"],))
    con.commit()
    con.close()
    bundle = {"tokens": [], "confidence": "LOW",
              "retrieved_chunks": [{"source": c["source_path"], "chunk_id": c["chunk_id"],
                                    "confidence": 0.9} for c in chunks]}
    out = ap.guard_bundle_freshness(bundle)
    kept_ids = {c["chunk_id"] for c in out["retrieved_chunks"]}
    assert victim["chunk_id"] not in kept_ids
    assert out["freshness"]["rejected"]
    assert any("freshness guard" in n for n in out.get("notes", []))


def test_guard_flags_stale_when_source_newer_than_index(indexed):
    root, db_path = indexed
    con = rf.connect(db_path)
    cv = rf.current_corpus_version(con)
    chunks = rf.active_chunks(con, cv)
    con.close()
    # a fonte de um chunk fica MAIS NOVA que o índice (mtime no futuro), sem reindex.
    # o fixture já fixou discover_sources no corpus fake -> o guard vê o mtime novo.
    import os
    os.utime(root / "references/tokens/hot_tower_niche.json",
             (1_900_000_000, 1_900_000_000))
    bundle = {"tokens": [], "confidence": "LOW",
              "retrieved_chunks": [{"source": c["source_path"], "chunk_id": c["chunk_id"],
                                    "confidence": 0.9} for c in chunks]}
    out = ap.guard_bundle_freshness(bundle)
    assert out["freshness"]["stale"], "chunk de fonte mais nova que o índice deve ser STALE"
    stale_ids = {s["chunk_id"] for s in out["freshness"]["stale"]}
    kept_ids = {c["chunk_id"] for c in out["retrieved_chunks"]}
    assert kept_ids.isdisjoint(stale_ids)  # stale não entra no contexto
