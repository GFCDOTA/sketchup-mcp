"""Room polygonization via wall-rectangle subtraction.

Walls in vector PDFs are slim filled rectangles whose BODIES (not just
centerlines) carry the geometry. Polygonising centerlines fails when
adjacent walls are joined via short connector segments rather than
sharing endpoints exactly. The robust approach:

  1. Build the union of all wall rectangles → wall_mask (MultiPolygon).
  2. Detect door openings: pairs of collinear wall ends with a gap
     in the door range → synthesise a door-bridge RECTANGLE of full
     thickness covering the gap.
  3. Add bridges to wall_mask. Now door openings are sealed.
  4. Take the planta envelope (bbox + margin), subtract the
     wall_mask. The result is a MultiPolygon whose connected pieces
     are rooms (the very largest piece is the OUTSIDE — it touches
     the envelope border on all sides — which we drop).
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from shapely.geometry import Polygon, box, Point
from shapely.ops import unary_union


def _wall_to_box(w: dict, t: float, end_extend: float = 0.0) -> Polygon:
    """Wall as a filled rect. ``end_extend`` lengthens the rect along
    the wall's long axis (BOTH ends) so T-junctions close: a partition
    that almost touches a backbone wall, but stops a fraction of t
    short, will reach into the backbone after extension. The thickness
    axis is left alone so rooms keep their drawn dimensions."""
    s, e = w["start"], w["end"]
    if w["orientation"] == "h":
        x0, x1 = sorted([s[0], e[0]])
        cy = s[1]
        return box(x0 - end_extend, cy - t / 2, x1 + end_extend, cy + t / 2)
    else:
        cx = s[0]
        y0, y1 = sorted([s[1], e[1]])
        return box(cx - t / 2, y0 - end_extend, cx + t / 2, y1 + end_extend)


def _detect_door_bridges(walls: list[dict], t: float,
                         door_min: float, door_max: float) -> list[dict]:
    coll_tol = t * 0.5
    bins: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for w in walls:
        const = w["start"][1] if w["orientation"] == "h" else w["start"][0]
        bins[(w["orientation"], int(round(const / coll_tol)))].append(w)

    grouped: list[list[dict]] = []
    seen: set[tuple[str, int]] = set()
    for k in sorted(bins):
        if k in seen:
            continue
        cluster = list(bins[k])
        seen.add(k)
        if (k[0], k[1] + 1) in bins:
            cluster.extend(bins[(k[0], k[1] + 1)])
            seen.add((k[0], k[1] + 1))
        grouped.append(cluster)

    bridges: list[dict] = []
    bid = 0
    for cluster in grouped:
        if len(cluster) < 2:
            continue
        ori = cluster[0]["orientation"]
        if ori == "h":
            cluster.sort(key=lambda w: min(w["start"][0], w["end"][0]))
        else:
            cluster.sort(key=lambda w: min(w["start"][1], w["end"][1]))
        for i in range(len(cluster) - 1):
            a, b = cluster[i], cluster[i + 1]
            if ori == "h":
                a_end = max(a["start"][0], a["end"][0])
                b_start = min(b["start"][0], b["end"][0])
                gap = b_start - a_end
                if door_min <= gap <= door_max:
                    cy = (a["start"][1] + b["start"][1]) / 2.0
                    bridges.append({
                        "id": f"door_{bid:03d}",
                        "start": [a_end, cy],
                        "end": [b_start, cy],
                        "thickness": t,
                        "orientation": "h",
                        "synthetic": True,
                    })
                    bid += 1
            else:
                a_end = max(a["start"][1], a["end"][1])
                b_start = min(b["start"][1], b["end"][1])
                gap = b_start - a_end
                if door_min <= gap <= door_max:
                    cx = (a["start"][0] + b["start"][0]) / 2.0
                    bridges.append({
                        "id": f"door_{bid:03d}",
                        "start": [cx, a_end],
                        "end": [cx, b_start],
                        "thickness": t,
                        "orientation": "v",
                        "synthetic": True,
                    })
                    bid += 1
    return bridges


def polygonize_rooms(consensus: dict,
                     door_min_pts: float = 15.0,
                     door_max_pts: float = 50.0,
                     envelope_margin_pts: float = 2.0,
                     min_room_area_factor: float = 12.0) -> tuple[list[dict], list[dict]]:
    walls = consensus["walls"]
    t = consensus["wall_thickness_pts"]

    bridges = _detect_door_bridges(walls, t, door_min_pts, door_max_pts)
    all_walls = walls + bridges

    # End-extend by t so partition walls reach into the backbone wall
    # at T-junctions; the perpendicular wall absorbs the overshoot.
    wall_polys = [_wall_to_box(w, t, end_extend=t) for w in all_walls]
    wall_union = unary_union(wall_polys)

    # If the wall network still has multiple disconnected components,
    # bridge the closest pair of components iteratively until merged.
    # This handles partition walls that don't quite touch a backbone
    # at any door-aligned axis (e.g. a freestanding partition wall
    # between two rooms whose ends fall slightly short of the
    # neighbouring backbone walls).
    if wall_union.geom_type == "MultiPolygon":
        comps = list(wall_union.geoms)
        max_iter = len(comps) + 5
        merge_bridges: list[Polygon] = []
        while len(comps) > 1 and max_iter > 0:
            max_iter -= 1
            comps.sort(key=lambda p: -p.area)
            biggest = comps[0]
            best = None
            best_d = float("inf")
            for other in comps[1:]:
                d = biggest.distance(other)
                if d < best_d:
                    best_d = d
                    best = other
            # Use a more permissive distance for merging components
            # than the door range — partitions can sit further from
            # backbone walls than a typical door width.
            if best is None or best_d > door_max_pts * 4:
                break
            # Pair of nearest points between biggest and best
            from shapely.ops import nearest_points
            p1, p2 = nearest_points(biggest, best)
            # Build a thin bridge rectangle along the segment p1→p2
            dx = p2.x - p1.x
            dy = p2.y - p1.y
            length = (dx * dx + dy * dy) ** 0.5
            if length < 1e-6:
                # Tangent/touching but treated as separate by float
                # imprecision; pad with a unit box to seal them.
                bridge = box(p1.x - t / 2, p1.y - t / 2,
                             p1.x + t / 2, p1.y + t / 2)
            else:
                from shapely.geometry import LineString as _LS
                bridge = _LS([(p1.x, p1.y), (p2.x, p2.y)]).buffer(t / 2,
                                                                   cap_style="square")
            merge_bridges.append(bridge)
            wall_union = unary_union([wall_union, bridge])
            comps = (list(wall_union.geoms) if wall_union.geom_type == "MultiPolygon"
                     else [wall_union])

    region = consensus.get("planta_region")
    if region:
        env = box(region[0] - envelope_margin_pts,
                  region[1] - envelope_margin_pts,
                  region[2] + envelope_margin_pts,
                  region[3] + envelope_margin_pts)
    else:
        env = wall_union.envelope.buffer(envelope_margin_pts)

    interior = env.difference(wall_union)
    if interior.is_empty:
        return [], bridges
    parts = list(interior.geoms) if hasattr(interior, "geoms") else [interior]
    parts.sort(key=lambda p: -p.area)

    # The OUTSIDE piece is the one that wraps the entire planta — it
    # touches the envelope on all four edges. Identify it and drop.
    env_xmin, env_ymin, env_xmax, env_ymax = env.bounds
    def touches_all_edges(p: Polygon) -> bool:
        bx0, by0, bx1, by1 = p.bounds
        eps = 1e-3
        return (bx0 <= env_xmin + eps and bx1 >= env_xmax - eps
                and by0 <= env_ymin + eps and by1 >= env_ymax - eps)

    rooms_raw = [p for p in parts if not touches_all_edges(p)]

    min_area = min_room_area_factor * t * t
    rooms: list[dict] = []
    for i, poly in enumerate(rooms_raw):
        if poly.area < min_area:
            continue
        rooms.append({
            "id": f"r{i:03d}",
            "polygon_pts": [[round(x, 3), round(y, 3)] for x, y in poly.exterior.coords],
            "area_pts2": round(poly.area, 2),
            "centroid": [round(poly.centroid.x, 3), round(poly.centroid.y, 3)],
        })
    return rooms, bridges


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("consensus", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--door-min", type=float, default=15.0)
    ap.add_argument("--door-max", type=float, default=50.0)
    args = ap.parse_args()
    out = args.out or args.consensus
    d = json.loads(args.consensus.read_text())
    rooms, bridges = polygonize_rooms(d, args.door_min, args.door_max)
    d["rooms"] = rooms
    d["openings"] = [
        {"id": b["id"], "type": "door", "wall_a_end": b["start"],
         "wall_b_start": b["end"],
         "width_pts": ((b["end"][0] - b["start"][0]) if b["orientation"] == "h"
                       else (b["end"][1] - b["start"][1]))}
        for b in bridges
    ]
    out.write_text(json.dumps(d, indent=2))
    print(f"[ok] {len(rooms)} rooms, {len(bridges)} door bridges -> {out}")
