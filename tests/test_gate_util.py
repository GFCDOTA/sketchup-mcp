"""Micro-tests for the shared gate primitives (tools/gate_util.py).

Locks the contract of the point-to-segment distance that was extracted from the
three byte-identical copies in kitchen_wall_regression_gate / wall_exact_match_gate
/ position_fidelity_gate, so a future "optimization" can't silently change a gate
verdict.
"""
from __future__ import annotations

import math

from tools.gate_util import load_json, pt_seg_dist


def test_point_on_segment_is_zero():
    assert pt_seg_dist(1, 0, 0, 0, 2, 0) == 0.0


def test_perpendicular_distance():
    # foot of (1,3) on segment (0,0)-(2,0) is (1,0) -> distance 3
    assert pt_seg_dist(1, 3, 0, 0, 2, 0) == 3.0


def test_projection_is_clamped_to_endpoints():
    assert pt_seg_dist(5, 0, 0, 0, 2, 0) == 3.0    # past B -> clamps to (2,0)
    assert pt_seg_dist(-4, 0, 0, 0, 2, 0) == 4.0   # before A -> clamps to (0,0)


def test_zero_length_segment_degenerates_to_point_distance():
    assert pt_seg_dist(3, 4, 0, 0, 0, 0) == 5.0    # 3-4-5


def test_matches_the_formula_the_gates_used():
    px, py, ax, ay, bx, by = 7.0, -2.0, 1.0, 1.0, 9.0, 5.0
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    expected = math.hypot(px - (ax + t * dx), py - (ay + t * dy))
    assert pt_seg_dist(px, py, ax, ay, bx, by) == expected


def test_load_json_tolerates_utf8_bom(tmp_path):
    p = tmp_path / "x.json"
    p.write_bytes(b'\xef\xbb\xbf{"k": 1}')  # UTF-8 BOM prefix (utf-8-sig)
    assert load_json(p) == {"k": 1}
    assert load_json(str(p)) == {"k": 1}    # str path accepted too
