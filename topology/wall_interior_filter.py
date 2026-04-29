"""Post-polygonize filters for room polygons produced by shapely.polygonize.

Two filters live here. Both operate on the output polygon list and are
opt-in (used only by the SVG path; raster continues unchanged).

1. ``is_wall_interior`` — removes polygons whose minimum rotated rectangle
   has a short side at or below ``wall_thickness * margin``. These are
   slivers between the two faces of a double-drawn wall.

2. ``is_room_noise`` — removes polygons that are too small or too narrow
   to represent an architectural space, with an explicit exception that
   preserves corridors (long, thin, but legitimate circulation).

The margin on ``is_wall_interior`` defaults to 1.5, keeping corridors
>= 80 cm and lavabos >= 90 cm safe in typical SVG input units (1 m ~ 14 u).
The ``is_room_noise`` thresholds are expressed in multiples of
wall_thickness so the filter is scale-invariant.
"""
from __future__ import annotations

import math

from shapely.geometry import Polygon


def _mrr_edges(polygon: Polygon) -> tuple[float, float] | None:
    mrr = polygon.minimum_rotated_rectangle
    if mrr.is_empty:
        return None
    x, y = mrr.exterior.coords.xy
    edges = sorted(math.hypot(x[i + 1] - x[i], y[i + 1] - y[i]) for i in range(4))
    return edges[0], edges[-1]


def is_wall_interior(polygon: Polygon, wall_thickness: float, margin: float = 1.5) -> bool:
    edges = _mrr_edges(polygon)
    if edges is None:
        return False
    short, _long = edges
    return short <= wall_thickness * margin


def is_triangle_artifact(
    polygon: Polygon,
    wall_thickness: float,
    min_area_mul: float = 30.0,
) -> bool:
    """Drop triangular polygons that are clearly polygonize artefacts.

    A triangle (3 unique vertices) below ``wall_thickness^2 * min_area_mul``
    is almost always a wedge between three walls that nearly-but-not-quite
    meet at a point, not a real triangular room. Real triangular rooms
    (corner cuts in irregular footprints) easily clear the floor.

    For wall_thickness = 6.25 (typical SVG units, ~ 22 cm wall) the floor
    is ``6.25^2 * 30 ≈ 1170`` sq units (≈ 6 m²). Calibrated against
    runs/openings_refine_final where triangles room-10 / room-11 / room-12 /
    room-23 (areas 556 to 1131) are visible polygonize artefacts and
    larger triangular rooms in test fixtures are preserved.

    Returns True when the polygon should be dropped.
    """
    coords = list(polygon.exterior.coords)
    # Shapely closes rings (last == first); a triangle has 4 coordinate entries.
    if len(coords) != 4:
        return False
    floor = (wall_thickness ** 2) * min_area_mul
    return polygon.area < floor


def is_room_noise(
    polygon: Polygon,
    wall_thickness: float,
    min_area_mul: float = 13.0,
    min_short_mul: float = 4.0,
    corridor_aspect: float = 3.0,
    corridor_short_mul: float = 1.5,
    large_area_mul: float = 25.0,
) -> bool:
    """Return True if polygon is likely a noise artefact rather than a room.

    Rules (thickness-scaled, deterministic):
      - Corridor exception: aspect > corridor_aspect AND short >=
        wall_thickness * corridor_short_mul -> NOT noise (keep).
      - Large-area guarantee: area >= wall_thickness^2 * large_area_mul
        -> NOT noise (even if narrow, it is a real room, e.g. a wide
        banheiro with an aspect close to 1).
      - Tiny area: area < wall_thickness^2 * min_area_mul -> noise.
      - Narrow medium: area below the large-area floor AND short <
        wall_thickness * min_short_mul -> noise.
      - Otherwise: keep.
    """
    edges = _mrr_edges(polygon)
    if edges is None:
        return False
    short, long = edges
    aspect = long / short if short > 0 else float("inf")

    corridor_short = wall_thickness * corridor_short_mul
    if aspect > corridor_aspect and short >= corridor_short:
        return False

    area = polygon.area
    large_area = (wall_thickness ** 2) * large_area_mul
    if area >= large_area:
        return False

    tiny_area = (wall_thickness ** 2) * min_area_mul
    if area < tiny_area:
        return True

    narrow = short < wall_thickness * min_short_mul
    if narrow:
        return True

    return False
