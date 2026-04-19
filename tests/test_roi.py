"""Synthetic tests for the ROI detector. These run BEFORE any real PDF.

Each fixture is a 600x600 raster painted with two kinds of strokes:
- "architectural": rectangles whose perpendicular pairs produce many
  T/cross junctions when classified.
- "noise": short isolated horizontals or random short stubs that mostly
  produce dangling-end junctions.

The tests exercise detect_architectural_roi directly so the ROI logic is
validated independently of the rest of the pipeline.
"""
from __future__ import annotations

import cv2
import numpy as np
import pytest

from roi.service import detect_architectural_roi


def _blank(size: int = 600) -> np.ndarray:
    return np.full((size, size, 3), 255, dtype=np.uint8)


def _draw_plan(canvas: np.ndarray, x0: int, y0: int, x1: int, y1: int) -> None:
    # Outer rectangle + interior cross + two extra subdividers, so the
    # plan produces enough T/cross junctions for the ROI density check
    # (corners of a bare rectangle are pass-through, not T/cross).
    cv2.rectangle(canvas, (x0, y0), (x1, y1), (0, 0, 0), thickness=6)
    mid_x = (x0 + x1) // 2
    mid_y = (y0 + y1) // 2
    cv2.line(canvas, (x0, mid_y), (x1, mid_y), (0, 0, 0), thickness=6)
    cv2.line(canvas, (mid_x, y0), (mid_x, y1), (0, 0, 0), thickness=6)
    # subdivide each quadrant with an additional perpendicular stub to
    # multiply T-junctions
    q1_x = (x0 + mid_x) // 2
    q3_x = (mid_x + x1) // 2
    q1_y = (y0 + mid_y) // 2
    q3_y = (mid_y + y1) // 2
    cv2.line(canvas, (q1_x, y0), (q1_x, mid_y), (0, 0, 0), thickness=6)
    cv2.line(canvas, (q3_x, mid_y), (q3_x, y1), (0, 0, 0), thickness=6)
    cv2.line(canvas, (x0, q1_y), (mid_x, q1_y), (0, 0, 0), thickness=6)
    cv2.line(canvas, (mid_x, q3_y), (x1, q3_y), (0, 0, 0), thickness=6)


def _scatter_short_horizontals(canvas: np.ndarray, region: tuple[int, int, int, int], count: int, seed: int) -> None:
    rng = np.random.default_rng(seed)
    x0, y0, x1, y1 = region
    for _ in range(count):
        y = int(rng.integers(y0, y1))
        sx = int(rng.integers(x0, x1 - 40))
        cv2.line(canvas, (sx, y), (sx + 30, y), (0, 0, 0), thickness=2)


# 1 — plan centered, noise around it ----------------------------------

def test_roi_finds_centered_plan() -> None:
    canvas = _blank()
    _draw_plan(canvas, 200, 200, 400, 400)
    _scatter_short_horizontals(canvas, (10, 10, 590, 180), count=30, seed=1)
    _scatter_short_horizontals(canvas, (10, 420, 590, 590), count=30, seed=2)

    result = detect_architectural_roi(canvas)
    assert result.applied is True, result
    assert result.bbox is not None
    min_x, min_y, max_x, max_y = result.bbox
    cx = (min_x + max_x) / 2
    cy = (min_y + max_y) / 2
    # Plan centered at ~(300, 300); allow margin + grid quantization slack.
    assert 220 < cx < 380, (cx, result.bbox)
    assert 220 < cy < 380, (cy, result.bbox)


# 2 — plan offset, ROI must follow it ---------------------------------

def test_roi_follows_offset_plan() -> None:
    canvas = _blank()
    _draw_plan(canvas, 380, 380, 560, 560)
    _scatter_short_horizontals(canvas, (10, 10, 590, 200), count=20, seed=3)

    result = detect_architectural_roi(canvas)
    assert result.applied is True, result
    min_x, min_y, max_x, max_y = result.bbox
    assert min_x >= 300, result.bbox
    assert min_y >= 300, result.bbox
    assert max_x <= 600 and max_y <= 600


# 3 — plan + dense text block; ROI must pick the plan ----------------

def test_roi_picks_plan_over_text_block() -> None:
    canvas = _blank()
    _draw_plan(canvas, 80, 80, 280, 280)
    # Dense parallel horizontal stack on the right (text-like)
    for k in range(15):
        y = 320 + k * 14
        cv2.line(canvas, (320, y), (560, y), (0, 0, 0), thickness=2)

    result = detect_architectural_roi(canvas)
    assert result.applied is True, result
    min_x, min_y, max_x, max_y = result.bbox
    # The plan center is roughly (180, 180); the text block is on the
    # right (x ~ 440). ROI must lean left.
    assert (min_x + max_x) / 2 < 320, ((min_x, max_x), result)


# 4 — degenerate page: no clear architectural cluster ----------------

def test_roi_falls_back_when_no_clear_region() -> None:
    canvas = _blank()
    _scatter_short_horizontals(canvas, (10, 10, 590, 590), count=200, seed=99)

    result = detect_architectural_roi(canvas)
    assert result.applied is False, result
    assert result.fallback_reason is not None


def test_roi_falls_back_on_blank_image() -> None:
    canvas = _blank()
    result = detect_architectural_roi(canvas)
    assert result.applied is False
    assert result.fallback_reason in {"no_components", "no_dominant_component"}
