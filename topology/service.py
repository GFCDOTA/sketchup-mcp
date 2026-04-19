from __future__ import annotations

from collections import defaultdict
from itertools import combinations

import networkx as nx
from shapely.geometry import LineString
from shapely.ops import polygonize, unary_union

from model.types import ConnectivityReport, Junction, Room, SplitWall, Wall


def build_topology(
    walls: list[Wall], snap_tolerance: float | None = None
) -> tuple[list[SplitWall], list[Junction], list[Room], ConnectivityReport]:
    if snap_tolerance is None:
        snap_tolerance = _infer_snap_tolerance(walls)

    split_walls = _split_walls_at_intersections(walls)
    split_walls = _snap_endpoints(split_walls, snap_tolerance)
    split_walls = _drop_degenerate(split_walls)

    graph = nx.Graph()
    for wall in split_walls:
        graph.add_edge(wall.start, wall.end, wall_id=wall.wall_id, length=wall.length)

    junctions = _build_junctions(graph)
    rooms = _polygonize_rooms(split_walls)
    report = _build_connectivity_report(graph, rooms)
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
    points = {wall.start for wall in walls} | {wall.end for wall in walls}
    mapping = _cluster_points(list(points), tolerance)
    return [
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
        for wall in walls
    ]


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


def _build_junctions(graph: nx.Graph) -> list[Junction]:
    junctions: list[Junction] = []
    for index, node in enumerate(sorted(graph.nodes), start=1):
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
                junction_id=f"junction-{index}",
                point=node,
                degree=degree,
                kind=kind,
            )
        )
    return junctions


def _polygonize_rooms(walls: list[SplitWall]) -> list[Room]:
    if not walls:
        return []

    lines = [LineString([wall.start, wall.end]) for wall in walls]
    merged = unary_union(lines)
    polygons = list(polygonize(merged))
    if not polygons:
        return []

    thickness_reference = max(1.0, min((wall.thickness for wall in walls), default=1.0))
    min_area = thickness_reference * thickness_reference

    rooms: list[Room] = []
    for index, polygon in enumerate(polygons, start=1):
        if polygon.area < min_area:
            continue
        centroid = polygon.centroid
        rooms.append(
            Room(
                room_id=f"room-{index}",
                polygon=[(float(x), float(y)) for x, y in polygon.exterior.coords[:-1]],
                area=float(polygon.area),
                centroid=(float(centroid.x), float(centroid.y)),
            )
        )
    return rooms


def _build_connectivity_report(
    graph: nx.Graph, rooms: list[Room]
) -> ConnectivityReport:
    components = [sorted(component) for component in nx.connected_components(graph)] if graph.number_of_nodes() else []
    component_sizes = [len(component) for component in components]
    edge_count = graph.number_of_edges()
    largest_component = max(component_sizes, default=0)
    connected_ratio = 0.0 if edge_count == 0 else largest_component / max(1, graph.number_of_nodes())
    return ConnectivityReport(
        node_count=graph.number_of_nodes(),
        edge_count=edge_count,
        component_count=len(components),
        component_sizes=component_sizes,
        largest_component_ratio=round(connected_ratio, 4),
        rooms_detected=len(rooms),
    )
