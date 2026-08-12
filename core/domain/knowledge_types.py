"""knowledge_types — vocabulário de tipo semântico de conhecimento
(Princípio 3: nunca misturar preferência com regra técnica com decisão de
projeto). Formaliza, sem tocar no indexador ainda, a que categoria cada
source_type já usado por tools/rag_freshness.py::SOURCES pertence.

Uso pretendido (Fase B): tools/knowledge_api.py filtra/pondera resultados
de retrieval por KnowledgeType e nunca deixa uma PREFERENCE sobrescrever um
TECHNICAL_RULE no ranking.
"""
from __future__ import annotations

from enum import Enum


class KnowledgeType(str, Enum):
    PREFERENCE = "PREFERENCE"
    TECHNICAL_RULE = "TECHNICAL_RULE"
    PROJECT_DECISION = "PROJECT_DECISION"
    ITERATION_RESULT = "ITERATION_RESULT"
    HUMAN_VERDICT = "HUMAN_VERDICT"
    REFERENCE = "REFERENCE"


# source_type -> KnowledgeType, para todo source_type que já existe em
# tools/rag_freshness.py::SOURCES (linhas 59-70, confirmado por leitura direta
# nesta sessão). "consensus" fica fora deliberadamente — geometria de planta
# não é conhecimento recuperável no sentido deste enum, é fato estrutural
# imutável (ver docs/architecture/knowledge_classification.md).
SOURCE_TYPE_TO_KNOWLEDGE_TYPE: dict[str, KnowledgeType] = {
    "style_dna": KnowledgeType.PREFERENCE,
    "token": KnowledgeType.REFERENCE,
    "design_rule": KnowledgeType.TECHNICAL_RULE,
    "anti_pattern": KnowledgeType.TECHNICAL_RULE,
    "human_verdict": KnowledgeType.HUMAN_VERDICT,
    "semantic_zones": KnowledgeType.TECHNICAL_RULE,
    "learning_patch": KnowledgeType.PROJECT_DECISION,
}

# Regra dura do Princípio 3: ordem de precedência quando dois KnowledgeType
# conflitam no mesmo ranking — menor índice nunca perde pra maior índice.
PRECEDENCE_OVER_PREFERENCE: tuple[KnowledgeType, ...] = (
    KnowledgeType.TECHNICAL_RULE,
    KnowledgeType.PROJECT_DECISION,
    KnowledgeType.HUMAN_VERDICT,
)


def knowledge_type_for_source_type(source_type: str) -> KnowledgeType:
    try:
        return SOURCE_TYPE_TO_KNOWLEDGE_TYPE[source_type]
    except KeyError:
        raise KeyError(
            f"source_type sem mapeamento em SOURCE_TYPE_TO_KNOWLEDGE_TYPE: {source_type!r}"
        ) from None


def preference_may_override(candidate: KnowledgeType) -> bool:
    """False se `candidate` é um tipo que uma PREFERENCE nunca pode sobrescrever."""
    return candidate not in PRECEDENCE_OVER_PREFERENCE
