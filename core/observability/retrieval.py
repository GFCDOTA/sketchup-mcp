"""retrieval — o contrato que separa INTENÇÃO/CONFIGURAÇÃO de EXECUÇÃO REAL.

Regra que motiva este módulo inteiro (Felipe, 2026-08-26):

    A trace não pode dizer "Vector RAG" porque essa era a configuração.
    Tem que dizer o que REALMENTE aconteceu naquela run.

O caso concreto que existe hoje: `RAG_BACKEND=embed` pede recall semântico, mas
se o Qdrant está fora, `_embed_recall_chunks` devolve `[]`, a fusão RRF nem
roda, e o ranking sai puramente faceted. Configuração e execução divergem, e a
trace tem que registrar as DUAS:

    backend_requested   = "embed"
    backend_actual      = "faceted"
    fallback_triggered  = True
    fallback_reason     = "Qdrant off (InfraUnavailable) -> faceted"
    resulting_taxonomy  = FACETED_STRUCTURED_RAG      <- DERIVADO, não declarado

`taxonomy` é uma property calculada por `classify_retrieval()` sobre os campos
REAIS. Não existe setter: é impossível carimbar um rótulo que a execução não
sustenta.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.observability.taxonomy import IndexKind, RetrievalKind, classify_retrieval, is_rag

# Contagem que o sistema não expõe naquele caminho. Distinto de 0 (que é uma
# medição: "buscou e não veio nada") e de None num campo opcional qualquer.
NOT_INSTRUMENTED = "NOT_INSTRUMENTED"


@dataclass
class RetrievalOutcome:
    """Uma operação de retrieval, como ela de fato ocorreu.

    Campos de INTENÇÃO: `backend_requested`, `top_k`, `threshold`.
    Campos de EXECUÇÃO: `backend_actual`, `*_count`, `latency_ms`, `fallback_*`.
    O rótulo taxonômico é derivado dos de execução.
    """

    retriever: str
    index: IndexKind = IndexKind.NONE

    # intenção / configuração
    backend_requested: str | None = None
    top_k: int | None = None
    threshold: float | None = None
    embedding_model: str | None = None

    # execução
    backend_actual: str | None = None
    collection: str | None = None
    fallback_triggered: bool = False
    fallback_reason: str | None = None
    fusion_strategy: str | None = None
    retrievers_fused: int = 1
    candidates_count: int | None = None
    retrieved_count: int | None = None
    selected_count: int | None = None
    rejected_count: int | None = None
    latency_ms: float | None = None

    # o que aconteceu com o resultado — decide RAG vs RETRIEVAL_ONLY
    dynamic_query: bool = True
    augments_context: bool = False
    feeds_generation: bool = False

    # hash/tamanho da query; NUNCA o texto (§6.4 — payload leve)
    query_chars: int | None = None
    query_hash: str | None = None

    @property
    def taxonomy(self) -> RetrievalKind:
        """Derivado dos campos de EXECUÇÃO. Sem setter, de propósito."""
        return classify_retrieval(
            dynamic_query=self.dynamic_query,
            index=self.index,
            retrievers_fused=self.retrievers_fused,
            augments_context=self.augments_context,
            feeds_generation=self.feeds_generation,
        )

    @property
    def is_rag(self) -> bool:
        return is_rag(self.taxonomy)

    @property
    def intent_matched_execution(self) -> bool:
        """False quando configuração e execução divergiram nesta run."""
        if self.backend_requested is None or self.backend_actual is None:
            return True
        return self.backend_requested == self.backend_actual and not self.fallback_triggered

    def to_meta(self) -> dict[str, Any]:
        """Payload do evento. Só id, número e enum — nunca query nem chunk."""
        meta: dict[str, Any] = {
            "retriever": self.retriever,
            "indexKind": self.index.value,
            "backendRequested": self.backend_requested,
            "backendActual": self.backend_actual,
            "fallbackTriggered": self.fallback_triggered,
            "resultingTaxonomy": self.taxonomy.value,
            "isRag": self.is_rag,
            "intentMatchedExecution": self.intent_matched_execution,
            "retrieversFused": self.retrievers_fused,
        }
        for key, value in (
            ("collection", self.collection),
            ("topK", self.top_k),
            ("threshold", self.threshold),
            ("embedModel", self.embedding_model),
            ("fusionStrategy", self.fusion_strategy),
            ("fallbackReason", self.fallback_reason),
            ("candidatesCount", self.candidates_count),
            ("nRetrieved", self.retrieved_count),
            ("nSelected", self.selected_count),
            ("nRejected", self.rejected_count),
            ("queryChars", self.query_chars),
            ("queryHash", self.query_hash),
        ):
            if value is not None:
                meta[key] = value
        if self.latency_ms is not None:
            meta["latencyMs"] = round(self.latency_ms, 3)
        return meta


# ---------------------------------------------------------------------------
# proveniência da fusão
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FusionMember:
    """Um retriever que produziu este item, e em que rank ele o produziu."""

    retriever: str
    rank: int          # 1-based, na lista daquele retriever


@dataclass(frozen=True)
class FusionEntry:
    """Um item do resultado fundido, com de onde veio.

    Responde as quatro perguntas do Inspector:
      "veio de qual retriever?"      -> [m.retriever for m in members]
      "apareceu em mais de um?"      -> len(members) > 1
      "qual era o rank original?"    -> m.rank
      "qual o rank depois da fusão?" -> rank_after
    """

    key: str                                  # chave do join (source_path / chunk_id)
    members: tuple[FusionMember, ...]
    rank_after: int                           # 1-based, na lista fundida
    score: float | None = None

    @property
    def in_multiple(self) -> bool:
        return len(self.members) > 1

    @property
    def rank_delta(self) -> int | None:
        """Quantas posições o item subiu (positivo) pela fusão, vs o melhor
        rank de origem. None se não dá pra comparar."""
        if not self.members:
            return None
        return min(m.rank for m in self.members) - self.rank_after


@dataclass(frozen=True)
class FusionTrace:
    strategy: str
    inputs: tuple[str, ...]                   # nomes dos retrievers de entrada
    entries: tuple[FusionEntry, ...]
    k: int | None = None

    @property
    def n_in_multiple(self) -> int:
        return sum(1 for e in self.entries if e.in_multiple)

    @property
    def n_promoted(self) -> int:
        """Itens que a fusão fez subir de posição."""
        return sum(1 for e in self.entries if (e.rank_delta or 0) > 0)

    def to_meta(self, *, limit: int = 24) -> dict[str, Any]:
        """Compacto por design: chaves curtas, teto de itens.

        A proveniência COMPLETA vive neste objeto; o evento leva um resumo
        + os `limit` primeiros. O contrato de dados comporta o detalhe todo
        (a Fase 4 serve isso sob demanda), o stream principal não carrega.
        """
        return {
            "fusionStrategy": self.strategy,
            "fusionK": self.k,
            "inputs": list(self.inputs),
            "retrieversFused": len(self.inputs),
            "counts": {"entries": len(self.entries),
                       "inMultiple": self.n_in_multiple,
                       "promoted": self.n_promoted},
            "provenance": [
                {"key": e.key,
                 "from": [m.retriever for m in e.members],
                 "ranksBefore": {m.retriever: m.rank for m in e.members},
                 "rankAfter": e.rank_after}
                for e in self.entries[:limit]
            ],
            "truncated": len(self.entries) > limit,
        }


def observe_fusion(*, strategy: str, ranked_inputs: dict[str, list[str]],
                   fused: list[str], k: int | None = None) -> FusionTrace:
    """Deriva a proveniência COMPARANDO entrada e saída — sem tocar no fusor.

    `_rrf_fuse` continua exatamente como está: recebe duas rank-lists, devolve
    uma. A proveniência é observada de fora (quem produziu cada chave, em que
    rank, e onde ela caiu depois). Observar em vez de instrumentar por dentro é
    o que mantém a regra "observability describes execution, not changes it".

    ranked_inputs: {nome_do_retriever: [chave em ordem de rank]}
    fused:         [chave em ordem final]
    """
    positions: dict[str, list[FusionMember]] = {}
    for retriever, keys in ranked_inputs.items():
        for i, key in enumerate(keys):
            positions.setdefault(key, []).append(
                FusionMember(retriever=retriever, rank=i + 1))

    entries = tuple(
        FusionEntry(key=key,
                    members=tuple(positions.get(key, ())),
                    rank_after=i + 1)
        for i, key in enumerate(fused)
    )
    return FusionTrace(strategy=strategy, inputs=tuple(ranked_inputs),
                       entries=entries, k=k)


# ---------------------------------------------------------------------------
# chunk — evento leve
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChunkRef:
    """Referência a um chunk. O CONTEÚDO nunca entra aqui.

    O contrato deliberadamente não tem campo `text`: recuperar o corpo é papel
    da rota sob demanda da Fase 4, a partir de `chunk_id` + `source`.
    """

    chunk_id: str
    source: str | None = None
    rank: int | None = None
    score: float | None = None
    selected: bool | None = None
    rejection_reason: str | None = None
    source_type: str | None = None
    chars: int | None = None

    def to_meta(self) -> dict[str, Any]:
        meta: dict[str, Any] = {"chunkId": self.chunk_id}
        for key, value in (("source", self.source), ("rank", self.rank),
                           ("score", self.score), ("selected", self.selected),
                           ("reason", self.rejection_reason),
                           ("sourceType", self.source_type), ("chars", self.chars)):
            if value is not None:
                meta[key] = value
        return meta


@dataclass
class ChunkLedger:
    """Acumula chunks de um retrieval e conta selecionados/rejeitados.

    Existe porque hoje o rejeitado é PERDIDO no ato — `search_preferences` faz
    `[r for r in result if r.score > 0.3]` numa list-comp e o descartado some.
    O ledger observa a mesma lista antes do corte, sem mudar o corte.
    """

    chunks: list[ChunkRef] = field(default_factory=list)

    def add(self, chunk: ChunkRef) -> ChunkRef:
        self.chunks.append(chunk)
        return chunk

    @property
    def selected(self) -> list[ChunkRef]:
        return [c for c in self.chunks if c.selected]

    @property
    def rejected(self) -> list[ChunkRef]:
        return [c for c in self.chunks if c.selected is False]

    def apply_to(self, outcome: RetrievalOutcome) -> RetrievalOutcome:
        outcome.retrieved_count = len(self.chunks)
        outcome.selected_count = len(self.selected)
        outcome.rejected_count = len(self.rejected)
        return outcome
