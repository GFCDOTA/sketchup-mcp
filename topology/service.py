from __future__ import annotations

from collections import defaultdict
from itertools import combinations

import networkx as nx
from shapely.geometry import LineString
from shapely.ops import polygonize, unary_union

from model.types import ConnectivityReport, Junction, Room, SplitWall, Wall


_MIN_COMPONENT_SIZE = 4


def build_topology(
    walls: list[Wall], snap_tolerance: float | None = None
) -> tuple[list[SplitWall], list[Junction], list[Room], ConnectivityReport]:
    if snap_tolerance is None:
        snap_tolerance = _infer_snap_tolerance(walls)

    split_walls = _split_walls_at_intersections(walls)
    split_walls = _snap_endpoints(split_walls, snap_tolerance)
    split_walls = _drop_degenerate(split_walls)
    split_walls = _drop_small_components(split_walls)

    by_page: dict[int, list[SplitWall]] = {}
    for wall in split_walls:
        by_page.setdefault(wall.page_index, []).append(wall)

    junctions: list[Junction] = []
    component_sizes: list[int] = []
    total_nodes = 0
    total_edges = 0
    max_components_within_page = 0
    per_page_ratios: list[float] = []
    junction_counter = 1

    for page_index in sorted(by_page):
        page_walls = by_page[page_index]
        graph = nx.Graph()
        for wall in page_walls:
            graph.add_edge(wall.start, wall.end, wall_id=wall.wall_id, length=wall.length)

        junctions.extend(_build_page_junctions(graph, start_id=junction_counter))
        junction_counter += len([node for node in graph.nodes if graph.degree(node) > 0])

        page_components = list(nx.connected_components(graph))
        max_components_within_page = max(max_components_within_page, len(page_components))

        page_nodes = graph.number_of_nodes()
        page_edges = graph.number_of_edges()
        total_nodes += page_nodes
        total_edges += page_edges
        for component in page_components:
            component_sizes.append(len(component))

        if page_edges > 0 and page_nodes > 0:
            largest = max((len(c) for c in page_components), default=0)
            per_page_ratios.append(largest / page_nodes)

    rooms = _polygonize_rooms(split_walls)
    report = _build_connectivity_report_aggregate(
        total_nodes=total_nodes,
        total_edges=total_edges,
        component_sizes=component_sizes,
        rooms=rooms,
        page_count=len(by_page),
        max_components_within_page=max_components_within_page,
        min_intra_page_connectivity_ratio=min(per_page_ratios) if per_page_ratios else 0.0,
    )
    return split_walls, junctions, rooms, report


def _infer_snap_tolerance(walls: list[Wall]) -> float:
    thicknesses = [w.thickness for w in walls if w.thickness > 0]
    if not thicknesses:
        return 2.0
    thicknesses.sort()
    median = thicknesses[len(thicknesses) // 2]
    return max(2.0, median)


def _snap_endpoints(walls: list[SplitWall], tolerance: float) -> list[SplitWall]:
    if not walls:
        return walls

    by_page: dict[int, list[SplitWall]] = {}
    for wall in walls:
        by_page.setdefault(wall.page_index, []).append(wall)

    snapped: list[SplitWall] = []
    for page_walls in by_page.values():
        points = {wall.start for wall in page_walls} | {wall.end for wall in page_walls}
        mapping = _cluster_points(list(points), tolerance)
        snapped.extend(
            SplitWall(
                wall_id=wall.wall_id,
                parent_wall_id=wall.parent_wall_id,
                page_index=wall.page_index,
                start=mapping[wall.start],
                end=mapping[wall.end],
                thickness=wall.thickness,
                orientation=wall.orientation,
                source=wall.source,
                confidence=wall.confidence,
            )
            for wall in page_walls
        )
    return snapped


def _cluster_points(
    points: list[tuple[float, float]], tolerance: float
) -> dict[tuple[float, float], tuple[float, float]]:
    ordered = sorted(points)
    clusters: list[list[tuple[float, float]]] = []
    for point in ordered:
        assigned = False
        for cluster in clusters:
            cx = sum(p[0] for p in cluster) / len(cluster)
            cy = sum(p[1] for p in cluster) / len(cluster)
            if abs(point[0] - cx) <= tolerance and abs(point[1] - cy) <= tolerance:
                cluster.append(point)
                assigned = True
                break
        if not assigned:
            clusters.append([point])

    mapping: dict[tuple[float, float], tuple[float, float]] = {}
    for cluster in clusters:
        cx = round(sum(p[0] for p in cluster) / len(cluster), 3)
        cy = round(sum(p[1] for p in cluster) / len(cluster), 3)
        representative = (cx, cy)
        for point in cluster:
            mapping[point] = representative
    return mapping


def _drop_degenerate(walls: list[SplitWall]) -> list[SplitWall]:
    return [wall for wall in walls if wall.start != wall.end]


def _drop_small_components(walls: list[SplitWall]) -> list[SplitWall]:
    """Remove walls that belong to a connected component smaller than
    _MIN_COMPONENT_SIZE. Per-page graph construction keeps pages
    isolated. A very small component is an orphan cluster of detections
    that cannot close a room anyway; dropping them reduces dangling
    `end` junctions and keeps the connectivity report honest.
    """
    if not walls:
        return walls

    by_page: dict[int, list[SplitWall]] = {}
    for wall in walls:
        by_page.setdefault(wall.page_index, []).append(wall)

    kept: list[SplitWall] = []
    for page_walls in by_page.values():
        graph = nx.Graph()
        for wall in page_walls:
            graph.add_edge(wall.start, wall.end)
        retained_nodes: set[tuple[float, float]] = set()
        for component in nx.connected_components(graph):
            if len(component) >= _MIN_COMPONENT_SIZE:
                retained_nodes.update(component)
        kept.extend(
            wall
            for wall in page_walls
            if wall.start in retained_nodes and wall.end in retained_nodes
        )
    return kept


def _split_walls_at_intersections(walls: list[Wall]) -> list[SplitWall]:
    split_points: dict[str, set[tuple[float, float]]] = defaultdict(set)

    for wall in walls:
        split_points[wall.wall_id].add(wall.start)
        split_points[wall.wall_id].add(wall.end)

    for wall_a, wall_b in combinations(walls, 2):
        intersection = _intersection_point(wall_a, wall_b)
        if intersection is None:
            continue
        split_points[wall_a.wall_id].add(intersection)
        split_points[wall_b.wall_id].add(intersection)

    result: list[SplitWall] = []
    counter = 1
    for wall in walls:
        ordered = _sort_points_along_wall(list(split_points[wall.wall_id]), wall.orientation)
        for start, end in zip(ordered, ordered[1:]):
            if _segment_length(start, end) == 0:
                continue
            result.append(
                SplitWall(
                    wall_id=f"segment-{counter}",
                    parent_wall_id=wall.wall_id,
                    page_index=wall.page_index,
                    start=start,
                    end=end,
                    thickness=wall.thickness,
                    orientation=wall.orientation,
                    source=wall.source,
                    confidence=wall.confidence,
                )
            )
            counter += 1
    return result


def _intersection_point(wall_a: Wall, wall_b: Wall) -> tuple[float, float] | None:
    if wall_a.page_index != wall_b.page_index:
        return None

    if wall_a.orientation == wall_b.orientation:
        return None

    horizontal = wall_a if wall_a.orientation == "horizontal" else wall_b
    vertical = wall_a if wall_a.orientation == "vertical" else wall_b

    x = vertical.start[0]
    y = horizontal.start[1]

    if horizontal.start[0] <= x <= horizontal.end[0] and vertical.start[1] <= y <= vertical.end[1]:
        return (round(x, 3), round(y, 3))
    return None


def _sort_points_along_wall(points: list[tuple[float, float]], orientation: str) -> list[tuple[float, float]]:
    unique_points = sorted(set((round(x, 3), round(y, 3)) for x, y in points))
    if orientation == "horizontal":
        return sorted(unique_points, key=lambda point: (point[0], point[1]))
    return sorted(unique_points, key=lambda point: (point[1], point[0]))


def _segment_length(start: tuple[float, float], end: tuple[float, float]) -> float:
    return abs(end[0] - start[0]) + abs(end[1] - start[1])


def _build_page_junctions(graph: nx.Graph, start_id: int) -> list[Junction]:
    junctions: list[Junction] = []
    counter = start_id
    for node in sorted(graph.nodes):
        degree = graph.degree(node)
        if degree == 0:
            continue
        kind = "end"
        if degree == 2:
            kind = "pass_through"
        elif degree == 3:
            kind = "tee"
        elif degree >= 4:
            kind = "cross"
        junctions.append(
            Junction(
                junction_id=f"junction-{counter}",
                point=node,
                degree=degree,
                kind=kind,
            )
        )
        counter += 1
    return junctions


def _polygonize_rooms(walls: list[SplitWall]) -> list[Room]:
    if not walls:
        return []

    by_page: dict[int, list[SplitWall]] = {}
    for wall in walls:
        by_page.setdefault(wall.page_index, []).append(wall)

    rooms: list[Room] = []
    counter = 1
    for page_index in sorted(by_page):
        page_walls = by_page[page_index]
        lines = [LineString([wall.start, wall.end]) for wall in page_walls]
        merged = unary_union(lines)
        polygons = list(polygonize(merged))
        if not polygons:
            continue

        # Use the median thickness as the spatial floor rather than the
        # minimum: a single thin fragment left over from extract would
        # otherwise push min_area to ~1 px^2 and admit any closed sliver.
        # A room must cover at least a square of side ~ median thickness
        # (in practice, 2x that square).
        thicknesses = sorted(w.thickness for w in page_walls if w.thickness > 0)
        if thicknesses:
            median_thickness = thicknesses[len(thicknesses) // 2]
        else:
            median_thickness = 1.0
        thickness_reference = max(1.0, median_thickness)
        min_area = (2.0 * thickness_reference) ** 2

        for polygon in polygons:
            if polygon.area < min_area:
                continue
            centroid = polygon.centroid
            rooms.append(
                Room(
                    room_id=f"room-{counter}",
                    polygon=[(float(x), float(y)) for x, y in polygon.exterior.coords[:-1]],
                    area=float(polygon.area),
                    centroid=(float(centroid.x), float(centroid.y)),
                )
            )
            counter += 1
    return rooms


def _build_connectivity_report_aggregate(
    total_nodes: int,
    total_edges: int,
    component_sizes: list[int],
    rooms: list[Room],
    page_count: int,
    max_components_within_page: int,
    min_intra_page_connectivity_ratio: float,
) -> ConnectivityReport:
    largest_component = max(component_sizes, default=0)
    connected_ratio = (
        0.0 if total_edges == 0 or total_nodes == 0 else largest_component / total_nodes
    )
    return ConnectivityReport(
        node_count=total_nodes,
        edge_count=total_edges,
        component_count=len(component_sizes),
        component_sizes=component_sizes,
        largest_component_ratio=round(connected_ratio, 4),
        rooms_detected=len(rooms),
        page_count=page_count,
        max_components_within_page=max_components_within_page,
        min_intra_page_connectivity_ratio=round(min_intra_page_connectivity_ratio, 4),
    )
