"""commit 9 — integração RECUPERAVEL: fecha o laço do write-back do gosto.

Prova de verdade que o aprendizado e' RECUPERAVEL, nao log solto: materializa um
verdict CURADO -> reindex (chunka, embedded=0) -> embed REAL no Qdrant ->
retrieve(backend='embed') traz o CONTEUDO aprendido nos retrieved_chunks.

INFRA-GATED: skip limpo se Qdrant(:6333)/Ollama(:11434) off (InfraUnavailable) —
o CI que so tem [dev] pula sem quebrar. Com a infra no ar, PROVA de verdade.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tools import rag_embed_backend as reb
from tools import rag_freshness as rf
from tools import taste_writeback as tw

T0 = "2026-07-07T10:00:00Z"
T1 = "2026-07-07T11:00:00Z"

requires_infra = pytest.mark.skipif(
    not reb.infra_up(),
    reason="Qdrant/Ollama off — integração pulada (InfraUnavailable, CI-safe)")


def _write(root: Path, rel: str, content: str, mtime: float = 1_700_000_000) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    os.utime(p, (mtime, mtime))
    return p


@requires_infra
def test_retrieve_recovers_learned_verdict(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    _write(root, "references/tokens/hot_tower_niche.json", json.dumps({
        "name": "hot_tower_niche",
        "rule": "coluna piso-teto agrupando forno, micro-ondas e airfryer em "
                "nichos quentes na altura ergonomica.",
        "applies_to_kinds": ["kc_niche_wood"]}))

    db_path = tmp_path / "rag_freshness.db"
    monkeypatch.setattr(rf, "DEFAULT_DB", db_path)   # o retrieve embed usa rf.connect()
    con = rf.connect(db_path)
    rf.reindex(con, root=root, now_iso=T0)

    # veredito CURADO do Felipe, com comentario distintivo de cozinha planejada
    curadoria = {"variant_id": "planta_74__kc_v1", "human_verdict": "IMPROVED",
                 "liked": True, "tags": ["torre quente marcada", "madeira nogueira"],
                 "note": "a marcenaria planejada da cozinha com torre quente ficou "
                         "perfeita — forno e micro-ondas na altura certa",
                 "batch_id": "b1", "t": T0}
    corpus_rec = {"variant_id": "planta_74__kc_v1", "run_id": "run1",
                  "plant": "planta_74", "room_id": "r004", "room_type": "KITCHEN",
                  "params": {"style": "black_wood_gold"},
                  "render_refs": {"iso": "planta_74__kc_v1/iso.png"}}
    vdir = root / "references" / "felipe" / "verdicts"
    tw.materialize(curadoria, corpus_rec, con, verdicts_dir=vdir)

    rep = rf.reindex(con, root=root, now_iso=T1)     # chunka o verdict (embedded=0)
    cv = rep["corpus_version"]
    con.close()

    monkeypatch.setattr(reb, "COLLECTION", "rag_chunks_test_taste_wb")
    con2 = rf.connect(db_path)
    try:
        reb.reindex_qdrant(con2, corpus_version=cv, now_iso=T1)   # embed REAL
    finally:
        con2.close()

    from tools import reference_db as rdb
    bundle = rdb.retrieve("kitchen", "black_wood_gold", backend="embed")
    try:
        assert bundle["rag_corpus_version"] == cv
        assert bundle["retrieved_chunks"], "embed backend nao trouxe chunks"
        sources = [c.get("source") or "" for c in bundle["retrieved_chunks"]]
        assert any("references/felipe/verdicts/" in s for s in sources), \
            f"o veredito aprendido nao foi recuperado no retrieve: {sources}"
    finally:
        try:
            reb._http("DELETE", f"{reb.QDRANT_URL}/collections/{reb.COLLECTION}")
        except reb.InfraUnavailable:
            pass
