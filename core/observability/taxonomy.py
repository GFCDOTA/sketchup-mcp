"""taxonomy — vocabulário de classificação do AI Pipeline Inspector.

Fonte ÚNICA da verdade sobre "isto é RAG?", consumida pelo emissor de eventos
(que carimba a categoria no envelope) E pelo Learning Mode da UI (que explica a
categoria em português). Prosa de ensino mora AQUI, não hardcoded no HTML — do
contrário as duas divergem e a tela passa a ensinar o que o código não faz.

DECISÃO DE DESIGN (correção do Felipe, 2026-08-26)
--------------------------------------------------
RAG é categoria AMPLA: *retrieval de informação externa relevante* +
*augmentation do contexto* + *generation*. A tecnologia do índice (vetor,
SQLite, faceta) determina o SUBTIPO, não se é RAG ou não.

Consequência prática: `reference_db.retrieve(backend="faceted")` É RAG
(FACETED_STRUCTURED_RAG) — consulta dinâmica sobre store estruturado cujo
resultado entra no prompt via `render_bundle_for_prompt`. O que o tira da
categoria não é a ausência de embedding; é a ausência de augmentation ou de
generation a jusante.

CLASSIFICAÇÃO DERIVADA, NÃO ASSERIDA
------------------------------------
`classify_retrieval()` deriva o rótulo dos FATOS OBSERVADOS na execução, não de
uma constante por call-site. Isso importa: quando o Qdrant cai, o caminho
`backend="embed"` degrada pro faceted, e a run daquele dia é honestamente
FACETED_STRUCTURED_RAG — não HYBRID_RAG. Um rótulo fixo mentiria; o derivado
conta a verdade daquela execução, que é exatamente o que o Inspector existe pra
mostrar.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

# ---------------------------------------------------------------------------
# categorias de componente
# ---------------------------------------------------------------------------


class Category(str, Enum):
    """Natureza do componente que emitiu o evento."""

    RAG = "RAG"
    LLM = "LLM"
    HARNESS = "HARNESS"
    TOOL = "TOOL"
    DETERMINISTIC = "DETERMINISTIC"
    DATABASE = "DATABASE"
    OBSERVABILITY = "OBSERVABILITY"


# ---------------------------------------------------------------------------
# subtipos de retrieval — o espectro inteiro, RAG e não-RAG
# ---------------------------------------------------------------------------


class RetrievalKind(str, Enum):
    """Espectro completo. Nem todo membro é RAG — ver `is_rag()`."""

    VECTOR_SEMANTIC_RAG = "VECTOR_SEMANTIC_RAG"
    FACETED_STRUCTURED_RAG = "FACETED_STRUCTURED_RAG"
    HYBRID_RAG = "HYBRID_RAG"
    RETRIEVAL_ONLY = "RETRIEVAL_ONLY"
    STATIC_CONTEXT_INJECTION = "STATIC_CONTEXT_INJECTION"


RAG_KINDS: frozenset[RetrievalKind] = frozenset({
    RetrievalKind.VECTOR_SEMANTIC_RAG,
    RetrievalKind.FACETED_STRUCTURED_RAG,
    RetrievalKind.HYBRID_RAG,
})


def is_rag(kind: RetrievalKind) -> bool:
    """True só para os subtipos que fecham retrieval + augmentation + generation."""
    return kind in RAG_KINDS


class IndexKind(str, Enum):
    """De onde o retrieval leu."""

    VECTOR = "VECTOR"          # Qdrant, similaridade de embedding
    STRUCTURED = "STRUCTURED"  # SQLite, índice de facetas, tokens em disco
    FILE = "FILE"              # leitura direta de arquivo, sem consulta
    NONE = "NONE"


def classify_retrieval(
    *,
    dynamic_query: bool,
    index: IndexKind,
    retrievers_fused: int = 1,
    augments_context: bool,
    feeds_generation: bool,
) -> RetrievalKind:
    """Deriva o subtipo dos fatos observados na execução.

    dynamic_query    a consulta foi construída a partir da solicitação (vs ler
                     um caminho fixo).
    index            natureza do store consultado.
    retrievers_fused nº de rank-lists efetivamente combinadas (RRF conta aqui;
                     1 = sem fusão).
    augments_context o resultado foi de fato inserido no contexto.
    feeds_generation esse contexto chegou a um modelo generativo.

    Precedência: STATIC vence tudo (não houve consulta); RETRIEVAL_ONLY vence os
    subtipos de RAG (recuperou mas ninguém gerou nada com aquilo); HYBRID vence
    VECTOR e FACETED (a fusão é o fato mais informativo sobre a run).
    """
    if not dynamic_query or index is IndexKind.FILE:
        return RetrievalKind.STATIC_CONTEXT_INJECTION
    if not (augments_context and feeds_generation):
        return RetrievalKind.RETRIEVAL_ONLY
    if retrievers_fused >= 2:
        return RetrievalKind.HYBRID_RAG
    if index is IndexKind.VECTOR:
        return RetrievalKind.VECTOR_SEMANTIC_RAG
    return RetrievalKind.FACETED_STRUCTURED_RAG


# ---------------------------------------------------------------------------
# runtimes de harness — o externo NÃO é o da aplicação
# ---------------------------------------------------------------------------


class HarnessKind(str, Enum):
    """Quem está coordenando. Duas camadas distintas, nunca colapsar.

    EXTERNAL_AGENT_RUNTIME  o runtime de agente FORA do processo (hoje: a sessão
        do Claude Code que lê o gate, decide e chama a próxima CLI/tool). Suas
        decisões internas não são observáveis por este sistema — o Inspector só
        vê os efeitos (tool chamada, arquivo escrito, evento emitido).
    APPLICATION_HARNESS  o loop de coordenação DENTRO da aplicação
        (`correction_loop.run_loop`, `interior_studio.cycles`, `auto_decider`).
        Aqui o estado é observável de verdade: ciclo, retry, terminal, fix
        aplicado, fix revertido.
    """

    EXTERNAL_AGENT_RUNTIME = "EXTERNAL_AGENT_RUNTIME"
    APPLICATION_HARNESS = "APPLICATION_HARNESS"


# ---------------------------------------------------------------------------
# evidência de decisão — SOMENTE sinal observável
# ---------------------------------------------------------------------------

# Restrição dura (Felipe, 2026-08-26): NÃO capturar chain-of-thought. "Por que o
# agente decidiu isso" é respondido reconstituindo sinais externos, nunca lendo
# raciocínio do modelo. Estes nomes são PROIBIDOS como campo — há teste que falha
# se alguém adicionar um deles ao dataclass abaixo.
FORBIDDEN_EVIDENCE_FIELDS: frozenset[str] = frozenset({
    "reasoning", "rationale", "thought", "thoughts", "chain_of_thought", "cot",
    "thinking", "scratchpad", "deliberation", "internal_monologue", "why",
})


@dataclass(frozen=True)
class DecisionEvidence:
    """Por que o harness fez o que fez — reconstituído de sinal externo.

    Cinco slots, todos observáveis de fora do modelo:
      trigger_event  o evento que causou a decisão (nome + spanId)
      gate_result    o veredito determinístico que estava na mesa, se houve
      context_refs   IDs do contexto disponível no momento (chunk_id, spanId) —
                     REFERÊNCIAS, nunca o texto (payload leve, §6.4 da spec)
      tool_called    a ação externa efetivamente disparada
      effect         o efeito produzido, medível (arquivo, entidade, delta)
    """

    trigger_event: str
    gate_result: str | None = None
    context_refs: tuple[str, ...] = field(default_factory=tuple)
    tool_called: str | None = None
    effect: str | None = None

    def to_meta(self) -> dict:
        return {
            "triggerEvent": self.trigger_event,
            "gateResult": self.gate_result,
            "contextRefs": list(self.context_refs),
            "toolCalled": self.tool_called,
            "effect": self.effect,
        }


# ---------------------------------------------------------------------------
# Learning Mode — a explicação de cada rótulo, em UMA fonte
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Explanation:
    """Card do Learning Mode. `verdict_line` responde 'isto é RAG?' direto."""

    title: str
    what: str
    verdict_line: str


RETRIEVAL_EXPLANATIONS: dict[RetrievalKind, Explanation] = {
    RetrievalKind.VECTOR_SEMANTIC_RAG: Explanation(
        title="Vector / Semantic RAG",
        what=(
            "A solicitação virou um vetor de embedding e o sistema procurou os "
            "trechos mais PARECIDOS num banco vetorial. Nada aqui é busca por "
            "palavra exata — a proximidade é de significado."
        ),
        verdict_line=(
            "É RAG. Recuperou conhecimento externo por similaridade, colocou no "
            "contexto e o modelo gerou com aquilo à vista."
        ),
    ),
    RetrievalKind.FACETED_STRUCTURED_RAG: Explanation(
        title="Faceted / Structured RAG",
        what=(
            "A consulta foi montada a partir da sua solicitação (cômodo, estilo, "
            "orçamento) e rodou contra um store ESTRUTURADO — índice SQLite e "
            "tokens curados em disco — com ranking determinístico por facetas."
        ),
        verdict_line=(
            "É RAG. Não usa embedding nem banco vetorial, mas o ciclo está "
            "completo: consulta dinâmica → recuperação → contexto → geração. "
            "O que define RAG é o ciclo, não a tecnologia do índice."
        ),
    ),
    RetrievalKind.HYBRID_RAG: Explanation(
        title="Hybrid RAG",
        what=(
            "Dois recuperadores rodaram e tiveram os rankings FUNDIDOS num só "
            "(Reciprocal Rank Fusion, k=60): o semântico melhora o recall, o "
            "faceted mantém a decisão determinística e auditável."
        ),
        verdict_line=(
            "É RAG, na forma mais completa que este sistema tem. Dois caminhos de "
            "recuperação, uma fusão, um contexto, uma geração."
        ),
    ),
    RetrievalKind.RETRIEVAL_ONLY: Explanation(
        title="Retrieval Only / Orphan Retriever",
        what=(
            "Houve consulta de verdade — embedding, similaridade, chunks "
            "ranqueados. E parou aí: nenhum prompt consumiu esse resultado."
        ),
        verdict_line=(
            "NÃO é RAG end-to-end. Tem o R, falta o A e o G. É um recuperador "
            "órfão: a peça existe e funciona, mas não está ligada a nenhuma "
            "geração."
        ),
    ),
    RetrievalKind.STATIC_CONTEXT_INJECTION: Explanation(
        title="Static Context Injection",
        what=(
            "Um arquivo de caminho FIXO foi lido inteiro e colado no contexto. "
            "Nenhuma consulta foi construída, nada foi ranqueado por relevância — "
            "o mesmo conteúdo entraria para qualquer pergunta."
        ),
        verdict_line=(
            "NÃO é RAG. O contexto foi aumentado, sim, mas sem recuperação: não "
            "houve query, não houve seleção. Isto é injeção estática."
        ),
    ),
}

CATEGORY_EXPLANATIONS: dict[Category, Explanation] = {
    Category.RAG: Explanation(
        title="RAG",
        what=(
            "Etapa que buscou informação fora do modelo e a colocou no contexto "
            "antes da geração. O subtipo diz COMO a busca foi feita."
        ),
        verdict_line="É RAG — ver o subtipo para saber qual variante.",
    ),
    Category.LLM: Explanation(
        title="LLM",
        what=(
            "Inferência: o modelo leu o contexto montado e produziu texto. Só "
            "aqui existe geração."
        ),
        verdict_line=(
            "NÃO é RAG e NÃO é harness. É o modelo — a peça que o RAG alimenta e "
            "que o harness comanda."
        ),
    ),
    Category.HARNESS: Explanation(
        title="Harness",
        what=(
            "O código que coordena: decide quando chamar retrieval, quando chamar "
            "o modelo, quais tools usar, quando repetir, quando desistir, e o que "
            "vira estado. Monta o contexto, mas não gera nada."
        ),
        verdict_line=(
            "O harness NÃO é o modelo. Trocar o modelo não muda o harness; mudar "
            "o harness muda todo o resto."
        ),
    ),
    Category.TOOL: Explanation(
        title="Tool / MCP",
        what=(
            "Ação executada FORA do processo do modelo — uma tool MCP, um "
            "subprocesso, um script Ruby que constrói geometria no SketchUp."
        ),
        verdict_line=(
            "NÃO é RAG: nada foi recuperado. NÃO é LLM: nenhuma inferência. É a "
            "mão do agente no mundo."
        ),
    ),
    Category.DETERMINISTIC: Explanation(
        title="Determinístico",
        what=(
            "Cálculo comum sobre dados concretos — geometria, aritmética, um "
            "limite declarado em código. Mesma entrada, sempre a mesma saída."
        ),
        verdict_line=(
            "NÃO é RAG: nenhum documento recuperado. NÃO é LLM: nenhum modelo "
            "envolvido. Trocar de modelo não muda este resultado."
        ),
    ),
    Category.DATABASE: Explanation(
        title="Banco de dados",
        what=(
            "O armazenamento em si — vetorial (Qdrant) ou tradicional (SQLite). "
            "Guarda e devolve; não decide."
        ),
        verdict_line=(
            "O banco vetorial NÃO é o RAG. Ele é uma PEÇA do RAG: sem query, sem "
            "contexto e sem geração em volta, é só um banco."
        ),
    ),
    Category.OBSERVABILITY: Explanation(
        title="Observabilidade",
        what=(
            "Eventos, spans, métricas e traces — o próprio Inspector se olhando. "
            "Não participa da decisão que está sendo observada."
        ),
        verdict_line="NÃO é RAG nem LLM. É a instrumentação, não o pipeline.",
    ),
}

HARNESS_EXPLANATIONS: dict[HarnessKind, Explanation] = {
    HarnessKind.EXTERNAL_AGENT_RUNTIME: Explanation(
        title="External Agent Runtime",
        what=(
            "O runtime de agente que roda FORA desta aplicação — hoje, a sessão "
            "do Claude Code que lê o veredito de um gate, decide o próximo passo "
            "e dispara a próxima tool."
        ),
        verdict_line=(
            "Camada de coordenação, não modelo. O Inspector não enxerga o "
            "raciocínio dela — só os efeitos observáveis: tool chamada, arquivo "
            "escrito, evento emitido."
        ),
    ),
    HarnessKind.APPLICATION_HARNESS: Explanation(
        title="Application Harness",
        what=(
            "O loop de coordenação DENTRO da aplicação — `correction_loop`, "
            "`cycles`, `auto_decider`. Detecta, classifica, corrige, re-checa e "
            "para num estado terminal declarado."
        ),
        verdict_line=(
            "Também é harness, e é o único cujo estado é totalmente observável: "
            "ciclo, retry, fix aplicado, fix revertido, motivo da parada."
        ),
    ),
}
