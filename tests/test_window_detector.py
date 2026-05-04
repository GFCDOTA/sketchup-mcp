"""Tests for the window-detector pieces of tools.extract_openings_vector.

Pure-geometry tests that don't need a PDF: feed bboxes/walls
synthetically and check the classification + projection +
deduplication helpers.

The full ``detect_openings`` pathway calls into pdfium via
``page.get_objects()`` which we don't try to mock — those are
integration-tested manually against ``runs/vector/consensus_model.json``
and documented in ``docs/validation/window_detector.md``.
"""
from __future__ import annotations

from tools import extract_openings_vector as eov


# ---------------------------------------------------------------------------
# _is_window_shape — pure classifier
# ---------------------------------------------------------------------------


def test_typical_window_passes():
    # 100 pt long, 7 pt deep — long, thin, no curves, in a 5.4 pt wall
    assert eov._is_window_shape((0.0, 0.0, 100.0, 7.0), n_cubic=0, thickness=5.4)


def test_window_shape_ignores_cubic_count():
    """Many PDF generators emit cubic Bezier primitives even for
    straight lines. The aspect-based filter (>=3 vs door arcs'
    0.4..2.5) is what distinguishes window from door, NOT n_cubic.
    A window-shaped bbox stays a window even with cubic segments."""
    assert eov._is_window_shape(
        (0.0, 0.0, 100.0, 7.0), n_cubic=2, thickness=5.4
    )


def test_window_too_short_rejected():
    """Long side below WINDOW_LONG_MIN means it's noise / a fixture."""
    assert not eov._is_window_shape(
        (0.0, 0.0, 18.0, 7.0), n_cubic=0, thickness=5.4
    )


def test_window_too_long_rejected():
    """A 5 m wall section that's exactly thickness deep is not a window."""
    assert not eov._is_window_shape(
        (0.0, 0.0, 400.0, 7.0), n_cubic=0, thickness=5.4
    )


def test_window_too_thick_rejected():
    """Short side wider than thickness * factor — probably a door leaf
    or a fixture, not a window."""
    assert not eov._is_window_shape(
        (0.0, 0.0, 100.0, 18.0), n_cubic=0, thickness=5.4
    )


def test_window_low_aspect_rejected():
    """30x20 — too square. Door arcs and fixtures, not windows."""
    assert not eov._is_window_shape(
        (0.0, 0.0, 30.0, 20.0), n_cubic=0, thickness=5.4
    )


def test_window_zero_short_side_rejected_safely():
    """Degenerate bbox must not divide-by-zero."""
    assert not eov._is_window_shape(
        (0.0, 0.0, 100.0, 0.0), n_cubic=0, thickness=5.4
    )


def test_window_orientation_independent():
    """Same shape rotated 90° should still classify as window."""
    h_oriented = eov._is_window_shape(
        (0.0, 0.0, 100.0, 7.0), n_cubic=0, thickness=5.4
    )
    v_oriented = eov._is_window_shape(
        (0.0, 0.0, 7.0, 100.0), n_cubic=0, thickness=5.4
    )
    assert h_oriented and v_oriented


# ---------------------------------------------------------------------------
# _window_to_wall — projection + distance threshold
# ---------------------------------------------------------------------------


def _wall(id_, start, end):
    return {"id": id_, "start": list(start), "end": list(end)}


def _window(bbox):
    return eov.WindowCandidate(bbox=bbox, n_seg=2)


def test_window_attaches_to_nearest_wall():
    # Window centered at (50, 0.5), wall along y=0 from x=0..100.
    walls = [
        _wall("w1", (0, 0), (100, 0)),
        _wall("w2", (0, 50), (100, 50)),  # far away
    ]
    win = _window((20.0, -3.0, 80.0, 4.0))   # cx=50, cy=0.5
    wall, proj, dist = eov._window_to_wall(win, walls, thickness=5.4)
    assert wall is not None
    assert wall["id"] == "w1"
    assert abs(proj[0] - 50.0) < 1e-6
    assert abs(proj[1] - 0.0) < 1e-6
    assert dist < 1.0


def test_window_too_far_from_any_wall_returns_none():
    walls = [_wall("w1", (0, 0), (100, 0))]
    # Center at (50, 30) — way off any wall
    win = _window((20.0, 28.0, 80.0, 32.0))
    wall, _, _ = eov._window_to_wall(win, walls, thickness=5.4)
    assert wall is None


def test_window_covering_almost_entire_wall_rejected_as_outline():
    """If a candidate's long side is >= WALL_LEN_RATIO_MAX of the wall
    length, it's almost certainly the wall's own stroked outline, not
    a window opening. Reject."""
    walls = [_wall("w1", (0, 0), (50, 0))]
    # Window long side 49 == 98 % of wall — clearly the outline.
    win = _window((0.5, -3.0, 49.5, 4.0))
    wall, _, _ = eov._window_to_wall(win, walls, thickness=5.4)
    assert wall is None


def test_window_at_half_wall_length_passes():
    """A window covering ~half the wall is a normal opening."""
    walls = [_wall("w1", (0, 0), (200, 0))]
    win = _window((50.0, -3.0, 130.0, 4.0))   # 80 pt long, 40 % of wall
    wall, _, _ = eov._window_to_wall(win, walls, thickness=5.4)
    assert wall is not None
    assert wall["id"] == "w1"


# ---------------------------------------------------------------------------
# _window_overlaps_arc — dedupe vs door arcs
# ---------------------------------------------------------------------------


def test_window_overlapping_arc_is_flagged():
    """Door drawn with a leaf rectangle (no curves) plus arc on the
    same bbox: the rectangle would qualify as a window, but should
    be filtered out because the arc covers it."""
    win = _window((0.0, 0.0, 60.0, 7.0))
    arc_bboxes = [(0.0, 0.0, 60.0, 60.0)]
    assert eov._window_overlaps_arc(win, arc_bboxes)


def test_window_not_overlapping_arc_passes():
    win = _window((100.0, 0.0, 200.0, 7.0))
    arc_bboxes = [(0.0, 0.0, 60.0, 60.0)]
    assert not eov._window_overlaps_arc(win, arc_bboxes)


def test_window_overlap_with_no_arcs_passes():
    win = _window((0.0, 0.0, 100.0, 7.0))
    assert not eov._window_overlaps_arc(win, [])


def test_window_overlap_threshold_partial_overlap_does_not_dedupe():
    """A small partial overlap (< 50 %) shouldn't drop a real window."""
    win = _window((0.0, 0.0, 100.0, 7.0))   # area=700
    # arc bbox barely clips the window's left edge
    arc_bboxes = [(-50.0, -10.0, 5.0, 17.0)]   # area=27*55=1485, intersect=5*7=35
    # 35/min(700,1485) = 35/700 = 0.05 — far below 0.5
    assert not eov._window_overlaps_arc(win, arc_bboxes)


# ---------------------------------------------------------------------------
# _emit_window_opening — schema/contract
# ---------------------------------------------------------------------------


def test_emit_window_opening_has_window_kind_and_no_hinge():
    win = _window((20.0, -3.0, 80.0, 4.0))
    wall = _wall("w1", (0, 0), (100, 0))
    proj = (50.0, 0.0)
    dist = 0.5
    op = eov._emit_window_opening(win, wall, proj, dist, thickness=5.4, idx=7)
    assert op["kind"] == "window"
    assert op["geometry_origin"] == "svg_segments"
    assert op["wall_id"] == "w1"
    assert op["id"] == "o007"
    assert op["center"] == [50.0, 0.0]
    assert "hinge_side" not in op
    assert "hinge_corner_pt" not in op
    assert "swing_deg" not in op
    assert op["opening_width_pts"] == 60.0  # max(60, 7)
    assert 0.0 <= op["confidence"] <= 1.0


def test_emit_window_opening_confidence_higher_when_centered_on_wall():
    """A window perfectly centered on a wall (dist=0) should score
    higher confidence than the same window 0.5 thickness away."""
    win = _window((20.0, -3.0, 80.0, 4.0))
    wall = _wall("w1", (0, 0), (100, 0))
    op_centered = eov._emit_window_opening(
        win, wall, proj=(50.0, 0.0), dist=0.0, thickness=5.4, idx=0,
    )
    op_offset = eov._emit_window_opening(
        win, wall, proj=(50.0, 0.0), dist=2.5, thickness=5.4, idx=1,
    )
    assert op_centered["confidence"] >= op_offset["confidence"]


# ---------------------------------------------------------------------------
# Door-classifier invariance — make sure the new code didn't break doors
# ---------------------------------------------------------------------------


def test_door_arc_shape_still_excluded_from_window_shape():
    """A typical door arc bbox (~60x60) must NOT be classified as a
    window — the aspect filter (>=3) is what excludes it, regardless
    of cubic count."""
    bbox = (0.0, 0.0, 60.0, 60.0)
    assert not eov._is_window_shape(bbox, n_cubic=2, thickness=5.4)
    assert not eov._is_window_shape(bbox, n_cubic=0, thickness=5.4)


def test_arc_candidate_dataclass_unchanged():
    """Smoke-test that the existing ArcCandidate API still exposes
    the properties the old door pipeline relies on."""
    arc = eov.ArcCandidate(bbox=(0.0, 0.0, 60.0, 60.0), n_seg=4, n_cubic=2)
    assert arc.w == 60.0
    assert arc.h == 60.0
    assert arc.cx == 30.0
    assert arc.cy == 30.0
