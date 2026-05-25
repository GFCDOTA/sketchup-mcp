"""Invariant tests for `fixtures/quadrado/consensus_uniform_4windows.json`.

This fixture is the uniform-quadrado variant: 4 walls + 4 identical
windows (one centered per wall). It exists as the **fidelity
reference** for the quadrado plant — geometrically uniform so the
fidelity engine can use it without asymmetry confounding the
metric. It complements `consensus_with_window.json` (single-window,
asymmetric) which remains the window-aperture contract reference.

These tests are PURE (no SU runtime) — they verify the JSON shape +
the geometric symmetry invariants. The downstream SKP / render
artifacts (`artifacts/human_review/quadrado/quadrado_uniform_4windows.*`)
are produced by `tools/build_plan_shell_skp.py` and validated by
the existing quadrado smoke gates against the uniform fixture
(see follow-up PR).
"""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE = REPO_ROOT / "fixtures" / "quadrado" / "consensus_uniform_4windows.json"


# --- Shape / schema ----------------------------------------------------


def _load() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_fixture_exists():
    assert FIXTURE.is_file(), f"missing canonical fixture at {FIXTURE}"


def test_fixture_loads_as_valid_consensus():
    data = _load()
    assert data["schema_version"] == "1.0.0"
    assert data["plan_id"] == "quadrado_uniform_4windows"
    assert data["wall_thickness_pts"] == 5.4
    assert isinstance(data["walls"], list)
    assert isinstance(data["rooms"], list)
    assert isinstance(data["openings"], list)
    assert isinstance(data["soft_barriers"], list)


def test_has_4_walls_1_room_4_openings():
    data = _load()
    assert len(data["walls"]) == 4
    assert len(data["rooms"]) == 1
    assert len(data["openings"]) == 4
    assert data["soft_barriers"] == []


# --- Wall topology -----------------------------------------------------


def test_walls_form_a_closed_square():
    """The 4 walls must form a closed square with shared corners."""
    data = _load()
    walls_by_id = {w["id"]: w for w in data["walls"]}
    # Expected corners (the 4 inner-clear corners shared between walls)
    expected_corners = {
        (100.0, 100.0),   # SW: bottom + left
        (213.684, 100.0), # SE: bottom + right
        (100.0, 213.684), # NW: top + left
        (213.684, 213.684), # NE: top + right
    }
    actual_endpoints: set[tuple[float, float]] = set()
    for w in walls_by_id.values():
        actual_endpoints.add(tuple(w["start"]))
        actual_endpoints.add(tuple(w["end"]))
    assert actual_endpoints == expected_corners


def test_all_walls_have_identical_thickness():
    data = _load()
    thicknesses = {w["thickness"] for w in data["walls"]}
    assert thicknesses == {5.4}


# --- Window symmetry (THE fidelity invariant) --------------------------


def test_each_wall_hosts_exactly_one_window():
    """The fidelity uniformity contract: 1 window per wall."""
    data = _load()
    wall_ids = {w["id"] for w in data["walls"]}
    opening_walls = [op["wall_id"] for op in data["openings"]]
    assert sorted(opening_walls) == sorted(wall_ids)
    # No duplicates — each wall hosts EXACTLY one opening.
    assert len(opening_walls) == len(set(opening_walls))


def test_all_windows_have_identical_width():
    """Uniformity: all 4 windows must have the same opening_width_pts."""
    data = _load()
    widths = {op["opening_width_pts"] for op in data["openings"]}
    assert widths == {30.0}, f"non-uniform widths: {widths}"


def test_all_windows_are_kind_window():
    """Uniformity: every opening is 'window' — not door, passage, or
    glazed_balcony. Routes through the 3D post-extrude aperture path
    per ADR-007 / CLAUDE.md §19."""
    data = _load()
    kinds = {op["kind_v5"] for op in data["openings"]}
    assert kinds == {"window"}


def test_each_window_centered_on_its_wall_midpoint():
    """Geometric symmetry: every window's center is the exact midpoint
    of its host wall. The fidelity-relevant invariant — any asymmetry
    here breaks the 'all walls are the same way' guarantee."""
    data = _load()
    walls_by_id = {w["id"]: w for w in data["walls"]}
    for op in data["openings"]:
        w = walls_by_id[op["wall_id"]]
        mid = (
            (w["start"][0] + w["end"][0]) / 2.0,
            (w["start"][1] + w["end"][1]) / 2.0,
        )
        cx, cy = op["center"]
        # Strict equality (< 1e-6) — these are hand-crafted exact midpoints.
        assert abs(cx - mid[0]) < 1e-6, (
            f"{op['id']} center.x={cx} not at wall midpoint.x={mid[0]}"
        )
        assert abs(cy - mid[1]) < 1e-6, (
            f"{op['id']} center.y={cy} not at wall midpoint.y={mid[1]}"
        )


def test_window_ids_cover_all_4_cardinal_sides():
    """Convention: win_south / win_north / win_west / win_east — a
    human-readable check that all 4 cardinal sides are explicit."""
    data = _load()
    expected_ids = {"win_south", "win_north", "win_west", "win_east"}
    actual_ids = {op["id"] for op in data["openings"]}
    assert actual_ids == expected_ids


# --- Room invariants ---------------------------------------------------


def test_room_polygon_is_inner_clear_square():
    """The single room is the inner-clear area between the wall
    centerlines, offset inward by half-thickness."""
    data = _load()
    room = data["rooms"][0]
    assert room["id"] == "r_main"
    assert room["name"] == "QUADRADO"
    # Polygon should be a 4-vertex square.
    pts = room["polygon_pts"]
    assert len(pts) == 4
    # Inner-clear corners: (100 + 2.7, 100 + 2.7) to (213.684 - 2.7, ...)
    expected = {
        (102.7, 102.7), (210.984, 102.7),
        (210.984, 210.984), (102.7, 210.984),
    }
    assert {tuple(p) for p in pts} == expected


def test_room_seed_pt_is_room_centroid():
    data = _load()
    room = data["rooms"][0]
    sx, sy = room["seed_pt"]
    # Centroid of the inner-clear square = mid of the 4 corners.
    # Inner-clear: [102.7, 102.7] to [210.984, 210.984]; mid = 156.842.
    assert abs(sx - 156.842) < 1e-6
    assert abs(sy - 156.842) < 1e-6
