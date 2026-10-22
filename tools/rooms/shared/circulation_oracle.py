"""FP-050/FP-053: minimal L1 oracle for a protected walking route.

Synthetic demo only. Does not approve placement in planta_74 or edit SketchUp.
Furniture use envelopes (e.g. chair pulled out) are checked separately from
solid footprints. Caller supplies route and clearance from an actual source.
"""
from __future__ import annotations

import math

from shapely.geometry import LineString, Polygon
from shapely.geometry.base import BaseGeometry


def check_protected_route(
    *,
    room: Polygon,
    route: LineString,
    required_width_m: float,
    footprints: dict[str, BaseGeometry],
    use_envelopes: dict[str, BaseGeometry],
    required_use_ids: set[str],
) -> dict:
    """Fail closed: exact protected route must remain unobstructed including use zones."""
    base = {"execution_authorized": False}
    if not math.isfinite(required_width_m) or required_width_m <= 0:
        return {**base, "state": "BLOCKED_INVALID_CLEARANCE"}
    if room.is_empty or not room.is_valid or room.area <= 0 or route.is_empty or not route.is_valid or route.length <= 0:
        return {**base, "state": "BLOCKED_INVALID_GEOMETRY"}
    if not required_use_ids.issubset(use_envelopes):
        return {**base, "state": "BLOCKED_USE_ENVELOPE_MISSING",
                "missing_ids": sorted(required_use_ids - use_envelopes.keys())}
    if not required_use_ids.issubset(footprints):
        return {**base, "state": "BLOCKED_INVALID_CONTEXT"}
    if any(x.is_empty or not x.is_valid for x in [*footprints.values(), *use_envelopes.values()]):
        return {**base, "state": "BLOCKED_INVALID_GEOMETRY"}
    corridor = route.buffer(required_width_m / 2.0, cap_style=2, join_style=2)
    if not room.covers(corridor):
        return {**base, "state": "BLOCKED_ROUTE_OUTSIDE_ROOM", "protected_area_m2": corridor.area}
    hits = []
    for key, shape in sorted(footprints.items()):
        if corridor.intersection(shape).area > 1e-9:
            hits.append({"id": key, "kind": "solid_footprint"})
    for key, shape in sorted(use_envelopes.items()):
        if corridor.intersection(shape).area > 1e-9:
            hits.append({"id": key, "kind": "functional_use_envelope"})
    if hits:
        return {**base, "state": "BLOCKED_CIRCULATION_OBSTRUCTED",
                "obstructions": hits, "protected_area_m2": corridor.area}
    return {**base, "state": "L1_ROUTE_CLEAR", "protected_area_m2": corridor.area,
            "checked_footprints": sorted(footprints), "checked_use_envelopes": sorted(use_envelopes),
            "note": "synthetic clearance proof, not SketchUp L2 or apartment placement"}
