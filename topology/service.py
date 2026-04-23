from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from itertools import combinations

import networkx as nx
from shapely.geometry import LineString, Polygon, box
from shapely.ops import polygonize, unary_union

from model.types import (
    ConnectivityReport,
    Junction,
    Room,
    RoomCheck,
    RoomTopologyReport,
    SplitWall,
    Wall,
)


_ORPHAN_COMPONENT_MAX_NODES = 3
_SMART_SPLIT_EPSILON_RATIO = 0.75
_SPUR_MIN_THICKNESS_RATIO = 1.0

# Sliver filter for polygonize output. Polygons below _SLIVER_AREA_GATE
# are subjected to two shape tests; if either fails they are dropped:
#   - bbox aspect ratio min_side / max_side < _SLIVER_ASPECT_MIN
#     (triangles and thin quads wedge against one side of their bbox)
#   - isoperimetric compactness 4*pi*area / perimeter^2 <
#     _SLIVER_COMPACTNESS_MIN (true rooms are roughly box-like; slivers
#     are elongated or degenerate)
# The gate on area protects legitimate small rooms (bathrooms, closets)
# from being filtered: a 3 m^2 bathroom drawn at 2x scale covers far
# more than _SLIVER_AREA_GATE px^2. Thresholds recommended by GPT after
# analysing the planta_74 area distribution (p25 ~ 1660 px^2, p75 ~
# 12400 px^2); tuned conservatively so an L-shape or long corridor does
# not trigger because its area puts it above the gate.
_SLIVER_AREA_GATE = 5000.0
# Thresholds calibrated against p12_red.pdf corridors: aspect 0.12 and
# compactness 0.20 are the tightest values at which all p12 rooms
# still pass (specifically the narrow corridor-shape rooms at
# area~5500, aspect~0.13). A stricter setting (0.18 / 0.30) drops
# one of those corridors, which counts as a regression. Catches ~6
# slivers per run on planta_74 without touching any p12 room.
_SLIVER_ASPECT_MIN = 0.12
_SLIVER_COMPACTNESS_MIN = 0.20

# Strip-room merge (F5): collapses thin long polygons produced between
# pairs of nearly-parallel walls that dedup (perp_tolerance=20) could
# not absorb because they are genuinely distinct walls, not twin
# detections. The merge is applied on the room adjacency graph after
# polygonize.
#
# Triggers merge iff ALL three signals agree:
#   - width_estimate = area / length_major_axis <= _STRIP_WIDTH_FACTOR *
#     median_wall_thickness   (decisive: strip thickness matches
#     wall thickness; a real room is ~5x wider functionally)
#   - bbox aspect_ratio <= _STRIP_ASPECT_MAX
#   - shared boundary length with at least one neighbour >=
#     _STRIP_SHARED_RATIO_MIN of the strip's own perimeter
# Multi-neighbour tie break: score = shared_length + 0.001 * area;
# highest score wins.
#
# No area gate: width_estimate already separates strips (width ~ wall
# thickness) from legitimate small rooms (bathrooms/closets have
# functional width >> 2.5 * wall_thickness). A 2 m^2 bathroom drawn
# at 2x raster scale has width_estimate around 100-150 px while the
# ceiling lands on 25-30 px.
_STRIP_WIDTH_FACTOR = 2.5
# General aspect bound for strip detection. A real room in a floor
# plan rarely has bbox aspect below ~0.15 (even a corridor has some
# width). A strip between two parallel walls, by contrast, has aspect
# close to 0 because its width is dominated by wall thickness.
_STRIP_ASPECT_MAX = 0.20
_STRIP_SHARED_RATIO_MIN = 0.60
# After a strip grows (absorbing neighbours on subsequent passes), its
# width_estimate can exceed the wall-thickness multiple; fall back to
# "almost fully enclosed by other rooms" (high total shared ratio) as
# the secondary signal. Tighter aspect gate in this path avoids
# catching legitimate corridors (p12_red has corridor-shape rooms at
# aspect 0.18 that are NOT strips — they have real architectural
# width, just happen to be long).
_STRIP_HIGH_RATIO = 0.80
_STRIP_HIGH_RATIO_ASPECT_MAX = 0.14
# Even in the elastic path (strip that has grown by absorbing
# neighbours), the effective width must stay within a few multiples
# of the median wall thickness. Real enclosed corridors have
# functional width >5x wall thickness (p12_red room-19 has a corridor
# with width_estimate ~7x wall_thickness that is NOT a strip), so this
# cap stops the merge from engulfing them.
_STRIP_HIGH_RATIO_WIDTH_FACTOR = 5.0
_STRIP_MAX_ITER = 5

# F6 room dedup thresholds — a final pass after F5 strip-merge to tame
# residual sliver artefacts that polygonize produced at wall junctions
# and small gaps. F6 only operates on the room set (walls/junctions are
# already frozen by this point so the topology snapshot hash is not
# affected). The three passes are composed in order:
#
#   F6.1 _drop_micro_slivers — reject polygons below a thickness-scaled
#     floor EXCEPT when the polygon looks architecturally plausible (a
#     compact quad with near-unit aspect, like a small closet). The
#     ``(4 * t) ** 2`` floor corresponds to "smaller than a 4-thickness
#     square" — at p12 raster scale that is ~233 px², at planta_74
#     scale ~2100 px². The ``max(1000.0, ...)`` guard exists so a very
#     thin-line plan does not lose the floor entirely.
#   F6.2 _merge_3vertex_slivers — triangular polygons are almost always
#     polygonize artefacts (real rooms are rectilinear). Absorb them
#     into their largest shared-boundary neighbour. Iterative: one
#     triangle can absorb into a growing neighbour over multiple
#     passes.
#   F6.3 _merge_adjacency_pairs — catches tight quad-pair splits where
#     dedup left two adjacent rectangles that are really one room.
#     Conservative: requires (a) boundary sharing > 55% of the smaller
#     room's perimeter, (b) bbox overlap > 30% of the smaller bbox,
#     and (c) the smaller room is below 5000 px² (legit big rooms do
#     not need to be merged).
_F6_MICRO_FLOOR_ABS = 1000.0
_F6_MICRO_FLOOR_FACTOR = 4.0
_F6_PROTECTED_ASPECT_MIN = 0.7
_F6_PROTECTED_COMPACTNESS_MIN = 0.5
_F6_PROTECTED_MIN_VERTICES = 4
_F6_3VERT_MAX_ITER = 3
_F6_ADJ_SHARED_RATIO_MIN = 0.55
_F6_ADJ_BBOX_OVERLAP_MIN = 0.30
_F6_ADJ_SMALL_AREA_MAX = 5000.0
_F6_ROOM_COUNT_DEVIATION_MIN = 9
_F6_ROOM_COUNT_DEVIATION_MAX = 18


def build_topology(
    walls: list[Wall],
    snap_tolerance: float | None = None,
    *,
    room_topology_report_sink: list | None = None,
    snapshot_hash_sink: list | None = None,
) -> tuple[list[SplitWall], list[Junction], list[Room], ConnectivityReport]:
    """Build topology from classified walls.

    Optional keyword-only sinks receive audit artifacts without changing
    the return tuple (preserves backward compatibility with existing
    call sites and tests):

    - ``room_topology_report_sink``: if an empty list is passed, a
      ``RoomTopologyReport`` describing polygon validity, area filter
      hits, and nested-containment warnings is appended.
    - ``snapshot_hash_sink``: if passed, a SHA256 hex string derived
      from the canonical (walls, junctions) serialization is appended.
      Clean baselines (p10/p11/p12) should produce identical hashes
      across semantically equivalent algorithm refactors — the hash
      is the regression gate for F1.
    """
    if snap_tolerance is None:
        snap_tolerance = _infer_snap_tolerance(walls)

    epsilon = _SMART_SPLIT_EPSILON_RATIO * snap_tolerance / 1.5  # = 0.75 * median
    split_walls = _split_walls_at_intersections(walls, epsilon=epsilon)
    split_walls = _snap_endpoints(split_walls, snap_tolerance)
    split_walls = _drop_degenerate(split_walls)
    # Junctions, polygonize and connectivity are computed from the
    # SPLIT graph (each intersection is a node), so cross/tee
    # information stays intact even after we merge colinear segments
    # for the wall-output list.
    output_walls = _merge_colinear_segments(split_walls)

    by_page: dict[int, list[SplitWall]] = {}
    for wall in split_walls:
        by_page.setdefault(wall.page_index, []).append(wall)

    junctions: list[Junction] = []
    component_sizes: list[int] = []
    total_nodes = 0
    total_edges = 0
    max_components_within_page = 0
    per_page_ratios: list[float] = []
    orphan_component_count = 0
    orphan_node_count = 0
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
            if len(component) <= _ORPHAN_COMPONENT_MAX_NODES:
                orphan_component_count += 1
                orphan_node_count += len(component)

        if page_edges > 0 and page_nodes > 0:
            largest = max((len(c) for c in page_components), default=0)
            per_page_ratios.append(largest / page_nodes)

    rooms, min_area_threshold = _polygonize_rooms_with_threshold(split_walls)
    rooms = _merge_strip_rooms(rooms, split_walls)
    # F6: dedup pass — drop micro slivers, absorb triangles, merge
    # obvious split pairs. Operates on rooms only, so topology snapshot
    # hash (derived from walls + junctions above) is unaffected.
    rooms = _drop_micro_slivers(rooms, split_walls)
    rooms = _merge_3vertex_slivers(rooms)
    rooms = _merge_adjacency_pairs(rooms)
    report = _build_connectivity_report_aggregate(
        total_nodes=total_nodes,
        total_edges=total_edges,
        component_sizes=component_sizes,
        rooms=rooms,
        page_count=len(by_page),
        max_components_within_page=max_components_within_page,
        min_intra_page_connectivity_ratio=min(per_page_ratios) if per_page_ratios else 0.0,
        orphan_component_count=orphan_component_count,
        orphan_node_count=orphan_node_count,
    )

    if room_topology_report_sink is not None:
        room_topology_report_sink.append(
            _validate_room_polygons(rooms, min_area_threshold)
        )
    if snapshot_hash_sink is not None:
        snapshot_hash_sink.append(
            _topology_snapshot_hash(output_walls, junctions)
        )

    return output_walls, junctions, rooms, report


def _infer_snap_tolerance(walls: list[Wall]) -> float:
    thicknesses = [w.thickness for w in walls if w.thickness > 0]
    if not thicknesses:
        return 2.0
    thicknesses.sort()
    median = thicknesses[len(thicknesses) // 2]
    # Quando o input ja vem limpo (poucas walls), os endpoints ficam mais
    # esparsos por causa dos gaps de porta — precisa de tolerancia maior
    # pra fechar polygons. Heuristica: floor adaptativo baseado em densidade.
    base = max(2.0, 3.0 * median)
    if len(walls) < 30:
        return max(base, 25.0)  # input limpo -> snap mais agressivo
    return base


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


def _is_near_existing(
    point: tuple[float, float],
    existing: set[tuple[float, float]],
    epsilon: float,
) -> bool:
    if epsilon <= 0:
        return False
    px, py = point
    for ex, ey in existing:
        if abs(px - ex) <= epsilon and abs(py - ey) <= epsilon:
            return True
    return False


def _merge_colinear_segments(walls: list[SplitWall]) -> list[SplitWall]:
    """Recombine SplitWalls that share an endpoint where they are the only
    two walls of their orientation.

    Cross junction (degree 4: 2 H + 2 V): the H pair merges through the V
    cross (V is unrelated, just intersects there) and vice versa.
    Tee (degree 3: 2 H + 1 V or 2 V + 1 H): the colinear pair merges
    through the stem.
    Pure pass-through (degree 2 same orientation): merges trivially.
    A degree-2 corner (H + V) cannot merge: different orientations.

    Page isolation: each page is processed independently.
    """
    if not walls:
        return walls

    by_page: dict[int, list[SplitWall]] = defaultdict(list)
    for wall in walls:
        by_page[wall.page_index].append(wall)

    merged: list[SplitWall] = []
    for page_walls in by_page.values():
        merged.extend(_merge_colinear_within_page(page_walls))
    return merged


def _merge_colinear_within_page(page_walls: list[SplitWall]) -> list[SplitWall]:
    walls = list(page_walls)
    while True:
        node_orient: dict[tuple[float, float], dict[str, list[int]]] = {}
        for i, w in enumerate(walls):
            for endpoint in (w.start, w.end):
                bucket = node_orient.setdefault(
                    endpoint, {"horizontal": [], "vertical": []}
                )
                bucket[w.orientation].append(i)

        merge_pair = None
        for node, by_orient in node_orient.items():
            for orient in ("horizontal", "vertical"):
                indices = by_orient[orient]
                if len(indices) == 2 and indices[0] != indices[1]:
                    merge_pair = (node, orient, indices[0], indices[1])
                    break
            if merge_pair:
                break

        if merge_pair is None:
            break

        node, orient, a_idx, b_idx = merge_pair
        a = walls[a_idx]
        b = walls[b_idx]
        other_a = a.start if a.end == node else a.end
        other_b = b.start if b.end == node else b.end
        if other_a == other_b:
            high, low = max(a_idx, b_idx), min(a_idx, b_idx)
            walls.pop(high)
            walls.pop(low)
            continue

        new_wall = SplitWall(
            wall_id=a.wall_id,
            parent_wall_id=a.parent_wall_id,
            page_index=a.page_index,
            start=other_a,
            end=other_b,
            thickness=max(a.thickness, b.thickness),
            orientation=orient,
            source=a.source,
            confidence=min(a.confidence, b.confidence),
        )
        high, low = max(a_idx, b_idx), min(a_idx, b_idx)
        walls.pop(high)
        walls[low] = new_wall

    return walls


def _split_walls_at_intersections(walls: list[Wall], epsilon: float = 0.0) -> list[SplitWall]:
    """Split each wall at every perpendicular intersection. When `epsilon`
    > 0, an intersection point that lies within `epsilon` of an existing
    endpoint of the wall being split is silently skipped (the existing
    endpoint absorbs it). This prevents micro-segments at locations where
    discretization noise creates a near-corner intersection.
    """
    split_points: dict[str, set[tuple[float, float]]] = defaultdict(set)

    for wall in walls:
        split_points[wall.wall_id].add(wall.start)
        split_points[wall.wall_id].add(wall.end)

    for wall_a, wall_b in combinations(walls, 2):
        intersection = _intersection_point(wall_a, wall_b)
        if intersection is None:
            continue
        if not _is_near_existing(intersection, split_points[wall_a.wall_id], epsilon):
            split_points[wall_a.wall_id].add(intersection)
        if not _is_near_existing(intersection, split_points[wall_b.wall_id], epsilon):
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
    rooms, _threshold = _polygonize_rooms_with_threshold(walls)
    return rooms


def _polygonize_rooms_with_threshold(
    walls: list[SplitWall],
) -> tuple[list[Room], float]:
    """Same as ``_polygonize_rooms`` but also returns the area floor
    used for the last page processed. Callers that only need rooms
    (the old signature) can call ``_polygonize_rooms`` unchanged;
    the audit path uses the threshold to report why a room passed
    or would have been dropped.

    When walls span multiple pages with different median thicknesses
    the threshold reported is the maximum across pages — the
    conservative floor that any kept room has cleared.
    """
    if not walls:
        return [], 0.0

    by_page: dict[int, list[SplitWall]] = {}
    for wall in walls:
        by_page.setdefault(wall.page_index, []).append(wall)

    rooms: list[Room] = []
    counter = 1
    max_threshold = 0.0
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
        max_threshold = max(max_threshold, min_area)

        for polygon in polygons:
            if polygon.area < min_area:
                continue
            if _is_sliver_polygon(polygon):
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
    return rooms, max_threshold


def _merge_strip_rooms(rooms: list[Room], walls: list[SplitWall]) -> list[Room]:
    """Iteratively merge "strip" rooms into their largest neighbour.

    A strip is a polygon whose width (minor axis length) matches the
    wall thickness — the signature of a polygon formed between two
    nearly-parallel walls that survived dedup. Because the criterion
    is an AND of four signals gated by area, legitimate small rooms
    (bathrooms, closets) cannot be misclassified: their width is
    several times the wall thickness even when their area is modest.

    Runs up to ``_STRIP_MAX_ITER`` iterations, rebuilding the adjacency
    graph after each batch; stops as soon as a pass produces no merge.
    Multi-neighbour ties are broken by shared-boundary length, with
    area as the secondary key (prefer merging into the larger neighbour
    when boundary lengths tie).
    """
    if len(rooms) < 2:
        return rooms

    wall_thicknesses = [w.thickness for w in walls if w.thickness > 0]
    if not wall_thicknesses:
        return rooms
    wall_thicknesses.sort()
    median_wall_thickness = wall_thicknesses[len(wall_thicknesses) // 2]
    width_ceiling = _STRIP_WIDTH_FACTOR * max(1.0, median_wall_thickness)

    current = list(rooms)
    for _ in range(_STRIP_MAX_ITER):
        if len(current) < 2:
            break

        polygons: dict[str, Polygon] = {}
        for r in current:
            if len(r.polygon) < 3:
                continue
            try:
                poly = Polygon(r.polygon)
                if poly.is_valid:
                    polygons[r.room_id] = poly
            except Exception:
                continue
        if len(polygons) < 2:
            break

        # Score each candidate strip against its best neighbour.
        merges: list[tuple[str, str]] = []  # (strip_id, target_id)
        claimed_targets: set[str] = set()
        claimed_strips: set[str] = set()

        for strip in current:
            if strip.room_id in claimed_strips or strip.room_id in claimed_targets:
                continue
            strip_poly = polygons.get(strip.room_id)
            if strip_poly is None:
                continue
            try:
                obb = strip_poly.minimum_rotated_rectangle
            except Exception:
                continue
            obb_coords = list(obb.exterior.coords)[:-1]
            if len(obb_coords) < 4:
                continue
            edges = [
                (
                    (obb_coords[i][0] - obb_coords[(i + 1) % 4][0]) ** 2
                    + (obb_coords[i][1] - obb_coords[(i + 1) % 4][1]) ** 2
                )
                ** 0.5
                for i in range(4)
            ]
            length_major = max(edges)
            if length_major <= 0:
                continue
            width_estimate = strip.area / length_major

            minx, miny, maxx, maxy = strip_poly.bounds
            bbox_w = max(1e-6, maxx - minx)
            bbox_h = max(1e-6, maxy - miny)
            bbox_aspect = min(bbox_w, bbox_h) / max(bbox_w, bbox_h)
            if bbox_aspect > _STRIP_ASPECT_MAX:
                continue

            strip_perim = max(1e-6, strip_poly.length)
            neighbour_shared: list[tuple[Room, float]] = []
            for other in current:
                if (
                    other.room_id == strip.room_id
                    or other.room_id in claimed_strips
                ):
                    continue
                other_poly = polygons.get(other.room_id)
                if other_poly is None:
                    continue
                if not strip_poly.touches(other_poly):
                    continue
                try:
                    boundary_inter = strip_poly.boundary.intersection(other_poly.boundary)
                except Exception:
                    continue
                shared_length = getattr(boundary_inter, "length", 0.0) or 0.0
                if shared_length <= 0:
                    continue
                neighbour_shared.append((other, shared_length))

            if not neighbour_shared:
                continue
            total_shared = sum(sl for _, sl in neighbour_shared)
            total_ratio = total_shared / strip_perim

            # Strip decision: width_estimate alone catches Hough-level
            # thin strips (width close to wall thickness). After a
            # merge in an earlier pass, the absorbed strip can grow
            # wider than the ceiling while keeping its strip aspect
            # and near-total enclosure — so we also accept polygons
            # that are visibly elongated (tighter aspect) AND mostly
            # bounded by other rooms.
            width_ok = width_estimate <= width_ceiling
            high_ratio_width_ceiling = (
                _STRIP_HIGH_RATIO_WIDTH_FACTOR * max(1.0, median_wall_thickness)
            )
            enclosed_ok = (
                total_ratio >= _STRIP_HIGH_RATIO
                and bbox_aspect <= _STRIP_HIGH_RATIO_ASPECT_MAX
                and width_estimate <= high_ratio_width_ceiling
            )
            if not (width_ok or enclosed_ok):
                continue
            if total_ratio < _STRIP_SHARED_RATIO_MIN:
                # Not sandwiched by neighbours enough — this is a real
                # room with exterior walls, not a strip between two
                # parallel walls.
                continue

            best_target = max(
                neighbour_shared,
                key=lambda pair: (pair[1], pair[0].area),
            )[0]
            merges.append((strip.room_id, best_target.room_id))
            claimed_strips.add(strip.room_id)
            claimed_targets.add(best_target.room_id)

        if not merges:
            break

        # Apply unions. Cannot chain merges into the same target in one
        # pass (would require re-scoring), hence the claimed_targets
        # guard above.
        target_updates: dict[str, Polygon] = {}
        for strip_id, target_id in merges:
            strip_poly = polygons[strip_id]
            target_poly = target_updates.get(target_id, polygons[target_id])
            try:
                union_poly = target_poly.union(strip_poly)
            except Exception:
                continue
            if union_poly.geom_type != "Polygon" or not union_poly.is_valid:
                # Merge would produce a disjoint multi-part — skip,
                # leave both rooms untouched.
                continue
            target_updates[target_id] = union_poly

        if not target_updates:
            break

        next_rooms: list[Room] = []
        for r in current:
            if r.room_id in claimed_strips:
                continue
            if r.room_id in target_updates:
                new_poly = target_updates[r.room_id]
                next_rooms.append(
                    Room(
                        room_id=r.room_id,
                        polygon=[
                            (float(x), float(y))
                            for x, y in new_poly.exterior.coords[:-1]
                        ],
                        area=float(new_poly.area),
                        centroid=(
                            float(new_poly.centroid.x),
                            float(new_poly.centroid.y),
                        ),
                    )
                )
            else:
                next_rooms.append(r)
        current = next_rooms

    return current


def _drop_micro_slivers(rooms: list[Room], walls: list[SplitWall]) -> list[Room]:
    """Drop rooms whose area falls below a thickness-scaled floor.

    The floor is ``max(_F6_MICRO_FLOOR_ABS, (factor * median_thickness) ** 2)``
    where ``factor = _F6_MICRO_FLOOR_FACTOR``. Intuition: a legitimate
    room must cover at least a square of side ``factor * wall thickness``.
    At p12 raster scale (median ~3.8 px) that produces a 1000 px² floor
    (absolute guard dominates); at planta_74 scale (median ~11.5 px) it
    grows to ~2100 px² which matches the raster's "visibly reasonable"
    size.

    The filter protects "small but architecturally plausible" rooms via
    a shape escape hatch: a polygon with >=4 vertices, aspect > 0.7, and
    compactness > 0.5 is kept even when below the floor. This saves
    small closets and utility rooms that read as rectangular (high
    aspect) and compact, while still catching thin splinters produced
    by polygonize at the end of wall splits.
    """
    if not rooms:
        return rooms
    thicknesses = [w.thickness for w in walls if w.thickness > 0]
    if not thicknesses:
        return rooms
    thicknesses.sort()
    median_thickness = thicknesses[len(thicknesses) // 2]
    floor = max(
        _F6_MICRO_FLOOR_ABS,
        (_F6_MICRO_FLOOR_FACTOR * max(1.0, median_thickness)) ** 2,
    )

    kept: list[Room] = []
    for room in rooms:
        if room.area >= floor:
            kept.append(room)
            continue
        if len(room.polygon) < 3:
            continue  # degenerate, drop regardless
        try:
            poly = Polygon(room.polygon)
        except Exception:
            continue
        if not poly.is_valid or poly.is_empty:
            continue
        minx, miny, maxx, maxy = poly.bounds
        bbox_w = max(1e-6, maxx - minx)
        bbox_h = max(1e-6, maxy - miny)
        aspect = min(bbox_w, bbox_h) / max(bbox_w, bbox_h)
        perim = poly.length
        compactness = 4.0 * math.pi * poly.area / (perim * perim) if perim > 0 else 0.0
        if (
            len(room.polygon) >= _F6_PROTECTED_MIN_VERTICES
            and aspect >= _F6_PROTECTED_ASPECT_MIN
            and compactness >= _F6_PROTECTED_COMPACTNESS_MIN
        ):
            kept.append(room)  # architecturally plausible small room
    return kept


def _merge_3vertex_slivers(rooms: list[Room]) -> list[Room]:
    """Absorb triangular polygons into their largest shared-boundary neighbour.

    Polygonize occasionally produces 3-vertex polygons where two walls
    converge at a gap or where a split intersects at an angle. These
    are always artefacts — a real room in a floor plan has >=4 sides.
    The merger picks the neighbour with the highest shared boundary
    length as the absorption target and performs a Shapely union. If
    the union would turn into a MultiPolygon or become invalid the
    merge is skipped (the triangle is left in place rather than
    corrupting the geometry).

    Iterative: a triangle that merges first may become a quad; a
    neighbouring triangle will then share a longer boundary with the
    grown room and merge in the next pass. Converges within a handful
    of passes in practice (``_F6_3VERT_MAX_ITER`` caps the cost in
    pathological inputs).
    """
    if len(rooms) < 2:
        return rooms

    current = list(rooms)
    for _ in range(_F6_3VERT_MAX_ITER):
        polygons: dict[str, Polygon] = {}
        for r in current:
            if len(r.polygon) < 3:
                continue
            try:
                poly = Polygon(r.polygon)
                if poly.is_valid:
                    polygons[r.room_id] = poly
            except Exception:
                continue

        merges: dict[str, str] = {}  # triangle_id -> target_id
        claimed_strips: set[str] = set()
        claimed_targets: set[str] = set()
        for triangle in current:
            if len(triangle.polygon) != 3:
                continue
            if triangle.room_id in claimed_strips or triangle.room_id in claimed_targets:
                continue
            tp = polygons.get(triangle.room_id)
            if tp is None:
                continue
            best_target: str | None = None
            best_shared = 0.0
            for other in current:
                if other.room_id == triangle.room_id:
                    continue
                if other.room_id in claimed_strips:
                    continue
                op = polygons.get(other.room_id)
                if op is None:
                    continue
                if not tp.touches(op):
                    continue
                try:
                    shared = tp.boundary.intersection(op.boundary).length
                except Exception:
                    shared = 0.0
                if shared > best_shared:
                    best_shared = shared
                    best_target = other.room_id
            if best_target is None or best_shared <= 0:
                continue
            merges[triangle.room_id] = best_target
            claimed_strips.add(triangle.room_id)
            claimed_targets.add(best_target)

        if not merges:
            break

        target_updates: dict[str, Polygon] = {}
        for strip_id, target_id in merges.items():
            target_poly = target_updates.get(target_id, polygons[target_id])
            strip_poly = polygons[strip_id]
            try:
                union_poly = target_poly.union(strip_poly)
            except Exception:
                continue
            if union_poly.geom_type != "Polygon" or not union_poly.is_valid:
                continue
            target_updates[target_id] = union_poly

        if not target_updates:
            break

        next_rooms: list[Room] = []
        for r in current:
            if r.room_id in merges and merges[r.room_id] in target_updates:
                # Triangle absorbed — drop.
                continue
            if r.room_id in target_updates:
                new_poly = target_updates[r.room_id]
                next_rooms.append(
                    Room(
                        room_id=r.room_id,
                        polygon=[
                            (float(x), float(y))
                            for x, y in new_poly.exterior.coords[:-1]
                        ],
                        area=float(new_poly.area),
                        centroid=(
                            float(new_poly.centroid.x),
                            float(new_poly.centroid.y),
                        ),
                    )
                )
            else:
                next_rooms.append(r)
        current = next_rooms

    return current


def _merge_adjacency_pairs(rooms: list[Room]) -> list[Room]:
    """Final relaxed pass: merge room pairs that are visibly one room.

    Two rooms are considered a split pair when:
      - their shared boundary exceeds ``_F6_ADJ_SHARED_RATIO_MIN`` of
        the smaller room's perimeter (the smaller one is "mostly inside"
        the larger);
      - their bounding boxes overlap by more than
        ``_F6_ADJ_BBOX_OVERLAP_MIN`` of the smaller bbox (they occupy
        the same region spatially, not just touch along an edge);
      - the smaller one is below ``_F6_ADJ_SMALL_AREA_MAX`` (a sanity
        gate; we do not merge two genuinely large rooms even if they
        happen to share a long wall).

    When the criteria hold, the smaller room is merged into the larger.
    Each room participates in at most one merge per pass (greedy; a
    chain like A-B-C only consumes one link, but any residual pair
    would be caught by a subsequent run).
    """
    if len(rooms) < 2:
        return rooms

    polygons: dict[str, Polygon] = {}
    area_map: dict[str, float] = {}
    for r in rooms:
        if len(r.polygon) < 3:
            continue
        try:
            poly = Polygon(r.polygon)
            if poly.is_valid:
                polygons[r.room_id] = poly
                area_map[r.room_id] = poly.area
        except Exception:
            continue
    if len(polygons) < 2:
        return rooms

    ids = [r.room_id for r in rooms if r.room_id in polygons]
    merges: dict[str, str] = {}  # smaller_id -> larger_id
    claimed: set[str] = set()
    for i, a_id in enumerate(ids):
        if a_id in claimed:
            continue
        ap = polygons[a_id]
        a_area = area_map[a_id]
        a_perim = max(1e-6, ap.length)
        for b_id in ids[i + 1 :]:
            if b_id in claimed:
                continue
            bp = polygons[b_id]
            if not ap.touches(bp):
                continue
            try:
                shared = ap.boundary.intersection(bp.boundary).length
            except Exception:
                shared = 0.0
            if shared <= 0:
                continue
            b_area = area_map[b_id]
            b_perim = max(1e-6, bp.length)
            shared_ratio = shared / min(a_perim, b_perim)
            if shared_ratio <= _F6_ADJ_SHARED_RATIO_MIN:
                continue
            ab = box(*ap.bounds)
            bb = box(*bp.bounds)
            min_bbox_area = max(1e-6, min(ab.area, bb.area))
            bbox_overlap = ab.intersection(bb).area / min_bbox_area
            if bbox_overlap <= _F6_ADJ_BBOX_OVERLAP_MIN:
                continue
            min_area = min(a_area, b_area)
            if min_area >= _F6_ADJ_SMALL_AREA_MAX:
                continue
            # Merge smaller into larger.
            if a_area <= b_area:
                smaller, larger = a_id, b_id
            else:
                smaller, larger = b_id, a_id
            merges[smaller] = larger
            claimed.add(smaller)
            claimed.add(larger)
            break  # a is consumed, move on

    if not merges:
        return rooms

    target_updates: dict[str, Polygon] = {}
    for smaller, larger in merges.items():
        larger_poly = target_updates.get(larger, polygons[larger])
        smaller_poly = polygons[smaller]
        try:
            union_poly = larger_poly.union(smaller_poly)
        except Exception:
            continue
        if union_poly.geom_type != "Polygon" or not union_poly.is_valid:
            continue
        target_updates[larger] = union_poly

    if not target_updates:
        return rooms

    next_rooms: list[Room] = []
    for r in rooms:
        if r.room_id in merges and merges[r.room_id] in target_updates:
            continue
        if r.room_id in target_updates:
            new_poly = target_updates[r.room_id]
            next_rooms.append(
                Room(
                    room_id=r.room_id,
                    polygon=[
                        (float(x), float(y))
                        for x, y in new_poly.exterior.coords[:-1]
                    ],
                    area=float(new_poly.area),
                    centroid=(
                        float(new_poly.centroid.x),
                        float(new_poly.centroid.y),
                    ),
                )
            )
        else:
            next_rooms.append(r)
    return next_rooms


def _is_sliver_polygon(polygon: Polygon) -> bool:
    """Return True when the polygon shape is degenerate enough to be a
    snap / split artefact rather than a real room.

    The filter runs only below ``_SLIVER_AREA_GATE`` so real small
    rooms (e.g. bathrooms, closets) that sit above the gate are not
    subject to shape scrutiny, and elongated corridors that happen to
    be large keep their area-based pass. Below the gate a polygon
    fails if its bbox aspect ratio OR its isoperimetric compactness
    falls under the respective thresholds — either signal is strong
    enough on its own because slivers typically exhibit both.
    """
    if polygon.area >= _SLIVER_AREA_GATE:
        return False

    minx, miny, maxx, maxy = polygon.bounds
    bbox_w = max(1e-6, maxx - minx)
    bbox_h = max(1e-6, maxy - miny)
    aspect_ratio = min(bbox_w, bbox_h) / max(bbox_w, bbox_h)
    if aspect_ratio < _SLIVER_ASPECT_MIN:
        return True

    perimeter = polygon.length
    if perimeter <= 0:
        return True
    import math

    compactness = 4.0 * math.pi * polygon.area / (perimeter * perimeter)
    if compactness < _SLIVER_COMPACTNESS_MIN:
        return True

    return False


def _validate_room_polygons(
    rooms: list[Room], min_area_threshold: float
) -> RoomTopologyReport:
    """Audit the post-polygonize room set.

    Checks per room: Shapely ``is_valid`` on the reconstructed polygon,
    and whether the reported area clears the threshold used during
    polygonize. Nested pairs (outer room strictly containing another
    room) are flagged but do not fail the outer — nesting happens in
    legitimate floor plans when an inner enclosure exists, so it's a
    warning, not an error.
    """
    checks: list[RoomCheck] = []
    nested_pairs: list[tuple[str, str]] = []

    reconstructed: list[tuple[Room, Polygon]] = []
    for room in rooms:
        poly = Polygon(room.polygon) if len(room.polygon) >= 3 else None
        reconstructed.append((room, poly))

    inner_ids: set[str] = set()
    for outer_room, outer_poly in reconstructed:
        if outer_poly is None or not outer_poly.is_valid:
            continue
        for inner_room, inner_poly in reconstructed:
            if outer_room is inner_room or inner_poly is None:
                continue
            try:
                # ``contains`` is a strict containment with shared
                # boundary tolerated as non-contained — that's what
                # we want for nested enclosures.
                if outer_poly.contains(inner_poly):
                    nested_pairs.append((outer_room.room_id, inner_room.room_id))
                    inner_ids.add(inner_room.room_id)
            except Exception:
                continue

    passed = 0
    failed = 0
    for room, poly in reconstructed:
        if poly is None or not poly.is_valid:
            checks.append(
                RoomCheck(
                    room_id=room.room_id,
                    status="invalid_polygon",
                    area=room.area,
                    notes="Shapely is_valid=False",
                )
            )
            failed += 1
            continue
        if room.area < min_area_threshold:
            checks.append(
                RoomCheck(
                    room_id=room.room_id,
                    status="below_min_area",
                    area=room.area,
                    notes=f"area < threshold {min_area_threshold:.1f}",
                )
            )
            failed += 1
            continue
        if room.room_id in inner_ids:
            checks.append(
                RoomCheck(
                    room_id=room.room_id,
                    status="nested",
                    area=room.area,
                    notes="contained by another room (warning, not failure)",
                )
            )
            passed += 1
            continue
        checks.append(
            RoomCheck(room_id=room.room_id, status="pass", area=room.area)
        )
        passed += 1

    return RoomTopologyReport(
        total_rooms=len(rooms),
        passed=passed,
        failed=failed,
        min_area_threshold=round(min_area_threshold, 3),
        checks=checks,
        nested_pairs=nested_pairs,
    )


def _topology_snapshot_hash(
    walls: list[SplitWall], junctions: list[Junction]
) -> str:
    """Canonical SHA256 of (walls, junctions).

    Coordinates are rounded to 3 decimals before serialization to
    absorb float noise. Walls are sorted by
    ``(page_index, start, end, orientation)`` and junctions by
    ``(point, degree, kind)`` so the hash depends only on topology,
    not on processing order.
    """

    def _round_point(point: tuple[float, float]) -> list[float]:
        return [round(point[0], 3), round(point[1], 3)]

    wall_rows = sorted(
        [
            (
                w.page_index,
                tuple(_round_point(w.start)),
                tuple(_round_point(w.end)),
                w.orientation,
            )
            for w in walls
        ]
    )
    junction_rows = sorted(
        [
            (tuple(_round_point(j.point)), j.degree, j.kind)
            for j in junctions
        ]
    )
    payload = json.dumps(
        {"walls": wall_rows, "junctions": junction_rows},
        sort_keys=True,
        default=list,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _build_connectivity_report_aggregate(
    total_nodes: int,
    total_edges: int,
    component_sizes: list[int],
    rooms: list[Room],
    page_count: int,
    max_components_within_page: int,
    min_intra_page_connectivity_ratio: float,
    orphan_component_count: int,
    orphan_node_count: int,
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
        orphan_component_count=orphan_component_count,
        orphan_node_count=orphan_node_count,
    )
