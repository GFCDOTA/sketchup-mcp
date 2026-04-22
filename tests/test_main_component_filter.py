"""Unit tests for ``topology.main_component_filter.select_main_component``.

Covers the safe-fallback contract: the filter may only drop walls when one
connected component's wall count dominates the second-largest by at least
``dominance_ratio``. In every other case (empty, singleton, single
component, ambiguous ratio) the input walls flow through unchanged.
"""
from __future__ import annotations

from model.types import Wall
from topology.main_component_filter import select_main_component


def _wall(wid: str, start: tuple[float, float], end: tuple[float, float],
          orientation: str = "horizontal") -> Wall:
    return Wall(
        wall_id=wid,
        page_index=0,
        start=start,
        end=end,
        thickness=6.0,
        orientation=orientation,
        source="test",
        confidence=1.0,
    )


def _rect_walls(prefix: str, x0: float, y0: float, w: float, h: float) -> list[Wall]:
    """Return 4 walls forming a closed rectangle with corners snapped together."""
    x1, y1 = x0 + w, y0 + h
    return [
        _wall(f"{prefix}_b", (x0, y0), (x1, y0), orientation="horizontal"),
        _wall(f"{prefix}_r", (x1, y0), (x1, y1), orientation="vertical"),
        _wall(f"{prefix}_t", (x1, y1), (x0, y1), orientation="horizontal"),
        _wall(f"{prefix}_l", (x0, y1), (x0, y0), orientation="vertical"),
    ]


def test_drops_isolated_small_component() -> None:
    # Apartment has MANY walls (simulated by 3 chained rectangles sharing
    # corners = 12 walls). Legend is a single small rectangle (4 walls).
    # wall_count ratio 12/4 = 3.0 > default 1.7 => cut.
    apartment = (
        _rect_walls("apt1", 0.0, 0.0, 100.0, 80.0)
        + _rect_walls("apt2", 100.0, 0.0, 100.0, 80.0)
        + _rect_walls("apt3", 0.0, 80.0, 200.0, 80.0)
    )
    legend = _rect_walls("leg", 800.0, 800.0, 10.0, 10.0)
    walls = apartment + legend

    kept, report = select_main_component(walls, snap_tolerance=3.0)

    assert len(kept) == len(apartment)
    assert all(w.wall_id.startswith("apt") for w in kept)
    assert report["component_count"] == 2
    assert report["dominance_applied"] is True
    assert report["walls_dropped"] == 4
    assert report["selected_wall_count"] == len(apartment)
    assert report["second_wall_count"] == len(legend)


def test_fallback_when_no_dominant() -> None:
    # Two similar-sized rectangles: 4 vs 4 walls, ratio 1.0 < 1.7 => fallback.
    comp_a = _rect_walls("a", 0.0, 0.0, 100.0, 100.0)
    comp_b = _rect_walls("b", 500.0, 500.0, 90.0, 90.0)
    walls = comp_a + comp_b

    kept, report = select_main_component(walls, snap_tolerance=3.0)

    assert len(kept) == 8
    assert report["component_count"] == 2
    assert report["dominance_applied"] is False
    assert report["walls_dropped"] == 0
    assert report["selected_wall_count"] == 4
    assert report["second_wall_count"] == 4


def test_single_component_is_noop() -> None:
    walls = _rect_walls("only", 0.0, 0.0, 100.0, 80.0)

    kept, report = select_main_component(walls, snap_tolerance=3.0)

    assert len(kept) == len(walls)
    assert report["component_count"] == 1
    assert report["dominance_applied"] is False
    assert report["walls_dropped"] == 0


def test_report_has_expected_shape() -> None:
    walls = _rect_walls("only", 0.0, 0.0, 50.0, 50.0)

    _, report = select_main_component(walls, snap_tolerance=3.0)

    assert set(report.keys()) == {
        "component_count",
        "selected_wall_count",
        "second_wall_count",
        "selected_bbox_area",
        "second_bbox_area",
        "dominance_applied",
        "walls_dropped",
    }


def test_empty_input_returns_empty() -> None:
    kept, report = select_main_component([], snap_tolerance=1.0)

    assert kept == []
    assert report["component_count"] == 0
    assert report["dominance_applied"] is False
    assert report["walls_dropped"] == 0
