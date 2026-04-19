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


def test_multipage_connected_pages_do_not_warn_disconnected() -> None:
    # Two pages, each a self-contained square. Each page's graph is a single
    # component; only the aggregate sees 2 components. walls_disconnected
    # warns on intra-page disconnection, so it must NOT fire here.
    from model.pipeline import _build_warnings

    walls = classify_walls(
        [
            _h(0, 40, 40, 200), _h(0, 200, 40, 200),
            _v(0, 40, 40, 200), _v(0, 200, 40, 200),
            _h(1, 40, 40, 200), _h(1, 200, 40, 200),
            _v(1, 40, 40, 200), _v(1, 200, 40, 200),
        ]
    )
    split_walls, _, rooms, report = build_topology(walls)

    assert report.page_count == 2
    assert report.component_count == 2  # aggregate
    assert report.max_components_within_page == 1  # per-page

    warnings = _build_warnings(
        candidates=[object()],  # non-empty stand-in
        walls=walls,
        split_walls=split_walls,
        rooms=rooms,
        connectivity_report=report,
    )
    assert "walls_disconnected" not in warnings, warnings


def test_multipage_connected_pages_keep_full_topology_score() -> None:
    # Two pages, each self-contained square. topology_score must not be
    # penalised for structural page partitioning: each page is internally
    # fully connected, so score should be 1.0.
    from model.pipeline import _topology_score

    walls = classify_walls(
        [
            _h(0, 40, 40, 200), _h(0, 200, 40, 200),
            _v(0, 40, 40, 200), _v(0, 200, 40, 200),
            _h(1, 40, 40, 200), _h(1, 200, 40, 200),
            _v(1, 40, 40, 200), _v(1, 200, 40, 200),
        ]
    )
    split_walls, _, _, report = build_topology(walls)

    assert report.min_intra_page_connectivity_ratio == 1.0, report
    assert report.max_components_within_page == 1, report
    assert _topology_score(split_walls, report) == 1.0


def test_many_orphan_components_warning_fires() -> None:
    # Build Wall objects directly so we exercise topology+pipeline warning
    # logic without classify reshaping the fixture. Six isolated horizontal
    # pairs at far-apart y coords and different x positions: each pair is
    # its own 2-node component (size 2 <= _ORPHAN_COMPONENT_MAX_NODES).
    from model.pipeline import _build_warnings
    from model.types import Wall

    walls: list[Wall] = []
    for i in range(6):
        walls.append(
            Wall(
                wall_id=f"wall-{i}",
                page_index=0,
                start=(10.0 + i * 200, 50.0 + i * 400),
                end=(60.0 + i * 200, 50.0 + i * 400),
                thickness=4.0,
                orientation="horizontal",
                source="synthetic",
                confidence=1.0,
            )
        )

    split_walls, _, rooms, report = build_topology(walls)

    assert report.orphan_component_count >= 5, report
    warnings = _build_warnings(
        candidates=[object()],
        walls=walls,
        split_walls=split_walls,
        rooms=rooms,
        connectivity_report=report,
    )
    assert "many_orphan_components" in warnings, warnings


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
