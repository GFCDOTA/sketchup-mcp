"""FP-054 F2C: geracao de alternativas dentro do DOF declarado e estados do solver (sinteticos)."""
from __future__ import annotations

import dataclasses

import pytest

from core.functional_constraints import FunctionalInterface
from tests.test_fp054_f1b_functional_clearance import M, _rect, _room
from tools.rooms.shared.spatial_solver.candidates import (
    Candidate,
    Move,
    apply_candidate,
    enumerate_candidates,
)
from tools.rooms.shared.spatial_solver.problem import build_problem
from tools.rooms.shared.spatial_solver.solver import neighborhood, solve

ROOM = "SINTETICO"


def _r(*a, **k):
    return {**_rect(*a, **k), "room": ROOM}


def _scene(obstacle=True):
    con, b = _room()
    x0, y0, x1, y1 = b
    cy = (y0 + y1) / 2
    fx = x1 - 0.65 * M
    vaso = _r("Vaso", "vaso", fx, cy - 0.18 * M, x1, cy + 0.18 * M)
    iface = FunctionalInterface("r_syn", "Vaso", "toilet", "use_face", ((fx, cy - 0.18 * M), (fx, cy + 0.18 * M)), (-1.0, 0.0),
                                "SEMANTIC_DECLARED", "teste")
    boxes = [vaso]
    if obstacle:                                           # armario a 0,30 m da frente, cobrindo so a metade sul
        ox = fx - 0.30 * M
        boxes.append(_r("Armario", "body", ox - 0.40 * M, y0, ox, cy + 0.05 * M, h=80))
    return con, boxes, {("r_syn", "Vaso"): iface}


def _solve(con, boxes, ifaces, **kw):
    p = build_problem(con, boxes, "r_syn", "BATHROOM", ifaces)
    return p, solve(p, con, boxes, ifaces, ROOM, **kw)


def test_enumeration_is_deterministic_and_starts_with_original():
    con, boxes, ifaces = _scene()
    p = build_problem(con, boxes, "r_syn", "BATHROOM", ifaces)
    a, b = enumerate_candidates(p), enumerate_candidates(p)
    assert [c.candidate_id for c in a] == [c.candidate_id for c in b]
    assert a[0].candidate_id == "ORIGINAL" and len(a) == 41
    assert [c.displacement_m for c in a] == sorted(c.displacement_m for c in a)


def test_slide_along_wall_clears_the_obstacle_and_is_feasible():
    con, boxes, ifaces = _scene()
    _p, r = _solve(con, boxes, ifaces)
    assert r.original is not None and not r.original.feasible
    assert r.status == "FEASIBLE"
    ok = {x.candidate.candidate_id for x in r.feasible}
    assert all(cid.startswith("r_syn:Vaso:+") for cid in ok)      # so para o lado livre (norte)


def test_apply_candidate_does_not_mutate_inputs_and_keeps_wall_backing():
    con, boxes, ifaces = _scene()
    p = build_problem(con, boxes, "r_syn", "BATHROOM", ifaces)
    snap = [dict(b, corners=[list(c) for c in b["corners"]]) for b in boxes]
    oid = p.objects[0].object_id
    nb, ni = apply_candidate(p, boxes, ifaces, Candidate("t", (Move(oid, 0.20),)), ROOM)
    assert boxes == snap
    assert nb[0]["x1"] == pytest.approx(boxes[0]["corners"][1][0])          # continua encostado na mesma parede
    assert nb[0]["y0"] - min(c[1] for c in boxes[0]["corners"]) == pytest.approx(0.20 * M, abs=1e-3)
    assert ni[("r_syn", "Vaso")].normal == (-1.0, 0.0)


def test_rotation_turns_the_interface_normal():
    con, boxes, ifaces = _scene(obstacle=False)
    p = build_problem(con, boxes, "r_syn", "BATHROOM", ifaces)
    _nb, ni = apply_candidate(p, boxes, ifaces, Candidate("t", (Move(p.objects[0].object_id, 0.0, False, 90),)), ROOM)
    assert ni[("r_syn", "Vaso")].normal == pytest.approx((0.0, -1.0))


def test_no_alternative_inside_the_declared_space_is_infeasible_not_unknown():
    con, boxes, ifaces = _scene()
    x0 = min(c[0] for c in boxes[1]["corners"])
    ys = [c[1] for c in boxes[0]["corners"]]          # armario corrido: nenhum deslize de ate 0,40 m sai da frente dele
    tall = _r("Armario", "body", x0, min(ys) - 0.9 * M, min(c[0] for c in boxes[0]["corners"]) - 0.30 * M, max(ys) + 0.9 * M, h=80)
    _p, r = _solve(con, [boxes[0], tall], ifaces)
    assert r.status == "INFEASIBLE" and r.evaluated == r.total_candidates
    assert "discretizacao" in " ".join(r.notes)


def test_budget_exhausted_without_feasible_is_unknown():
    con, boxes, ifaces = _scene()
    _p, r = _solve(con, boxes, ifaces, max_candidates=1)              # so o ORIGINAL, que falha
    assert r.status == "UNKNOWN" and r.evaluated == 1


def test_invalid_input_never_enumerates():
    con, boxes, ifaces = _scene()
    p = build_problem(con, boxes, "r_syn", "BATHROOM", ifaces)
    bad = dataclasses.replace(p, unit="ft")
    r = solve(bad, con, boxes, ifaces, ROOM)
    assert r.status == "INVALID_INPUT" and r.evaluated == 0 and r.issues


def test_profile_world_piece_is_refused_not_half_moved():
    con, boxes, ifaces = _scene()
    boxes[0]["profile_world"] = [[0, 0]]
    _p, r = _solve(con, boxes, ifaces)
    moved = [x for x in r.results if x.candidate.candidate_id != "ORIGINAL"]
    assert moved and all(x.hard_violations[0]["code"] == "CANDIDATE_TRANSFORM_REFUSED" for x in moved)


def test_neighborhood_keeps_every_piece_near_the_room():
    con, boxes, ifaces = _scene()
    far = _r("Longe", "body", 10_000, 10_000, 10_010, 10_010)
    assert neighborhood(con, [*boxes, far], "r_syn") == boxes
