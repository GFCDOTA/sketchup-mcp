"""Taxonomia do Inspector — a correção conceitual do Felipe (2026-08-26).

RAG é categoria AMPLA (retrieval + augmentation + generation); a tecnologia do
índice define o SUBTIPO. Estes testes travam essa decisão: se alguém voltar a
classificar o caminho faceted como "não é RAG" porque não tem embedding, quebra
aqui.
"""
from __future__ import annotations

import dataclasses

import pytest

from core.observability.taxonomy import (
    CATEGORY_EXPLANATIONS,
    FORBIDDEN_EVIDENCE_FIELDS,
    HARNESS_EXPLANATIONS,
    RAG_KINDS,
    RETRIEVAL_EXPLANATIONS,
    Category,
    DecisionEvidence,
    HarnessKind,
    IndexKind,
    RetrievalKind,
    classify_retrieval,
    is_rag,
)


def test_faceted_structured_retrieval_is_rag():
    """reference_db.retrieve(backend='faceted'): consulta dinâmica sobre store
    estruturado cujo resultado entra no prompt. É RAG — sem embedding."""
    kind = classify_retrieval(
        dynamic_query=True, index=IndexKind.STRUCTURED,
        augments_context=True, feeds_generation=True)
    assert kind is RetrievalKind.FACETED_STRUCTURED_RAG
    assert is_rag(kind)


def test_vector_path_is_semantic_rag():
    kind = classify_retrieval(
        dynamic_query=True, index=IndexKind.VECTOR,
        augments_context=True, feeds_generation=True)
    assert kind is RetrievalKind.VECTOR_SEMANTIC_RAG
    assert is_rag(kind)


def test_rrf_fusion_of_two_retrievers_is_hybrid_rag():
    kind = classify_retrieval(
        dynamic_query=True, index=IndexKind.VECTOR, retrievers_fused=2,
        augments_context=True, feeds_generation=True)
    assert kind is RetrievalKind.HYBRID_RAG
    assert is_rag(kind)


def test_orphan_retriever_is_not_rag_end_to_end():
    """project_memory_db: embeda e ranqueia, mas nenhum prompt consome."""
    kind = classify_retrieval(
        dynamic_query=True, index=IndexKind.VECTOR,
        augments_context=False, feeds_generation=False)
    assert kind is RetrievalKind.RETRIEVAL_ONLY
    assert not is_rag(kind)


def test_retrieval_that_augments_but_never_generates_is_still_orphan():
    kind = classify_retrieval(
        dynamic_query=True, index=IndexKind.STRUCTURED,
        augments_context=True, feeds_generation=False)
    assert kind is RetrievalKind.RETRIEVAL_ONLY


def test_static_file_read_is_context_injection_not_rag():
    """felipe_style_dna.md via read_text(): aumenta contexto, não recupera nada."""
    kind = classify_retrieval(
        dynamic_query=False, index=IndexKind.FILE,
        augments_context=True, feeds_generation=True)
    assert kind is RetrievalKind.STATIC_CONTEXT_INJECTION
    assert not is_rag(kind)


def test_file_index_is_static_even_when_query_looks_dynamic():
    kind = classify_retrieval(
        dynamic_query=True, index=IndexKind.FILE,
        augments_context=True, feeds_generation=True)
    assert kind is RetrievalKind.STATIC_CONTEXT_INJECTION


def test_degraded_embed_run_is_labelled_by_what_actually_happened():
    """Qdrant off -> o caminho embed degrada pro faceted. A run daquele dia é
    FACETED_STRUCTURED_RAG. Rótulo fixo por call-site mentiria."""
    degraded = classify_retrieval(
        dynamic_query=True, index=IndexKind.STRUCTURED, retrievers_fused=1,
        augments_context=True, feeds_generation=True)
    healthy = classify_retrieval(
        dynamic_query=True, index=IndexKind.VECTOR, retrievers_fused=2,
        augments_context=True, feeds_generation=True)
    assert degraded is RetrievalKind.FACETED_STRUCTURED_RAG
    assert healthy is RetrievalKind.HYBRID_RAG
    assert degraded is not healthy


def test_rag_kinds_set_matches_is_rag():
    for kind in RetrievalKind:
        assert is_rag(kind) == (kind in RAG_KINDS)


# ---------------------------------------------------------------------------
# harness: as duas camadas nunca colapsam
# ---------------------------------------------------------------------------


def test_external_runtime_and_application_harness_are_distinct():
    assert HarnessKind.EXTERNAL_AGENT_RUNTIME is not HarnessKind.APPLICATION_HARNESS
    assert len({k.value for k in HarnessKind}) == 2


# ---------------------------------------------------------------------------
# evidência de decisão: sinal observável, nunca chain-of-thought
# ---------------------------------------------------------------------------


def test_decision_evidence_carries_no_chain_of_thought_field():
    """Restrição dura do Felipe. Se alguém adicionar `reasoning`/`thought`/
    `rationale` ao dataclass, este teste falha."""
    fields = {f.name for f in dataclasses.fields(DecisionEvidence)}
    assert not (fields & FORBIDDEN_EVIDENCE_FIELDS), (
        f"campo de raciocínio proibido em DecisionEvidence: "
        f"{sorted(fields & FORBIDDEN_EVIDENCE_FIELDS)}")


def test_decision_evidence_meta_is_reference_only():
    ev = DecisionEvidence(
        trigger_event="gate.failed",
        gate_result="FAIL",
        context_refs=("chunk_a1", "chunk_b2"),
        tool_called="place_fixture",
        effect="entity#9821 movida 6 cm",
    )
    meta = ev.to_meta()
    assert meta["contextRefs"] == ["chunk_a1", "chunk_b2"]
    assert meta["triggerEvent"] == "gate.failed"
    # referências, nunca corpo
    assert not any(len(str(v)) > 200 for v in meta.values())


# ---------------------------------------------------------------------------
# Learning Mode: uma fonte, cobertura total
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", list(RetrievalKind))
def test_every_retrieval_kind_has_a_learning_card(kind):
    exp = RETRIEVAL_EXPLANATIONS[kind]
    assert exp.title and exp.what and exp.verdict_line


@pytest.mark.parametrize("cat", list(Category))
def test_every_category_has_a_learning_card(cat):
    exp = CATEGORY_EXPLANATIONS[cat]
    assert exp.title and exp.what and exp.verdict_line


@pytest.mark.parametrize("kind", list(HarnessKind))
def test_every_harness_kind_has_a_learning_card(kind):
    assert HARNESS_EXPLANATIONS[kind].verdict_line


def test_non_rag_cards_say_so_explicitly():
    """O card precisa RESPONDER 'isto é RAG?', não só descrever a etapa."""
    for kind in (RetrievalKind.RETRIEVAL_ONLY, RetrievalKind.STATIC_CONTEXT_INJECTION):
        assert "NÃO é RAG" in RETRIEVAL_EXPLANATIONS[kind].verdict_line
    for kind in RAG_KINDS:
        assert "É RAG" in RETRIEVAL_EXPLANATIONS[kind].verdict_line
