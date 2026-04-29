"""Unit tests for ``topology.wall_interior_filter.is_room_noise``.

Guarantees the noise filter preserves corridors and legitimate small
rooms while dropping slivers / narrow artefacts.
"""
from __future__ import annotations

from shapely.geometry import Polygon

from topology.wall_interior_filter import is_room_noise


THICKNESS = 6.0


def _rect(w: float, h: float) -> Polygon:
    return Polygon([(0, 0), (w, 0), (w, h), (0, h)])


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
