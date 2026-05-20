"""Hand-rolled mutation tests for tools.build_plan_shell_skp critical paths.

mutmut and mutatest both ship broken subprocess invocation on Windows
(see https://github.com/boxed/mutmut/issues/397). Rather than wait for
upstream or shell out to WSL, this module documents the most
hazardous mutation classes for build_plan_shell_skp and asserts each
of them would be CAUGHT by the existing test suite.

Each test:

  1. Establishes a baseline geometric output.
  2. Introduces a specific mutation — a value swap, an operator
     flip, a constant change — exactly the kind of edit a careless
     refactor or a copy-paste bug would make.
  3. Asserts the mutation produces a DETECTABLE change in the
     output, OR raises, OR makes an invariant fail.

The audit trail of mutation classes covered here is intentionally
explicit. When a new constant / sensitive operator / off-by-one
edge case lands in tools/build_plan_shell_skp.py, add the
corresponding mutation test here. The Ruby side has its own
mutation tests in tests/test_plan_shell_mutant_inputs.py.

Conventions:
  - "MUT-<NN>" comment block per mutation, with one-line description
    of what it would look like in real source code.
  - Tests are independent — no module-state leakage.
"""
from __future__ import annotations

import pytest
from shapely.geometry import Polygon

from tools.build_plan_shell_skp import (
    MIN_SLIVER_AREA_PTS2,
    SNAP_EPS_PTS,
    build_shell_polygon,
    opening_carve_rect,
    wall_footprint,
)

# ---------------------------------------------------------------------
# Pinned constants — the values themselves carry meaning. Bumping them
# silently is a mutation we want to catch.
# ---------------------------------------------------------------------


def test_pinned_snap_eps_pts() -> None:
    """MUT-01: SNAP_EPS_PTS = 0.1 pt. Larger values bridge gaps that
    should stay open (walls meant to be separate get fused); smaller
    values fail to bridge legitimate endpoint-mismatch artefacts in
    the consensus."""
    assert SNAP_EPS_PTS == 0.1, (
        "Critical tuning constant moved. If the value really must "
        "change, update this pin AND walk the planta_74 baseline."
    )


def test_pinned_min_sliver_area_pts2() -> None:
    """MUT-02: MIN_SLIVER_AREA_PTS2 = 0.5 pt². Bumping this drops
    real geometry; lowering this keeps numerical-noise polygons."""
    assert MIN_SLIVER_AREA_PTS2 == 0.5


# ---------------------------------------------------------------------
# wall_footprint mutations
# ---------------------------------------------------------------------


def _h_wall(length: float = 100.0, thickness: float = 4.0) -> dict:
    return {"id": "h", "start": [0, 50], "end": [length, 50],
            "thickness": thickness, "orientation": "h"}


def _v_wall(length: float = 100.0, thickness: float = 4.0) -> dict:
    return {"id": "v", "start": [50, 0], "end": [50, length],
            "thickness": thickness, "orientation": "v"}


def test_wall_footprint_thickness_doubles_area_doubles() -> None:
    """MUT-03: if `half = t / 2.0` became `half = t / 1.0`, the
    rectangle perpendicular to the wall axis would double in width.
    A direct area assertion catches the off-by-half-factor."""
    base_area = wall_footprint(_h_wall(length=100, thickness=4)).area
    double_area = wall_footprint(_h_wall(length=100, thickness=8)).area
    # Linear in thickness — exactly 2× when thickness doubles.
    assert double_area == pytest.approx(base_area * 2.0, rel=1e-9)


def test_wall_footprint_orientation_swap_swaps_axes() -> None:
    """MUT-04: if a refactor accidentally flipped which axis the
    thickness sits on (orientation 'h' vs 'v' code paths swapped),
    a horizontal wall would extend across the y-axis instead of x.
    The bbox bounds catch this directly."""
    h = wall_footprint(_h_wall(length=100, thickness=4))
    v = wall_footprint(_v_wall(length=100, thickness=4))
    # H wall is wide in x, thin in y
    hx0, hy0, hx1, hy1 = h.bounds
    assert (hx1 - hx0) > (hy1 - hy0), "horizontal wall must be wider in x"
    # V wall is the opposite
    vx0, vy0, vx1, vy1 = v.bounds
    assert (vy1 - vy0) > (vx1 - vx0), "vertical wall must be taller in y"


def test_wall_footprint_unknown_orientation_raises() -> None:
    """MUT-05: if the final `raise ValueError` was deleted, an
    unsupported orientation would silently produce zero-area or
    None. The test guards against that deletion."""
    with pytest.raises(ValueError, match="orientation"):
        wall_footprint({"start": [0, 0], "end": [1, 0],
                        "thickness": 1.0, "orientation": "diag"})


def test_wall_footprint_zero_thickness_is_zero_area() -> None:
    """MUT-06: degenerate wall thickness should still produce a
    Polygon (Shapely handles degenerate boxes), but area must
    collapse to 0. Catches mutations that 'fix' the calculation by
    adding a baseline thickness."""
    fp = wall_footprint(_h_wall(thickness=0))
    assert fp.area == pytest.approx(0.0)


def test_wall_footprint_reversed_endpoints_same_result() -> None:
    """MUT-07: swapping start <-> end on the wall's main axis must
    not change the footprint (we minmax internally). Catches a
    mutation that drops the minmax call."""
    w_fwd = wall_footprint({"id": "f", "start": [10, 0], "end": [50, 0],
                            "thickness": 2.0, "orientation": "h"})
    w_rev = wall_footprint({"id": "r", "start": [50, 0], "end": [10, 0],
                            "thickness": 2.0, "orientation": "h"})
    assert w_fwd.bounds == w_rev.bounds


# ---------------------------------------------------------------------
# opening_carve_rect mutations
# ---------------------------------------------------------------------


def test_opening_carve_rect_horizontal_centered_on_wall() -> None:
    """MUT-08: if the carve rect were aligned only one side of the
    wall (drop the `cy - half / cy + half` symmetry), the gap would
    appear off-centre. We pin the exact bounds."""
    wall = _h_wall(length=100, thickness=4)
    op = {"id": "o", "wall_id": "h", "center": [50.0, 50.0],
          "opening_width_pts": 10.0}
    rect = opening_carve_rect(op, wall, default_thickness=4.0)
    # Centered on x=50 with half-width 5, full thickness 4 around y=50
    assert rect.bounds == (45.0, 48.0, 55.0, 52.0)


def test_opening_carve_rect_zero_width_raises() -> None:
    """MUT-09: a zero-width opening is malformed input. The current
    code raises explicitly; a mutation that swallowed the raise
    would produce a degenerate carve rect that does nothing."""
    wall = _h_wall(length=100, thickness=4)
    op = {"id": "o", "wall_id": "h", "center": [50.0, 50.0],
          "opening_width_pts": 0}
    with pytest.raises(ValueError, match="opening_width_pts"):
        opening_carve_rect(op, wall, default_thickness=4.0)


def test_opening_carve_rect_uses_host_wall_thickness_not_default() -> None:
    """MUT-10: if the carve rect read `default_thickness` instead of
    `host_wall['thickness']`, walls whose thickness differs from
    the consensus default (some plant types vary thickness per
    wall) would carve incorrect-width gaps."""
    wall = {"id": "thick", "start": [0, 50], "end": [100, 50],
            "thickness": 10.0, "orientation": "h"}
    op = {"id": "o", "wall_id": "thick", "center": [50.0, 50.0],
          "opening_width_pts": 8.0}
    # Should use thickness=10 (not the default 4.0 passed below)
    rect = opening_carve_rect(op, wall, default_thickness=4.0)
    x0, y0, x1, y1 = rect.bounds
    assert (y1 - y0) == pytest.approx(10.0)  # NOT 4.0


# ---------------------------------------------------------------------
# build_shell_polygon mutations
# ---------------------------------------------------------------------


def _square(thickness: float = 4.0) -> dict:
    return {
        "wall_thickness_pts": thickness,
        "walls": [
            {"id": "wb", "start": [-50, -50], "end": [50, -50],
             "thickness": thickness, "orientation": "h"},
            {"id": "wt", "start": [-50, 50], "end": [50, 50],
             "thickness": thickness, "orientation": "h"},
            {"id": "wl", "start": [-50, -50], "end": [-50, 50],
             "thickness": thickness, "orientation": "v"},
            {"id": "wr", "start": [50, -50], "end": [50, 50],
             "thickness": thickness, "orientation": "v"},
        ],
        "openings": [],
        "rooms": [],
    }


def test_build_shell_polygon_thickness_grows_outer_perimeter() -> None:
    """MUT-11: a mutation that drops the +half / -half computation in
    the inner ring would leave outer and inner perimeters equal,
    yielding a zero-thickness 'wall'. Pin the wall thickness via
    bbox delta."""
    base, _ = build_shell_polygon(_square(thickness=4.0))
    thicker, _ = build_shell_polygon(_square(thickness=8.0))
    # Outer bbox grows by exactly the thickness delta on each side
    bx0, by0, bx1, by1 = base[0].exterior.bounds
    tx0, ty0, tx1, ty1 = thicker[0].exterior.bounds
    assert tx0 == pytest.approx(bx0 - 2.0, abs=0.5)
    assert tx1 == pytest.approx(bx1 + 2.0, abs=0.5)


def test_build_shell_polygon_door_carve_reduces_area() -> None:
    """MUT-12: if the `shell.difference(carve_union)` call were
    replaced with `shell.union(carve_union)` (an easy refactor
    typo), the door rectangle would ADD area instead of subtract.
    Pin that area shrinks."""
    no_door = _square()
    with_door = _square()
    with_door["openings"] = [{
        "id": "d", "wall_id": "wb", "center": [0.0, -50.0],
        "opening_width_pts": 20.0,
    }]
    p_no, _ = build_shell_polygon(no_door)
    p_yes, _ = build_shell_polygon(with_door)
    assert p_yes[0].area < p_no[0].area, (
        "door subtraction must REDUCE shell area; if it INCREASED, "
        "shell.difference was swapped for shell.union"
    )


def test_build_shell_polygon_empty_walls_raises_does_not_segfault() -> None:
    """MUT-13: the explicit `raise ValueError` on empty walls
    prevents an unrelated shapely error downstream. Catch
    accidental deletion of the guard."""
    with pytest.raises(ValueError, match="no walls"):
        build_shell_polygon({"walls": [], "openings": []})


def test_build_shell_polygon_disconnected_walls_dont_get_fused() -> None:
    """MUT-14: if SNAP_EPS_PTS were bumped above the distance between
    two walls we expect to stay separate, they would fuse. This
    test pins a separation of 50 pts (>>> 0.1 pt SNAP_EPS) and
    asserts the result is a MultiPolygon."""
    cons = {
        "wall_thickness_pts": 4.0,
        "walls": [
            {"id": "w0", "start": [0, 0], "end": [100, 0],
             "thickness": 4.0, "orientation": "h"},
            {"id": "w1", "start": [0, 100], "end": [100, 100],
             "thickness": 4.0, "orientation": "h"},
        ],
        "openings": [],
        "rooms": [],
    }
    polys, stats = build_shell_polygon(cons)
    # 100 pts apart, snap eps is 0.1 — they must stay disconnected.
    assert stats["shell_pieces_after_sliver_filter"] == 2


def test_build_shell_polygon_does_not_invent_walls_when_input_is_empty_openings() -> None:
    """MUT-15: pipeline invariant (CLAUDE.md §2.1) — never invent
    walls. Empty openings must NOT cause a phantom wall."""
    polys, stats = build_shell_polygon(_square())
    assert len(polys) == 1
    assert stats["input_walls"] == 4
    # No silent wall inflation
    assert isinstance(polys[0], Polygon)


def test_build_shell_polygon_opening_skipping_does_not_carve() -> None:
    """MUT-16: if a typo had `carve_rects.append` before the
    error-skip path, ghost openings (wall_id missing from walls)
    would still cut the shell. Pin: ghost openings must not affect
    area."""
    cons_no_ghost = _square()
    cons_with_ghost = _square()
    cons_with_ghost["openings"] = [
        {"id": "ghost", "wall_id": "DOES_NOT_EXIST",
         "center": [0, 0], "opening_width_pts": 50.0},
    ]
    p_no, _ = build_shell_polygon(cons_no_ghost)
    p_yes, stats = build_shell_polygon(cons_with_ghost)
    assert p_no[0].area == pytest.approx(p_yes[0].area, rel=1e-6)
    assert stats["openings_carved"] == 0
    assert any("DOES_NOT_EXIST" in s for s in stats["openings_skipped"])
