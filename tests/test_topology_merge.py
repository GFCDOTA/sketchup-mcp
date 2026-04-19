"""Tests for the post-split colinear merge in topology.

Each test builds a synthetic Wall fixture, runs build_topology, and asserts
on the resulting SplitWalls and junctions. The intent is to verify that
artificial fragmentation introduced by `_split_walls_at_intersections` is
recovered by `_merge_colinear_segments`.
"""
from __future__ import annotations

from model.types import Wall
from topology.service import build_topology


def _wall(
    wid: str,
    start: tuple[float, float],
    end: tuple[float, float],
    orientation: str,
    thickness: float = 8.0,
) -> Wall:
    return Wall(
        wall_id=wid,
        page_index=0,
        start=start,
        end=end,
        thickness=thickness,
        orientation=orientation,
        source="synthetic",
        confidence=1.0,
    )


def test_long_h_with_three_v_crossings_collapses_to_continuous_segments() -> None:
    # 1 long horizontal at y=100, three verticals crossing it at x=200,500,800.
    # Without merge: H splits into 4 segments, each V into 2 -> 4 + 6 = 10
    # SplitWalls.
    # With merge (passing through cross junctions): H becomes 1 segment that
    # spans the full extent, each V becomes 1 segment (top+bottom recombined)
    # -> 1 + 3 = 4 SplitWalls, plus the 3 cross junctions are preserved.
    walls = [
        _wall("h-main", (0.0, 100.0), (1000.0, 100.0), "horizontal"),
        _wall("v1", (200.0, 0.0), (200.0, 200.0), "vertical"),
        _wall("v2", (500.0, 0.0), (500.0, 200.0), "vertical"),
        _wall("v3", (800.0, 0.0), (800.0, 200.0), "vertical"),
    ]
    split_walls, junctions, _, _ = build_topology(walls)
    assert len(split_walls) == 4, [(w.start, w.end) for w in split_walls]

    # The original geometry must be preserved: the three intersections at
    # (200,100), (500,100), (800,100) appear as cross junctions (degree 4).
    cross = [j for j in junctions if j.kind == "cross"]
    cross_points = {j.point for j in cross}
    assert (200.0, 100.0) in cross_points, [j.point for j in cross]
    assert (500.0, 100.0) in cross_points
    assert (800.0, 100.0) in cross_points


def test_l_junction_preserves_two_walls() -> None:
    # An L: one H + one V meeting at a corner. Different orientations cannot
    # merge across a degree-2 corner, so both walls survive intact.
    walls = [
        _wall("h", (0.0, 100.0), (200.0, 100.0), "horizontal"),
        _wall("v", (200.0, 100.0), (200.0, 300.0), "vertical"),
    ]
    split_walls, junctions, _, _ = build_topology(walls)
    assert len(split_walls) == 2

    corner = [j for j in junctions if j.point == (200.0, 100.0)]
    assert len(corner) == 1
    assert corner[0].degree == 2


def test_intersection_near_endpoint_does_not_create_micro_segment() -> None:
    # H wall from (0,100) to (200,100), thickness 10. A V wall ends at x=5
    # (only 5 px away from the H wall's left endpoint). With smart-split
    # epsilon = 0.75 * median_thickness = 7.5, the V/H intersection at
    # (5,100) is too close to (0,100) to justify a new split point on H.
    walls = [
        _wall("h", (0.0, 100.0), (200.0, 100.0), "horizontal"),
        _wall("v", (5.0, 0.0), (5.0, 200.0), "vertical"),
    ]
    split_walls, _, _, _ = build_topology(walls)
    # H must remain a single segment (no micro stub of length 5).
    horizontal = [w for w in split_walls if w.orientation == "horizontal"]
    assert len(horizontal) == 1, [(w.start, w.end) for w in horizontal]
    h = horizontal[0]
    # The smart-split rejected the intersection so H is not divided. Snap
    # may pull the left endpoint a few px toward the intersection point,
    # but H stays close to its original 200 px span.
    assert abs((h.end[0] - h.start[0]) - 200.0) <= 5.0


def test_chain_of_three_colinear_segments_merges_to_one() -> None:
    # Three colinear horizontal segments connected end-to-end. Without
    # merge: 3 SplitWalls and 4 nodes (two of which are pure degree-2
    # pass-through). With merge: 1 segment from (0,100) to (300,100).
    walls = [
        _wall("a", (0.0, 100.0), (100.0, 100.0), "horizontal"),
        _wall("b", (100.0, 100.0), (200.0, 100.0), "horizontal"),
        _wall("c", (200.0, 100.0), (300.0, 100.0), "horizontal"),
    ]
    split_walls, junctions, _, _ = build_topology(walls)
    assert len(split_walls) == 1, [(w.start, w.end) for w in split_walls]
    only = split_walls[0]
    assert only.start == (0.0, 100.0) or only.end == (0.0, 100.0)
    assert only.start == (300.0, 100.0) or only.end == (300.0, 100.0)
    # The two intermediate pass-through nodes are gone; only the two
    # endpoints survive as degree-1 ends.
    ends = [j for j in junctions if j.kind == "end"]
    assert len(ends) == 2


def test_existing_t_junction_preserved_after_merge() -> None:
    # A T: long H crossed by a V whose endpoint sits ON the H. The T has
    # degree-3 at the intersection. Merge across the H pair must still
    # work (V is the stem, not in the way). Result: 1 H + 1 V = 2 walls,
    # one tee junction.
    walls = [
        _wall("h", (0.0, 100.0), (200.0, 100.0), "horizontal"),
        _wall("v", (100.0, 100.0), (100.0, 200.0), "vertical"),
    ]
    split_walls, junctions, _, _ = build_topology(walls)
    assert len(split_walls) == 2, [(w.start, w.end) for w in split_walls]
    tees = [j for j in junctions if j.kind == "tee"]
    assert len(tees) == 1
    assert tees[0].point == (100.0, 100.0)
