"""Keep walls belonging to the geometric component with the most walls,
dropping disconnected annotations (carimbo, legenda, mini-plan, rodape)
in SVG inputs.

Must run AFTER detect_openings (so door-bridge walls reconnect through
doorways) and BEFORE build_topology (so polygonize only sees the
apartment's walls).

Implementation: buffer each wall by snap_tolerance, union, walk connected
polygons. Rank components by number of member walls. Wall count is a
robust discriminator because a mini-plan has simplified geometry with
fewer walls than the full plan, even when bbox-area is comparable.

Safe fallback: when the largest component does not have at least
`dominance_ratio` times more walls than the second-largest, walls are
returned unchanged. Never cuts blindly when ambiguous.
"""
from __future__ import annotations

from typing import TypedDict

from shapely.geometry import LineString, Point
from shapely.ops import unary_union

from model.types import Wall


class MainComponentReport(TypedDict):
    component_count: int
    selected_wall_count: int
    second_wall_count: int
    selected_bbox_area: float
    second_bbox_area: float
    dominance_applied: bool
    walls_dropped: int


def _bbox_area_of(geom) -> float:
    if geom.is_empty:
        return 0.0
    minx, miny, maxx, maxy = geom.bounds
    return (maxx - minx) * (maxy - miny)


def _midpoint(w: Wall) -> Point:
    return Point((w.start[0] + w.end[0]) / 2.0, (w.start[1] + w.end[1]) / 2.0)


def select_main_component(
    walls: list[Wall],
    snap_tolerance: float,
    dominance_ratio: float = 1.7,
) -> tuple[list[Wall], MainComponentReport]:
    """Return the subset of walls belonging to the geometric component
    with the most walls. Falls back to the full input when:
      - input has <= 1 wall
      - the buffered geometry is a single connected component
      - the largest component has fewer than `dominance_ratio` times more
        walls than the second-largest (ambiguous -> never cut)
    """
    if len(walls) <= 1:
        return list(walls), MainComponentReport(
            component_count=1 if walls else 0,
            selected_wall_count=len(walls),
            second_wall_count=0,
            selected_bbox_area=0.0,
            second_bbox_area=0.0,
            dominance_applied=False,
            walls_dropped=0,
        )

    buf = max(snap_tolerance, 1e-6)
    buffered = [LineString([w.start, w.end]).buffer(buf, cap_style=1) for w in walls]
    mass = unary_union(buffered)
    components = list(mass.geoms) if mass.geom_type == "MultiPolygon" else [mass]

    if len(components) <= 1:
        return list(walls), MainComponentReport(
            component_count=1,
            selected_wall_count=len(walls),
            second_wall_count=0,
            selected_bbox_area=_bbox_area_of(components[0]) if components else 0.0,
            second_bbox_area=0.0,
            dominance_applied=False,
            walls_dropped=0,
        )

    # Assign each wall to the component whose buffered geometry contains
    # its midpoint. Ties (a wall on a shared boundary) are rare after the
    # buffer step; we use the first hit deterministically.
    comp_walls: list[list[Wall]] = [[] for _ in components]
    for w in walls:
        mid = _midpoint(w)
        for idx, comp in enumerate(components):
            if comp.intersects(mid):
                comp_walls[idx].append(w)
                break

    # Sort components by wall count (primary), bbox area (tiebreaker).
    order = sorted(
        range(len(components)),
        key=lambda i: (len(comp_walls[i]), _bbox_area_of(components[i])),
        reverse=True,
    )
    main_idx = order[0]
    runner_up = order[1]
    main_count = len(comp_walls[main_idx])
    runner_count = len(comp_walls[runner_up])

    if runner_count > 0 and main_count < dominance_ratio * runner_count:
        return list(walls), MainComponentReport(
            component_count=len(components),
            selected_wall_count=main_count,
            second_wall_count=runner_count,
            selected_bbox_area=_bbox_area_of(components[main_idx]),
            second_bbox_area=_bbox_area_of(components[runner_up]),
            dominance_applied=False,
            walls_dropped=0,
        )

    main_walls = comp_walls[main_idx]
    return main_walls, MainComponentReport(
        component_count=len(components),
        selected_wall_count=main_count,
        second_wall_count=runner_count,
        selected_bbox_area=_bbox_area_of(components[main_idx]),
        second_bbox_area=_bbox_area_of(components[runner_up]),
        dominance_applied=True,
        walls_dropped=len(walls) - len(main_walls),
    )
