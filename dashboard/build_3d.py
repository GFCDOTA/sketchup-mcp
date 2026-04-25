"""Build a GLB 3D model from a consensus_model.json so the dashboard can render
floor-plan geometry without SketchUp.

Usage:
    E:/Python312/python.exe E:/Claude/sketchup-mcp-exp-dedup/dashboard/build_3d.py \
        E:/Claude/sketchup-mcp-exp-dedup/runs/final_planta_74

Inputs : <run_dir>/consensus_model.json
Outputs: <run_dir>/consensus_3d.glb

Geometry choices
----------------
- All units in metres in the GLB.
- Coord space of the JSON is "pdf_points"; we pick a scale so total room
  polygon area ~= 74 m^2 (the apartment is the 74m2 reference unit). When the
  rooms list is empty we fall back to a fixed 0.014 m/pt.
- Walls: oriented box per centerline with default 0.15 m thickness and
  2.70 m height. SVG-only walls render slightly narrower (0.10 m).
- Openings: marker cylinder (radius=chord/2) standing inside the wall,
  coloured per origin. We do *not* attempt CSG subtraction (trimesh CSG depends
  on optional native libs and is brittle for many tiny boxes).
- Rooms: extruded polygon 0.05 m tall, soft pastel colour cycle.
- Furniture: 0.5 x 0.5 x 0.5 m cube at the centroid (different palette).

Coordinate flip: PDF Y grows downward, so we negate Y when emitting the
metric model so "up" in the GLB scene matches the floor-plan top.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import trimesh
from trimesh.creation import box as create_box
from trimesh.creation import cylinder as create_cylinder
from trimesh.creation import extrude_polygon
from shapely.geometry import Polygon

WALL_HEIGHT_M = 2.70
WALL_THICKNESS_DEFAULT_M = 0.15
WALL_THICKNESS_SVG_ONLY_M = 0.10
ROOM_SLAB_HEIGHT_M = 0.05
FURNITURE_BOX_M = 0.50

WALL_COLOR_AGREED = [220, 220, 215, 255]
WALL_COLOR_SVG_ONLY = [200, 175, 160, 255]
ROOM_PALETTE = [
    [255, 224, 178, 230],
    [220, 237, 200, 230],
    [187, 222, 251, 230],
    [248, 187, 208, 230],
    [255, 245, 157, 230],
    [197, 202, 233, 230],
    [255, 204, 188, 230],
    [200, 230, 201, 230],
]
OPENING_COLOR_DOOR_ARC = [255, 140, 0, 255]
OPENING_COLOR_GAP = [255, 200, 100, 255]
FURNITURE_COLOR = [120, 144, 156, 255]


def _derive_scale(rooms: list[dict], target_area_m2: float = 74.0) -> float:
    """Return metres-per-PDF-point so the sum of room polygon areas equals 74 m^2."""
    if not rooms:
        return 0.014
    total = 0.0
    for r in rooms:
        poly = r.get("polygon") or []
        if len(poly) < 3:
            continue
        try:
            total += abs(Polygon(poly).area)
        except Exception:
            continue
    if total <= 0:
        return 0.014
    # area scales with scale^2
    return math.sqrt(target_area_m2 / total)


def _to_xy(pt, scale: float, origin_xy):
    """Convert a (px, py) point in PDF points to scene metres, flipping Y."""
    x = (pt[0] - origin_xy[0]) * scale
    y = -(pt[1] - origin_xy[1]) * scale  # flip Y
    return x, y


def _build_wall(start_m, end_m, thickness_m, height_m, color):
    sx, sy = start_m
    ex, ey = end_m
    dx, dy = ex - sx, ey - sy
    length = math.hypot(dx, dy)
    if length < 1e-4:
        return None
    box = create_box(extents=[length, thickness_m, height_m])
    angle = math.atan2(dy, dx)
    cx, cy = (sx + ex) / 2.0, (sy + ey) / 2.0
    cz = height_m / 2.0
    rot = trimesh.transformations.rotation_matrix(angle, [0, 0, 1])
    trans = trimesh.transformations.translation_matrix([cx, cy, cz])
    box.apply_transform(rot)
    box.apply_transform(trans)
    box.visual.face_colors = color
    return box


def _build_room_slab(polygon_pts_m, color):
    if len(polygon_pts_m) < 3:
        return None
    try:
        poly = Polygon(polygon_pts_m)
        if not poly.is_valid:
            poly = poly.buffer(0)
        if poly.is_empty or poly.area <= 0:
            return None
        mesh = extrude_polygon(poly, ROOM_SLAB_HEIGHT_M)
    except Exception:
        return None
    # extrude_polygon places base at z=0; nudge to -0.01 so it stays under walls
    mesh.apply_translation([0, 0, -0.01])
    mesh.visual.face_colors = color
    return mesh


def _build_opening(center_m, chord_m, kind, color):
    radius = max(chord_m / 2.0, 0.05)
    height = 2.10  # door height
    cyl = create_cylinder(radius=radius, height=height, sections=16)
    cyl.apply_translation([center_m[0], center_m[1], height / 2.0])
    cyl.visual.face_colors = color
    return cyl


def _build_furniture(center_m):
    cube = create_box(extents=[FURNITURE_BOX_M, FURNITURE_BOX_M, FURNITURE_BOX_M])
    cube.apply_translation([center_m[0], center_m[1], FURNITURE_BOX_M / 2.0])
    cube.visual.face_colors = FURNITURE_COLOR
    return cube


def build_scene(consensus: dict) -> tuple[trimesh.Scene, dict]:
    walls = consensus.get("walls", [])
    openings = consensus.get("openings", [])
    rooms = consensus.get("rooms", [])
    furniture = consensus.get("furniture", [])

    scale = _derive_scale(rooms)
    # use page_bounds.min if available, else compute from walls
    bounds = consensus.get("metadata", {}).get("page_bounds") or {}
    if bounds:
        origin = (bounds.get("min_x", 0.0), bounds.get("min_y", 0.0))
    else:
        xs = [w["start"][0] for w in walls] + [w["end"][0] for w in walls]
        ys = [w["start"][1] for w in walls] + [w["end"][1] for w in walls]
        origin = (min(xs) if xs else 0.0, min(ys) if ys else 0.0)

    scene = trimesh.Scene()
    counters = {
        "walls_in": len(walls),
        "walls_out": 0,
        "openings_in": len(openings),
        "openings_out": 0,
        "rooms_in": len(rooms),
        "rooms_out": 0,
        "furniture_in": len(furniture),
        "furniture_out": 0,
        "scale_m_per_pt": scale,
    }

    # ----- room slabs -----
    for i, r in enumerate(rooms):
        poly_pts = [_to_xy(p, scale, origin) for p in r.get("polygon", [])]
        color = ROOM_PALETTE[i % len(ROOM_PALETTE)]
        mesh = _build_room_slab(poly_pts, color)
        if mesh is not None:
            scene.add_geometry(mesh, node_name=f"room_{r.get('room_id', i)}")
            counters["rooms_out"] += 1

    # ----- walls -----
    for w in walls:
        start_m = _to_xy(w["start"], scale, origin)
        end_m = _to_xy(w["end"], scale, origin)
        sources = w.get("sources") or []
        if "pipeline_v13" in sources:
            color = WALL_COLOR_AGREED
            t_m = WALL_THICKNESS_DEFAULT_M
        else:
            color = WALL_COLOR_SVG_ONLY
            t_m = WALL_THICKNESS_SVG_ONLY_M
        mesh = _build_wall(start_m, end_m, t_m, WALL_HEIGHT_M, color)
        if mesh is not None:
            scene.add_geometry(mesh, node_name=f"wall_{w.get('wall_id', '')}")
            counters["walls_out"] += 1

    # ----- openings -----
    for op in openings:
        center_m = _to_xy(op["center"], scale, origin)
        chord_m = max(float(op.get("chord_pt") or 30.0) * scale, 0.30)
        kind = op.get("kind", "door")
        if op.get("geometry_origin") == "svg_arc":
            color = OPENING_COLOR_DOOR_ARC
        else:
            color = OPENING_COLOR_GAP
        mesh = _build_opening(center_m, chord_m, kind, color)
        if mesh is not None:
            scene.add_geometry(mesh, node_name=f"opening_{op.get('opening_id', '')}")
            counters["openings_out"] += 1

    # ----- furniture -----
    # Furniture coords come from cubicasa_resized space (not PDF pts).
    # We rescale by ratio-of-bounding-box so they at least land inside the apt
    # extents. Cheap heuristic; OK for a viewer hint.
    fx, fy = [], []
    for f in furniture:
        c = f.get("approx_center_cubicasa_resized")
        if not c:
            continue
        fx.append(c[0]); fy.append(c[1])
    if fx and walls:
        wx = [_to_xy(w["start"], scale, origin)[0] for w in walls] + \
             [_to_xy(w["end"], scale, origin)[0] for w in walls]
        wy = [_to_xy(w["start"], scale, origin)[1] for w in walls] + \
             [_to_xy(w["end"], scale, origin)[1] for w in walls]
        f_minx, f_maxx = min(fx), max(fx)
        f_miny, f_maxy = min(fy), max(fy)
        w_minx, w_maxx = min(wx), max(wx)
        w_miny, w_maxy = min(wy), max(wy)
        f_w = max(f_maxx - f_minx, 1e-6)
        f_h = max(f_maxy - f_miny, 1e-6)
        s_x = (w_maxx - w_minx) / f_w
        s_y = (w_maxy - w_miny) / f_h
        for f in furniture:
            c = f.get("approx_center_cubicasa_resized")
            if not c:
                continue
            cx = w_minx + (c[0] - f_minx) * s_x
            # cubicasa Y also grows down; flip into our scene
            cy = w_maxy - (c[1] - f_miny) * s_y
            mesh = _build_furniture((cx, cy))
            scene.add_geometry(mesh, node_name=f"furn_{f.get('type', '')}_{counters['furniture_out']}")
            counters["furniture_out"] += 1

    return scene, counters


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build GLB from consensus_model.json")
    parser.add_argument("run_dir", type=Path,
                        help="Directory containing consensus_model.json")
    parser.add_argument("--output", type=Path, default=None,
                        help="Output .glb path (default: <run_dir>/consensus_3d.glb)")
    args = parser.parse_args(argv)

    run_dir: Path = args.run_dir
    src = run_dir / "consensus_model.json"
    if not src.exists():
        print(f"[ERR] not found: {src}", file=sys.stderr)
        return 2
    out = args.output or (run_dir / "consensus_3d.glb")

    consensus = json.loads(src.read_text(encoding="utf-8"))
    scene, counters = build_scene(consensus)
    scene.export(str(out))

    size = out.stat().st_size
    counters["output"] = str(out)
    counters["size_bytes"] = size
    counters["size_kb"] = round(size / 1024.0, 2)
    print(json.dumps(counters, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
