"""Post-polygonize filter for double-wall sliver polygons.

A polygon whose minimum rotated rectangle has a short side at or below
wall_thickness * margin is most likely the gap between the inner and outer
face of a double-drawn wall, not a real room. This filter removes those.

The margin default (1.3) preserves all architectural rooms >= 60 cm while
removing slivers around wall_thickness. See plan: svg-ingest-integration.md.
"""
from __future__ import annotations

import math

from shapely.geometry import Polygon


def is_wall_interior(polygon: Polygon, wall_thickness: float, margin: float = 1.3) -> bool:
    mrr = polygon.minimum_rotated_rectangle
    if mrr.is_empty:
        return False
    x, y = mrr.exterior.coords.xy
    edges = sorted(math.hypot(x[i + 1] - x[i], y[i + 1] - y[i]) for i in range(4))
    return edges[0] <= wall_thickness * margin
