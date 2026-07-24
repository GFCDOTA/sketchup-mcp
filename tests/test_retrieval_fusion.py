"""FP-035 epic "ligar o embed" — fusão RRF do recall semântico no ranking.

Antes: reference_db.py computava o cosine e o DESCARTAVA (:467 "o ranking segue
faceted"). Agora, no caminho backend='embed', os hits semânticos são FUNDIDOS via
Reciprocal Rank Fusion (determinístico, join por source_path). Invariantes:
  - infra off / retrieved_chunks vazio -> colapso BYTE-IDÊNTICO ao faceted.
  - confidence NUNCA tocada pelo cosine (segue facets/gates).
  - determinístico: 2× = idêntico; desempate estável por nome.

Testes SEM infra: stubam _embed_recall_chunks (a fronteira que devolve os chunks).
O ganho de métrica é provado sobre o golden-set com sinal semântico bom (mecanismo).
"""
from __future__ import annotations

import json

from tools import reference_db as rdb
from tools import retrieval_eval as rev

GOLDEN = rev.DEFAULT_GOLDEN


def _chunks(names: list[str]) -> list[dict]:
    """Fabrica retrieved_chunks (source=source_path do token) em ordem de cosine."""
    return [{"source": f"references/tokens/{n}.json", "chunk_id": n,
             "confidence": round(1.0 - i * 0.01, 4)} for i, n in enumerate(names)]


# --- fusão reordena pelo sinal semântico -----------------------------------

def test_rrf_pulls_semantic_top_tokens_up(monkeypatch):
    # warm_fendi_upper e coordinated_oak_base são alfabeticamente TARDIOS (afundam
    # no empate faceted). Com sinal semântico no topo, o RRF os puxa pro topo.
    def _stub(room, style_norm):
        return _chunks(["coordinated_oak_base", "warm_fendi_upper"]), "cv-test", []
    monkeypatch.setattr(rdb, "_embed_recall_chunks", _stub)
    bundle = rdb.retrieve("kitchen", "warm_compact", top_n=12, backend="embed")
    names = [t["name"] for t in bundle["tokens"]]
    assert set(names[:2]) == {"coordinated_oak_base", "warm_fendi_upper"}
    # confidence não inflada pelo cosine (segue a regra faceted/gates)
    assert bundle["confidence"] == "LOW"


def test_embed_empty_chunks_is_byte_identical_to_faceted(monkeypatch):
    # infra off: _embed_recall_chunks devolve [] -> a fusão NÃO roda -> ordem
    # dos tokens idêntica ao faceted puro (retrocompat garantida).
    def _stub(room, style_norm):
        return [], None, ["degradou p/ faceted (infra off)"]
    monkeypatch.setattr(rdb, "_embed_recall_chunks", _stub)
    emb = rdb.retrieve("kitchen", "black_wood_gold", top_n=12, backend="embed")
    fac = rdb.retrieve("kitchen", "black_wood_gold", top_n=12, backend="faceted")
    assert [t["name"] for t in emb["tokens"]] == [t["name"] for t in fac["tokens"]]
    assert emb["retrieved_chunks"] == []


def test_fusion_is_deterministic(monkeypatch):
    def _stub(room, style_norm):
        return _chunks(["subtle_veined_stone", "matte_black_cabinetry"]), "cv", []
    monkeypatch.setattr(rdb, "_embed_recall_chunks", _stub)
    a = rdb.retrieve("kitchen", "black_wood_gold", top_n=12, backend="embed")
    b = rdb.retrieve("kitchen", "black_wood_gold", top_n=12, backend="embed")
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


# --- _rrf_fuse unit ---------------------------------------------------------

def test_rrf_fuse_preserves_faceted_when_no_semantic():
    faceted = [{"name": "a", "source_path": "pa"}, {"name": "b", "source_path": "pb"}]
    out = rdb._rrf_fuse(faceted, [])
    assert [t["name"] for t in out] == ["a", "b"]


def test_rrf_fuse_reorders_on_semantic():
    faceted = [{"name": "a", "source_path": "pa"},
               {"name": "b", "source_path": "pb"},
               {"name": "c", "source_path": "pc"}]
    # 'c' é último no faceted mas 1º no semântico -> sobe.
    out = rdb._rrf_fuse(faceted, ["pc"])
    assert out[0]["name"] == "c"


# --- build_retrieval_query --------------------------------------------------

def test_build_retrieval_query_style_aware_and_deterministic():
    q1 = rdb.build_retrieval_query("kitchen", "black_wood_gold")
    q2 = rdb.build_retrieval_query("kitchen", "black_wood_gold")
    assert q1 == q2                          # determinístico
    assert "kitchen" in q1                   # room presente
    assert q1 != rdb.build_retrieval_query("kitchen", "warm_compact")  # style muda a query


# --- mecanismo: fusão LEVANTA a métrica do golden-set -----------------------

def test_fusion_lifts_ndcg_on_golden(monkeypatch):
    """Dado um sinal semântico BOM (a ordem esperada do golden), a fusão RRF
    levanta o nDCG agregado vs o faceted degenerado. Prova o MECANISMO (não que
    os embeddings reais acham essa ordem — isso é o teste de integração)."""
    golden = rev.load_golden(GOLDEN)
    by_style = {rdb.normalize_theme(r["style"]): r["relevant"]
                for r in golden if r["room"] == "kitchen" and r["relevant"]}

    def _stub(room, style_norm):
        return _chunks(by_style.get(style_norm, [])), "cv", []
    monkeypatch.setattr(rdb, "_embed_recall_chunks", _stub)

    emb = rev.evaluate(GOLDEN, k=6, backend="embed")
    fac = rev.evaluate(GOLDEN, k=6, backend="faceted")
    assert emb["aggregate"]["ndcg_at_k"] > fac["aggregate"]["ndcg_at_k"]
    # o pior caso do faceted (warm_compact) melhora concretamente
    emb_rows = {r["query"]["style"]: r for r in emb["rows"]}
    fac_rows = {r["query"]["style"]: r for r in fac["rows"]}
    assert emb_rows["warm_compact"]["ndcg_at_k"] > fac_rows["warm_compact"]["ndcg_at_k"]
