"""FP-050 pure geometry L1 — never opens SketchUp or edits canonical assets."""
from __future__ import annotations

from shapely.geometry import LineString, Point, Polygon, box

from tools.rooms.kitchen.planning.cabinet_placement import select_wall_cabinet_positions

ROOM = box(0, 0, 3, 4)
WEST = LineString([(0, 0), (0, 4)])


def select(**changes):
    req = dict(room=ROOM, wall=WEST, inward=(1, 0), anchor=Point(0, 2),
               width_m=0.6, depth_m=0.6, access_depth_m=0.8,
               furniture=[], door_swings=[], protected_circulation=[], step_m=0.1)
    req.update(changes)
    return select_wall_cabinet_positions(**req)


def test_anchors_to_requested_wall_and_declares_front_access():
    a = select()
    assert a["status"] == "OPTIONS_ONLY" and not a["execution_authorized"]
    candidate = a["selected"]
    footprint = Polygon(candidate["footprint_xy_m"])
    clearance = Polygon(candidate["front_access_xy_m"])
    assert footprint.bounds[0] == 0 and footprint.bounds[2] == 0.6
    assert clearance.bounds[0] == 0.6 and clearance.bounds[2] == 1.4
    assert ROOM.covers(footprint) and ROOM.covers(clearance)
    assert candidate["pose"]["rotation_deg"] == -90.0
    assert candidate["anchor_offset_m"] < 0.001


def test_access_rejects_cabinet_where_an_obstacle_blocks_the_door_or_drawer():
    o = box(0.6, 1.35, 1.25, 2.65)
    out = select(furniture=[o])
    assert out["status"] == "OPTIONS_ONLY"
    assert out["rejection_counts"].get("FRONT_ACCESS_BLOCKED", 0) > 0
    assert Polygon(out["selected"]["front_access_xy_m"]).intersection(o).area < 1e-8


def test_never_accepts_middle_of_kitchen_or_protected_path():
    out = select(protected_circulation=[box(0, 0, 0.65, 4)])
    assert out["status"] == "NO_VALID_POSITION"
    assert out["rejection_counts"]["BLOCKS_PROTECTED_CIRCULATION"] > 0
    assert out["execution_authorized"] is False


def test_impossible_room_returns_no_position_not_fallback_center():
    out = select(room=box(0, 0, 1.0, 4))
    assert out["status"] == "NO_VALID_POSITION"
    assert out["rejection_counts"]["FRONT_ACCESS_OUTSIDE_ROOM"] > 0


def test_wrong_wall_anchor_and_normal_fail_closed():
    assert select(anchor=Point(3, 2))["findings"] == ["ANCHOR_NOT_ON_REQUESTED_WALL"]
    assert select(inward=(-1, 0))["findings"] == ["NORMAL_DOES_NOT_POINT_INTO_ROOM"]
    assert select(wall=LineString([(1, 0), (1, 4)]))["findings"] == ["WALL_NOT_ON_ROOM_BOUNDARY_OR_NOT_AXIS_ALIGNED"]


def test_missing_context_and_invalid_units_refused():
    assert select(door_swings=None)["status"] == "BLOCKED_INVALID_CONTEXT"
    assert select(access_depth_m=0)["findings"] == ["INVALID_DIMENSIONS_OR_STEP"]
    assert select(width_m=float("nan"))["status"] == "BLOCKED_INVALID_CONTEXT"
    assert select(step_m=0.000001)["findings"] == ["TOO_MANY_CANDIDATES"]


def test_door_swing_blocks_cabinet_and_access():
    assert select(door_swings=[box(0, 0, 1.5, 4)])["status"] == "NO_VALID_POSITION"


def test_wall_end_order_does_not_change_best_pose():
    forward = select()
    backward = select(wall=LineString([(0, 4), (0, 0)]))
    assert forward["selected"] == backward["selected"]
    assert forward["alternatives"] == backward["alternatives"]


def test_obstacle_corner_contact_not_intersection():
    out = select(furniture=[box(1.4, 0, 1.8, 4)])
    assert out["status"] == "OPTIONS_ONLY"
    assert out["rejection_counts"].get("FRONT_ACCESS_BLOCKED", 0) == 0


def test_front_direction_rotation_is_compatible_with_shared_cabinet():
    out = select(wall=LineString([(0, 0), (3, 0)]), inward=(0, 1), anchor=Point(1.5, 0))
    assert out["status"] == "OPTIONS_ONLY"
    assert out["selected"]["pose"]["rotation_deg"] == 0.0


def test_synthetic_preview_produces_a_diagram_and_a_machine_readable_report(tmp_path):
    from tools.rooms.kitchen.planning.preview import demo
    report = demo(tmp_path)
    assert report["status"] == "OPTIONS_ONLY"
    assert (tmp_path / "placement_plan.png").read_bytes().startswith(b"\x89PNG")
    assert '"execution_authorized": false' in (tmp_path / "placement_report.json").read_text()
