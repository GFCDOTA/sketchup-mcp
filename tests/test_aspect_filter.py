from __future__ import annotations

from classify.service import classify_walls
from model.types import WallCandidate


def _h(y: float, x0: float, x1: float, thickness: float) -> WallCandidate:
    return WallCandidate(
        page_index=0,
        start=(x0, y),
        end=(x1, y),
        thickness=thickness,
        source="test_h",
        confidence=1.0,
    )


def test_chunky_stroke_is_dropped() -> None:
    # length 10 / thickness 20 -> aspect 0.5, well below 1.5 threshold.
    walls = classify_walls([_h(y=10, x0=10, x1=20, thickness=20.0)])
    assert walls == []


def test_square_stroke_is_dropped() -> None:
    # length == thickness -> aspect 1, below threshold.
    walls = classify_walls([_h(y=10, x0=10, x1=20, thickness=10.0)])
    assert walls == []


def test_aspect_at_threshold_survives() -> None:
    # length / thickness == 2.0 exactly (_MIN_ASPECT_RATIO). Comparison is
    # `>=`, so the stroke just barely passes.
    walls = classify_walls([_h(y=10, x0=10, x1=30, thickness=10.0)])
    assert len(walls) == 1


def test_long_thin_stroke_survives() -> None:
    walls = classify_walls([_h(y=10, x0=10, x1=210, thickness=2.0)])
    assert len(walls) == 1


def test_zero_thickness_stroke_is_not_dropped_by_aspect_filter() -> None:
    # Thickness 0 makes the ratio undefined. The filter leaves the stroke
    # alone; downstream stages may still drop it via other rules.
    walls = classify_walls([_h(y=10, x0=10, x1=50, thickness=0.0)])
    assert len(walls) == 1
