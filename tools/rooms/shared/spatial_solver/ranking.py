"""Ordenacao lexicografica das alternativas (FP-054 F2D). NUNCA soma ponderada: um criterio so desempata o anterior.

Chave, nesta ordem:
  1. viavel (zero violacao rigida) antes de inviavel;
  2. menos violacoes rigidas;
  3. menos regras abaixo do ALVO de projeto (VALID_BELOW_TARGET) — o minimo de referencia ja foi garantido por (1);
  4. maior margem minima sobre o minimo de referencia (a regra mais apertada);
  5. maior margem somada;
  6. menos objetos movidos, menor deslocamento, menos giros/reflexoes (menor intervencao na planta);
  7. identificador do candidato (desempate deterministico).
Margem nunca compensa violacao: (1)/(2) vem antes de qualquer margem. Entre inviaveis a ordem diz so "o mais proximo",
nunca "uma solucao".
"""
from __future__ import annotations

from dataclasses import dataclass

from tools.rooms.shared.spatial_solver.solver import CandidateResult

CRITERIA = ("feasible", "hard_violations", "below_target", "min_margin_m", "sum_margin_m", "moved", "displacement_m",
            "turns", "candidate_id")


@dataclass(frozen=True)
class RankedCandidate:
    rank: int
    result: CandidateResult
    key: tuple
    explanation: str

    def to_dict(self) -> dict:
        return {"rank": self.rank, **self.result.to_dict(), "key": dict(zip(CRITERIA, self.key)),
                "explanation": self.explanation}


def _below_target(r: CandidateResult) -> int:
    return sum(1 for row in r.evaluation.get("rows", []) if row.get("verdict") == "VALID_BELOW_TARGET")


def rank_key(r: CandidateResult) -> tuple:
    m, c = r.metrics or {}, r.candidate
    neg = float("inf")
    return (not r.feasible, len(r.hard_violations), _below_target(r),
            -(m.get("min_margin_m") if m.get("min_margin_m") is not None else -neg),
            -(m.get("sum_margin_m") if m.get("sum_margin_m") is not None else -neg),
            len(c.moved), c.displacement_m, sum(bool(x.mirrored) + bool(x.rotation_deg % 360) for x in c.moves),
            c.candidate_id)


def _explain(prev: tuple | None, key: tuple, r: CandidateResult) -> str:
    head = ("viavel" if r.feasible else f"INVIAVEL ({len(r.hard_violations)} violacao(oes) rigida(s): "
            + ", ".join(sorted({v['code'] for v in r.hard_violations})) + ")")
    if prev is None:
        return head + "; primeira da ordem"
    i = next((k for k, (a, b) in enumerate(zip(prev, key)) if a != b), len(CRITERIA) - 1)
    return f"{head}; fica atras da anterior pelo criterio '{CRITERIA[i]}'"


def rank(results: list[CandidateResult]) -> list[RankedCandidate]:
    keyed = sorted(((rank_key(r), r) for r in results), key=lambda kr: kr[0])
    out, prev = [], None
    for i, (k, r) in enumerate(keyed, 1):
        out.append(RankedCandidate(i, r, k, _explain(prev, k, r)))
        prev = k
    return out
