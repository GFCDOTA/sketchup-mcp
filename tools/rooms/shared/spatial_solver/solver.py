"""Solver espacial (FP-054 F2C/F2D): valida a entrada, enumera as alternativas do DOF declarado, avalia cada uma com o motor de
restricoes rigidas (F2B) e decide o estado. NUNCA altera a planta: trabalha em copias das caixas.

Estados: INVALID_INPUT (contrato) · FEASIBLE (ha alternativa sem violacao rigida) · INFEASIBLE (TODO o espaco declarado foi
avaliado e todas violam algo rigido — vale so para essa discretizacao) · UNKNOWN (orcamento acabou sem achar viavel).
Desempenho: avaliacao com as caixas na vizinhanca do comodo (celula + 1 m), equivalencia com a lista completa testada.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from tools.rooms.shared.spatial_solver.candidates import (
    Candidate,
    apply_candidate,
    enumerate_candidates,
)
from tools.rooms.shared.spatial_solver.contracts import SolverProblem, validate_problem
from tools.rooms.shared.spatial_solver.engine import evaluate_layout

DEFAULT_MAX_CANDIDATES = 5000
NEIGHBORHOOD_IN = 39.37


@dataclass
class CandidateResult:
    candidate: Candidate
    feasible: bool
    hard_violations: list[dict]
    metrics: dict
    evaluation: dict = field(default_factory=dict)

    def to_dict(self, with_rows: bool = False) -> dict:
        out = {**self.candidate.to_dict(), "feasible": self.feasible, "hard_violations": self.hard_violations,
               "metrics": self.metrics}
        if with_rows:
            out["evaluation"] = self.evaluation
        return out


@dataclass
class SolveResult:
    room_id: str
    status: str
    issues: list[dict]
    total_candidates: int
    evaluated: int
    original: CandidateResult | None
    results: list[CandidateResult]
    algorithm_version: str
    policy_version: str
    notes: list[str] = field(default_factory=list)

    @property
    def feasible(self) -> list[CandidateResult]:
        return [r for r in self.results if r.feasible]


def neighborhood(con, boxes, room_id):
    from shapely.geometry import Polygon

    from core.scale import PT_TO_IN
    from tools.spatial_model import build_spatial_model
    from tools.validation.circulation_gate import _footprint
    cell = Polygon([(x * PT_TO_IN, y * PT_TO_IN) for x, y in build_spatial_model(con, room_id)["_geom"]["cell"].exterior.coords])
    zone = cell.buffer(NEIGHBORHOOD_IN)
    return [b for b in boxes if b.get("corners") and _footprint(b).intersects(zone)]


def solve(problem: SolverProblem, con: dict, boxes: list[dict], interfaces: dict, room_name: str,
          max_candidates: int = DEFAULT_MAX_CANDIDATES) -> SolveResult:
    issues = [i.to_dict() for i in validate_problem(problem)]
    if issues:
        return SolveResult(problem.room_id, "INVALID_INPUT", issues, 0, 0, None, [], problem.algorithm_version,
                           problem.policy_version)
    local = neighborhood(con, boxes, problem.room_id)
    cands = enumerate_candidates(problem)
    results: list[CandidateResult] = []
    for cand in cands[:max_candidates]:
        try:
            b2, i2 = apply_candidate(problem, local, interfaces, cand, room_name)
        except ValueError as exc:                           # transformacao recusada: candidato invalido, nunca "meio movido"
            results.append(CandidateResult(cand, False, [{"code": "CANDIDATE_TRANSFORM_REFUSED", "detail": str(exc)}], {}))
            continue
        ev = evaluate_layout(con, b2, problem.room_id, problem.room_type, i2, room_name)
        results.append(CandidateResult(cand, ev.feasible, [v.to_dict() for v in ev.hard_violations], ev.metrics,
                                       {"rows": ev.rows}))
    original = next((r for r in results if r.candidate.candidate_id == "ORIGINAL"), None)
    if any(r.feasible for r in results):
        status = "FEASIBLE"
    elif len(results) == len(cands):
        status = "INFEASIBLE"
    else:
        status = "UNKNOWN"
    notes = [f"espaco declarado: {len(cands)} candidatos; avaliados {len(results)}"]
    if status == "INFEASIBLE":
        notes.append("INFEASIBLE vale para os graus de liberdade e a discretizacao declarados, nao para qualquer layout")
    return SolveResult(problem.room_id, status, [], len(cands), len(results), original, results, problem.algorithm_version,
                       problem.policy_version, notes)
