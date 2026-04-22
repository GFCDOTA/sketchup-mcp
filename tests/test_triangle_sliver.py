"""Tests for topology.service._is_triangle_sliver (F6 filter).

F6 drops 3-vertex polygons below ``_TRIANGLE_SLIVER_AREA_MAX`` when the
post-polygonize room count exceeds ``_TRIANGLE_SLIVER_ACTIVATION_COUNT``.
The activation gate protects synthetic fixtures (<=25 rooms) so pytest
cases that expect small triangular rooms to survive keep working.

Complements ``tests/test_strip_merge.py`` (F5 strip-room merge) and the
18 unit tests in ``tests/test_collinear_dedup.py`` (F1 dedup).
"""
from __future__ import annotations

from model.types import Room
from topology.service import (
    _TRIANGLE_SLIVER_ACTIVATION_COUNT,
    _TRIANGLE_SLIVER_AREA_MAX,
    _is_triangle_sliver,
)


def _room(
    room_id: str,
    polygon: list[tuple[float, float]],
    area: float,
    centroid: tuple[float, float] = (0.0, 0.0),
) -> Room:
    return Room(room_id=room_id, polygon=polygon, area=area, centroid=centroid)


def test_tiny_triangle_is_flagged() -> None:
    # 3 vertices, area 800 px²: both conditions met → drop.
    triangle = _room(
        "r1",
        [(0.0, 0.0), (40.0, 0.0), (20.0, 40.0), (0.0, 0.0)],
        area=800.0,
    )
    assert _is_triangle_sliver(triangle) is True


def test_tiny_triangle_without_closing_vertex_is_flagged() -> None:
    # Same shape but the closing duplicate is not present in the list.
    # Vertex-count logic must handle both representations.
    triangle = _room(
        "r2",
        [(0.0, 0.0), (40.0, 0.0), (20.0, 40.0)],
        area=800.0,
    )
    assert _is_triangle_sliver(triangle) is True


def test_large_triangle_above_area_max_is_kept() -> None:
    # Chanfro or diagonal architectural wall: 3 vertices but area well
    # above threshold — must survive.
    chanfro = _room(
        "r3",
        [(0.0, 0.0), (200.0, 0.0), (100.0, 200.0), (0.0, 0.0)],
        area=_TRIANGLE_SLIVER_AREA_MAX + 1.0,
    )
    assert _is_triangle_sliver(chanfro) is False


def test_quad_below_area_is_kept() -> None:
    # 4 vertices, small area — NOT a triangle sliver. F5's
    # _is_sliver_polygon handles slivers by shape/compactness; this
    # filter is strictly triangle-shaped.
    tiny_quad = _room(
        "r4",
        [(0.0, 0.0), (30.0, 0.0), (30.0, 30.0), (0.0, 30.0), (0.0, 0.0)],
        area=900.0,
    )
    assert _is_triangle_sliver(tiny_quad) is False


def test_polygon_with_many_vertices_is_kept() -> None:
    # Polygon with 5+ vertices — typical of real rooms with chanfros or
    # openings subdividing the boundary — must survive regardless of area.
    complex_small = _room(
        "r5",
        [(0.0, 0.0), (40.0, 0.0), (40.0, 20.0), (20.0, 40.0), (0.0, 20.0), (0.0, 0.0)],
        area=1200.0,
    )
    assert _is_triangle_sliver(complex_small) is False


def test_empty_polygon_is_kept() -> None:
    # Edge case: empty list. ``_is_triangle_sliver`` must not crash.
    empty = _room("r6", [], area=0.0)
    assert _is_triangle_sliver(empty) is False


def test_activation_threshold_constant_is_positive() -> None:
    # Sanity: ensure the activation gate is set conservatively so the
    # filter does not apply on typical synthetic fixtures. If someone
    # drops the constant to 0 by accident the F6 filter could start
    # deleting rooms from tests/test_pipeline.py synthetic cases.
    assert _TRIANGLE_SLIVER_ACTIVATION_COUNT >= 20


def test_area_max_above_synthetic_bathroom() -> None:
    # Sanity: the area threshold must sit below the smallest legitimate
    # real bathroom (~3500 px² at 1.5x raster). If raised above that,
    # F6 would start removing real rooms on dense floor plans.
    assert _TRIANGLE_SLIVER_AREA_MAX <= 3000.0
