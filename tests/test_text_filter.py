from __future__ import annotations

from classify.service import classify_walls
from model.types import WallCandidate


def _h(page: int, y: float, x0: float, x1: float, thickness: float = 2.0) -> WallCandidate:
    return WallCandidate(
        page_index=page,
        start=(x0, y),
        end=(x1, y),
        thickness=thickness,
        source="test_h",
        confidence=1.0,
    )


def _v(page: int, x: float, y0: float, y1: float, thickness: float = 2.0) -> WallCandidate:
    return WallCandidate(
        page_index=page,
        start=(x, y0),
        end=(x, y1),
        thickness=thickness,
        source="test_v",
        confidence=1.0,
    )


def test_text_baseline_stack_is_removed() -> None:
    # Five horizontal baselines 15 px apart, all spanning x=10..110. That is
    # the signature of a paragraph block (NOTAS / LEGENDA). None should
    # survive as walls.
    candidates = [_h(page=0, y=40 + k * 15, x0=10, x1=110) for k in range(5)]
    walls = classify_walls(candidates)
    assert walls == [], [(w.start, w.end) for w in walls]


def test_vertical_text_like_stack_is_removed() -> None:
    # Same pattern but vertical (a column label block).
    candidates = [_v(page=0, x=40 + k * 12, y0=10, y1=110) for k in range(4)]
    walls = classify_walls(candidates)
    assert walls == []


def test_two_parallel_walls_survive() -> None:
    # A classic double-line wall pair: 2 strokes, not a 3+ chain.
    candidates = [
        _h(page=0, y=40, x0=10, x1=110, thickness=2.0),
        _h(page=0, y=70, x0=10, x1=110, thickness=2.0),
    ]
    walls = classify_walls(candidates)
    # pair-merge collapses them into one centerline; the filter must not have
    # removed them first.
    assert len(walls) == 1
    assert walls[0].thickness == 30.0


def test_chain_without_parallel_overlap_is_preserved() -> None:
    # Three horizontal strokes at uniform y-spacing but in different x
    # regions. They are NOT a text block (no shared column), so the filter
    # must leave them alone.
    candidates = [
        _h(page=0, y=40, x0=10, x1=60),
        _h(page=0, y=55, x0=300, x1=350),
        _h(page=0, y=70, x0=600, x1=650),
    ]
    walls = classify_walls(candidates)
    assert len(walls) == 3


def test_non_uniform_gaps_are_not_treated_as_text() -> None:
    # Three strokes at irregular perpendicular spacing (15 px and 45 px):
    # the text filter must not treat them as a text block. The downstream
    # pair-merge will still merge the first two into one wall centerline
    # because their gap falls in the pair-merge range, so the pipeline
    # emits two walls, not three. The assertion here pins the filter
    # behaviour: nothing gets dropped.
    candidates = [
        _h(page=0, y=40, x0=10, x1=110),
        _h(page=0, y=55, x0=10, x1=110),   # gap 15
        _h(page=0, y=100, x0=10, x1=110),  # gap 45 -> non-uniform
    ]
    walls = classify_walls(candidates)
    assert len(walls) == 2, [(w.start, w.end, w.thickness) for w in walls]
    # first wall is the pair-merged centerline of the 15-px spaced pair
    assert any(w.thickness == 15.0 for w in walls)
    # second wall is the lone stroke at y=100
    assert any(w.start[1] == 100.0 for w in walls)


def test_filter_respects_page_isolation() -> None:
    # A text stack on page 0 must not poison strokes on page 1.
    text_page_0 = [_h(page=0, y=40 + k * 15, x0=10, x1=110) for k in range(4)]
    wall_page_1 = [
        _h(page=1, y=100, x0=10, x1=110, thickness=2.0),
        _h(page=1, y=140, x0=10, x1=110, thickness=2.0),
    ]
    walls = classify_walls(text_page_0 + wall_page_1)
    assert len(walls) == 1
    assert walls[0].page_index == 1
