from __future__ import annotations

from classify.service import classify_walls
from model.types import WallCandidate


def _h(page: int, y: float, x0: float, x1: float, thickness: float = 3.0) -> WallCandidate:
    return WallCandidate(
        page_index=page,
        start=(x0, y),
        end=(x1, y),
        thickness=thickness,
        source="test_h",
        confidence=1.0,
    )


def _v(page: int, x: float, y0: float, y1: float, thickness: float = 3.0) -> WallCandidate:
    return WallCandidate(
        page_index=page,
        start=(x, y0),
        end=(x, y1),
        thickness=thickness,
        source="test_v",
        confidence=1.0,
    )


def test_balanced_region_keeps_all_short_strokes() -> None:
    # Four short H plus four short V strokes in one cell -> balanced.
    # Dispersed at large perpendicular gaps so the text filter does not fire.
    candidates = [
        _h(page=0, y=10, x0=10, x1=50),
        _h(page=0, y=60, x0=10, x1=50),
        _h(page=0, y=110, x0=10, x1=50),
        _h(page=0, y=160, x0=10, x1=50),
        _v(page=0, x=10, y0=10, y1=50),
        _v(page=0, x=60, y0=10, y1=50),
        _v(page=0, x=110, y0=10, y1=50),
        _v(page=0, x=160, y0=10, y1=50),
    ]
    walls = classify_walls(candidates)
    assert len(walls) == 8


def test_h_dominated_cell_drops_short_h_strokes() -> None:
    # 6 short H strokes, 0 V in the same 120x120 cell -> H dominance fires.
    # Perpendicular gaps > _TEXT_CHAIN_MAX_GAP so text filter does NOT catch
    # them (this exercises orientation-dominance alone).
    candidates = [
        _h(page=0, y=10, x0=10, x1=50),
        _h(page=0, y=45, x0=10, x1=50),   # gap 35 (> TEXT_CHAIN_MAX_GAP=30)
        _h(page=0, y=80, x0=10, x1=50),   # gap 35
        _h(page=0, y=115, x0=10, x1=50),  # gap 35
    ]
    walls = classify_walls(candidates)
    assert walls == [], [(w.start, w.end) for w in walls]


def test_long_h_stroke_survives_h_dominated_cell() -> None:
    # Long H stroke (length 200 > _IMBALANCE_MAX_STROKE_LENGTH=100) must
    # survive even when the cell is H-dominated.
    candidates = [
        _h(page=0, y=10, x0=10, x1=50),
        _h(page=0, y=45, x0=10, x1=50),
        _h(page=0, y=80, x0=10, x1=50),
        _h(page=0, y=115, x0=10, x1=210),  # len 200
    ]
    walls = classify_walls(candidates)
    # only the long stroke remains
    assert len(walls) == 1
    remaining = walls[0]
    assert (remaining.end[0] - remaining.start[0]) == 200


def test_l_shape_survives_orientation_filter() -> None:
    # L-shape: 3 H strokes, 3 V strokes arranged around a closed region.
    # Different cells, so no cell is imbalanced; everything must survive
    # and still produce a valid topology downstream.
    candidates = [
        _h(page=0, y=40,  x0=40,  x1=200),
        _h(page=0, y=100, x0=120, x1=200),
        _h(page=0, y=200, x0=40,  x1=120),
        _v(page=0, x=40,  y0=40,  y1=200),
        _v(page=0, x=120, y0=100, y1=200),
        _v(page=0, x=200, y0=40,  y1=100),
    ]
    walls = classify_walls(candidates)
    assert len(walls) == 6


def test_filter_is_page_scoped() -> None:
    # An H-imbalanced cell on page 0 must not affect page 1.
    candidates = [
        _h(page=0, y=10, x0=10, x1=50),
        _h(page=0, y=45, x0=10, x1=50),
        _h(page=0, y=80, x0=10, x1=50),
        _h(page=0, y=115, x0=10, x1=50),
        # page 1 lone short horizontal -> survives (no dominance on that page)
        _h(page=1, y=50, x0=10, x1=50),
    ]
    walls = classify_walls(candidates)
    assert len(walls) == 1
    assert walls[0].page_index == 1
