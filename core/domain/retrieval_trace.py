"""retrieval_trace — contrato de observabilidade mínima por execução
RAG/LLM (Princípio 8). Só o contrato + serialização nesta fase; o sink que
grava isso em .ai_bridge/traces/*.jsonl via logging estruturado é trabalho
da Fase D, não desta.

Custo é deliberadamente opcional (None) — não há informação confiável de
preço hoje (Ollama local não cobra por token); nunca inventar esse número.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field


@dataclass
class RetrievedChunk:
    chunk_id: str
    source: str
    source_type: str
    score: float
    rank: int


@dataclass
class RetrievalStage:
    chunks: list[RetrievedChunk] = field(default_factory=list)
    latency_ms: float | None = None


@dataclass
class LLMStage:
    model: str | None = None
    latency_ms: float | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


@dataclass
class ExecutionStage:
    tool_calls: list[str] = field(default_factory=list)


@dataclass
class ValidationStage:
    gates: list[dict] = field(default_factory=list)
    passed: bool | None = None


@dataclass
class EvaluationStage:
    score: float | None = None
    verdict: str | None = None


@dataclass
class RetrievalTrace:
    trace_id: str
    project_id: str
    room_id: str | None
    query: str
    retrieval: RetrievalStage = field(default_factory=RetrievalStage)
    llm: LLMStage = field(default_factory=LLMStage)
    execution: ExecutionStage = field(default_factory=ExecutionStage)
    validation: ValidationStage = field(default_factory=ValidationStage)
    evaluation: EvaluationStage = field(default_factory=EvaluationStage)
    total_latency_ms: float | None = None
    estimated_cost: float | None = None  # opcional por design, ver docstring

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, d: dict) -> "RetrievalTrace":
        d = dict(d)
        retrieval = d.pop("retrieval", None) or {}
        chunks = [RetrievedChunk(**c) for c in retrieval.get("chunks", [])]
        retrieval_stage = RetrievalStage(chunks=chunks, latency_ms=retrieval.get("latency_ms"))
        llm = LLMStage(**(d.pop("llm", None) or {}))
        execution = ExecutionStage(**(d.pop("execution", None) or {}))
        validation = ValidationStage(**(d.pop("validation", None) or {}))
        evaluation = EvaluationStage(**(d.pop("evaluation", None) or {}))
        return cls(
            retrieval=retrieval_stage, llm=llm, execution=execution,
            validation=validation, evaluation=evaluation, **d,
        )

    @classmethod
    def from_json(cls, text: str) -> "RetrievalTrace":
        return cls.from_dict(json.loads(text))
