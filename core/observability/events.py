"""events — o envelope v1 e o catálogo de nomes de evento.

Um envelope só, versionado, para RAG, LLM, harness, tool, gate e SketchUp. O
consumidor (grafo, trace tree, replay) nunca precisa saber de qual módulo o
evento veio — só da `category`, do `status` e do par `spanId`/`parentSpanId`.

REGRA DE PESO (§6.4 da spec): `meta` carrega ID e número, nunca corpo. Texto de
chunk, prompt montado e resposta do modelo ficam fora do evento e são buscados
sob demanda. Um `rag.chunk.retrieved` com o texto do chunk dentro transformaria
um retrieval de 12 chunks em ~30 KB de evento e derrubaria a memória do browser
num replay longo — que é exatamente a carroça que a spec proíbe.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from core.observability.taxonomy import Category

SCHEMA_VERSION = 1


class Status(str, Enum):
    STARTED = "started"
    OK = "ok"
    FAILED = "failed"
    SKIPPED = "skipped"
    DEGRADED = "degraded"   # rodou, mas em modo reduzido (infra off, fallback)


# ---------------------------------------------------------------------------
# catálogo de nomes — fechado de propósito
#
# Nome fora do catálogo levanta erro em vez de virar um evento órfão que a UI
# não sabe desenhar. Adicionar evento é um ato deliberado, não um typo.
# ---------------------------------------------------------------------------

RUN_EVENTS = (
    "run.started", "run.finished", "run.failed", "run.canceled",
)
HARNESS_EVENTS = (
    "harness.started", "harness.finished",
    "harness.cycle.started", "harness.cycle.finished",
    # as quatro fases do correction_loop, nomeadas — são elas que mostram o
    # APPLICATION HARNESS trabalhando (distinto do runtime de agente externo)
    "harness.detect", "harness.classify", "harness.fix", "harness.recheck",
    "harness.terminal",
    "agent.retry", "agent.correction",
)
RAG_EVENTS = (
    "rag.query.started", "rag.query.finished",
    "rag.embedding.started", "rag.embedding.finished",
    "rag.retrieval.started", "rag.retrieval.finished",
    "rag.chunk.retrieved", "rag.chunk.selected", "rag.chunk.rejected",
    "rag.fusion.finished",
    "rag.freshness.filtered",
    "rag.degraded",
)
CONTEXT_EVENTS = (
    "context.build.started", "context.build.finished",
)
LLM_EVENTS = (
    "llm.started", "llm.first_token", "llm.finished", "llm.failed",
)
TOOL_EVENTS = (
    "tool.started", "tool.finished", "tool.failed",
)
SKETCHUP_EVENTS = (
    "sketchup.command.started", "sketchup.command.finished",
)
GATE_EVENTS = (
    "gate.started", "gate.passed", "gate.failed",
    "gate.skipped", "gate.incomplete", "gate.measurement",
)

EVENT_NAMES: frozenset[str] = frozenset(
    RUN_EVENTS + HARNESS_EVENTS + RAG_EVENTS + CONTEXT_EVENTS
    + LLM_EVENTS + TOOL_EVENTS + SKETCHUP_EVENTS + GATE_EVENTS
)

# Categoria default por prefixo. O emissor pode sobrescrever (um `tool.*` que é
# na verdade uma chamada de banco, p.ex.), mas o default cobre o caso comum e
# evita que cada call-site repita a classificação — e divirja.
_PREFIX_CATEGORY: tuple[tuple[str, Category], ...] = (
    ("rag.", Category.RAG),
    ("llm.", Category.LLM),
    ("tool.", Category.TOOL),
    ("gate.", Category.DETERMINISTIC),
    ("sketchup.", Category.TOOL),
    ("context.", Category.HARNESS),
    ("harness.", Category.HARNESS),
    ("agent.", Category.HARNESS),
    ("run.", Category.OBSERVABILITY),
)


def default_category(name: str) -> Category:
    for prefix, cat in _PREFIX_CATEGORY:
        if name.startswith(prefix):
            return cat
    raise ValueError(f"sem categoria default para evento {name!r}")


class UnknownEventName(ValueError):
    """Nome fora do catálogo — provavelmente typo, nunca vira evento."""


@dataclass(frozen=True)
class Event:
    """Envelope v1. `seq` ordena; `ts` só informa."""

    name: str
    run_id: str
    trace_id: str
    seq: int
    ts: str
    category: Category
    status: Status
    component: str
    span_id: str | None = None
    parent_span_id: str | None = None
    duration_ms: float | None = None
    meta: dict[str, Any] = field(default_factory=dict)
    v: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.name not in EVENT_NAMES:
            raise UnknownEventName(
                f"{self.name!r} não está no catálogo de events.py. "
                "Adicione ao catálogo de propósito, ou corrija o nome."
            )

    def to_dict(self) -> dict[str, Any]:
        """Chaves em camelCase — é o que a UI consome; o Python fica snake_case."""
        d: dict[str, Any] = {
            "v": self.v,
            "runId": self.run_id,
            "traceId": self.trace_id,
            "spanId": self.span_id,
            "parentSpanId": self.parent_span_id,
            "seq": self.seq,
            "ts": self.ts,
            "durationMs": self.duration_ms,
            "component": self.component,
            "category": self.category.value,
            "status": self.status.value,
            "name": self.name,
            "meta": self.meta,
        }
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Event":
        return cls(
            name=d["name"],
            run_id=d["runId"],
            trace_id=d["traceId"],
            seq=int(d["seq"]),
            ts=d["ts"],
            category=Category(d["category"]),
            status=Status(d["status"]),
            component=d["component"],
            span_id=d.get("spanId"),
            parent_span_id=d.get("parentSpanId"),
            duration_ms=d.get("durationMs"),
            meta=d.get("meta") or {},
            v=int(d.get("v", SCHEMA_VERSION)),
        )


# ---------------------------------------------------------------------------
# eventos incompletos — reconhecer sem inventar
# ---------------------------------------------------------------------------

_REQUIRED = ("name", "runId", "traceId", "seq", "ts", "category", "status", "component")


def is_well_formed(row: dict[str, Any]) -> bool:
    """True se a linha tem o mínimo pra ser posicionada num trace.

    Um trace pode ser lido no meio de uma escrita (o sink é append-only e
    lido por outro processo). Linha torta é DESCARTADA e CONTADA, nunca
    completada com default — um `status` inventado viraria um nó verde que
    ninguém executou.
    """
    if not isinstance(row, dict):
        return False
    if any(row.get(k) in (None, "") for k in _REQUIRED):
        return False
    if row.get("name") not in EVENT_NAMES:
        return False
    try:
        Category(row["category"])
        Status(row["status"])
        int(row["seq"])
    except (ValueError, TypeError, KeyError):
        return False
    return True
