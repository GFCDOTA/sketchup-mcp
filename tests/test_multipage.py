from __future__ import annotations

from classify.service import classify_walls
from model.types import WallCandidate
from topology.service import build_topology


def _h(page: int, y: float, x0: float, x1: float, thickness: float = 8.0) -> WallCandidate:
    return WallCandidate(
        page_index=page,
        start=(x0, y),
        end=(x1, y),
        thickness=thickness,
        source="test_horizontal",
        confidence=1.0,
    )


def _v(page: int, x: float, y0: float, y1: float, thickness: float = 8.0) -> WallCandidate:
    return WallCandidate(
        page_index=page,
        start=(x, y0),
        end=(x, y1),
        thickness=thickness,
        source="test_vertical",
        confidence=1.0,
    )


def test_classify_keeps_pages_separate_when_coords_collide() -> None:
    # Two pages, each with a complete square at EXACTLY the same coordinates.
    square_page_0 = [
        _h(0, 40, 40, 200),
        _h(0, 200, 40, 200),
        _v(0, 40, 40, 200),
        _v(0, 200, 40, 200),
    ]
    square_page_1 = [
        _h(1, 40, 40, 200),
        _h(1, 200, 40, 200),
        _v(1, 40, 40, 200),
        _v(1, 200, 40, 200),
    ]
    walls = classify_walls(square_page_0 + square_page_1)

    pages = {wall.page_index for wall in walls}
    assert pages == {0, 1}, f"expected both pages preserved, got {pages}"

    per_page_count = {p: sum(1 for w in walls if w.page_index == p) for p in pages}
    # Each page has 4 edges; shared coords between pages must not collapse them.
    assert per_page_count == {0: 4, 1: 4}, per_page_count


def test_topology_does_not_connect_across_pages() -> None:
    # Same square on page 0 and page 1; topology must not create cross-page edges.
    walls_page_0 = classify_walls(
        [
            _h(0, 40, 40, 200),
            _h(0, 200, 40, 200),
            _v(0, 40, 40, 200),
            _v(0, 200, 40, 200),
        ]
    )
    walls_page_1 = classify_walls(
        [
            _h(1, 40, 40, 200),
            _h(1, 200, 40, 200),
            _v(1, 40, 40, 200),
            _v(1, 200, 40, 200),
        ]
    )
    split_walls, _, rooms, report = build_topology(walls_page_0 + walls_page_1)

    # Each page must produce its own room; no cross-page merging.
    assert len(rooms) == 2, f"expected one room per page, got {len(rooms)}"

    # Each split_wall must keep its original page_index.
    pages_seen = {wall.page_index for wall in split_walls}
    assert pages_seen == {0, 1}

    # Graph should have two components (one per page), never merged.
    assert report.component_count == 2, report
