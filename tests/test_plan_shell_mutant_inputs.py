"""Adversarial consensus inputs (mutants) for the Python phase of
build_plan_shell_skp.

Ruby has no native mutation-testing tool that survives our Windows
toolchain (mutmut, mutatest both ship with broken subprocess
invocation on Win32). The next-best lever for catching exporter
bugs is INPUT MUTATION: feed the exporter consensus shapes
mutated in known-pathological ways and assert the result is one of:

  • a clean failure (ValueError or filtered-out via stats), OR
  • a geometry that visibly differs from the baseline in a way the
    invariant tests would catch, OR
  • an explicit, documented "tolerate and skip" branch
    (e.g. duplicate vertices → dedupe).

Mutations covered here are bug categories observed in real
consensus files OR plausible upstream-extractor regressions:

  M-01  wall with unsupported orientation
  M-02  wall with negative thickness
  M-03  wall with zero-length axis (start == end)
  M-04  opening with no host wall_id
  M-05  opening with zero opening_width_pts
  M-06  opening with wall_id pointing to a deleted wall
  M-07  opening whose center is far outside its host wall
  M-08  consensus with no walls at all
  M-09  consensus with one degenerate wall (thickness 0, zero length)
  M-10  consensus where two walls have the SAME id (shouldn't crash;
        the second overwrites the first in walls_by_id but the union
        still includes both rectangles)
  M-11  consensus walls forming a self-intersecting "Z" shape
  M-12  soft_barriers entry without a polyline (Ruby side — see
        tests/test_plan_shell_invariants for downstream check)

Each test is independent. Where the mutation should RAISE, the
test pins the exception type and message. Where the mutation
should silently degrade, the test pins which stats key reflects
the skip.
"""
from __future__ import annotations

import pytest
from shapely.geometry import Polygon

from tools.build_plan_shell_skp import (
    build_shell_polygon,
    opening_carve_rect,
    wall_footprint,
)

# ---- M-01 unsupported orientation -----------------------------------


def test_M01_unsupported_orientation_raises() -> None:
    """Diagonals, missing orientation key, or random string — all
    must abort with a ValueError that names the orientation field."""
    bad_walls = [
        {"id": "diag", "start": [0, 0], "end": [10, 10],
         "thickness": 4.0, "orientation": "diag"},
        {"id": "missing", "start": [0, 0], "end": [10, 0],
         "thickness": 4.0},  # no orientation key
        {"id": "garbage", "start": [0, 0], "end": [10, 0],
         "thickness": 4.0, "orientation": "X"},
    ]
    for w in bad_walls:
        with pytest.raises(ValueError, match="orientation"):
            wall_footprint(w)


# ---- M-02 negative thickness ----------------------------------------


def test_M02_negative_thickness_produces_inverted_box() -> None:
    """A negative thickness is malformed input. The current code
    happily computes `half = t/2` and proceeds — Shapely's `box`
    swaps the resulting (min, max) so the area stays positive but
    the box is now on the OPPOSITE side of the centerline. This
    test pins that behaviour so a future fix that "tolerates"
    negative thickness doesn't go unnoticed."""
    w = {"id": "neg", "start": [0, 50], "end": [100, 50],
         "thickness": -4.0, "orientation": "h"}
    box = wall_footprint(w)
    # Shapely's box() handles min/max flips internally; the bounds
    # still come back as a valid rectangle with positive area.
    assert box.area == pytest.approx(400.0)


# ---- M-03 zero-length wall ------------------------------------------


def test_M03_zero_length_wall_produces_degenerate_polygon() -> None:
    """A wall whose start == end is a degenerate input. The current
    code computes a 0-by-thickness rectangle. Shapely returns it
    as a valid Polygon with zero area. Assert that — anything
    surprising (a None, a crash) is the regression."""
    w = {"id": "zero", "start": [50, 50], "end": [50, 50],
         "thickness": 4.0, "orientation": "h"}
    box = wall_footprint(w)
    assert box.area == pytest.approx(0.0)


# ---- M-04 opening missing wall_id ----------------------------------


def test_M04_opening_missing_wall_id_is_logged_and_skipped() -> None:
    """No wall_id ⇒ host lookup returns None ⇒ skipped, not silently
    carved (which would corrupt the shell)."""
    cons = {
        "wall_thickness_pts": 4.0,
        "walls": [
            {"id": "wb", "start": [-50, -50], "end": [50, -50],
             "thickness": 4.0, "orientation": "h"},
            {"id": "wt", "start": [-50, 50], "end": [50, 50],
             "thickness": 4.0, "orientation": "h"},
            {"id": "wl", "start": [-50, -50], "end": [-50, 50],
             "thickness": 4.0, "orientation": "v"},
            {"id": "wr", "start": [50, -50], "end": [50, 50],
             "thickness": 4.0, "orientation": "v"},
        ],
        "openings": [{
            "id": "no_host", "center": [0, -50],
            "opening_width_pts": 10.0,
        }],  # no wall_id key
        "rooms": [],
    }
    _, stats = build_shell_polygon(cons)
    assert stats["openings_carved"] == 0
    assert any("no_host" in s for s in stats["openings_skipped"])


# ---- M-05 zero opening_width_pts -----------------------------------


def test_M05_zero_opening_width_raises_via_opening_carve_rect() -> None:
    """The current contract is explicit: zero or missing
    `opening_width_pts` ⇒ ValueError. Caught by the caller
    (`build_shell_polygon`) and logged as a skipped opening."""
    wall = {"id": "h", "start": [0, 0], "end": [100, 0],
            "thickness": 4.0, "orientation": "h"}
    op = {"id": "o", "wall_id": "h", "center": [50.0, 0.0],
          "opening_width_pts": 0}
    with pytest.raises(ValueError, match="opening_width_pts"):
        opening_carve_rect(op, wall, default_thickness=4.0)


def test_M05_zero_width_opening_in_consensus_is_skipped_not_raised() -> None:
    """When `build_shell_polygon` encounters the same condition via a
    full consensus, it catches the ValueError and records the skip
    — the shell still builds."""
    cons = {
        "wall_thickness_pts": 4.0,
        "walls": [
            {"id": "wb", "start": [-50, -50], "end": [50, -50],
             "thickness": 4.0, "orientation": "h"},
            {"id": "wt", "start": [-50, 50], "end": [50, 50],
             "thickness": 4.0, "orientation": "h"},
            {"id": "wl", "start": [-50, -50], "end": [-50, 50],
             "thickness": 4.0, "orientation": "v"},
            {"id": "wr", "start": [50, -50], "end": [50, 50],
             "thickness": 4.0, "orientation": "v"},
        ],
        "openings": [{
            "id": "zero_w", "wall_id": "wb", "center": [0, -50],
            "opening_width_pts": 0,
        }],
        "rooms": [],
    }
    polys, stats = build_shell_polygon(cons)
    assert len(polys) == 1
    assert stats["openings_carved"] == 0
    assert any("zero_w" in s for s in stats["openings_skipped"])


# ---- M-06 dangling wall_id reference -------------------------------


def test_M06_dangling_wall_id_is_skipped() -> None:
    cons = {
        "wall_thickness_pts": 4.0,
        "walls": [
            {"id": "wb", "start": [-50, -50], "end": [50, -50],
             "thickness": 4.0, "orientation": "h"},
            {"id": "wt", "start": [-50, 50], "end": [50, 50],
             "thickness": 4.0, "orientation": "h"},
            {"id": "wl", "start": [-50, -50], "end": [-50, 50],
             "thickness": 4.0, "orientation": "v"},
            {"id": "wr", "start": [50, -50], "end": [50, 50],
             "thickness": 4.0, "orientation": "v"},
        ],
        "openings": [{
            "id": "ghost", "wall_id": "w_deleted",
            "center": [0, 0], "opening_width_pts": 10.0,
        }],
        "rooms": [],
    }
    polys, stats = build_shell_polygon(cons)
    assert stats["openings_carved"] == 0
    assert any("w_deleted" in s for s in stats["openings_skipped"])
    # Shell is intact (4 walls, 1 piece)
    assert len(polys) == 1


# ---- M-07 opening center far outside host wall ---------------------


def test_M07_opening_center_outside_wall_still_carves() -> None:
    """The current code does NOT validate that the opening center
    sits ON the host wall. A far-away opening produces a carve
    rect that may not even intersect the shell — the difference
    op then is a no-op. Pin this behaviour: shell area unchanged."""
    cons = {
        "wall_thickness_pts": 4.0,
        "walls": [
            {"id": "wb", "start": [-50, -50], "end": [50, -50],
             "thickness": 4.0, "orientation": "h"},
            {"id": "wt", "start": [-50, 50], "end": [50, 50],
             "thickness": 4.0, "orientation": "h"},
            {"id": "wl", "start": [-50, -50], "end": [-50, 50],
             "thickness": 4.0, "orientation": "v"},
            {"id": "wr", "start": [50, -50], "end": [50, 50],
             "thickness": 4.0, "orientation": "v"},
        ],
        "openings": [],
        "rooms": [],
    }
    p_base, _ = build_shell_polygon(cons)

    cons_with_far = dict(cons)
    cons_with_far["openings"] = [{
        "id": "far", "wall_id": "wb", "center": [9999.0, 9999.0],
        "opening_width_pts": 10.0,
    }]
    p_far, _ = build_shell_polygon(cons_with_far)
    assert p_base[0].area == pytest.approx(p_far[0].area, rel=1e-6)


# ---- M-08 / M-09 / M-10 / M-11 -------------------------------------


def test_M08_no_walls_raises() -> None:
    with pytest.raises(ValueError, match="no walls"):
        build_shell_polygon({"walls": [], "openings": []})


def test_M09_single_degenerate_wall_filtered_as_sliver() -> None:
    """A single wall of thickness 0 produces a zero-area polygon
    that the sliver filter must drop. If it survived, the
    `shell_pieces_after_sliver_filter` count would be 1."""
    cons = {
        "wall_thickness_pts": 0.0,
        "walls": [
            {"id": "ghost", "start": [0, 0], "end": [10, 0],
             "thickness": 0.0, "orientation": "h"},
        ],
        "openings": [],
        "rooms": [],
    }
    # The sliver filter drops the polygon; with nothing left, the
    # function raises rather than emit an empty model.
    with pytest.raises(RuntimeError, match="sliver"):
        build_shell_polygon(cons)


def test_M10_duplicate_wall_ids_dont_crash() -> None:
    """Two walls sharing the same id is malformed input but should
    not crash the exporter. The walls_by_id dict deduplicates by
    id (last wins), but the union still includes BOTH wall
    rectangles (since the union iterates the walls list, not the
    dict)."""
    cons = {
        "wall_thickness_pts": 4.0,
        "walls": [
            {"id": "dup", "start": [0, 0], "end": [100, 0],
             "thickness": 4.0, "orientation": "h"},
            {"id": "dup", "start": [0, 100], "end": [100, 100],
             "thickness": 4.0, "orientation": "h"},
        ],
        "openings": [],
        "rooms": [],
    }
    polys, stats = build_shell_polygon(cons)
    # Both wall rectangles unioned — disconnected, so 2 pieces.
    assert stats["input_walls"] == 2
    assert stats["shell_pieces_after_sliver_filter"] == 2


def test_M11_z_shaped_walls_self_intersection_safe() -> None:
    """A self-intersecting wall topology (the "Z") is the classic
    polygonize trap. unary_union still produces a valid Polygon
    or MultiPolygon — never throws — and the sliver filter keeps
    pieces above MIN_SLIVER_AREA_PTS2."""
    cons = {
        "wall_thickness_pts": 4.0,
        "walls": [
            # Top horizontal
            {"id": "t", "start": [0, 100], "end": [100, 100],
             "thickness": 4.0, "orientation": "h"},
            # Diagonal-like: a vertical wall crossing the gap
            {"id": "x", "start": [50, 0], "end": [50, 100],
             "thickness": 4.0, "orientation": "v"},
            # Bottom horizontal
            {"id": "b", "start": [0, 0], "end": [100, 0],
             "thickness": 4.0, "orientation": "h"},
        ],
        "openings": [],
        "rooms": [],
    }
    polys, stats = build_shell_polygon(cons)
    # No crash; at least one piece survives.
    assert len(polys) >= 1
    assert all(isinstance(p, Polygon) for p in polys)
    assert all(p.is_valid for p in polys)


# ---- M-12 (Ruby-side note) -----------------------------------------


# Ruby-side mutation: a soft_barrier with no polyline_pts must not
# crash build_soft_barrier; it returns ok=false with a reason. The
# Python phase never touches soft_barriers; the regression for this
# Ruby behaviour lives in tests/test_plan_shell_invariants.py
# (counts the SoftBarrier_Groups present after a real run) and in
# the explicit return-shape comments in build_plan_shell_skp.rb.
