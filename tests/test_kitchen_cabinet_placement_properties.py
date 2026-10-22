"""FP-050 property tests (CI dev extra installs Hypothesis)."""
from __future__ import annotations

import pytest
from shapely.geometry import LineString, Point, Polygon, box

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import given, settings, strategies as st  # noqa: E402

from tools.rooms.kitchen.planning.cabinet_placement import select_wall_cabinet_positions


@settings(max_examples=150, deadline=None)
@given(room_width=st.floats(min_value=1.65, max_value=5, allow_nan=False, allow_infinity=False),
       room_length=st.floats(min_value=1.4, max_value=6, allow_nan=False, allow_infinity=False),
       cabinet_width=st.floats(min_value=0.3, max_value=1.2, allow_nan=False, allow_infinity=False),
       cabinet_depth=st.floats(min_value=0.25, max_value=0.7, allow_nan=False, allow_infinity=False),
       front_clearance=st.floats(min_value=0.5, max_value=0.9, allow_nan=False, allow_infinity=False))
def test_every_selected_footprint_and_access_are_inside_declared_room(
    room_width, room_length, cabinet_width, cabinet_depth, front_clearance,
):
    room = box(0, 0, room_width, room_length)
    result = select_wall_cabinet_positions(
        room=room, wall=LineString([(0, 0), (0, room_length)]), inward=(1, 0),
        anchor=Point(0, room_length / 2), width_m=cabinet_width, depth_m=cabinet_depth,
        access_depth_m=front_clearance, furniture=[], door_swings=[],
        protected_circulation=[], step_m=0.1,
    )
    assert result["execution_authorized"] is False
    if result["status"] == "OPTIONS_ONLY":
        for candidate in [result["selected"], *result["alternatives"]]:
            assert room.buffer(2e-6).covers(Polygon(candidate["footprint_xy_m"]))
            assert room.buffer(2e-6).covers(Polygon(candidate["front_access_xy_m"]))
    else:
        assert result["status"] == "NO_VALID_POSITION"


@settings(max_examples=80, deadline=None)
@given(position=st.floats(min_value=0, max_value=3, allow_nan=False, allow_infinity=False))
def test_fully_protected_wall_strip_yields_no_valid_position(position):
    result = select_wall_cabinet_positions(
        room=box(0, 0, 3, 4), wall=LineString([(0, 0), (0, 4)]), inward=(1, 0),
        anchor=Point(0, position), width_m=0.6, depth_m=0.6, access_depth_m=0.8,
        furniture=[], door_swings=[], protected_circulation=[box(0, 0, 0.7, 4)],
    )
    assert result["status"] == "NO_VALID_POSITION"
    assert not result["execution_authorized"]
