"""FP-054 F2A: unidades e frames explicitos, contrato de entrada do solver com erros estruturados, problemas reais (read-only)."""
from __future__ import annotations

import contextlib
import dataclasses
import io
import json
import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from core.frames import RoomFrame
from core.functional_constraints import FunctionalInterface
from core.units import pt_to, to_pt, to_unit
from tools.rooms.shared.spatial_solver.contracts import (
    DegreesOfFreedom,
    Portal,
    SolverObject,
    SolverProblem,
    validate_problem,
)


# --------------------------------------------------------------------------------------------------- unidades
@pytest.mark.parametrize("v,a,b,exp", [(1, "m", "cm", 100), (1, "in", "m", 0.0254), (254, "mm", "in", 10), (0.9, "m", "in", 35.43307)])
def test_unit_conversion_is_explicit(v, a, b, exp):
    assert to_unit(v, a, b) == pytest.approx(exp, rel=1e-6)


def test_unknown_unit_and_implicit_points_are_refused():
    with pytest.raises(ValueError):
        to_unit(1, "pt", "m")                       # pt depende da escala da planta: so via pt_to
    with pytest.raises(ValueError):
        to_unit(1, "ft", "m")
    with pytest.raises(ValueError):
        pt_to(1, "m", pt_to_m=0)
    assert pt_to(100, "m", pt_to_m=0.0259) == pytest.approx(2.59)
    assert to_pt(pt_to(37.0, "in", pt_to_m=0.0259), "in", pt_to_m=0.0259) == pytest.approx(37.0)


# ----------------------------------------------------------------------------------------------------- frames
@settings(max_examples=40, deadline=None, derandomize=True)
@given(st.floats(-500, 500), st.floats(-500, 500), st.floats(-math.pi, math.pi), st.floats(-100, 100), st.floats(-100, 100))
def test_frame_round_trip_and_rigidity(ox, oy, rot, px, py):
    f = RoomFrame("r", (ox, oy), rot)
    g = f.to_plant((px, py))
    back = f.to_local(g)
    assert back[0] == pytest.approx(px, abs=1e-6) and back[1] == pytest.approx(py, abs=1e-6)
    a, b = f.to_plant((0.0, 0.0)), f.to_plant((px, py))
    assert math.dist(a, b) == pytest.approx(math.hypot(px, py), abs=1e-6)


def test_frame_refuses_other_units():
    with pytest.raises(ValueError):
        RoomFrame("r", (0, 0), 0, unit="m")


# ------------------------------------------------------------------------------------------------- contrato
SQ = ((0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0))
TOILET_FP = ((70.0, 40.0), (100.0, 40.0), (100.0, 55.0), (70.0, 55.0))
DOF = DegreesOfFreedom((-0.4, 0.4), 0.02, False, "PROJECT_POLICY", "teste")


def _iface(basis="SEMANTIC_DECLARED", seg=((70.0, 40.0), (70.0, 55.0))):
    return FunctionalInterface("r", "Vaso", "toilet", "use_face", seg, (-1.0, 0.0), basis, "teste")


def _obj(**over):
    base = dict(object_id="r:Vaso", room_id="r", module="Vaso", object_type="toilet", footprint_in=TOILET_FP,
                interfaces=(_iface(),), anchor="WALL_BACKED", dof=DOF)
    base.update(over)
    return SolverObject(**base)


def _problem(**over):
    base = dict(room_id="r", room_type="BATHROOM", frame=RoomFrame("r", (0.0, 0.0)), room_polygon_in=SQ,
                portals=(Portal("r:p0", (5.0, 50.0)),), objects=(_obj(),))
    base.update(over)
    return SolverProblem(**base)


def _codes(p):
    return sorted(i.code for i in validate_problem(p))


def test_valid_problem_has_no_issues():
    assert validate_problem(_problem()) == []


@pytest.mark.parametrize("over,code", [
    ({"portals": ()}, "NO_PORTAL"),
    ({"room_polygon_in": ((0, 0), (1, 1), (2, 2))}, "ROOM_GEOMETRY_INVALID"),
    ({"unit": "m"}, "UNIT_INVALID"),
    ({"objects": (_obj(), _obj())}, "OBJECT_ID_DUPLICATED"),
    ({"objects": (_obj(interfaces=()),)}, "MISSING_SEMANTIC_INTERFACE"),
    ({"objects": (_obj(interfaces=(_iface("HEURISTIC_GEOMETRY"),)),)}, "HEURISTIC_INTERFACE_REJECTED"),
    ({"objects": (_obj(interfaces=(_iface(seg=((10.0, 10.0), (10.0, 20.0))),)),)}, "INTERFACE_GEOMETRY_MISMATCH"),
    ({"objects": (_obj(footprint_in=((150, 150), (180, 150), (180, 170), (150, 170))),)}, "OUTSIDE_ROOM"),
    ({"objects": (_obj(footprint_in=((0, 0), (1, 0), (2, 0))),)}, "FOOTPRINT_INVALID"),
    ({"objects": (_obj(object_type="sofa"),)}, "OBJECT_TYPE_UNKNOWN"),
    ({"objects": (_obj(anchor="FLOATING"),)}, "ANCHOR_UNKNOWN"),
    ({"objects": (_obj(dof=DegreesOfFreedom((0.4, -0.4), 0.02, False, "PROJECT_POLICY", "x")),)}, "DOF_INVALID"),
    ({"objects": (_obj(dof=DegreesOfFreedom((0, 0), 0.02, False, "PROJECT_POLICY", "")),)}, "DOF_INVALID"),
])
def test_each_contract_violation_is_a_structured_error(over, code):
    assert code in _codes(_problem(**over))


def test_dof_enumeration_is_explicit_and_includes_current_position():
    vals = DegreesOfFreedom((-0.04, 0.05), 0.02, False, "PROJECT_POLICY", "x").slide_values()
    assert vals == [-0.04, -0.02, 0.0, 0.02, 0.04]


def test_problem_is_immutable():
    with pytest.raises(dataclasses.FrozenInstanceError):
        _problem().room_id = "x"


# ------------------------------------------------------------------------------------------------- planta real
@pytest.mark.planta74_scale
def test_real_problems_are_valid_and_read_only():
    from tools.furnish_apartment import CONSENSUS, collect_boxes
    from tools.rooms.shared.spatial_solver.problem import build_problem
    from tools.validation.functional_clearance import collect_interfaces
    con = json.loads(CONSENSUS.read_text("utf-8"))
    with contextlib.redirect_stdout(io.StringIO()):
        boxes, _ = collect_boxes(con)
        ifaces = collect_interfaces(con, boxes)
    before = json.dumps(boxes, sort_keys=True)
    got = {}
    for rid, rtype in (("r004", "KITCHEN"), ("r005", "BATHROOM"), ("r006", "BATHROOM"), ("r007", "BATHROOM")):
        p = build_problem(con, boxes, rid, rtype, ifaces)
        assert validate_problem(p) == [], (rid, [i.to_dict() for i in validate_problem(p)])
        got[rid] = sorted(o.module for o in p.objects)
    assert got == {"r004": ["countertop"], "r005": ["Bancada", "Box", "Vaso"], "r006": ["Bancada", "Box", "Vaso"],
                   "r007": ["Bancada", "Vaso"]}
    assert json.dumps(boxes, sort_keys=True) == before
