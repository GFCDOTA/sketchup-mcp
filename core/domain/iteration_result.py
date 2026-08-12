"""iteration_result — contrato para o histórico machine-readable de uma
iteração de design (Princípio 5). Só o contrato + serialização nesta fase;
persistência append-only em artifacts/<project_id>/<room_id>/iterations/
é trabalho da Fase E, não desta.

Segue o padrão stdlib-only já usado em
tools/interior_studio/consult_gpt_bridge/contracts.py (validação
hand-rolled, sem dependência de jsonschema).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum


class IterationStatus(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"
    PENDING = "PENDING"


@dataclass
class Evaluation:
    score: float | None = None
    verdict: str | None = None
    strengths: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


@dataclass
class IterationResult:
    iteration_id: str
    project_id: str
    room_id: str
    timestamp: str  # ISO-8601, atribuído pelo chamador (sem Date.now aqui)
    request: str
    retrieval_snapshot: list[dict] = field(default_factory=list)
    design_changes: list[dict] = field(default_factory=list)
    gate_results: list[dict] = field(default_factory=list)
    render_artifacts: list[str] = field(default_factory=list)
    evaluation: Evaluation = field(default_factory=Evaluation)
    status: IterationStatus = IterationStatus.PENDING

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, d: dict) -> "IterationResult":
        d = dict(d)
        raw_eval = d.pop("evaluation", None) or {}
        evaluation = Evaluation(**raw_eval)
        status = IterationStatus(d.pop("status", IterationStatus.PENDING.value))
        return cls(evaluation=evaluation, status=status, **d)

    @classmethod
    def from_json(cls, text: str) -> "IterationResult":
        return cls.from_dict(json.loads(text))
