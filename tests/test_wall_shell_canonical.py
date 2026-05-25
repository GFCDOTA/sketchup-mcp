"""Canonicalisation gates for the wall shell (LL-017 / FP-025).

Rule: after `build_shell_polygon` runs, the wall shell rings MUST be
canonical:
  - axis-aligned rectangles have NO collinear redundant vertices
    (a corner-junction L-shape notch is the FP-025 signature)
  - the outer boundary of a simple N-wall room equals N vertices
    (4 for a quadrado, not 12)
  - all edges are axis-aligned (no diagonal artifacts from
    boolean ops on aligned input)
  - no slivers / overhangs / faces sobrando

These tests run without SketchUp and operate purely on the Python
shell polygon output.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from shapely.geometry import Polygon

from tools.build_plan_shell_skp import (
    _canonicalise_axis_aligned_ring,
    build_shell_polygon,
    canonicalise_axis_aligned_polygon,
    wall_footprint,
)

# ---- fixtures =======================================================

def _quadrado_consensus(openings: list[dict] | None = None) -> dict:
    """Canonical 4-wall single-room consensus."""
    return {
        "schema_version": "1.0.0",
        "wall_thickness_pts": 5.4,
        "dimension_mode": "inner_clear",
        "plan_id": "test_canonical",
        "walls": [
            {"id": "w_bottom", "start": [100.0, 100.0],
             "end": [213.684, 100.0], "thickness": 5.4, "orientation": "h"},
            {"id": "w_top", "start": [100.0, 213.684],
             "end": [213.684, 213.684], "thickness": 5.4, "orientation": "h"},
            {"id": "w_left", "start": [100.0, 100.0],
             "end": [100.0, 213.684], "thickness": 5.4, "orientation": "v"},
            {"id": "w_right", "start": [213.684, 100.0],
             "end": [213.684, 213.684], "thickness": 5.4, "orientation": "v"},
        ],
        "rooms": [{
            "id": "r_main", "name": "QUADRADO",
            "polygon_pts": [[102.7, 102.7], [210.984, 102.7],
                            [210.984, 210.984], [102.7, 210.984]],
            "area_pts2": 11725.4,
        }],
        "openings": openings or [],
        "soft_barriers": [],
    }


def _ring_vertex_count(ring_coords) -> int:
    """Vertex count excluding the closing duplicate."""
    coords = list(ring_coords)
    if len(coords) >= 2 and coords[0] == coords[-1]:
        return len(coords) - 1
    return len(coords)


# ---- 1. wall_footprint extension at endpoints =======================

def test_wall_footprint_extends_horizontal_by_half_at_both_endpoints():
    """The wall must extend by half-thickness in BOTH +x and -x at
    its endpoints. Without this, perpendicular junctions leave
    L-shape notches at the outer corner (FP-025)."""
    wall = {"id": "w", "start": [10.0, 5.0], "end": [20.0, 5.0],
            "thickness": 2.0, "orientation": "h"}
    fp = wall_footprint(wall)
    # x: should be [10 - 1, 20 + 1] = [9, 21]; y: [5 - 1, 5 + 1] = [4, 6]
    minx, miny, maxx, maxy = fp.bounds
    assert minx == 9.0
    assert maxx == 21.0
    assert miny == 4.0
    assert maxy == 6.0


def test_wall_footprint_extends_vertical_by_half_at_both_endpoints():
    wall = {"id": "w", "start": [5.0, 10.0], "end": [5.0, 20.0],
            "thickness": 2.0, "orientation": "v"}
    fp = wall_footprint(wall)
    minx, miny, maxx, maxy = fp.bounds
    assert miny == 9.0
    assert maxy == 21.0
    assert minx == 4.0
    assert maxx == 6.0


def test_wall_footprint_extend_endpoints_false_preserves_legacy_behaviour():
    """Opt-out flag for tests that need the un-extended box."""
    wall = {"id": "w", "start": [10.0, 5.0], "end": [20.0, 5.0],
            "thickness": 2.0, "orientation": "h"}
    fp = wall_footprint(wall, extend_endpoints=False)
    minx, _, maxx, _ = fp.bounds
    assert minx == 10.0  # NOT 9.0 (no extension)
    assert maxx == 20.0


# ---- 2. quadrado shell is canonical rectangle =======================

def test_quadrado_outer_ring_is_canonical_4_vertex_rectangle():
    """The CORE assertion of LL-017/FP-025: the outer boundary of a
    4-wall single-room shell is exactly 4 vertices. Anything more is
    the corner-notch bug signature."""
    polys, stats = build_shell_polygon(_quadrado_consensus())
    assert len(polys) == 1, "single room must produce single piece"
    poly = polys[0]
    n_outer = _ring_vertex_count(poly.exterior.coords)
    assert n_outer == 4, (
        f"outer ring has {n_outer} vertices; expected 4. "
        f"Excess indicates corner-notch bug (FP-025). Vertices: "
        f"{list(poly.exterior.coords)[:-1]}"
    )


def test_quadrado_inner_hole_is_canonical_4_vertex_rectangle():
    polys, stats = build_shell_polygon(_quadrado_consensus())
    poly = polys[0]
    assert len(poly.interiors) == 1, "expected single interior hole (room)"
    n_inner = _ring_vertex_count(poly.interiors[0].coords)
    assert n_inner == 4, (
        f"inner ring has {n_inner} vertices; expected 4. "
        f"Same FP-025 signature on the inner boundary."
    )


def test_quadrado_outer_corners_are_canonical_positions():
    """For a 4m x 4m room (113.684 pt edge), thickness 5.4 pt,
    outer corners must be exactly at (97.3, 97.3), (216.384, 97.3),
    (216.384, 216.384), (97.3, 216.384) — no half-step interior
    vertices."""
    polys, _ = build_shell_polygon(_quadrado_consensus())
    coords = [(round(x, 3), round(y, 3))
              for x, y in list(polys[0].exterior.coords)[:-1]]
    expected = {(97.3, 97.3), (216.384, 97.3),
                (216.384, 216.384), (97.3, 216.384)}
    assert set(coords) == expected, (
        f"outer corners {set(coords)} != canonical {expected}"
    )


def test_quadrado_all_edges_are_axis_aligned():
    """No diagonal edges allowed for axis-aligned wall input."""
    polys, _ = build_shell_polygon(_quadrado_consensus())
    poly = polys[0]
    coords = list(poly.exterior.coords)
    for (x0, y0), (x1, y1) in zip(coords[:-1], coords[1:]):
        is_horizontal = abs(y1 - y0) < 1e-6
        is_vertical = abs(x1 - x0) < 1e-6
        assert is_horizontal or is_vertical, (
            f"non-axis-aligned edge: ({x0}, {y0}) -> ({x1}, {y1})"
        )


# ---- 3. canonicaliser unit tests ====================================

def test_canonicaliser_drops_collinear_redundant_vertex():
    """A vertex sandwiched between two same-direction edges must be
    dropped."""
    # Square with an extra vertex on the bottom edge.
    ring = [(0.0, 0.0), (5.0, 0.0), (10.0, 0.0), (10.0, 10.0),
            (0.0, 10.0)]
    cleaned = _canonicalise_axis_aligned_ring(ring)
    # The (5.0, 0.0) midpoint is sandwiched between two horizontal
    # edges going +x — must be dropped.
    assert (5.0, 0.0) not in cleaned
    assert len(cleaned) == 4


def test_canonicaliser_preserves_real_corners():
    ring = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    cleaned = _canonicalise_axis_aligned_ring(ring)
    assert len(cleaned) == 4
    assert set(cleaned) == set(ring)


def test_canonicaliser_handles_l_shape_correctly():
    """L-shape has 6 real corners — all must survive."""
    ring = [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0),
            (5.0, 5.0), (5.0, 10.0), (0.0, 10.0)]
    cleaned = _canonicalise_axis_aligned_ring(ring)
    assert len(cleaned) == 6


def test_canonicaliser_drops_collinear_on_polygon_with_hole():
    outer = [(0.0, 0.0), (5.0, 0.0), (10.0, 0.0), (10.0, 10.0),
             (0.0, 10.0)]
    hole = [(2.0, 2.0), (4.0, 2.0), (8.0, 2.0), (8.0, 8.0),
            (2.0, 8.0)]
    poly = Polygon(outer, holes=[hole])
    clean = canonicalise_axis_aligned_polygon(poly)
    assert _ring_vertex_count(clean.exterior.coords) == 4
    assert _ring_vertex_count(clean.interiors[0].coords) == 4


# ---- 4. canonicalisation counter in stats ===========================

def test_stats_reports_redundant_vertices_dropped_field():
    _, stats = build_shell_polygon(_quadrado_consensus())
    assert "redundant_vertices_dropped" in stats
    assert isinstance(stats["redundant_vertices_dropped"], int)


# ---- 5. quadrado WITH window: shell still canonical =================

def test_quadrado_with_window_keeps_canonical_outer_ring():
    """Window aperture goes through 3D carve path (ADR-007) — must
    NOT pollute the 2D outer ring with notches."""
    window = {
        "id": "win_south", "wall_id": "w_bottom", "kind_v5": "window",
        "geometry_origin": "svg_segments", "decision": "clean",
        "confidence": 0.95, "center": [156.842, 100.0],
        "opening_width_pts": 30.0,
    }
    polys, _ = build_shell_polygon(_quadrado_consensus(openings=[window]))
    poly = polys[0]
    n_outer = _ring_vertex_count(poly.exterior.coords)
    assert n_outer == 4, (
        f"window aperture must not affect outer ring; got {n_outer} verts"
    )


# ---- 6. planta_74 regression ========================================

PLANTA_74_CONSENSUS = (
    Path(__file__).parent.parent / "fixtures" / "planta_74"
    / "consensus_with_human_walls_and_soft_barriers.json"
)


@pytest.mark.skipif(
    not PLANTA_74_CONSENSUS.exists(),
    reason="planta_74 consensus fixture not present",
)
def test_planta_74_no_collinear_redundant_vertices_after_canonicalise():
    """After canonicalisation, no piece may carry a collinear
    redundant vertex (FP-025 signature). Test runs the canoniser
    a second time and asserts it is idempotent (drops 0)."""
    consensus = json.loads(PLANTA_74_CONSENSUS.read_text(encoding="utf-8"))
    polys, _ = build_shell_polygon(consensus)
    for i, p in enumerate(polys):
        clean = canonicalise_axis_aligned_polygon(p)
        before = _ring_vertex_count(p.exterior.coords)
        after = _ring_vertex_count(clean.exterior.coords)
        assert before == after, (
            f"piece[{i}] outer ring is NOT canonical: "
            f"canonicaliser dropped {before - after} additional verts "
            f"on re-run. build_shell_polygon must canonicalise once."
        )


@pytest.mark.skipif(
    not PLANTA_74_CONSENSUS.exists(),
    reason="planta_74 consensus fixture not present",
)
def test_planta_74_all_edges_axis_aligned():
    """Planta_74 uses axis-aligned walls; the shell must too."""
    consensus = json.loads(PLANTA_74_CONSENSUS.read_text(encoding="utf-8"))
    polys, _ = build_shell_polygon(consensus)
    for i, p in enumerate(polys):
        coords = list(p.exterior.coords)
        for (x0, y0), (x1, y1) in zip(coords[:-1], coords[1:]):
            is_h = abs(y1 - y0) < 1e-6
            is_v = abs(x1 - x0) < 1e-6
            assert is_h or is_v, (
                f"piece[{i}] non-axis-aligned edge: "
                f"({x0:.3f}, {y0:.3f}) -> ({x1:.3f}, {y1:.3f})"
            )


@pytest.mark.skipif(
    not PLANTA_74_CONSENSUS.exists(),
    reason="planta_74 consensus fixture not present",
)
def test_planta_74_no_slivers_after_canonicalise():
    """All shell pieces must clear the sliver threshold."""
    consensus = json.loads(PLANTA_74_CONSENSUS.read_text(encoding="utf-8"))
    polys, stats = build_shell_polygon(consensus)
    assert stats["slivers_removed"] == 0, (
        f"slivers_removed={stats['slivers_removed']} — input may have "
        f"degenerate walls or canonicalisation introduced slivers"
    )
    for i, p in enumerate(polys):
        assert p.is_valid, f"piece[{i}] is invalid after canonicalise"
        assert p.area > 0.5, f"piece[{i}] area = {p.area:.3f} (sliver)"
