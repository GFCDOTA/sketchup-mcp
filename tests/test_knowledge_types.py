import re
from pathlib import Path

import pytest

from core.domain.knowledge_types import (
    KnowledgeType,
    SOURCE_TYPE_TO_KNOWLEDGE_TYPE,
    knowledge_type_for_source_type,
    preference_may_override,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


# "consensus" existe em SOURCES mas é excluído deliberadamente do mapeamento —
# geometria de planta não é "conhecimento recuperável" no sentido do enum, é
# fato estrutural imutável (ver docs/architecture/knowledge_classification.md).
DELIBERATELY_UNMAPPED_SOURCE_TYPES = {"consensus"}


def _source_types_declared_in_rag_freshness() -> set[str]:
    """Extrai os source_type literais só de dentro do bloco
    `SOURCES: list[tuple[str, str, str]] = [ ... ]` em tools/rag_freshness.py,
    sem importar o módulo (evita puxar dependências pesadas nos testes)."""
    text = (REPO_ROOT / "tools" / "rag_freshness.py").read_text(encoding="utf-8")
    block_match = re.search(r"SOURCES:\s*list\[tuple\[str, str, str\]\]\s*=\s*\[(.*?)\n\]", text, re.S)
    assert block_match, "bloco SOURCES não encontrado em tools/rag_freshness.py — arquivo mudou de formato?"
    block = block_match.group(1)
    # cada entrada é ("<glob-ou-path>", "<source_type>", "<strategy>")
    return set(re.findall(r'"([a-z_]+)",\s*"[a-z]+"\),?\s*$', block, re.M))


def test_every_rag_freshness_source_type_has_a_mapping():
    declared = _source_types_declared_in_rag_freshness()
    assert declared, "não achei nenhum source_type em tools/rag_freshness.py — regex desatualizada?"
    missing = declared - set(SOURCE_TYPE_TO_KNOWLEDGE_TYPE) - DELIBERATELY_UNMAPPED_SOURCE_TYPES
    assert not missing, f"source_type sem KnowledgeType mapeado: {missing}"


@pytest.mark.parametrize(
    "source_type,expected",
    [
        ("style_dna", KnowledgeType.PREFERENCE),
        ("token", KnowledgeType.REFERENCE),
        ("design_rule", KnowledgeType.TECHNICAL_RULE),
        ("anti_pattern", KnowledgeType.TECHNICAL_RULE),
        ("human_verdict", KnowledgeType.HUMAN_VERDICT),
        ("semantic_zones", KnowledgeType.TECHNICAL_RULE),
        ("learning_patch", KnowledgeType.PROJECT_DECISION),
    ],
)
def test_known_mappings(source_type, expected):
    assert knowledge_type_for_source_type(source_type) == expected


def test_unmapped_source_type_raises():
    with pytest.raises(KeyError):
        knowledge_type_for_source_type("totally_unmapped_source")


def test_preference_never_overrides_technical_rule_or_decision_or_verdict():
    for hard in (KnowledgeType.TECHNICAL_RULE, KnowledgeType.PROJECT_DECISION, KnowledgeType.HUMAN_VERDICT):
        assert preference_may_override(hard) is False


def test_preference_may_override_reference_and_iteration_result():
    assert preference_may_override(KnowledgeType.REFERENCE) is True
    assert preference_may_override(KnowledgeType.ITERATION_RESULT) is True
