"""FP-037 Camada 2 — embed backend (Qdrant + Ollama). INTEGRAÇÃO.

Dois grupos:
  1) UNIT (rodam SEMPRE no CI, sem infra): fallback determinístico — quando a
     infra aponta pra uma porta MORTA, backend='embed' degrada pro faceted, loga,
     e a confidence NÃO infla. E o retrieve carrega os campos aditivos do FP-037.
  2) INTEGRAÇÃO (skip automático se Qdrant/Ollama off): reindex real -> busca
     semântica retorna o chunk certo. Prova o recall real.

O skip usa um probe rápido (infra_up) — o CI, sem infra, pula o grupo 2 inteiro
sem quebrar. Determinístico onde é unit; o grupo de integração é honestamente
não-determinístico (depende do modelo real) e por isso é separado + skippable.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools import rag_embed_backend as reb
from tools import rag_freshness as rf

INFRA_UP = reb.infra_up()
requires_infra = pytest.mark.skipif(
    not INFRA_UP, reason="Qdrant/Ollama off — teste de integração pulado (CI-safe)")

T0 = "2026-07-07T10:00:00Z"


def _write(root: Path, rel: str, content: str, mtime: float = 1_700_000_000) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    import os
    os.utime(p, (mtime, mtime))
    return p


# =========================================================================== UNIT (sempre)
def test_fallback_to_faceted_when_qdrant_port_dead(monkeypatch):
    # aponta o adapter pra uma porta morta -> retrieve(backend='embed') degrada
    monkeypatch.setattr(reb, "QDRANT_URL", "http://127.0.0.1:6553")   # porta morta
    monkeypatch.setattr(reb, "OLLAMA_URL", "http://127.0.0.1:6554")   # porta morta
    from tools import reference_db as rdb
    bundle = rdb.retrieve("kitchen", "black_wood_gold", backend="embed")
    # degradou honesto: tokens continuam vindo do faceted, confidence NÃO inflada
    assert bundle["tokens"]                       # faceted ainda entrega
    assert bundle["confidence"] == "LOW"          # nunca HIGH fabricado
    assert bundle["retrieved_chunks"] == []       # sem recall (infra off)
    assert any("degrad" in n.lower() or "faceted" in n.lower() for n in bundle["notes"])


def test_retrieve_carries_additive_fp037_fields():
    # retrocompat aditivo: mesmo no faceted default, os campos novos existem
    from tools import reference_db as rdb
    bundle = rdb.retrieve("kitchen", "black_wood_gold")
    assert "rag_corpus_version" in bundle
    assert "retrieved_chunks" in bundle
    assert bundle["retrieved_chunks"] == []       # faceted puro: sem chunks


def test_embed_raises_infra_unavailable_on_dead_port(monkeypatch):
    monkeypatch.setattr(reb, "OLLAMA_URL", "http://127.0.0.1:6554")
    with pytest.raises(reb.InfraUnavailable):
        reb.embed("qualquer texto")


def test_probes_false_on_dead_ports(monkeypatch):
    monkeypatch.setattr(reb, "QDRANT_URL", "http://127.0.0.1:6553")
    monkeypatch.setattr(reb, "OLLAMA_URL", "http://127.0.0.1:6554")
    assert reb.qdrant_up(timeout=1) is False
    assert reb.ollama_up(timeout=1) is False
    assert reb.infra_up(timeout=1) is False


def test_point_id_is_deterministic():
    a = reb._point_id("deadbeefdeadbeef0001")
    b = reb._point_id("deadbeefdeadbeef0001")
    assert a == b and isinstance(a, int)


# =========================================================================== INTEGRAÇÃO (skip)
@pytest.fixture
def integ_corpus(tmp_path):
    """Corpus fake com 2 tokens semânticamente distintos, indexado no freshness."""
    root = tmp_path / "repo"
    _write(root, "references/tokens/hot_tower_niche.json", json.dumps({
        "name": "hot_tower_niche",
        "rule": "coluna piso-teto agrupando forno, micro-ondas e airfryer em "
                "nichos quentes empilhados na altura ergonômica.",
        "anti_pattern": "forno embaixo do cooktop.",
        "applies_to_kinds": ["kc_niche_wood"]}))
    _write(root, "references/tokens/subtle_veined_stone.json", json.dumps({
        "name": "subtle_veined_stone",
        "rule": "tampo de pedra clara com veio sutil sobe como backsplash contínuo.",
        "applies_to_kinds": ["kc_tampo"]}))
    db_path = tmp_path / "rag_freshness.db"
    con = rf.connect(db_path)
    rep = rf.reindex(con, root=root, now_iso=T0)
    return root, db_path, con, rep


@requires_infra
def test_reindex_and_semantic_search_returns_right_chunk(integ_corpus, monkeypatch):
    root, db_path, con, rep = integ_corpus
    cv = rep["corpus_version"]
    # usa uma collection de teste isolada (não polui a de produção)
    monkeypatch.setattr(reb, "COLLECTION", "rag_chunks_test_fp037")
    try:
        reb.reindex_qdrant(con, corpus_version=cv, now_iso=T0)
        # query semântica sobre ELETRO QUENTE -> deve trazer o hot_tower_niche,
        # não a pedra (recall que casamento de palavra-chave exato erraria)
        hits = reb.semantic_recall("onde coloco o forno e o micro-ondas embutidos",
                                   corpus_version=cv, top_k=2)
        assert hits, "busca semântica não retornou nada"
        top_sources = [h["payload"].get("source_path") for h in hits]
        assert "references/tokens/hot_tower_niche.json" == top_sources[0], top_sources
    finally:
        # limpeza: dropa a collection de teste
        try:
            reb._http("DELETE", f"{reb.QDRANT_URL}/collections/{reb.COLLECTION}")
        except reb.InfraUnavailable:
            pass
        con.close()


@requires_infra
def test_reindex_qdrant_is_incremental(integ_corpus, monkeypatch):
    root, db_path, con, rep = integ_corpus
    cv = rep["corpus_version"]
    monkeypatch.setattr(reb, "COLLECTION", "rag_chunks_test_fp037_inc")
    try:
        r1 = reb.reindex_qdrant(con, corpus_version=cv, now_iso=T0)
        assert r1["embedded"] >= 2                 # 1ª vez: embeda tudo
        # 2ª vez sem mudança: todos embedded=1 -> zero re-embed
        r2 = reb.reindex_qdrant(con, corpus_version=cv, now_iso=T0)
        assert r2["embedded"] == 0
    finally:
        try:
            reb._http("DELETE", f"{reb.QDRANT_URL}/collections/{reb.COLLECTION}")
        except reb.InfraUnavailable:
            pass
        con.close()


@requires_infra
def test_retrieve_embed_backend_populates_retrieved_chunks(integ_corpus, monkeypatch):
    root, db_path, con, rep = integ_corpus
    cv = rep["corpus_version"]
    con.close()
    monkeypatch.setattr(reb, "COLLECTION", "rag_chunks_test_fp037_e2e")
    # o _embed_recall_chunks do reference_db usa rf.connect() (lê DEFAULT_DB) +
    # rf.current_corpus_version + reb.semantic_recall — só precisa do DB apontado.
    monkeypatch.setattr(rf, "DEFAULT_DB", db_path)
    con2 = rf.connect(db_path)
    try:
        reb.reindex_qdrant(con2, corpus_version=cv, now_iso=T0)
    finally:
        con2.close()
    from tools import reference_db as rdb
    bundle = rdb.retrieve("kitchen", "black_wood_gold", backend="embed")
    try:
        assert bundle["rag_corpus_version"] == cv
        assert bundle["retrieved_chunks"], "embed backend deveria trazer chunks"
        assert bundle["confidence"] == "LOW"       # facets ainda decidem, sem inflar
    finally:
        try:
            reb._http("DELETE", f"{reb.QDRANT_URL}/collections/{reb.COLLECTION}")
        except reb.InfraUnavailable:
            pass
