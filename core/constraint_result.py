"""constraint_result.py — veredito tipado de uma regra espacial (FP-054 F1, BLOCO 4).

Um gate que nao conseguiu medir nao pode responder PASS. Cada regra devolve um `ConstraintResult` com o status, o codigo do
motivo e, quando mediu, a medida, o limiar e a unidade; quando nao mediu, o porque (`evidence["why"]`). O construtor recusa
um resultado sem essas pecas — a falta vira erro de programacao, nao um PASS silencioso.

Status:
  PASS                  mediu e cumpre o limiar
  FAIL                  mediu e viola o limiar
  WARN                  mediu; passa, mas com ressalva declarada (ex.: gargalo herdado do shell)
  BLOCKED_MISSING_INPUT faltou entrada obrigatoria (portal, semantica, geometria) — fail-closed, nunca vira PASS
  NOT_APPLICABLE        a regra nao se aplica a esta cena, por motivo declarado (ex.: comodo de portal unico)

`combine` resume varias regras: FAIL > BLOCKED_MISSING_INPUT > PASS (inclui WARN) > NOT_APPLICABLE. So da PASS se ao menos
uma regra mediu e nenhuma falhou ou ficou bloqueada; so N/A se nenhuma se aplicou.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Status = Literal["PASS", "FAIL", "WARN", "BLOCKED_MISSING_INPUT", "NOT_APPLICABLE"]
STATUSES: tuple[str, ...] = ("PASS", "FAIL", "WARN", "BLOCKED_MISSING_INPUT", "NOT_APPLICABLE")
MEASURED = ("PASS", "FAIL", "WARN")


@dataclass(frozen=True)
class ConstraintResult:
    rule_id: str
    status: Status
    reason_code: str
    measured: float | None = None
    threshold: float | None = None
    units: str | None = None
    evidence: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(f"{self.rule_id}: status desconhecido {self.status!r}")
        if not self.reason_code:
            raise ValueError(f"{self.rule_id}: reason_code obrigatorio")
        if self.status in MEASURED and (self.measured is None or self.threshold is None or not self.units):
            raise ValueError(f"{self.rule_id}: {self.status} exige measured, threshold e units")
        if self.status not in MEASURED and not self.evidence.get("why"):
            raise ValueError(f"{self.rule_id}: {self.status} exige evidence['why'] (por que nao mediu)")

    def to_dict(self) -> dict:
        return {"rule_id": self.rule_id, "status": self.status, "reason_code": self.reason_code,
                "measured": self.measured, "threshold": self.threshold, "units": self.units, "evidence": self.evidence}


def combine(statuses) -> Status:
    """Status agregado de varias regras (ver docstring do modulo). Lista vazia = NOT_APPLICABLE."""
    s = set(statuses)
    unknown = s - set(STATUSES)
    if unknown:
        raise ValueError(f"status desconhecido: {sorted(unknown)}")
    if "FAIL" in s:
        return "FAIL"
    if "BLOCKED_MISSING_INPUT" in s:
        return "BLOCKED_MISSING_INPUT"
    if s & {"PASS", "WARN"}:
        return "PASS"
    return "NOT_APPLICABLE"
