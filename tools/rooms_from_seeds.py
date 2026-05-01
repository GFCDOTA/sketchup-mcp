"""Room detection by flood-fill from PDF text seeds.

The architectural plan contains text labels (COZINHA, SUITE 01, ...)
positioned inside their rooms. We use those positions as seed points
and flood-fill in a raster of the wall network to recover each room
polygon.

Steps:
  1. Rasterise wall rectangles + door bridges to a binary barrier mask.
  2. For each room label seed, run cv2.floodFill from the seed inside
     the white (non-wall) area.
  3. The filled region's contour, transformed back to PDF coords, is
     the room polygon.
  4. Filter: drop seeds whose flood region is empty (seed sat on a
     wall) or escapes the planta envelope (room not closed by walls).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

THIS = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS))

from polygonize_rooms import _wall_to_box, _detect_door_bridges  # noqa: E402


def rasterize_walls(walls: list[dict], bridges: list[dict], t: float,
                    region: tuple[float, float, float, float],
                    scale: int = 8) -> tuple[np.ndarray, callable, callable]:
    rx0, ry0, rx1, ry1 = region
    W = int((rx1 - rx0) * scale) + 4
    H = int((ry1 - ry0) * scale) + 4

    def to_px(x: float, y: float) -> tuple[int, int]:
        return (int(round((x - rx0) * scale)) + 2,
                int(round((ry1 - y) * scale)) + 2)

    def from_px(px: int, py: int) -> tuple[float, float]:
        return ((px - 2) / scale + rx0,
                ry1 - (py - 2) / scale)

    mask = np.zeros((H, W), np.uint8)
    for w in walls + bridges:
        s, e = w["start"], w["end"]
        if w["orientation"] == "h":
            x0, x1 = sorted([s[0], e[0]])
            cy = s[1]
            x0p, y1p = to_px(x0, cy + t / 2)
            x1p, y0p = to_px(x1, cy - t / 2)
        else:
            cx = s[0]
            y0, y1 = sorted([s[1], e[1]])
            x0p, y1p = to_px(cx - t / 2, y1)
            x1p, y0p = to_px(cx + t / 2, y0)
        cv2.rectangle(mask, (x0p, y1p), (x1p, y0p), 255, -1)

    return mask, to_px, from_px


def add_soft_barriers(mask: np.ndarray, to_px,
                      barriers: list[dict], thickness_px: int = 2) -> np.ndarray:
    """Rasterise polylines from soft_barriers onto the mask.

    These are non-structural elements (peitoril, grade, building
    outline traces) that bound rooms but are NOT load-bearing walls.
    They seal terraço regions for watershed without polluting the
    structural wall list. Drawn at a thin pixel width since they
    represent thin lines in the source, not solid bands.
    """
    out = mask.copy()
    for b in barriers:
        pts = b.get("polyline_pts", [])
        if len(pts) < 2:
            continue
        for i in range(len(pts) - 1):
            p1 = to_px(pts[i][0], pts[i][1])
            p2 = to_px(pts[i + 1][0], pts[i + 1][1])
            cv2.line(out, p1, p2, 255, thickness_px)
    return out


def flood_room(mask: np.ndarray, seed_px: tuple[int, int]) -> np.ndarray | None:
    """Returns a binary mask of the connected white region containing
    ``seed_px``, or None if seed sits on a wall pixel.
    """
    H, W = mask.shape
    sx, sy = seed_px
    if not (0 <= sx < W and 0 <= sy < H):
        return None
    if mask[sy, sx] != 0:
        return None  # seed is on a wall

    # cv2.floodFill needs a 1-pixel padded mask.
    fill_mask = np.zeros((H + 2, W + 2), np.uint8)
    flooded = mask.copy()
    cv2.floodFill(flooded, fill_mask, (sx, sy), 128)
    return (flooded == 128).astype(np.uint8) * 255


def mask_to_polygon(mask: np.ndarray, from_px,
                    simplify_tolerance: float = 0.5) -> list[list[float]] | None:
    """Extract the room contour as a polygon and Douglas-Peucker
    simplify to drop sub-pixel jagged vertices. ``simplify_tolerance``
    is in PDF points; 0.5 ≈ wall-thickness/10 keeps rectangles axis-
    aligned and shaves the staircase artefacts contour-following
    introduces around 1-2px walls."""
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_TC89_L1)
    if not contours:
        return None
    cnt = max(contours, key=cv2.contourArea)
    poly_pts = [from_px(int(p[0][0]), int(p[0][1])) for p in cnt]
    if simplify_tolerance > 0 and len(poly_pts) >= 4:
        try:
            from shapely.geometry import Polygon as _Poly
            poly = _Poly(poly_pts)
            if poly.is_valid:
                simp = poly.simplify(simplify_tolerance, preserve_topology=True)
                if simp.is_valid and not simp.is_empty:
                    poly_pts = list(simp.exterior.coords)
        except Exception:
            pass
    return [list(p) for p in poly_pts]


def detect_rooms(consensus: dict, labels: list[dict],
                 door_min: float, door_max: float, scale: int = 8,
                 use_voronoi: bool = True) -> list[dict]:
    walls = consensus["walls"]
    t = consensus["wall_thickness_pts"]
    region = tuple(consensus["planta_region"])

    bridges = _detect_door_bridges(walls, t, door_min, door_max)
    mask, to_px, from_px = rasterize_walls(walls, bridges, t, region, scale)

    # Apply soft barriers AFTER filtering: peitoril/grade traces with
    # bbox not overlapping any wall (filter done in build step).
    soft_barriers = consensus.get("soft_barriers", [])
    if soft_barriers:
        mask = add_soft_barriers(mask, to_px, soft_barriers, thickness_px=2)

    # Border seal so a leaked flood is contained at envelope edges.
    H, W = mask.shape
    cv2.rectangle(mask, (0, 0), (W - 1, H - 1), 255, 1)

    if use_voronoi:
        # Watershed segmentation: each label seed expands outward
        # through white space until it meets another room's expansion.
        # Walls act as hard barriers (markers ignore them). This
        # tracks actual wall geometry instead of Voronoi straight
        # bisectors — rooms hug the walls. Clipped to the convex hull
        # of the wall network so rooms don't bleed off the building
        # footprint where exterior peitoril is unwalled.
        seed_pts = [to_px(l["seed_pt"][0], l["seed_pt"][1]) for l in labels]

        # Build interior mask: convex hull of wall pixels
        wall_pts = np.column_stack(np.where(mask > 0))
        if len(wall_pts) > 0:
            xy = wall_pts[:, ::-1].astype(np.int32)
            hull = cv2.convexHull(xy)
            interior = np.zeros_like(mask)
            cv2.fillPoly(interior, [hull], 255)
        else:
            interior = np.full_like(mask, 255)
        # Build a label image: -1 where wall, 0..N-1 where assigned.
        white = (mask == 0).astype(np.uint8)
        # cv2.watershed: 3-channel image input, markers as int32 with
        # one positive ID per seed and 0 elsewhere; walls are -1
        # afterwards. Seeds expand outward through low-gradient regions
        # — using the wall mask itself as the gradient image makes
        # watershed treat walls as ridges and rooms as basins.
        markers = np.zeros(mask.shape, np.int32)
        for i, (sx, sy) in enumerate(seed_pts):
            if 0 <= sx < W and 0 <= sy < H and mask[sy, sx] == 0:
                cv2.circle(markers, (sx, sy), 2, i + 1, -1)
        # Mark walls with a sentinel positive id outside seed range so
        # watershed treats them as their own region (we filter later).
        WALL_MARKER = len(seed_pts) + 100
        markers[mask > 0] = WALL_MARKER
        gradient = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
        cv2.watershed(gradient, markers)
        # cv2.watershed marks watershed boundaries with -1; rooms are
        # 1..N, walls are WALL_MARKER. Build label_img.
        label_img = markers.copy()
        # Watershed boundaries (-1) belong to walls visually
        label_img[label_img == -1] = 0
        label_img[label_img == WALL_MARKER] = 0
        cv_label_to_seed = {i + 1: i for i in range(len(seed_pts))}

        rooms: list[dict] = []
        for cv_lbl, seed_i in cv_label_to_seed.items():
            label = labels[seed_i]
            rmask = ((label_img == cv_lbl) & (mask == 0) & (interior > 0)).astype(np.uint8) * 255
            area_px = int(rmask.sum() // 255)
            area_pts2 = area_px / (scale * scale)
            if area_pts2 < 4 * t * t:
                continue
            poly = mask_to_polygon(rmask, from_px)
            if poly is None or len(poly) < 4:
                continue
            cx_px = float(np.mean([p[0] for p in poly]))
            cy_px = float(np.mean([p[1] for p in poly]))
            rooms.append({
                "id": f"r{len(rooms):03d}",
                "name": label["name"],
                "label_id": label["id"],
                "seed_pt": label["seed_pt"],
                "polygon_pts": [[round(x, 3), round(y, 3)] for x, y in poly],
                "area_pts2": round(area_pts2, 2),
                "centroid": [round(cx_px, 3), round(cy_px, 3)],
                "method": "voronoi",
            })
        return rooms

    # Flood once per seed against the IMMUTABLE wall mask. Rooms that
    # share a connected white region (because a separating wall is
    # missing in the PDF) will all return the same merged region; we
    # detect that case via centroid sharing and keep the largest match
    # only — better than over-counting rooms.
    envelope_area_px = (H - 4) * (W - 4)
    max_room_pts2 = (envelope_area_px / (scale * scale)) * 0.45  # > 45%
                                                                  # of envelope = leaked
    raw_results: list[dict] = []
    for label in labels:
        sx, sy = to_px(label["seed_pt"][0], label["seed_pt"][1])
        rmask = flood_room(mask, (sx, sy))
        if rmask is None:
            continue
        area_px = int(rmask.sum() // 255)
        area_pts2 = area_px / (scale * scale)
        if area_pts2 < 4 * t * t or area_pts2 > max_room_pts2:
            # Too small (sliver) or leaked into outside-of-building
            continue
        # Hash the region by a coarse fingerprint of its pixels: any
        # two seeds whose floods cover the same region collide.
        ys, xs = np.where(rmask > 0)
        if len(xs) == 0:
            continue
        fp = (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))
        raw_results.append({
            "label": label,
            "rmask": rmask,
            "area_pts2": area_pts2,
            "fp": fp,
        })

    # Group by fingerprint
    groups: dict[tuple, list[dict]] = {}
    for r in raw_results:
        groups.setdefault(r["fp"], []).append(r)

    rooms: list[dict] = []
    for fp, group in groups.items():
        # If multiple seeds share the same flooded region, the wall
        # network is missing a separator. Keep all label names but
        # only one polygon.
        primary = group[0]
        poly = mask_to_polygon(primary["rmask"], from_px)
        if poly is None or len(poly) < 4:
            continue
        rooms.append({
            "id": f"r{len(rooms):03d}",
            "name": " | ".join(g["label"]["name"] for g in group),
            "label_ids": [g["label"]["id"] for g in group],
            "seed_pt": primary["label"]["seed_pt"],
            "polygon_pts": [[round(x, 3), round(y, 3)] for x, y in poly],
            "area_pts2": round(primary["area_pts2"], 2),
            "merged_seeds": [g["label"]["seed_pt"] for g in group],
        })

    return rooms


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("consensus", type=Path)
    ap.add_argument("labels", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--door-min", type=float, default=15.0)
    ap.add_argument("--door-max", type=float, default=50.0)
    ap.add_argument("--scale", type=int, default=8)
    args = ap.parse_args()

    consensus = json.loads(args.consensus.read_text())
    labels = json.loads(args.labels.read_text())
    rooms = detect_rooms(consensus, labels, args.door_min, args.door_max, args.scale)

    consensus["rooms"] = rooms
    out = args.out or args.consensus
    out.write_text(json.dumps(consensus, indent=2))
    print(f"[ok] {len(rooms)} rooms detected from labels -> {out}")
    for r in rooms:
        print(f"  {r['id']}: {r['name']!r} area={r['area_pts2']:.0f}pts^2")
