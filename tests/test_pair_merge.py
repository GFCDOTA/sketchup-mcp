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


def test_two_parallel_strokes_merge_into_one_centerline() -> None:
    # Two horizontal strokes 30 px apart, fully overlapping in x.
    # Pair-merge must collapse them into a single centerline at the midpoint.
    candidates = [
        _h(page=0, y=40, x0=10, x1=110, thickness=3.0),
        _h(page=0, y=70, x0=10, x1=110, thickness=3.0),
    ]
    walls = classify_walls(candidates)

    assert len(walls) == 1, [(w.start, w.end, w.thickness) for w in walls]
    wall = walls[0]
    assert wall.orientation == "horizontal"
    # centerline must sit at the midpoint of the two strokes
    assert wall.start[1] == 55.0 and wall.end[1] == 55.0
    # gap between strokes becomes the reported wall thickness
    assert wall.thickness == 30.0
    # parallel extent must cover the overlap
    assert wall.start[0] == 10 and wall.end[0] == 110


def test_low_overlap_parallel_strokes_do_not_pair() -> None:
    # Only ~33% of the longer stroke overlaps its parallel neighbour. The
    # two are not symmetrically the "two faces" of one wall; keep them
    # separate. This protects single-line geometries (e.g. opposite sides
    # of an L-shape floor plan) from false pairing.
    candidates = [
        _h(page=0, y=40, x0=0, x1=100, thickness=3.0),
        _h(page=0, y=70, x0=50, x1=200, thickness=3.0),
    ]
    walls = classify_walls(candidates)

    assert len(walls) == 2, [(w.start, w.end) for w in walls]


def test_hachura_chain_does_not_pair() -> None:
    # Three parallel horizontal strokes 15 px apart (uniform spacing). This is
    # the signature of hachura / repeating pattern, not a wall pair; none of
    # them may be merged.
    candidates = [
        _h(page=0, y=40, x0=10, x1=110),
        _h(page=0, y=55, x0=10, x1=110),
        _h(page=0, y=70, x0=10, x1=110),
    ]
    walls = classify_walls(candidates)

    # After classify's own per-page perpendicular clustering, the three
    # strokes remain distinguishable as long as none got pair-merged. The
    # thickness inferred from the candidates is 3.0, so the classify
    # clustering tolerance is small and the three perpendicular coords stay
    # in separate clusters -> 3 walls come out.
    assert len(walls) == 3, [(w.start, w.end, w.thickness) for w in walls]
    assert all(w.thickness == 3.0 for w in walls), [w.thickness for w in walls]


def test_strokes_too_close_are_left_to_classify_clustering() -> None:
    # Gap below _PAIR_MIN_GAP (4.0 px): these look like duplicated detections
    # of the same stroke. Pair-merge must not pair them; classify's cluster
    # step handles them instead (collapsing to a single wall).
    candidates = [
        _h(page=0, y=40.0, x0=10, x1=110, thickness=3.0),
        _h(page=0, y=41.5, x0=10, x1=110, thickness=3.0),
    ]
    walls = classify_walls(candidates)

    assert len(walls) == 1
    # The merged wall comes from classify's cluster, not from pair-merge, so
    # it keeps the original stroke thickness instead of using the tiny gap.
    assert walls[0].thickness == 3.0


def test_strokes_too_far_do_not_pair() -> None:
    # Gap above _PAIR_MAX_GAP (100 px): these are two separate walls, not
    # two sides of the same wall. Both must survive as distinct walls.
    candidates = [
        _h(page=0, y=40, x0=10, x1=110, thickness=3.0),
        _h(page=0, y=250, x0=10, x1=110, thickness=3.0),
    ]
    walls = classify_walls(candidates)
    assert len(walls) == 2


def test_vertical_pair_merge_works_too() -> None:
    candidates = [
        _v(page=0, x=40, y0=10, y1=110, thickness=3.0),
        _v(page=0, x=70, y0=10, y1=110, thickness=3.0),
    ]
    walls = classify_walls(candidates)
    assert len(walls) == 1
    wall = walls[0]
    assert wall.orientation == "vertical"
    assert wall.start[0] == 55.0 and wall.end[0] == 55.0
    assert wall.thickness == 30.0


def test_l_shape_single_line_geometry_does_not_pair() -> None:
    # An L-shaped outline drawn as single strokes: top and middle-top are
    # parallel horizontals but cover different parallel extents (they are
    # opposite sides of the L's short arm, not two faces of the same wall).
    # They must NOT pair or the L stops being a closed polygon downstream.
    candidates = [
        _h(page=0, y=40,  x0=40,  x1=200),   # top
        _v(page=0, x=200, y0=40,  y1=100),   # upper-right
        _h(page=0, y=100, x0=120, x1=200),   # middle-top
        _v(page=0, x=120, y0=100, y1=200),   # middle-right
        _h(page=0, y=200, x0=40,  x1=120),   # bottom
        _v(page=0, x=40,  y0=40,  y1=200),   # left
    ]
    walls = classify_walls(candidates)
    assert len(walls) == 6, [(w.start, w.end) for w in walls]


def test_pair_merge_respects_page_isolation() -> None:
    # Parallel strokes on two different pages must not pair across pages.
    candidates = [
        _h(page=0, y=40, x0=10, x1=110),
        _h(page=1, y=70, x0=10, x1=110),
    ]
    walls = classify_walls(candidates)
    assert len(walls) == 2
    pages = {w.page_index for w in walls}
    assert pages == {0, 1}
