"""Adversarial tests for _merge_strip_rooms.

The merger must aggressively collapse "strip" polygons created between
pairs of nearly-parallel walls that dedup did not absorb, WITHOUT
touching legitimate rooms (including narrow corridors and small
bathrooms). These tests pin the boundary behaviour so regressions
become loud.
"""
from __future__ import annotations

from model.types import Room, SplitWall
from topology.service import _merge_strip_rooms


def _wall(
    wid: str,
    start: tuple[float, float],
    end: tuple[float, float],
    thickness: float = 4.0,
    orientation: str = "horizontal",
) -> SplitWall:
    return SplitWall(
        wall_id=wid,
        parent_wall_id=wid,
        page_index=0,
        start=start,
        end=end,
        thickness=thickness,
        orientation=orientation,
        source="test",
        confidence=1.0,
    )


def _rect_room(room_id: str, x0: float, y0: float, x1: float, y1: float) -> Room:
    return Room(
        room_id=room_id,
        polygon=[(x0, y0), (x1, y0), (x1, y1), (x0, y1)],
        area=(x1 - x0) * (y1 - y0),
        centroid=((x0 + x1) / 2.0, (y0 + y1) / 2.0),
    )


def test_strip_between_two_rooms_merges_into_larger() -> None:
    # Three-rectangle layout along x:
    #   [0..100] big room   [100..108] strip     [108..400] bigger room
    # The 8-px strip has wall-thickness width (4 px), aspect = 8/200 = 0.04,
    # is fully sandwiched (ratio = 1.0), and should be absorbed by the
    # largest neighbour.
    walls = [_wall("w1", (0, 0), (400, 0), thickness=4.0)]
    rooms = [
        _rect_room("big_a", 0, 0, 100, 200),
        _rect_room("strip", 100, 0, 108, 200),
        _rect_room("big_b", 108, 0, 400, 200),
    ]
    merged = _merge_strip_rooms(rooms, walls)
    ids = {r.room_id for r in merged}
    assert "strip" not in ids
    # Target is the larger neighbour: big_b (58400 px^2 > big_a 20000)
    assert "big_b" in ids


def test_bathroom_is_not_merged() -> None:
    # Small square-ish room sandwiched between two bigger rooms. Width is
    # ~60 px — far above 2.5 * wall_thickness (10 px) and above the
    # elastic 5x bound (20 px). Aspect 1.0. Must survive.
    walls = [_wall("w1", (0, 0), (300, 0), thickness=4.0)]
    rooms = [
        _rect_room("left", 0, 0, 100, 200),
        _rect_room("bath", 100, 0, 160, 60),
        _rect_room("right", 160, 0, 300, 200),
    ]
    merged = _merge_strip_rooms(rooms, walls)
    ids = {r.room_id for r in merged}
    assert "bath" in ids


def test_narrow_corridor_with_real_width_survives() -> None:
    # Long corridor (aspect 0.13) but 30 px wide — above 5x wall
    # thickness = 20 px. Enclosed by two rooms (ratio 1.0). Must
    # survive because its functional width is not a wall-thickness
    # artefact.
    walls = [_wall("w1", (0, 0), (500, 0), thickness=4.0)]
    rooms = [
        _rect_room("top", 0, 40, 500, 240),
        _rect_room("corridor", 0, 10, 500, 40),
        _rect_room("bottom", 0, 0, 500, 10),
    ]
    merged = _merge_strip_rooms(rooms, walls)
    ids = {r.room_id for r in merged}
    assert "corridor" in ids, (
        "Corridor with width 30 > 5*wall_thickness=20 must NOT be merged"
    )


def test_strip_with_low_shared_ratio_survives() -> None:
    # A strip-shaped room that only touches one neighbour on a short
    # edge. Its total shared ratio is below 0.6, so it is NOT a "room
    # sandwiched between walls" and must survive.
    walls = [_wall("w1", (0, 0), (300, 0), thickness=4.0)]
    # Strip 200x8 at top, big room below touches only the bottom short
    # edge.
    rooms = [
        _rect_room("strip_isolated", 0, 200, 200, 208),
        _rect_room("big", 0, 0, 200, 200),
    ]
    merged = _merge_strip_rooms(rooms, walls)
    ids = {r.room_id for r in merged}
    assert "strip_isolated" in ids
    assert "big" in ids


def test_two_strips_each_sandwiched_both_merge_eventually() -> None:
    # Five-room layout: two strips, each sandwiched between two bigger
    # rooms. In a single pass the claimed_targets constraint can only
    # consume one strip; the iterative loop must converge by absorbing
    # both over multiple passes.
    walls = [_wall("w1", (0, 0), (700, 0), thickness=4.0)]
    rooms = [
        _rect_room("left_big", 0, 0, 100, 200),
        _rect_room("strip_1", 100, 0, 108, 200),
        _rect_room("middle_big", 108, 0, 400, 200),
        _rect_room("strip_2", 400, 0, 408, 200),
        _rect_room("right_big", 408, 0, 700, 200),
    ]
    merged = _merge_strip_rooms(rooms, walls)
    ids = {r.room_id for r in merged}
    # Both strips must be gone after iteration convergence.
    assert "strip_1" not in ids
    assert "strip_2" not in ids
    # Exactly three rooms survive (one per side plus the middle,
    # whichever absorbs the strips).
    assert len(merged) == 3


def test_empty_input_returns_empty() -> None:
    assert _merge_strip_rooms([], []) == []


def test_single_room_is_returned_unchanged() -> None:
    rooms = [_rect_room("solo", 0, 0, 100, 100)]
    walls = [_wall("w1", (0, 0), (100, 0))]
    assert _merge_strip_rooms(rooms, walls) == rooms
