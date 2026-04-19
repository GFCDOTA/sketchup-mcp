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
    # 4 short H strokes, 0 V in the same 120x120 cell -> H dominance fires.
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


def test_short_walls_survive_when_perpendicular_partners_present() -> None:
    # A short wall pair (2 H + 2 V) in one cell must not be dropped by the
    # orientation filter: the cell is balanced 2:2, not dominated. Using
    # _PAIR_MAX_GAP+50 = 150 px spacing keeps pair-merge from collapsing
    # the pairs so the assertion stays on wall count, not topology.
    candidates = [
        _h(page=0, y=20, x0=20, x1=60),    # short H
        _h(page=0, y=170, x0=20, x1=60),   # short H (gap 150, > PAIR_MAX_GAP)
        _v(page=0, x=20, y0=20, y1=60),    # short V
        _v(page=0, x=170, y0=20, y1=60),   # short V (gap 150)
    ]
    walls = classify_walls(candidates)
    # All four short strokes survive: cell counts per orientation are 2
    # each, not dominant; pair-merge skips because gaps exceed its range.
    assert len(walls) == 4


def test_length_exactly_at_threshold_is_protected() -> None:
    # Strokes with length == _IMBALANCE_MAX_STROKE_LENGTH (100 px) are
    # treated as "long" and protected from dropping even in a dominated
    # cell. The check is `length < threshold` strictly, so length == 100
    # survives.
    candidates = [
        _h(page=0, y=10, x0=10, x1=110),   # len exactly 100
        _h(page=0, y=45, x0=10, x1=50),    # short, dropped
        _h(page=0, y=80, x0=10, x1=50),    # short, dropped
        _h(page=0, y=115, x0=10, x1=50),   # short, dropped
    ]
    walls = classify_walls(candidates)
    assert len(walls) == 1
    wall = walls[0]
    assert (wall.end[0] - wall.start[0]) == 100


def test_ratio_exactly_at_threshold_fires() -> None:
    # _IMBALANCE_RATIO = 4.0 with inclusive >= comparison: 4 H, 1 V in the
    # same cell satisfies H >= 4 * max(1, V=1) = 4, so H is dominant. The
    # 4 short H strokes drop; the lone V stroke stays.
    candidates = [
        _h(page=0, y=10, x0=10, x1=50),
        _h(page=0, y=45, x0=10, x1=50),
        _h(page=0, y=80, x0=10, x1=50),
        _h(page=0, y=115, x0=10, x1=50),
        _v(page=0, x=60, y0=10, y1=50),
    ]
    walls = classify_walls(candidates)
    assert len(walls) == 1
    assert walls[0].orientation == "vertical"


def test_midpoint_on_cell_boundary_is_deterministic() -> None:
    # Midpoint x = 120 sits exactly on the boundary between cell (0, *)
    # and cell (1, *). `int(120 // 120) == 1` so the stroke belongs to
    # cell (1, 0). Five short H strokes with midpoints on this boundary
    # end up in the same cell and drop together.
    candidates = [_h(page=0, y=10 + i * 40, x0=100, x1=140) for i in range(4)]
    # midpoints: x=120, y=10,50,90,130 -> cells (1,0),(1,0),(1,0),(1,1)
    # cell (1,0) has 3 H; cell (1,1) has 1 H. (1,0) total=3 < 4 -> not fired
    walls = classify_walls(candidates)
    # All 4 preserved because no single cell reaches MIN_TOTAL=4
    assert len(walls) == 4


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
