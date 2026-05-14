"""Algorithmic-check unit tests for `tools/visual_fidelity_gate.py`
(PR B3 — the 8 failure conditions).

Each check has dedicated synthetic-consensus fixtures so the test
doesn't depend on planta_74. The planta_74 smoke check lives in
`test_visual_fidelity_gate.py::test_planta_74_end_to_end_smoke`.
"""
from __future__ import annotations

import pytest

from tools.visual_fidelity_gate import (
    EIGHT_CHECKS,
    _adjacent_room_pairs,
    _check_door_crossing_or_displaced,
    _check_door_swing_diverges,
    _check_door_without_opening,
    _check_invented_or_wrong_height_exterior,
    _check_room_polygon_bleeds_outside,
    _check_room_polygon_not_closed,
    _check_room_rendered_as_bbox,
    _check_wet_or_terrace_adjacency_wrong,
    _point_in_polygon,
    _polygon_looks_like_bbox,
    run_check,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check_def(key: str) -> dict:
    """Return the check_def dict from EIGHT_CHECKS for a given key."""
    for c in EIGHT_CHECKS:
        if c["key"] == key:
            return c
    raise KeyError(key)


def _hwall(wid: str, x0: float, y: float, x1: float,
           thickness: float = 5.4) -> dict:
    return {"id": wid, "start": [x0, y], "end": [x1, y],
            "thickness": thickness, "orientation": "h"}


def _vwall(wid: str, x: float, y0: float, y1: float,
           thickness: float = 5.4) -> dict:
    return {"id": wid, "start": [x, y0], "end": [x, y1],
            "thickness": thickness, "orientation": "v"}


def _door(oid: str, wid: str, center: tuple[float, float],
          host_mode: str = "cut_into_wall",
          kind_v5: str = "interior_door",
          hinge_side: str = "left",
          width_pts: float = 20.0,
          evidence: dict | None = None) -> dict:
    op = {
        "id": oid, "kind_v5": kind_v5, "wall_id": wid,
        "center": [center[0], center[1]],
        "opening_width_pts": width_pts,
        "host_mode": host_mode,
        "hinge_side": hinge_side,
    }
    if evidence is not None:
        op["evidence"] = evidence
    return op


def _square_room(rid: str, name: str, x0: float, y0: float,
                  x1: float, y1: float) -> dict:
    pts = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
    return {
        "id": rid, "name": name, "polygon_pts": pts,
        "area_pts2": (x1 - x0) * (y1 - y0),
        "seed_pt": [(x0 + x1) / 2, (y0 + y1) / 2],
    }


def _multi_vertex_room(rid: str, name: str) -> dict:
    """An L-shape with 6 vertices — not a bbox rectangle."""
    pts = [[0, 0], [100, 0], [100, 50], [50, 50], [50, 100], [0, 100]]
    return {"id": rid, "name": name, "polygon_pts": pts,
            "area_pts2": 7500.0, "seed_pt": [25, 25]}


def _passing_consensus() -> dict:
    """Synthetic consensus where every check should PASS."""
    return {
        "wall_thickness_pts": 5.4,
        "walls": [
            _hwall("w0", 0, 0, 200),
            _hwall("w1", 0, 100, 200),
            _vwall("w2", 0, 0, 100),
            _vwall("w3", 200, 0, 100),
            _vwall("w4", 100, 0, 100),  # internal divider
        ],
        "rooms": [
            _multi_vertex_room("r0", "SALA"),
            _multi_vertex_room("r1", "COZINHA"),
        ],
        "openings": [
            _door("o0", "w4", (100, 50)),  # cut_into_wall on w4
        ],
        "soft_barriers": [],
    }


# ---------------------------------------------------------------------------
# Check 1 — door_without_opening
# ---------------------------------------------------------------------------

def test_check1_passes_with_hosted_doors():
    res = _check_door_without_opening(
        _passing_consensus(), _check_def("door_without_opening"),
    )
    assert res["status"] == "checked"
    assert res["verdict"] == "PASS"
    assert res["failing_elements"] == []


def test_check1_fails_when_unhosted_door():
    consensus = _passing_consensus()
    consensus["openings"].append(_door("o1", "w99", (50, 50),
                                         host_mode="unhosted"))
    res = _check_door_without_opening(
        consensus, _check_def("door_without_opening"),
    )
    assert res["verdict"] == "FAIL"
    assert len(res["failing_elements"]) == 1
    assert res["failing_elements"][0]["opening_id"] == "o1"


def test_check1_fails_when_host_mode_missing():
    consensus = _passing_consensus()
    consensus["openings"].append(_door("o1", "w0", (50, 0),
                                         host_mode="missing"))
    res = _check_door_without_opening(
        consensus, _check_def("door_without_opening"),
    )
    assert res["verdict"] == "FAIL"


def test_check1_ignores_window_openings():
    """Check 1 only inspects door-type openings."""
    consensus = _passing_consensus()
    consensus["openings"].append({
        "id": "win0", "kind_v5": "window", "wall_id": None,
        "host_mode": "missing", "center": [50, 0],
    })
    res = _check_door_without_opening(
        consensus, _check_def("door_without_opening"),
    )
    assert res["verdict"] == "PASS"


# ---------------------------------------------------------------------------
# Check 2 — door_crossing_or_displaced
# ---------------------------------------------------------------------------

def test_check2_passes_when_door_on_wall_centerline():
    res = _check_door_crossing_or_displaced(
        _passing_consensus(), _check_def("door_crossing_or_displaced"),
    )
    assert res["verdict"] == "PASS"


def test_check2_fails_when_door_displaced():
    consensus = _passing_consensus()
    # wall w4 is vertical at x=100; displace door center to x=150 (50pt off)
    consensus["openings"][0]["center"] = [150.0, 50.0]
    res = _check_door_crossing_or_displaced(
        consensus, _check_def("door_crossing_or_displaced"),
    )
    assert res["verdict"] == "FAIL"
    assert res["failing_elements"][0]["opening_id"] == "o0"
    # shift_pts ≈ 50, max_tolerated_pts ≈ 5.4/2 + 1 ≈ 3.7
    assert res["failing_elements"][0]["shift_pts"] > 10


# ---------------------------------------------------------------------------
# Check 3 — door_swing_diverges
# ---------------------------------------------------------------------------

def test_check3_pass_when_arc_matches_hinge():
    consensus = _passing_consensus()
    consensus["openings"][0]["evidence"] = {
        "svg_arc": {"hinge_side": "left"},
    }
    res = _check_door_swing_diverges(
        consensus, _check_def("door_swing_diverges"),
    )
    assert res["verdict"] == "PASS"
    assert res["failing_elements"] == []


def test_check3_fail_when_arc_disagrees():
    consensus = _passing_consensus()
    consensus["openings"][0]["evidence"] = {
        "svg_arc": {"hinge_side": "right"},
    }
    res = _check_door_swing_diverges(
        consensus, _check_def("door_swing_diverges"),
    )
    assert res["verdict"] == "FAIL"
    assert res["failing_elements"][0]["opening_id"] == "o0"
    assert res["failing_elements"][0]["detected_hinge_side"] == "left"
    assert res["failing_elements"][0]["arc_hinge_side"] == "right"


def test_check3_warns_when_no_arc_evidence():
    consensus = _passing_consensus()
    # No `evidence` field on the opening at all.
    res = _check_door_swing_diverges(
        consensus, _check_def("door_swing_diverges"),
    )
    assert res["verdict"] == "WARN"
    assert res["failing_elements"][0]["reason"] == (
        "no_arc_evidence_in_consensus"
    )


# ---------------------------------------------------------------------------
# Check 4 — room_polygon_not_closed
# ---------------------------------------------------------------------------

def test_check4_passes_on_valid_polygons():
    res = _check_room_polygon_not_closed(
        _passing_consensus(), _check_def("room_polygon_not_closed"),
    )
    assert res["verdict"] == "PASS"


def test_check4_fails_on_below_3_vertices():
    consensus = _passing_consensus()
    consensus["rooms"][0]["polygon_pts"] = [[0, 0], [10, 0]]
    res = _check_room_polygon_not_closed(
        consensus, _check_def("room_polygon_not_closed"),
    )
    assert res["verdict"] == "FAIL"
    assert res["failing_elements"][0]["reason"] == "vertex_count_below_3"


def test_check4_fails_on_zero_area():
    consensus = _passing_consensus()
    # Collinear points → zero area
    consensus["rooms"][0]["polygon_pts"] = [[0, 0], [10, 0], [20, 0]]
    res = _check_room_polygon_not_closed(
        consensus, _check_def("room_polygon_not_closed"),
    )
    assert res["verdict"] == "FAIL"
    assert res["failing_elements"][0]["reason"] == "zero_area"


def test_check4_fails_on_self_intersecting():
    consensus = _passing_consensus()
    # Self-intersecting polygon with non-zero shoelace area (edge
    # 1-2 from (10,0)->(5,10) crosses edge 3-4 (horizontal at y=5)).
    consensus["rooms"][0]["polygon_pts"] = [
        [0, 0], [10, 0], [5, 10], [0, 5], [10, 5],
    ]
    res = _check_room_polygon_not_closed(
        consensus, _check_def("room_polygon_not_closed"),
    )
    assert res["verdict"] == "FAIL"
    assert res["failing_elements"][0]["reason"] == "self_intersecting"


# ---------------------------------------------------------------------------
# Check 5 — room_polygon_bleeds_outside
# ---------------------------------------------------------------------------

def test_check5_passes_when_room_inside_bbox():
    res = _check_room_polygon_bleeds_outside(
        _passing_consensus(),
        _check_def("room_polygon_bleeds_outside"),
    )
    assert res["verdict"] == "PASS"


def test_check5_fails_when_room_bleeds_outside():
    consensus = _passing_consensus()
    # Move r0 way outside the building bbox.
    consensus["rooms"][0]["polygon_pts"] = [
        [-500, -500], [-400, -500], [-400, -400], [-500, -400],
    ]
    res = _check_room_polygon_bleeds_outside(
        consensus, _check_def("room_polygon_bleeds_outside"),
    )
    assert res["verdict"] == "FAIL"
    assert res["failing_elements"][0]["room_id"] == "r0"


def test_check5_warns_when_no_walls():
    consensus = _passing_consensus()
    consensus["walls"] = []
    res = _check_room_polygon_bleeds_outside(
        consensus, _check_def("room_polygon_bleeds_outside"),
    )
    assert res["verdict"] == "WARN"


# ---------------------------------------------------------------------------
# Check 6 — invented_or_wrong_height_exterior
# ---------------------------------------------------------------------------

def test_check6_passes_with_plausible_walls():
    res = _check_invented_or_wrong_height_exterior(
        _passing_consensus(),
        _check_def("invented_or_wrong_height_exterior"),
    )
    assert res["verdict"] == "PASS"


def test_check6_fails_on_zero_length_wall():
    consensus = _passing_consensus()
    consensus["walls"].append({
        "id": "wbad", "start": [50, 50], "end": [50, 50],
        "thickness": 5.4, "orientation": "h",
    })
    res = _check_invented_or_wrong_height_exterior(
        consensus, _check_def("invented_or_wrong_height_exterior"),
    )
    assert res["verdict"] == "FAIL"
    assert any(
        "near_zero_length" in e["reasons"]
        for e in res["failing_elements"]
    )


def test_check6_fails_on_thickness_outlier():
    consensus = _passing_consensus()
    consensus["walls"].append(
        _hwall("wbad", 0, 50, 100, thickness=20.0),  # 4x default
    )
    res = _check_invented_or_wrong_height_exterior(
        consensus, _check_def("invented_or_wrong_height_exterior"),
    )
    assert res["verdict"] == "FAIL"
    bad = next(e for e in res["failing_elements"]
                if e["wall_id"] == "wbad")
    assert any("thickness_outlier" in r for r in bad["reasons"])


def test_check6_fails_on_mismatched_orientation():
    consensus = _passing_consensus()
    consensus["walls"].append({
        "id": "wbad", "start": [0, 0], "end": [100, 100],
        "thickness": 5.4, "orientation": "h",  # claims h but diagonal
    })
    res = _check_invented_or_wrong_height_exterior(
        consensus, _check_def("invented_or_wrong_height_exterior"),
    )
    assert res["verdict"] == "FAIL"


# ---------------------------------------------------------------------------
# Check 7 — wet_or_terrace_adjacency_wrong
# ---------------------------------------------------------------------------

def test_check7_no_op_when_plan_id_unregistered():
    consensus = _passing_consensus()
    res = _check_wet_or_terrace_adjacency_wrong(
        consensus, _check_def("wet_or_terrace_adjacency_wrong"),
    )
    # No plan_id → PASS with explanatory note.
    assert res["verdict"] == "PASS"
    assert "no_op" in res["notes"] or "no expected_adjacency" in res["notes"]


def test_check7_fails_when_expected_adjacency_missing():
    consensus = {
        "plan_id": "planta_74",
        "wall_thickness_pts": 5.4,
        "walls": [
            _hwall("w0", 0, 0, 200),
            _vwall("w1", 100, 0, 100),
        ],
        # SUITE 01 exists but BANHO 01 does not — adjacency fails.
        "rooms": [
            _square_room("rsuite", "SUITE 01", 0, 0, 100, 100),
            _square_room("rsala", "SALA DE JANTAR", 100, 0, 200, 100),
        ],
        "openings": [],
        "soft_barriers": [],
    }
    res = _check_wet_or_terrace_adjacency_wrong(
        consensus, _check_def("wet_or_terrace_adjacency_wrong"),
    )
    assert res["verdict"] == "FAIL"


def test_check7_passes_with_merged_cell_adjacency():
    """Merged-cell membership counts as adjacency. A merged cell of
    'SUITE 01 | BANHO 01' is enough to satisfy that pair."""
    consensus = {
        "source": "planta_74.pdf",
        "wall_thickness_pts": 5.4,
        "walls": [_hwall("w0", 0, 0, 200)],
        "rooms": [
            _square_room(
                "rmerged", "SUITE 01 | BANHO 01",
                0, 0, 100, 100,
            ),
            _square_room(
                "rmerged2", "SUITE 02 | BANHO 02",
                100, 0, 200, 100,
            ),
            _square_room("rsala", "SALA DE ESTAR", 0, 100, 200, 200),
            _square_room("rlavabo", "LAVABO", 200, 0, 300, 100),
            _square_room("ras", "A.S.", 300, 0, 400, 100),
            _square_room("rterraco", "TERRACO SOCIAL",
                          0, 200, 400, 250),
            _square_room("rcozinha", "COZINHA",
                          400, 0, 500, 100),
        ],
        "openings": [],
        "soft_barriers": [],
    }
    pairs = _adjacent_room_pairs(consensus)
    assert frozenset({"SUITE 01", "BANHO 01"}) in pairs
    assert frozenset({"SUITE 02", "BANHO 02"}) in pairs


# ---------------------------------------------------------------------------
# Check 8 — room_rendered_as_bbox
# ---------------------------------------------------------------------------

def test_check8_warns_when_too_few_walls():
    consensus = {
        "wall_thickness_pts": 5.4,
        "walls": [_hwall("w0", 0, 0, 100)],
        "rooms": [_square_room("r0", "SALA", 0, 0, 100, 100)],
        "openings": [], "soft_barriers": [],
    }
    res = _check_room_rendered_as_bbox(
        consensus, _check_def("room_rendered_as_bbox"),
    )
    assert res["verdict"] == "WARN"


def test_check8_passes_with_multi_vertex_rooms():
    res = _check_room_rendered_as_bbox(
        _passing_consensus(),
        _check_def("room_rendered_as_bbox"),
    )
    assert res["verdict"] == "PASS"


def test_check8_fails_when_room_collapsed_to_bbox():
    consensus = _passing_consensus()
    # Replace r0 with an exact bbox rectangle.
    consensus["rooms"][0] = _square_room("r0", "SALA", 10, 10, 90, 90)
    res = _check_room_rendered_as_bbox(
        consensus, _check_def("room_rendered_as_bbox"),
    )
    assert res["verdict"] == "FAIL"
    assert res["failing_elements"][0]["room_id"] == "r0"


# ---------------------------------------------------------------------------
# Geometry primitives
# ---------------------------------------------------------------------------

def test_polygon_looks_like_bbox_rejects_non_rectangle():
    """L-shape is not bbox-shaped."""
    pts = [[0, 0], [100, 0], [100, 50], [50, 50], [50, 100], [0, 100]]
    assert _polygon_looks_like_bbox(pts) is False


def test_polygon_looks_like_bbox_accepts_rectangle():
    pts = [[0, 0], [100, 0], [100, 50], [0, 50]]
    assert _polygon_looks_like_bbox(pts) is True


def test_point_in_polygon_inside_outside():
    square = [[0, 0], [10, 0], [10, 10], [0, 10]]
    assert _point_in_polygon(5, 5, square) is True
    assert _point_in_polygon(15, 15, square) is False
    assert _point_in_polygon(-1, 5, square) is False


# ---------------------------------------------------------------------------
# Adjacency probing
# ---------------------------------------------------------------------------

def test_adjacent_room_pairs_via_opening_position():
    """A vertical wall at x=100 with a door at (100, 50) connects
    the rooms on either side."""
    consensus = {
        "wall_thickness_pts": 5.4,
        "walls": [_vwall("w0", 100, 0, 100)],
        "rooms": [
            _square_room("rL", "SALA", 0, 0, 100, 100),
            _square_room("rR", "COZINHA", 100, 0, 200, 100),
        ],
        "openings": [_door("o0", "w0", (100, 50))],
        "soft_barriers": [],
    }
    pairs = _adjacent_room_pairs(consensus)
    assert frozenset({"SALA", "COZINHA"}) in pairs


def test_adjacent_room_pairs_filters_unknown_names():
    """A merged cell with a room name absent from rooms[] gets
    filtered out (defends against label typos)."""
    consensus = {
        "wall_thickness_pts": 5.4,
        "walls": [],
        "rooms": [
            _square_room("r0", "A | B", 0, 0, 100, 100),
            _square_room("r1", "A", 100, 0, 200, 100),
        ],
        "openings": [], "soft_barriers": [],
    }
    pairs = _adjacent_room_pairs(consensus)
    # A and B come from the merged cell; B isn't a standalone room
    # but it's still a constituent label, so the pair stands.
    assert frozenset({"A", "B"}) in pairs


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def test_run_check_dispatches_when_consensus_supplied():
    check = run_check(_check_def("door_without_opening"),
                       _passing_consensus())
    assert check["status"] == "checked"
    assert check["verdict"] == "PASS"


def test_run_check_falls_back_to_scaffold_when_consensus_none():
    check = run_check(_check_def("door_without_opening"), None)
    assert check["status"] == "not_yet_checked"
    assert check["verdict"] == "WARN"


def test_run_check_unknown_key_returns_scaffold():
    """A check_def with a key not in CHECK_RUNNERS falls back to the
    scaffold (defensive)."""
    fake = {"key": "definitely_not_a_real_check",
            "description": "X", "severity_on_fail": "FAIL"}
    res = run_check(fake, _passing_consensus())
    assert res["status"] == "not_yet_checked"


# ---------------------------------------------------------------------------
# Parametric: every check key has a registered runner
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("check_def", list(EIGHT_CHECKS))
def test_every_check_runs_against_passing_consensus(check_def: dict):
    """Every check returns a well-shaped result on the passing
    fixture. Verdict may be PASS/WARN per the check's semantics."""
    consensus = _passing_consensus()
    # The wet/terrace check is no-op without plan_id; PASS is fine.
    res = run_check(check_def, consensus)
    assert res["status"] in {"checked", "not_yet_checked"}
    assert res["verdict"] in {"PASS", "WARN", "FAIL"}
    assert isinstance(res["failing_elements"], list)
    assert isinstance(res["notes"], str)
