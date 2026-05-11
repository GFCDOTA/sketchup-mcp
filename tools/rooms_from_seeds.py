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

from polygonize_rooms import _detect_door_bridges, polygonize_rooms  # noqa: E402, I001


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


def _build_interior_mask(mask: np.ndarray, walls: list[dict],
                         to_px,
                         *, use_concave_hull: bool,
                         concave_hull_ratio: float) -> np.ndarray:
    """Build the interior-mask used to clip watershed output.

    Default path (``use_concave_hull=False``): convex hull of every
    wall pixel. Cheap, robust, but over-encloses non-convex
    footprints (FP-012).

    Concave path (``use_concave_hull=True``): ``shapely.concave_hull``
    over wall ENDPOINTS (~60–70 points typical, ms-scale even on
    planta_74 which has ~750k wall pixels). Empirical default
    ratio 0.3 keeps the building outline without slicing into
    interior rooms. Falls back to convex hull if concave_hull
    returns a non-Polygon (degenerate input).
    """
    H, W = mask.shape

    if use_concave_hull and walls:
        try:
            from shapely import concave_hull as _shapely_concave_hull
            from shapely.geometry import MultiPoint
        except ImportError:
            use_concave_hull = False  # graceful fall-through

    if use_concave_hull and walls:
        endpts_px: list[tuple[int, int]] = []
        seen: set[tuple[int, int]] = set()
        for w in walls:
            for pt in (w.get("start"), w.get("end")):
                if pt is None:
                    continue
                px = to_px(float(pt[0]), float(pt[1]))
                if px not in seen:
                    seen.add(px)
                    endpts_px.append(px)
        if len(endpts_px) >= 3:
            try:
                ch = _shapely_concave_hull(MultiPoint(endpts_px),
                                            ratio=concave_hull_ratio)
            except Exception:
                ch = None
            if ch is not None and ch.geom_type == "Polygon" and not ch.is_empty:
                hull_pts = np.array(list(ch.exterior.coords),
                                     dtype=np.int32)
                interior = np.zeros_like(mask)
                cv2.fillPoly(interior, [hull_pts], 255)
                return interior

    wall_pts = np.column_stack(np.where(mask > 0))
    if len(wall_pts) > 0:
        xy = wall_pts[:, ::-1].astype(np.int32)
        hull = cv2.convexHull(xy)
        interior = np.zeros_like(mask)
        cv2.fillPoly(interior, [hull], 255)
        return interior
    return np.full_like(mask, 255)


def detect_rooms(consensus: dict, labels: list[dict],
                 door_min: float, door_max: float, scale: int = 8,
                 use_voronoi: bool = True,
                 use_concave_hull: bool = True,
                 concave_hull_ratio: float = 0.5) -> list[dict]:
    """Detect room polygons via watershed seeded from PDF text labels.

    ``use_concave_hull`` (default **True** since Cycle 8b, 2026-05-08):
    uses a ``shapely.concave_hull`` over wall endpoints instead of
    ``cv2.convexHull``. Fixes FP-012 (SUITE 01 leakage on planta_74)
    where the convex envelope over-encloses non-convex footprints
    and the watershed assigns unwalled exterior to the nearest seed.

    Pass ``use_concave_hull=False`` (or CLI ``--no-concave-hull``)
    to recover the legacy convex behaviour for debugging or for
    plants whose envelope is genuinely convex.

    ``concave_hull_ratio`` (default 0.5): only effective when
    ``use_concave_hull`` is True. Range 0.0 (tightest, may shrink
    inside) to 1.0 (= convex hull). 0.5 chosen empirically on
    planta_74 (Cycle 8b empirical decision: SUITE 01 = 26.75 m²
    in [10, 28]; 10/11 rooms in GT range; only TERRACO TECNICO
    marginally below floor; ratio=0.30 was rejected because it
    cut into A.S./COZINHA/TERRACO TECNICO). See
    ``docs/diagnostics/2026-05-07_planta_74_fp012_spike_results.md``
    for the full sweep + Cycle 8b decision rationale.
    """
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
        # bisectors — rooms hug the walls. The interior mask clips
        # the result so rooms don't bleed off the building footprint
        # where exterior peitoril is unwalled.
        seed_pts = [to_px(label["seed_pt"][0], label["seed_pt"][1])
                    for label in labels]

        interior = _build_interior_mask(
            mask, walls, to_px,
            use_concave_hull=use_concave_hull,
            concave_hull_ratio=concave_hull_ratio,
        )
        # Build a label image: -1 where wall, 0..N-1 where assigned.
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


def detect_rooms_polygonize(consensus: dict, labels: list[dict],
                            door_min: float = 15.0,
                            door_max: float = 50.0,
                            envelope_margin_pts: float = 2.0,
                            min_room_area_factor: float = 12.0) -> list[dict]:
    """Detect rooms via wall-rectangle subtraction (FP-014 P0 fix).

    Delegates the closed-cell extraction to ``polygonize_rooms.polygonize_rooms``
    (which builds ``unary_union(wall_boxes) → env.difference()``), then maps
    each label's ``seed_pt`` to the cell that contains it. Produces polygons
    with 4–20 vertices, perfectly wall-aligned — the FP-014 fix for the
    legacy raster-watershed method that emitted SUITE 01 with 738 vts.

    Two labels resolving to the same cell are kept as a single room with
    ``name = "X | Y"`` plus ``metadata.warnings = ["seeds_share_cell"]``
    (honest signal that a structural wall is missing — the cell-merged
    polygon is the correct observation given the wall data). Seeds outside
    every cell are dropped and recorded under
    ``consensus.metadata.rooms_from_seeds.dropped_seeds``.

    See ``docs/diagnostics/2026-05-09_skp_visual_failure_fp014.md`` §"Opção A"
    for the design rationale and the empirical evidence behind picking
    polygonize over raster-watershed.
    """
    from shapely.geometry import Point, Polygon

    cells_raw, _bridges = polygonize_rooms(
        consensus,
        door_min_pts=door_min,
        door_max_pts=door_max,
        envelope_margin_pts=envelope_margin_pts,
        min_room_area_factor=min_room_area_factor,
    )

    cell_polys: list[tuple[dict, Polygon]] = []
    for c in cells_raw:
        try:
            poly = Polygon(c["polygon_pts"])
        except Exception:
            continue
        if poly.is_valid and not poly.is_empty:
            cell_polys.append((c, poly))

    t = float(consensus["wall_thickness_pts"])
    dropped: list[dict] = []
    seed_to_cell: dict[int, int] = {}

    for li, label in enumerate(labels):
        sp = label.get("seed_pt")
        if not sp:
            dropped.append({"label_id": label.get("id"),
                            "label_name": label.get("name"),
                            "reason": "no_seed_pt"})
            continue
        point = Point(float(sp[0]), float(sp[1]))

        assigned: int | None = None
        for ci, (_c, poly) in enumerate(cell_polys):
            if poly.contains(point):
                assigned = ci
                break
        if assigned is None:
            best_ci = None
            best_d = float("inf")
            for ci, (_c, poly) in enumerate(cell_polys):
                d = poly.centroid.distance(point)
                if d < best_d:
                    best_d = d
                    best_ci = ci
            if best_ci is not None and best_d <= 3.0 * t:
                assigned = best_ci

        if assigned is None:
            dropped.append({
                "label_id": label.get("id"),
                "label_name": label.get("name"),
                "seed_pt": list(sp),
                "reason": "no_containing_cell",
            })
            continue
        seed_to_cell[li] = assigned

    cell_to_labels: dict[int, list[dict]] = {}
    for li, ci in seed_to_cell.items():
        cell_to_labels.setdefault(ci, []).append(labels[li])

    rooms: list[dict] = []
    for ci in sorted(cell_to_labels.keys()):
        cell, _poly = cell_polys[ci]
        lbls = cell_to_labels[ci]
        merged = len(lbls) > 1
        names = [lb["name"] for lb in lbls]
        label_ids = [lb.get("id") for lb in lbls if lb.get("id") is not None]
        room: dict = {
            "id": f"r{len(rooms):03d}",
            "name": " | ".join(names) if merged else names[0],
            "label_id": label_ids[0] if not merged and label_ids else None,
            "seed_pt": list(lbls[0]["seed_pt"]),
            "polygon_pts": cell["polygon_pts"],
            "area_pts2": cell["area_pts2"],
            "centroid": cell["centroid"],
            "method": "polygonize",
        }
        if merged:
            room["label_ids"] = label_ids
            room["merged_seeds"] = [list(lb["seed_pt"]) for lb in lbls]
            room["metadata"] = {"warnings": ["seeds_share_cell"]}
        rooms.append(room)

    if dropped:
        md = consensus.setdefault("metadata", {})
        rfs = md.setdefault("rooms_from_seeds", {})
        rfs.setdefault("dropped_seeds", []).extend(dropped)

    return rooms


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("consensus", type=Path)
    ap.add_argument("labels", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--door-min", type=float, default=15.0)
    ap.add_argument("--door-max", type=float, default=50.0)
    ap.add_argument("--scale", type=int, default=8)
    # V1 fix wiring (CLAUDE.md §3 paradigm: opt-in only).
    # See docs/tour/matterport_visual_findings_74m2.md V1 verdict and
    # tests/test_living_terraco_shape_canonicity.py for the empirical
    # tolerance choice. Default OFF — flipping to ON is a deliberate
    # operational decision; the flag keeps the change reversible.
    ap.add_argument("--canonicalize-rooms", action="store_true",
                    help="Snap room polygon vertices to wall-induced axis "
                         "grid after watershed (V1 fix: SALA DE ESTAR "
                         "diagonal mordida). Off by default.")
    ap.add_argument("--room-canonicalization-tol", type=float, default=8.0,
                    help="Snap tolerance in PDF points (default 8.0 = "
                         "1.5x wall_thickness on planta_74). Only effective "
                         "when --canonicalize-rooms is set.")
    # FP-012 fix (Cycle 8b, 2026-05-08): concave-hull envelope clip
    # is now the DEFAULT. Pass --no-concave-hull to recover the
    # legacy convex behaviour. See
    # docs/diagnostics/2026-05-07_planta_74_suite01_polygon_leakage.md
    # for the bug history and
    # docs/diagnostics/2026-05-07_planta_74_fp012_spike_results.md
    # for the empirical sweep that picked ratio 0.3.
    ap.add_argument("--no-concave-hull", action="store_true",
                    help="Disable the default shapely.concave_hull "
                         "envelope clip; use legacy cv2.convexHull "
                         "instead. Provided as an escape hatch for "
                         "plants whose envelope is genuinely convex.")
    ap.add_argument("--concave-hull-ratio", type=float, default=0.5,
                    help="shapely concave_hull ratio. 0.0 = tightest "
                         "(may shrink inside rooms), 1.0 = convex "
                         "hull. Default 0.5 (Cycle 8b empirical: "
                         "lower ratios cut A.S./COZINHA/TERRACO; "
                         "0.5 keeps SUITE 01 in [10, 28] m²).")
    # FP-014 P0 (2026-05-11): opt-in polygonize method that swaps the
    # legacy raster-watershed for shapely.unary_union(wall_boxes) +
    # env.difference(). Polygons emerge wall-aligned with 4–20 vts
    # instead of the 738-vts raster-contour traces that caused SUITE 01
    # to leak across BANHO 02. Default stays 'voronoi' in PR-A1; the
    # default flips to 'polygonize' in PR-A2 (refactor/rooms-polygonize-
    # default) once the baseline JSON is updated to match the new vts /
    # area expectations.
    ap.add_argument("--method",
                    choices=["voronoi", "flood", "polygonize"],
                    default="voronoi",
                    help="Room detection method. 'voronoi' (default) is the "
                         "legacy raster watershed; 'flood' is the raster "
                         "flood-fill fallback; 'polygonize' uses shapely "
                         "wall-rectangle subtraction (FP-014 P0 fix).")
    ap.add_argument("--envelope-margin-pts", type=float, default=2.0,
                    help="Envelope padding around planta_region "
                         "(--method polygonize only).")
    ap.add_argument("--min-room-area-factor", type=float, default=12.0,
                    help="Min room area = factor * thickness² to drop "
                         "slivers (--method polygonize only).")
    args = ap.parse_args()

    consensus = json.loads(args.consensus.read_text())
    labels = json.loads(args.labels.read_text())
    if args.method == "polygonize":
        rooms = detect_rooms_polygonize(
            consensus, labels,
            door_min=args.door_min,
            door_max=args.door_max,
            envelope_margin_pts=args.envelope_margin_pts,
            min_room_area_factor=args.min_room_area_factor,
        )
    elif args.method == "flood":
        rooms = detect_rooms(
            consensus, labels, args.door_min, args.door_max, args.scale,
            use_voronoi=False,
            use_concave_hull=not args.no_concave_hull,
            concave_hull_ratio=args.concave_hull_ratio,
        )
    else:  # voronoi
        rooms = detect_rooms(consensus, labels, args.door_min, args.door_max,
                             args.scale,
                             use_concave_hull=not args.no_concave_hull,
                             concave_hull_ratio=args.concave_hull_ratio)

    if args.canonicalize_rooms and args.method == "polygonize":
        # Polygonize emits wall-aligned cells (4–20 vts); the canonicalize
        # pass is designed to repair raster-watershed staircase artefacts,
        # not these clean polygons. Running it would either be a no-op or
        # snap legitimate vertices to nearby wall axes that don't belong
        # to the cell — silently skip with a notice.
        print("[warn] --canonicalize-rooms ignored with --method=polygonize "
              "(cells already wall-aligned)")
    elif args.canonicalize_rooms:
        # Local import to keep cv2 import cheap when feature unused. The
        # parent dir is on sys.path so canonicalize_room_polygons resolves
        # whether this script runs as `python tools/rooms_from_seeds.py`
        # or `python -m tools.rooms_from_seeds` (the documented form in
        # OVERVIEW.md §4.4).
        try:
            from tools.canonicalize_room_polygons import canonicalize_rooms
        except ModuleNotFoundError:
            from canonicalize_room_polygons import canonicalize_rooms
        n_before_pts = sum(len(r.get("polygon_pts", [])) for r in rooms)
        rooms = canonicalize_rooms(
            rooms,
            consensus["walls"],
            consensus["wall_thickness_pts"],
            tol_pts=args.room_canonicalization_tol,
        )
        n_after_pts = sum(len(r.get("polygon_pts", [])) for r in rooms)
        print(f"[canonicalize] tol={args.room_canonicalization_tol}pt: "
              f"polygon vertex count {n_before_pts} -> {n_after_pts}")

    consensus["rooms"] = rooms
    # Stamp how the consensus was produced so downstream / debug can tell
    # which method ran and whether canonicalization applied. Stays inside
    # the existing schema-additive metadata field per docs/SCHEMA-V2.md.
    md = consensus.setdefault("metadata", {})
    existing_rfs = md.get("rooms_from_seeds", {}) or {}
    dropped_seeds = existing_rfs.get("dropped_seeds", [])
    md["rooms_from_seeds"] = {
        "method": args.method,
        "canonicalize_rooms": bool(args.canonicalize_rooms) and args.method != "polygonize",
        "room_canonicalization_tol": (
            args.room_canonicalization_tol
            if (args.canonicalize_rooms and args.method != "polygonize") else None
        ),
        "use_concave_hull": not bool(args.no_concave_hull),
        "concave_hull_ratio": (
            args.concave_hull_ratio if not args.no_concave_hull else None
        ),
        "envelope_margin_pts": (
            args.envelope_margin_pts if args.method == "polygonize" else None
        ),
        "min_room_area_factor": (
            args.min_room_area_factor if args.method == "polygonize" else None
        ),
    }
    if dropped_seeds:
        md["rooms_from_seeds"]["dropped_seeds"] = dropped_seeds
    out = args.out or args.consensus
    out.write_text(json.dumps(consensus, indent=2))
    print(f"[ok] {len(rooms)} rooms detected from labels -> {out}")
    for r in rooms:
        print(f"  {r['id']}: {r['name']!r} area={r['area_pts2']:.0f}pts^2")
