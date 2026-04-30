from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from itertools import combinations

import networkx as nx
from shapely.geometry import LineString, Polygon
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
from topology.wall_interior_filter import is_room_noise, is_triangle_artifact, is_wall_interior


_ORPHAN_COMPONENT_MAX_NODES = 3
_SMART_SPLIT_EPSILON_RATIO = 0.75
_SPUR_MIN_THICKNESS_RATIO = 1.0


def build_topology(
    walls: list[Wall],
    snap_tolerance: float | None = None,
    *,
    room_topology_report_sink: list | None = None,
    snapshot_hash_sink: list | None = None,
    filter_wall_interior: bool = False,
    wall_thickness: float | None = None,
    filter_triangle_artifacts: bool = False,
    filter_room_noise: bool = False,
    rectify_to_orientation: bool = False,
    parallel_dedup_factor: float | None = None,
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

    Filter flags layer additively (each implies all weaker filters):
      - ``filter_wall_interior=True`` -> wall_interior + room_noise + triangle
        (SVG path: aggressive, requires double-drawn wall geometry)
      - ``filter_room_noise=True`` -> room_noise + triangle
        (raster path: drops slivers, narrow medium polygons; preserves
        corridors via aspect>3 + short>=1.5*thickness exception)
      - ``filter_triangle_artifacts=True`` -> triangle only
        (legacy raster: only 3-vertex artefacts dropped)

    Pre-split passes (raster path on by default once enabled by caller):
      - ``rectify_to_orientation=True``: each input ``Wall`` whose
        declared ``orientation`` is horizontal/vertical has its endpoints
        collapsed to the perpendicular midpoint, removing 5-15 degree
        jitter that otherwise propagates through ``_split_walls`` (which
        assumes pure H/V) and produces trapezoidal rooms after polygonize.
        Diagonal walls (orientation neither H nor V, or large declared
        deviation) pass through unchanged.
      - ``parallel_dedup_factor`` (``None`` to disable, otherwise a float
        in (0, 1.5] interpreted as a multiple of the median ``Wall``
        thickness): adjacent parallel walls within
        ``factor * median_thickness`` perpendicular and overlapping in
        the parallel direction are merged into a single wall whose
        perpendicular coordinate is the cluster centroid and whose
        parallel range is the union of input ranges. Use 0.5 to merge
        the inner+outer line of a double-drawn wall while preserving
        genuinely parallel walls separated by at least one thickness.
    """
    if filter_wall_interior and wall_thickness is None:
        raise ValueError(
            "filter_wall_interior=True requires wall_thickness to be provided "
            "(got None); pass the median wall thickness in the same units as "
            "the wall coordinates."
        )
    if filter_room_noise and wall_thickness is None:
        raise ValueError(
            "filter_room_noise=True requires wall_thickness to be provided; "
            "pass the median wall thickness in the same units as the wall "
            "coordinates."
        )
    if filter_triangle_artifacts and wall_thickness is None:
        raise ValueError(
            "filter_triangle_artifacts=True requires wall_thickness to be "
            "provided; pass the median wall thickness in the same units as "
            "the wall coordinates."
        )

    if snap_tolerance is None:
        snap_tolerance = _infer_snap_tolerance(walls)

    # Pre-split rectify + parallel dedup (raster path). Each is
    # opt-in so SVG path and existing tests stay byte-identical.
    if rectify_to_orientation:
        walls = _rectify_walls_to_orientation(walls)
    if parallel_dedup_factor is not None and walls:
        walls = _collapse_parallel_walls(walls, factor=parallel_dedup_factor)

    epsilon = _SMART_SPLIT_EPSILON_RATIO * snap_tolerance / 1.5  # = 0.75 * median
    split_walls = _split_walls_at_intersections(walls, epsilon=epsilon)
    split_walls = _snap_endpoints(split_walls, snap_tolerance)
    split_walls = _drop_degenerate(split_walls)
    # Junctions, polygonize and connectivity are computed from the
    # SPLIT graph (each intersection is a node), so cross/tee
    # information stays intact even after we merge colinear segments
    # for the wall-output list.
    output_walls = _merge_colinear_segments(split_walls)

    # _snap_endpoints clusters endpoints by axis-aligned proximity and
    # MIXES H/V endpoints, so a horizontal wall whose endpoint sat near
    # a vertical wall's endpoint can come out of merge with start.y !=
    # end.y — re-introducing the jitter that ``rectify_to_orientation``
    # tried to remove. A final pass on the output list, scoped to the
    # already-decided orientation tag, restores strict H/V geometry.
    # Junctions/rooms keep using split_walls (pre-merge), so this only
    # affects what callers see as ``walls`` in observed_model.
    if rectify_to_orientation:
        output_walls = _rectify_split_walls_to_orientation(output_walls)
        output_walls = [w for w in output_walls if w.start != w.end]

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

    rooms, min_area_threshold = _polygonize_rooms_with_threshold(
        split_walls,
        filter_wall_interior=filter_wall_interior,
        wall_thickness_override=wall_thickness,
        filter_triangle_artifacts=filter_triangle_artifacts,
        filter_room_noise=filter_room_noise,
    )
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


def _rectify_walls_to_orientation(walls: list[Wall]) -> list[Wall]:
    """Collapse each H/V-labeled wall to strict horizontal or vertical.

    Walls produced by the raster path carry an ``orientation`` label
    derived in ``classify._orientation`` from whichever span dominates,
    but their endpoints frequently retain 5-15 degree jitter from the
    underlying Hough fit. ``_split_walls_at_intersections`` and
    ``_intersection_point`` downstream assume *pure* horizontal/vertical
    geometry — they read ``horizontal.start[1]`` as the wall's y-line
    even when ``end[1]`` differs by 8 pixels. The mismatch is what
    produces the trapezoidal rooms after ``polygonize``: each room
    polygon traces wall lines with inconsistent perpendicular offsets.

    The fix is to make the geometry agree with the label *before* the
    pipeline relies on it. For each wall:

      - ``horizontal`` -> y = (start.y + end.y) / 2 for both endpoints
      - ``vertical``   -> x = (start.x + end.x) / 2 for both endpoints
      - other          -> kept as-is (genuine diagonals: corner cuts,
        staircases, scenic walls — must not be silently flattened).

    Why midpoint and not min/max: midpoint is unbiased w.r.t. which
    Hough sample produced which endpoint. Using min/max would
    systematically shift the wall toward one neighbor and break tee
    junctions.

    Returns a NEW list of ``Wall`` instances; inputs are unchanged.
    """
    rectified: list[Wall] = []
    for wall in walls:
        orientation = (wall.orientation or "").lower()
        if orientation == "horizontal":
            ymid = (wall.start[1] + wall.end[1]) / 2.0
            new_start = (round(wall.start[0], 3), round(ymid, 3))
            new_end = (round(wall.end[0], 3), round(ymid, 3))
        elif orientation == "vertical":
            xmid = (wall.start[0] + wall.end[0]) / 2.0
            new_start = (round(xmid, 3), round(wall.start[1], 3))
            new_end = (round(xmid, 3), round(wall.end[1], 3))
        else:
            rectified.append(wall)
            continue
        if new_start == new_end:
            # Wall collapsed to a point under rectification (very short
            # wall whose perpendicular jitter exceeded its parallel
            # length). Drop — it was noise, not a real wall.
            continue
        rectified.append(
            Wall(
                wall_id=wall.wall_id,
                page_index=wall.page_index,
                start=new_start,
                end=new_end,
                thickness=wall.thickness,
                orientation=wall.orientation,
                source=wall.source,
                confidence=wall.confidence,
            )
        )
    return rectified


def _rectify_split_walls_to_orientation(walls: list[SplitWall]) -> list[SplitWall]:
    """SplitWall variant of :func:`_rectify_walls_to_orientation`.

    Applied AFTER ``_merge_colinear_segments`` to undo the jitter that
    ``_snap_endpoints`` re-introduces when it clusters H and V endpoints
    in the same axis-aligned tolerance band. This pass is purely
    cosmetic for the output list — junctions/rooms reference the
    pre-merge ``split_walls`` and are not affected.
    """
    out: list[SplitWall] = []
    for wall in walls:
        orientation = (wall.orientation or "").lower()
        if orientation == "horizontal":
            ymid = (wall.start[1] + wall.end[1]) / 2.0
            new_start = (round(wall.start[0], 3), round(ymid, 3))
            new_end = (round(wall.end[0], 3), round(ymid, 3))
        elif orientation == "vertical":
            xmid = (wall.start[0] + wall.end[0]) / 2.0
            new_start = (round(xmid, 3), round(wall.start[1], 3))
            new_end = (round(xmid, 3), round(wall.end[1], 3))
        else:
            out.append(wall)
            continue
        out.append(
            SplitWall(
                wall_id=wall.wall_id,
                parent_wall_id=wall.parent_wall_id,
                page_index=wall.page_index,
                start=new_start,
                end=new_end,
                thickness=wall.thickness,
                orientation=wall.orientation,
                source=wall.source,
                confidence=wall.confidence,
            )
        )
    return out


def _collapse_parallel_walls(
    walls: list[Wall], *, factor: float
) -> list[Wall]:
    """Merge adjacent parallel walls inside a thickness-derived band.

    The raster path emits both the inner and outer line of every
    double-drawn wall as separate ``Wall`` entries. They share the
    same ``orientation`` and lie within ~ 1 thickness of each other
    perpendicular-wise, with parallel ranges that often overlap by
    >50 percent. The ``_merge_colinear_segments`` pass downstream
    cannot fuse them (it requires shared endpoints, not just
    parallelism), so polygonize sees twice as many lines as needed and
    every room's edge is bracketed by two near-identical walls.

    Algorithm (per page, per orientation):
      1. Compute a per-page median thickness, ``T``. Skip the page if
         the candidate set is empty or all thicknesses are zero.
      2. Sort walls by perpendicular coordinate.
      3. Scan; group walls whose perpendicular distance to the running
         cluster centroid stays within ``factor * T`` AND whose
         parallel range overlaps any wall in the cluster.
      4. Emit one ``Wall`` per cluster: perpendicular coord =
         cluster centroid (length-weighted), parallel range =
         union of cluster ranges, thickness = max in cluster,
         orientation = group orientation.
    """
    if not walls:
        return walls
    by_page: dict[int, list[Wall]] = defaultdict(list)
    for w in walls:
        by_page[w.page_index].append(w)
    out: list[Wall] = []
    for page_walls in by_page.values():
        thicknesses = sorted(w.thickness for w in page_walls if w.thickness > 0)
        if not thicknesses:
            out.extend(page_walls)
            continue
        median_t = thicknesses[len(thicknesses) // 2]
        tol = max(1.0, median_t) * factor

        by_orient: dict[str, list[Wall]] = defaultdict(list)
        for w in page_walls:
            by_orient[(w.orientation or "").lower()].append(w)

        for orient, group in by_orient.items():
            if orient not in ("horizontal", "vertical"):
                # Diagonals are not deduped (no single perpendicular axis).
                out.extend(group)
                continue
            out.extend(_collapse_parallel_group(group, orient, tol))
    return out


def _collapse_parallel_group(
    group: list[Wall], orientation: str, tol: float
) -> list[Wall]:
    if not group:
        return []

    def perp(w: Wall) -> float:
        # After rectify both endpoints share the perpendicular coord;
        # without rectify we use the midpoint to absorb jitter.
        return (
            (w.start[1] + w.end[1]) / 2.0
            if orientation == "horizontal"
            else (w.start[0] + w.end[0]) / 2.0
        )

    def para_range(w: Wall) -> tuple[float, float]:
        if orientation == "horizontal":
            lo = min(w.start[0], w.end[0])
            hi = max(w.start[0], w.end[0])
        else:
            lo = min(w.start[1], w.end[1])
            hi = max(w.start[1], w.end[1])
        return lo, hi

    ordered = sorted(group, key=perp)
    clusters: list[list[Wall]] = []
    centroids: list[float] = []
    for w in ordered:
        wp = perp(w)
        wlo, whi = para_range(w)
        attached = False
        for idx, cluster in enumerate(clusters):
            if abs(wp - centroids[idx]) > tol:
                continue
            # Require parallel-range overlap with at least one cluster member.
            if any(_ranges_overlap(para_range(c), (wlo, whi)) for c in cluster):
                cluster.append(w)
                # Update centroid as length-weighted mean (longer walls
                # carry more signal about the true line).
                total_w = sum((para_range(c)[1] - para_range(c)[0]) for c in cluster) or 1.0
                centroids[idx] = sum(
                    perp(c) * (para_range(c)[1] - para_range(c)[0]) for c in cluster
                ) / total_w
                attached = True
                break
        if not attached:
            clusters.append([w])
            centroids.append(wp)

    merged: list[Wall] = []
    for cluster, centroid in zip(clusters, centroids):
        if len(cluster) == 1:
            merged.append(cluster[0])
            continue
        ranges = [para_range(c) for c in cluster]
        lo = min(r[0] for r in ranges)
        hi = max(r[1] for r in ranges)
        thickness = max(c.thickness for c in cluster)
        # Pick a representative (highest confidence, longest range).
        rep = max(
            cluster,
            key=lambda c: (
                c.confidence or 0.0,
                para_range(c)[1] - para_range(c)[0],
            ),
        )
        if orientation == "horizontal":
            new_start = (round(lo, 3), round(centroid, 3))
            new_end = (round(hi, 3), round(centroid, 3))
        else:
            new_start = (round(centroid, 3), round(lo, 3))
            new_end = (round(centroid, 3), round(hi, 3))
        merged.append(
            Wall(
                wall_id=rep.wall_id,
                page_index=rep.page_index,
                start=new_start,
                end=new_end,
                thickness=thickness,
                orientation=orientation,
                source=rep.source,
                confidence=min(c.confidence for c in cluster),
            )
        )
    return merged


def _ranges_overlap(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return not (a[1] < b[0] or b[1] < a[0])


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
    *,
    filter_wall_interior: bool = False,
    wall_thickness_override: float | None = None,
    filter_triangle_artifacts: bool = False,
    filter_room_noise: bool = False,
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

        # Post-polygonize filters layer additively, each implying the
        # weaker ones. Run BEFORE min_area so audit reports reflect the
        # true drop cause.
        #   wall_interior  : SVG path only — assumes double-drawn walls.
        #   room_noise     : drops slivers + narrow medium polygons,
        #                    preserves corridors via aspect/short rule.
        #   triangle       : drops 3-vertex wedges below thickness^2*30.
        if wall_thickness_override is not None and (
            filter_wall_interior or filter_room_noise or filter_triangle_artifacts
        ):
            if filter_wall_interior:
                polygons = [
                    poly
                    for poly in polygons
                    if not is_wall_interior(poly, wall_thickness_override)
                ]
            if filter_wall_interior or filter_room_noise:
                polygons = [
                    poly
                    for poly in polygons
                    if not is_room_noise(poly, wall_thickness_override)
                ]
            polygons = [
                poly
                for poly in polygons
                if not is_triangle_artifact(poly, wall_thickness_override)
            ]
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
