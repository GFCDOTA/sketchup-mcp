"""FP-054 F2D: ordem lexicografica (violacao rigida nunca perde para margem), desempates, estabilidade."""
from __future__ import annotations

import random

from tests.test_fp054_f2c_candidates import _scene, _solve
from tools.rooms.shared.spatial_solver.candidates import Candidate, Move
from tools.rooms.shared.spatial_solver.ranking import rank
from tools.rooms.shared.spatial_solver.solver import CandidateResult


def _res(cid, hard=0, minm=0.1, summ=0.2, slide=0.0, rows=()):
    moves = (Move("r:X", slide),) if slide else ()
    return CandidateResult(Candidate(cid, moves), hard == 0, [{"code": "C"}] * hard,
                           {"hard_violations": hard, "min_margin_m": minm, "sum_margin_m": summ},
                           {"rows": [{"verdict": v} for v in rows]})


def test_hard_violation_never_wins_by_margin():
    order = [r.result.candidate.candidate_id for r in rank([_res("huge_margin", hard=1, minm=9.0, summ=99.0),
                                                            _res("tight", minm=0.001)])]
    assert order == ["tight", "huge_margin"]


def test_fewer_violations_rank_first_among_infeasible():
    order = [r.result.candidate.candidate_id for r in rank([_res("two", hard=2, minm=5), _res("one", hard=1, minm=-1)])]
    assert order == ["one", "two"]


def test_below_target_rule_counts_before_margin():
    a = _res("below", minm=0.9, rows=("VALID_BELOW_TARGET",))
    b = _res("target", minm=0.05, rows=("VALID",))
    assert [r.result.candidate.candidate_id for r in rank([a, b])] == ["target", "below"]


def test_tie_on_quality_prefers_smaller_intervention_then_id():
    r = rank([_res("b", slide=0.2), _res("a", slide=0.2), _res("ORIGINAL"), _res("c", slide=0.1)])
    assert [x.result.candidate.candidate_id for x in r] == ["ORIGINAL", "c", "a", "b"]
    assert "displacement_m" in r[2].explanation and "candidate_id" in r[3].explanation


def test_missing_margin_ranks_last_within_equal_violations():
    r = rank([_res("none", minm=None, summ=None), _res("some", minm=0.0)])
    assert r[0].result.candidate.candidate_id == "some"


def test_ranking_is_independent_of_input_order():
    items = [_res(f"k{i}", hard=i % 3, minm=(i * 7 % 5) / 10, slide=(i % 4) / 10) for i in range(30)]
    base = [x.result.candidate.candidate_id for x in rank(items)]
    rnd = random.Random(54)
    for _ in range(5):
        rnd.shuffle(items)
        assert [x.result.candidate.candidate_id for x in rank(items)] == base


def test_synthetic_solve_ranks_a_feasible_slide_first_and_is_reproducible():
    con, boxes, ifaces = _scene()
    _p, r1 = _solve(con, boxes, ifaces)
    _p, r2 = _solve(con, boxes, ifaces)
    a, b = rank(r1.results), rank(r2.results)
    assert [x.to_dict() for x in a] == [x.to_dict() for x in b]
    assert a[0].result.feasible and a[0].result.candidate.candidate_id != "ORIGINAL"
    best = max(x.metrics["min_margin_m"] for x in r1.feasible)     # margem decide antes do deslocamento
    assert a[0].result.metrics["min_margin_m"] == best
    tied = [x for x in r1.feasible if x.metrics["min_margin_m"] == best]
    assert a[0].result.candidate.displacement_m == min(x.candidate.displacement_m for x in tied) or len(tied) == 1
