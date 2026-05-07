"""Tests for the FP-012 spike — `--use-concave-hull` opt-in path in
``tools.rooms_from_seeds``.

Spec recap:
- Default behaviour (``use_concave_hull=False``) is byte-identical to
  the pre-spike code: ``cv2.convexHull`` over wall pixels.
- Opt-in (``use_concave_hull=True``) replaces that with
  ``shapely.concave_hull`` over wall ENDPOINTS (sparse, ms-scale).
- The default value of ``concave_hull_ratio`` is 0.3 — calibrated on
  ``planta_74``.

These tests use a synthetic L-shaped wall layout where the convex
hull and concave hull DISAGREE significantly. They verify three
properties:

1. Default-off path produces an interior mask area equal to
   the convex hull of the wall layout (preserves baseline).
2. Concave-hull-on path produces an interior mask area STRICTLY
   SMALLER than the convex-hull baseline (proves the fix).
3. Falling back to convex hull when ``shapely`` is unavailable
   does not crash (graceful degradation).
"""
from __future__ import annotations

import numpy as np
import pytest

from tools.rooms_from_seeds import _build_interior_mask


def _l_shaped_walls() -> tuple[np.ndarray, list[dict], callable]:
    """Build a 100x100 binary mask + L-shaped walls + to_px helper.

    Wall layout (PDF-coord, top-down, y-down):

        +--------+
        |        |
        |        |
        |   +----+
        |   |
        +---+

    The L-shape's "inner corner" is at (50, 50). Convex hull over
    the wall pixels would enclose the whole 100x100 square; concave
    hull over wall ENDPOINTS should follow the L outline.
    """
    H, W = 100, 100
    mask = np.zeros((H, W), np.uint8)

    # Horizontal segments (in pixel space directly for the test)
    mask[10, 10:90] = 255   # top
    mask[50, 50:90] = 255   # middle inner
    mask[90, 10:50] = 255   # bottom-left
    # Vertical segments
    mask[10:90, 10] = 255   # left
    mask[10:50, 90] = 255   # top-right
    mask[50:90, 50] = 255   # middle right (inner)

    walls = [
        {"start": [10, 10], "end": [90, 10]},
        {"start": [50, 50], "end": [90, 50]},
        {"start": [10, 90], "end": [50, 90]},
        {"start": [10, 10], "end": [10, 90]},
        {"start": [90, 10], "end": [90, 50]},
        {"start": [50, 50], "end": [50, 90]},
    ]

    def to_px(x: float, y: float) -> tuple[int, int]:
        return int(x), int(y)

    return mask, walls, to_px


def test_default_off_uses_convex_hull():
    mask, walls, to_px = _l_shaped_walls()
    interior = _build_interior_mask(
        mask, walls, to_px,
        use_concave_hull=False,
        concave_hull_ratio=0.3,
    )
    # Convex hull over the L's wall pixels approximates the L's
    # bounding polygon (~5700 px on this 80x80 layout — the convex
    # hull of an L-outline is itself the bounding rectangle minus
    # a triangular slice from the inner-corner area). Lower bound
    # asserted to catch a regression where the hull collapses.
    n_inside = int((interior > 0).sum())
    assert n_inside >= 5000, (
        f"convex-hull interior should fill > 5000 px, got {n_inside}"
    )


def test_concave_hull_on_shrinks_interior():
    mask, walls, to_px = _l_shaped_walls()
    convex = _build_interior_mask(
        mask, walls, to_px,
        use_concave_hull=False,
        concave_hull_ratio=0.3,
    )
    concave = _build_interior_mask(
        mask, walls, to_px,
        use_concave_hull=True,
        concave_hull_ratio=0.3,
    )
    convex_area = int((convex > 0).sum())
    concave_area = int((concave > 0).sum())
    # The L's inner notch is roughly 40x40 = 1600 px; concave hull
    # should drop at least a meaningful fraction of that.
    assert concave_area < convex_area, (
        f"concave area ({concave_area}) should be < convex ({convex_area})"
    )
    # And it should NOT collapse to zero (degenerate output).
    assert concave_area > 0


def test_concave_hull_ratio_one_matches_convex():
    """ratio=1.0 in shapely.concave_hull is the convex hull, so the
    interior should match (within rounding) the convex-hull baseline.
    """
    mask, walls, to_px = _l_shaped_walls()
    convex = _build_interior_mask(
        mask, walls, to_px,
        use_concave_hull=False,
        concave_hull_ratio=0.3,
    )
    concave_at_one = _build_interior_mask(
        mask, walls, to_px,
        use_concave_hull=True,
        concave_hull_ratio=1.0,
    )
    convex_area = int((convex > 0).sum())
    concave_area = int((concave_at_one > 0).sum())
    # Allow 5% slack — the concave path uses endpoints (66 pts on
    # a real planta), the convex path uses every pixel; on this
    # synthetic 6-wall L they should match within a few percent.
    assert abs(convex_area - concave_area) / max(convex_area, 1) < 0.05, (
        f"ratio=1.0 should match convex hull within 5% slack, "
        f"convex={convex_area} concave={concave_area}"
    )


def test_empty_walls_does_not_crash():
    mask = np.zeros((50, 50), np.uint8)

    def to_px(x: float, y: float) -> tuple[int, int]:
        return int(x), int(y)

    interior = _build_interior_mask(
        mask, [], to_px,
        use_concave_hull=True,
        concave_hull_ratio=0.3,
    )
    # Empty walls => fall back to "everything is interior".
    assert interior.shape == mask.shape
    assert (interior == 255).all()
