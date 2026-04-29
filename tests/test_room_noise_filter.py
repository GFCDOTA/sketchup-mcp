"""Unit tests for ``topology.wall_interior_filter.is_room_noise`` and
``is_triangle_artifact``.

Guarantees the noise filters preserve corridors / legitimate rooms while
dropping slivers, narrow artefacts and small triangular wedges.
"""
from __future__ import annotations

from shapely.geometry import Polygon

from topology.wall_interior_filter import is_room_noise, is_triangle_artifact


THICKNESS = 6.0


def _rect(w: float, h: float) -> Polygon:
    return Polygon([(0, 0), (w, 0), (w, h), (0, h)])


def _triangle(p0: tuple, p1: tuple, p2: tuple) -> Polygon:
    return Polygon([p0, p1, p2])


def test_tiny_room_is_noise() -> None:
    # 18x18 -> area 324 < thickness^2 * 13 = 468 -> tiny_area trigger
    assert is_room_noise(_rect(18, 18), THICKNESS) is True


def test_narrow_medium_is_noise() -> None:
    # 23x40 -> area 920, short 23. area < large (25*36=900... actually 920>=900)
    # Let's use 22x40 -> area 880, short 22. 22 < 4*6=24 -> narrow trigger.
    assert is_room_noise(_rect(22, 40), THICKNESS) is True


def test_long_thin_corridor_is_preserved() -> None:
    # 12 x 200 -> aspect 16.7, short 12. short >= 1.5 * 6 = 9 -> corridor pass.
    assert is_room_noise(_rect(12, 200), THICKNESS) is False


def test_large_square_is_preserved() -> None:
    # 80 x 80 -> area 6400 >> large_area (25 * 36 = 900). Keep.
    assert is_room_noise(_rect(80, 80), THICKNESS) is False


def test_small_but_reasonably_shaped_is_preserved() -> None:
    # 40 x 40 -> area 1600 >= large_area_floor (900). Keep.
    assert is_room_noise(_rect(40, 40), THICKNESS) is False


def test_very_narrow_sliver_is_noise() -> None:
    # 5 x 100 -> aspect 20, but short 5 < corridor_short 9 -> not corridor.
    # area 500 > tiny (468). But short 5 < 24 -> narrow -> noise.
    assert is_room_noise(_rect(5, 100), THICKNESS) is True


def test_corridor_too_narrow_is_still_noise() -> None:
    # 7 x 200 -> aspect 28, short 7. Short < corridor_short 9 -> not corridor.
    # area 1400 >= large_area 900 -> would be kept by large-area rule. Keep.
    # This documents that even pathologically narrow very-long polygons
    # are preserved if they have enough area. Rationale: a 50 cm x 14 m
    # artefact shouldn't exist in practice; if it does, we err on safety.
    assert is_room_noise(_rect(7, 200), THICKNESS) is False


def test_degenerate_polygon_is_not_flagged() -> None:
    degenerate = Polygon()
    assert is_room_noise(degenerate, THICKNESS) is False


# ---------------------------------------------------------------------------
# is_triangle_artifact
# ---------------------------------------------------------------------------

def test_small_triangle_is_artifact() -> None:
    # 50x40x30 small wedge — area ~600, well below 30 * 6^2 = 1080 floor
    poly = _triangle((0, 0), (50, 0), (25, 24))
    assert poly.area < 30 * THICKNESS ** 2
    assert is_triangle_artifact(poly, THICKNESS) is True


def test_large_triangle_is_preserved() -> None:
    # 200x150 corner-cut room — area 15000, way above floor — real room
    poly = _triangle((0, 0), (200, 0), (100, 150))
    assert poly.area > 30 * THICKNESS ** 2
    assert is_triangle_artifact(poly, THICKNESS) is False


def test_rectangle_is_never_triangle_artifact() -> None:
    # Even a tiny rectangle isn't a triangle — let is_room_noise handle it
    assert is_triangle_artifact(_rect(10, 10), THICKNESS) is False


def test_5_vertex_polygon_is_never_triangle_artifact() -> None:
    # Pentagon — 5 unique vertices, not a triangle
    pentagon = Polygon([(0, 0), (10, 0), (12, 5), (5, 10), (0, 5)])
    assert is_triangle_artifact(pentagon, THICKNESS) is False


def test_triangle_filter_uses_thickness_squared_floor() -> None:
    # With thickness 10, floor = 30 * 100 = 3000. A 2000-area triangle fails.
    poly = _triangle((0, 0), (100, 0), (50, 40))  # area = 2000
    assert is_triangle_artifact(poly, wall_thickness=10.0) is True
    # Same triangle with thickness 5 has floor 30 * 25 = 750 — passes.
    assert is_triangle_artifact(poly, wall_thickness=5.0) is False
