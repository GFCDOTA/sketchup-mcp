"""FP-026 — Wall-stub canonicalisation regression tests.

These tests lock the LL-017 junction-aware extension behaviour (already
landed in PR #192) and the FP-026 diagnostic outputs (this PR). They
exercise small synthetic fixtures (L, T, straight, door-carve) so the
canonicalisation rules can be verified without the planta_74 cost.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.build_plan_shell_skp import (
    _classify_endpoint_junctions,
    build_shell_polygon,
    wall_footprint,
)
from tools.diagnose_wall_stubs import (
    STUB_MAX_LENGTH_RATIO,
    STUB_WIDTH_TOLERANCE,
    detect_candidates,
)

# ---- synthetic fixtures =============================================


def _l_junction_consensus() -> dict:
    """Two walls forming an L. Both endpoints at the corner are junctions."""
    return {
        "wall_thickness_pts": 5.4,
        "walls": [
            {"id": "h", "start": [100.0, 100.0], "end": [200.0, 100.0],
             "thickness": 5.4, "orientation": "h"},
            {"id": "v", "start": [200.0, 100.0], "end": [200.0, 200.0],
             "thickness": 5.4, "orientation": "v"},
        ],
        "rooms": [], "openings": [], "soft_barriers": [],
    }


def _t_junction_consensus() -> dict:
    """T-junction: vertical wall stops at the horizontal wall's body."""
    return {
        "wall_thickness_pts": 5.4,
        "walls": [
            {"id": "spine", "start": [50.0, 100.0], "end": [250.0, 100.0],
             "thickness": 5.4, "orientation": "h"},
            {"id": "stem", "start": [150.0, 50.0], "end": [150.0, 100.0],
             "thickness": 5.4, "orientation": "v"},
        ],
        "rooms": [], "openings": [], "soft_barriers": [],
    }


def _straight_collinear_consensus() -> dict:
    """Two horizontal walls that should merge into one rectangle."""
    return {
        "wall_thickness_pts": 5.4,
        "walls": [
            {"id": "left", "start": [50.0, 100.0], "end": [150.0, 100.0],
             "thickness": 5.4, "orientation": "h"},
            {"id": "right", "start": [150.0, 100.0], "end": [250.0, 100.0],
             "thickness": 5.4, "orientation": "h"},
        ],
        "rooms": [], "openings": [], "soft_barriers": [],
    }


def _door_carve_consensus() -> dict:
    """L-shape with a door in the bottom wall."""
    return {
        "wall_thickness_pts": 5.4,
        "walls": [
            {"id": "bottom", "start": [100.0, 100.0], "end": [300.0, 100.0],
             "thickness": 5.4, "orientation": "h"},
            {"id": "left", "start": [100.0, 100.0], "end": [100.0, 200.0],
             "thickness": 5.4, "orientation": "v"},
        ],
        "rooms": [], "openings": [
            {"id": "d0", "wall_id": "bottom", "kind_v5": "interior_door",
             "geometry_origin": "human_annotation",
             "center": [200.0, 100.0], "opening_width_pts": 32.0},
        ],
        "soft_barriers": [],
    }


# ---- tests ==========================================================


def test_l_junction_no_residual_cap():
    """L: corner endpoints extend, free ends do not → no stubs."""
    cons = _l_junction_consensus()
    j = _classify_endpoint_junctions(cons["walls"])
    assert j["h"][1] is True, "h.end at corner should be junction"
    assert j["v"][0] is True, "v.start at corner should be junction"
    assert j["h"][0] is False
    assert j["v"][1] is False

    polys, stats = build_shell_polygon(cons)
    assert stats["shell_pieces_after_sliver_filter"] == 1
    candidates, _ = detect_candidates(cons)
    fails = [c for c in candidates if c.verdict == "FAIL"]
    warns = [c for c in candidates if c.verdict == "WARN"]
    assert not fails, f"L-junction has FAIL stubs: {fails}"
    assert not warns, f"L-junction has WARN stubs: {warns}"


def test_t_junction_no_dangling_cap():
    """T-junction: stem's inner endpoint is a perpendicular junction."""
    cons = _t_junction_consensus()
    j = _classify_endpoint_junctions(cons["walls"])
    assert j["stem"][1] is True, "stem top should be junction"
    assert j["stem"][0] is False, "stem bottom should be FREE"
    assert j["spine"] == (False, False)

    candidates, _ = detect_candidates(cons)
    fails = [c for c in candidates if c.verdict == "FAIL"]
    assert not fails, f"T-junction has FAIL stubs: {fails}"


def test_straight_collinear_merge():
    """Two collinear walls produce a single shell piece."""
    cons = _straight_collinear_consensus()
    polys, stats = build_shell_polygon(cons)
    assert stats["shell_pieces_after_sliver_filter"] == 1
    j = _classify_endpoint_junctions(cons["walls"])
    # Per LL-017 perpendicular requirement, parallel collinear walls
    # do NOT classify as junctions — both endpoints stay FREE.
    assert j["left"][1] is False
    assert j["right"][0] is False


def test_door_carve_no_jamb_fragment():
    """Door carve does NOT leave a residual jamb island."""
    cons = _door_carve_consensus()
    polys, stats = build_shell_polygon(cons)
    for p in polys:
        assert p.area > 5.4 ** 2, (
            f"door carve left a fragment: piece area={p.area:.3f}"
        )
    candidates, _ = detect_candidates(cons)
    fails = [c for c in candidates if c.verdict == "FAIL"]
    assert not fails, f"door carve has FAIL stubs: {fails}"


# ---- planta_74 smoke ===============================================

PLANTA_74_CONSENSUS = Path(
    "fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json"
)


@pytest.mark.skipif(
    not PLANTA_74_CONSENSUS.exists(),
    reason="planta_74 consensus fixture not present",
)
def test_planta_74_no_fail_stubs():
    """FP-026 acceptance: zero FAIL stubs on the canonical fixture."""
    cons = json.loads(PLANTA_74_CONSENSUS.read_text(encoding="utf-8"))
    candidates, _ = detect_candidates(cons)
    fails = [c for c in candidates if c.verdict == "FAIL"]
    warns = [c for c in candidates if c.verdict == "WARN"]
    assert not fails, (
        f"planta_74 has {len(fails)} FAIL stubs: "
        + ", ".join(f"{c.stub_id} @ {c.centroid}" for c in fails[:5])
    )
    assert len(warns) <= 2, (
        f"planta_74 has {len(warns)} WARN stubs (budget=2): "
        + ", ".join(f"{c.stub_id} @ {c.centroid}" for c in warns[:5])
    )
