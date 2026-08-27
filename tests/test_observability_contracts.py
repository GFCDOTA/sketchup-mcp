"""Contratos da Fase 3: intenção vs execução, proveniência da fusão, LLM, contexto.

A regra que estes testes protegem: *observability must describe execution, not
change execution* — e, dentro disso, a trace nunca pode carimbar um rótulo que
veio da CONFIGURAÇÃO em vez da EXECUÇÃO.
"""
from __future__ import annotations

import pytest

from core.observability.llm import (
    NOT_INSTRUMENTED,
    ContextComposition,
    ContextSource,
    LLMCall,
    from_ollama,
)
from core.observability.retrieval import (
    ChunkLedger,
    ChunkRef,
    RetrievalOutcome,
    observe_fusion,
)
from core.observability.taxonomy import IndexKind, RetrievalKind

# ---------------------------------------------------------------------------
# intenção vs execução — o coração da Fase 3
# ---------------------------------------------------------------------------


def test_requested_embed_that_fell_back_is_labelled_faceted():
    """O exemplo literal do Felipe: pediu embed, Qdrant fora, executou faceted."""
    out = RetrievalOutcome(
        retriever="reference_db.tokens",
        index=IndexKind.STRUCTURED,
        backend_requested="embed",
        backend_actual="faceted",
        fallback_triggered=True,
        fallback_reason="InfraUnavailable: Qdrant off",
        augments_context=True,
        feeds_generation=True,
    )
    assert out.taxonomy is RetrievalKind.FACETED_STRUCTURED_RAG
    assert out.is_rag
    assert not out.intent_matched_execution

    meta = out.to_meta()
    assert meta["backendRequested"] == "embed"
    assert meta["backendActual"] == "faceted"
    assert meta["fallbackTriggered"] is True
    assert meta["resultingTaxonomy"] == "FACETED_STRUCTURED_RAG"
    assert meta["intentMatchedExecution"] is False


def test_embed_that_actually_ran_with_fusion_is_hybrid():
    out = RetrievalOutcome(
        retriever="reference_db.tokens", index=IndexKind.VECTOR,
        backend_requested="embed", backend_actual="embed",
        fusion_strategy="RRF", retrievers_fused=2,
        augments_context=True, feeds_generation=True)
    assert out.taxonomy is RetrievalKind.HYBRID_RAG
    assert out.intent_matched_execution


def test_taxonomy_has_no_setter():
    """Impossível carimbar um rótulo que a execução não sustenta."""
    out = RetrievalOutcome(retriever="x", index=IndexKind.VECTOR,
                           augments_context=True, feeds_generation=True)
    with pytest.raises(AttributeError):
        out.taxonomy = RetrievalKind.HYBRID_RAG  # type: ignore[misc]


def test_intent_matches_when_no_backend_was_declared():
    """Retriever sem noção de backend (o chat) não conta como divergência."""
    out = RetrievalOutcome(retriever="qdrant.felipe_preferences",
                           index=IndexKind.VECTOR,
                           augments_context=True, feeds_generation=True)
    assert out.intent_matched_execution


def test_meta_omits_absent_fields_instead_of_sending_null_noise():
    meta = RetrievalOutcome(retriever="x", index=IndexKind.STRUCTURED).to_meta()
    assert "collection" not in meta
    assert "topK" not in meta
    assert meta["retriever"] == "x"


def test_meta_carries_no_query_text():
    out = RetrievalOutcome(retriever="x", index=IndexKind.VECTOR,
                           query_chars=64, query_hash="abc123def456")
    meta = out.to_meta()
    assert meta["queryChars"] == 64 and meta["queryHash"] == "abc123def456"
    assert not any(isinstance(v, str) and len(v) > 80 for v in meta.values())


# ---------------------------------------------------------------------------
# proveniência da fusão — as quatro perguntas
# ---------------------------------------------------------------------------


@pytest.fixture
def fusion():
    return observe_fusion(
        strategy="RRF", k=60,
        ranked_inputs={"faceted": ["a.json", "b.json", "c.json"],
                       "semantic": ["c.json", "a.json"]},
        fused=["a.json", "c.json", "b.json"])


def test_fusion_answers_which_retriever_produced_it(fusion):
    a = next(e for e in fusion.entries if e.key == "a.json")
    assert {m.retriever for m in a.members} == {"faceted", "semantic"}


def test_fusion_answers_whether_it_appeared_in_more_than_one(fusion):
    by_key = {e.key: e for e in fusion.entries}
    assert by_key["a.json"].in_multiple
    assert by_key["c.json"].in_multiple
    assert not by_key["b.json"].in_multiple
    assert fusion.n_in_multiple == 2


def test_fusion_answers_original_and_final_rank(fusion):
    c = next(e for e in fusion.entries if e.key == "c.json")
    assert {m.retriever: m.rank for m in c.members} == {"faceted": 3, "semantic": 1}
    assert c.rank_after == 2
    assert c.rank_delta == -1        # melhor rank de origem era 1, caiu pra 2


def test_fusion_counts_promoted_items(fusion):
    b = next(e for e in fusion.entries if e.key == "b.json")
    assert b.rank_delta == -1        # era 2 no faceted, virou 3
    assert fusion.n_promoted == 0


def test_fusion_meta_is_compact_and_declares_truncation():
    big = observe_fusion(strategy="RRF", k=60,
                         ranked_inputs={"faceted": [f"t{i}.json" for i in range(80)]},
                         fused=[f"t{i}.json" for i in range(80)])
    meta = big.to_meta(limit=10)
    assert len(meta["provenance"]) == 10
    assert meta["truncated"] is True
    assert meta["counts"]["entries"] == 80


def test_fusion_of_a_single_retriever_is_not_hybrid():
    f = observe_fusion(strategy="RRF", ranked_inputs={"faceted": ["a"]}, fused=["a"])
    out = RetrievalOutcome(retriever="x", index=IndexKind.STRUCTURED,
                           retrievers_fused=len(f.inputs),
                           augments_context=True, feeds_generation=True)
    assert out.taxonomy is RetrievalKind.FACETED_STRUCTURED_RAG


# ---------------------------------------------------------------------------
# chunks — leve, e o rejeitado não some
# ---------------------------------------------------------------------------


def test_chunk_ref_has_no_content_field():
    assert "text" not in ChunkRef.__dataclass_fields__
    assert "content" not in ChunkRef.__dataclass_fields__


def test_ledger_counts_selected_and_rejected():
    led = ChunkLedger()
    led.add(ChunkRef("a", score=0.94, rank=1, selected=True))
    led.add(ChunkRef("b", score=0.89, rank=2, selected=True))
    led.add(ChunkRef("c", score=0.21, rank=3, selected=False,
                     rejection_reason="abaixo do threshold"))
    out = led.apply_to(RetrievalOutcome(retriever="x", index=IndexKind.VECTOR))
    assert (out.retrieved_count, out.selected_count, out.rejected_count) == (3, 2, 1)
    assert led.rejected[0].rejection_reason == "abaixo do threshold"


# ---------------------------------------------------------------------------
# LLM — normalizar, não repassar
# ---------------------------------------------------------------------------


def test_ollama_token_counts_are_normalized_into_our_contract():
    call = from_ollama({"model": "deepseek-r1:14b", "prompt_eval_count": 3841,
                        "eval_count": 742, "total_duration": 2_100_000_000},
                       model="deepseek", latency_ms=2100.0)
    assert call.provider == "ollama"
    assert call.model == "deepseek-r1:14b"
    assert call.prompt_tokens == 3841
    assert call.completion_tokens == 742
    assert call.total_tokens == 4583


def test_missing_counts_are_none_never_zero():
    """Resposta truncada/erro: 'não sei' != 'zero tokens'."""
    call = from_ollama({"model": "x"}, model="x")
    assert call.prompt_tokens is None
    assert call.total_tokens is None
    assert call.to_meta()["promptTokens"] == NOT_INSTRUMENTED


def test_provider_raw_keeps_only_phase_durations():
    call = from_ollama({"prompt_eval_count": 1, "eval_count": 2,
                        "total_duration": 9, "context": [1, 2, 3],
                        "response": "texto enorme"}, model="m")
    assert call.provider_raw == {"total_duration": 9}
    assert "response" not in call.provider_raw
    assert "context" not in call.provider_raw


def test_raw_can_be_dropped_entirely():
    call = from_ollama({"total_duration": 9}, model="m", keep_raw=False)
    assert call.provider_raw == {}


def test_our_contract_does_not_assume_ollama_field_names():
    """Outro provider preenche o MESMO contrato por outro adapter."""
    call = LLMCall(provider="outro", model="m", prompt_tokens=10,
                   completion_tokens=5)
    assert call.total_tokens == 15
    assert call.to_meta()["model"] == "m"


# ---------------------------------------------------------------------------
# decomposição do contexto
# ---------------------------------------------------------------------------


def test_context_breakdown_by_source_with_percentages():
    comp = (ContextComposition()
            .add(ContextSource.SYSTEM_STATIC, "s" * 100)
            .add(ContextSource.RETRIEVED_KNOWLEDGE, "k" * 60)
            .add(ContextSource.RETRIEVED_PREFERENCES, "p" * 40))
    meta = comp.to_meta()
    assert meta["totalChars"] == 200
    top = meta["sections"][0]
    assert top["source"] == "system/static" and top["pct"] == 50.0
    assert [s["source"] for s in meta["sections"]] == [
        "system/static", "retrieved knowledge", "retrieved preferences"]


def test_tokens_per_source_are_declared_not_instrumented():
    """Estimar token sem tokenizer seria inventar. O campo é honesto."""
    meta = ContextComposition().add(ContextSource.CONVERSATION, "oi").to_meta()
    assert meta["totalTokens"] == NOT_INSTRUMENTED


def test_unattributed_context_is_surfaced_not_normalized_away():
    """Se as seções medidas não explicam o prompt inteiro, a UI precisa saber."""
    comp = ContextComposition().add(ContextSource.SYSTEM_STATIC, "a" * 50)
    meta = comp.to_meta(prompt="a" * 100)
    assert meta["attributedFraction"] == 0.5
    assert meta["promptChars"] == 100


def test_empty_sections_are_skipped():
    comp = (ContextComposition()
            .add(ContextSource.RETRIEVED_KNOWLEDGE, "")
            .add(ContextSource.RETRIEVED_PREFERENCES, None))
    assert comp.total_chars == 0
    assert comp.to_meta()["sections"] == []


def test_same_source_added_twice_is_summed():
    comp = (ContextComposition()
            .add(ContextSource.SYSTEM_STATIC, "a" * 10, "template")
            .add(ContextSource.SYSTEM_STATIC, "b" * 5, "core_hint"))
    assert comp.by_source()[ContextSource.SYSTEM_STATIC] == 15
