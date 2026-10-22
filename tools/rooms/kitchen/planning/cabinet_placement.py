"""Deterministic L1 pilot: choose a wall-anchored base-cabinet position in metres.

This is a proposal, not authorization to alter a SketchUp model. The caller
must supply the requested wall, an exact anchor, inward direction, existing
furniture, door swing zones and protected circulation. None are inferred.
Placement and clearance are 2D floor envelopes, not a full 3D proof.
"""
from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence

from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.base import BaseGeometry

SCHEMA = "kitchen_cabinet_wall_placement.v1"
EPS = 1e-8
MAX_CANDIDATES = 5000


def _result(status: str, **extra) -> dict:
    return {"schema_version": SCHEMA, "status": status, "execution_authorized": False, **extra}


def _valid_zone_list(zones: Sequence[BaseGeometry] | None) -> bool:
    return (isinstance(zones, (list, tuple))
            and all(isinstance(g, BaseGeometry) and g.is_valid and not g.is_empty for g in zones))


def _coords(geom: Polygon) -> list[list[float]]:
    return [[round(x, 6), round(y, 6)] for x, y in list(geom.exterior.coords)[:-1]]


def _hits(a: Polygon, zones: Sequence[BaseGeometry]) -> bool:
    return any(a.intersection(zone).area > EPS for zone in zones)


def select_wall_cabinet_positions(
    *,
    room: Polygon,
    wall: LineString,
    inward: tuple[float, float],
    anchor: Point,
    width_m: float,
    depth_m: float,
    access_depth_m: float,
    furniture: Sequence[BaseGeometry],
    door_swings: Sequence[BaseGeometry],
    protected_circulation: Sequence[BaseGeometry],
    step_m: float = 0.10,
    max_options: int = 5,
) -> dict:
    """Find wall-aligned placements, fail-closed on incomplete context.

    Anchor is a point on the requested wall to prefer for cabinet centre.
    Protected circulation stays free of the cabinet, but may overlap free
    access space. Poses use shared.cabinet's +x width and +y front convention.
    """
    if (not isinstance(room, Polygon) or not room.is_valid or room.is_empty
            or room.area <= 0 or not isinstance(wall, LineString)
            or not wall.is_valid or wall.is_empty or len(wall.coords) != 2
            or not isinstance(anchor, Point) or anchor.is_empty
            or not _valid_zone_list(furniture)
            or not _valid_zone_list(door_swings)
            or not _valid_zone_list(protected_circulation)):
        return _result("BLOCKED_INVALID_CONTEXT", findings=["INCOMPLETE_OR_INVALID_GEOMETRY"])

    vals = (width_m, depth_m, access_depth_m, step_m)
    if (any(isinstance(v, bool) or not isinstance(v, (int, float))
            or not math.isfinite(v) or v <= 0 for v in vals)
            or isinstance(max_options, bool) or not isinstance(max_options, int)
            or max_options < 1):
        return _result("BLOCKED_INVALID_CONTEXT", findings=["INVALID_DIMENSIONS_OR_STEP"])

    if (not isinstance(inward, (tuple, list)) or len(inward) != 2
            or tuple(inward) not in ((1, 0), (-1, 0), (0, 1), (0, -1))):
        return _result("BLOCKED_INVALID_CONTEXT", findings=["INVALID_INWARD_NORMAL"])
    nx, ny = inward
    a, b = tuple(wall.coords[0]), tuple(wall.coords[1])
    if (not ((abs(a[0] - b[0]) <= EPS) ^ (abs(a[1] - b[1]) <= EPS))
            or not room.boundary.buffer(1e-7).covers(wall)):
        return _result("BLOCKED_INVALID_CONTEXT", findings=["WALL_NOT_ON_ROOM_BOUNDARY_OR_NOT_AXIS_ALIGNED"])
    if wall.distance(anchor) > 1e-7:
        return _result("BLOCKED_INVALID_CONTEXT", findings=["ANCHOR_NOT_ON_REQUESTED_WALL"])

    # Local +x width, +y depth/front: local +y is the left normal to +x.
    tx, ty = ny, -nx
    start = a if (b[0] - a[0]) * tx + (b[1] - a[1]) * ty > 0 else b
    length = wall.length
    midpoint = Point(start[0] + tx * length / 2 + nx * 0.01,
                     start[1] + ty * length / 2 + ny * 0.01)
    if not room.contains(midpoint):
        return _result("BLOCKED_INVALID_CONTEXT", findings=["NORMAL_DOES_NOT_POINT_INTO_ROOM"])
    if width_m > length + EPS:
        return _result("NO_VALID_POSITION", findings=["CABINET_WIDER_THAN_WALL"], total_candidates=0)

    last = max(0.0, length - width_m)
    count = math.ceil(last / step_m) + 1
    if count > MAX_CANDIDATES:
        return _result("BLOCKED_INVALID_CONTEXT", findings=["TOO_MANY_CANDIDATES"])
    offsets = [min(i * step_m, last) for i in range(count)]
    if not offsets or last - offsets[-1] > EPS:
        offsets.append(last)
    offsets = sorted({round(s, 6) for s in offsets})
    anchor_s = (anchor.x - start[0]) * tx + (anchor.y - start[1]) * ty
    rejects: Counter[str] = Counter()
    valid: list[dict] = []
    for s in offsets:
        px, py = start[0] + tx * s, start[1] + ty * s

        def envelope(d0: float, d1: float) -> Polygon:
            return Polygon([
                (px + nx * d0, py + ny * d0),
                (px + tx * width_m + nx * d0, py + ty * width_m + ny * d0),
                (px + tx * width_m + nx * d1, py + ty * width_m + ny * d1),
                (px + nx * d1, py + ny * d1),
            ])

        cabinet = envelope(0.0, depth_m)
        access = envelope(depth_m, depth_m + access_depth_m)
        if not room.covers(cabinet):
            rejects["CABINET_OUTSIDE_ROOM"] += 1
        elif not room.covers(access):
            rejects["FRONT_ACCESS_OUTSIDE_ROOM"] += 1
        elif _hits(cabinet, furniture) or _hits(cabinet, door_swings):
            rejects["CABINET_COLLIDES"] += 1
        elif _hits(cabinet, protected_circulation):
            rejects["BLOCKS_PROTECTED_CIRCULATION"] += 1
        elif _hits(access, furniture) or _hits(access, door_swings):
            rejects["FRONT_ACCESS_BLOCKED"] += 1
        else:
            dist = round(abs(anchor_s - (s + width_m / 2)), 6)
            valid.append({
                "id": f"along-wall-{round(s * 1000):06d}mm",
                "pose": {"x_m": round(px, 6), "y_m": round(py, 6),
                         "rotation_deg": round(math.degrees(math.atan2(ty, tx)), 6)},
                "anchor_offset_m": dist,
                "footprint_xy_m": _coords(cabinet),
                "front_access_xy_m": _coords(access),
            })
    valid.sort(key=lambda c: (c["anchor_offset_m"], c["id"]))
    if not valid:
        return _result("NO_VALID_POSITION", total_candidates=len(offsets),
                       rejection_counts=dict(sorted(rejects.items())),
                       findings=["NO_POSITION_SATISFIES_ALL_HARD_GATES"])
    return _result("OPTIONS_ONLY", total_candidates=len(offsets), valid_candidates=len(valid),
                   rejection_counts=dict(sorted(rejects.items())),
                   ranking_rule="minimum_distance_to_declared_wall_anchor_then_stable_id",
                   selected=valid[0], alternatives=valid[1:max_options])
