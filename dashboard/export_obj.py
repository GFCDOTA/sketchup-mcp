"""Export consensus_model.json -> Wavefront OBJ + MTL via trimesh.

Reads runs/final_planta_74/consensus_model.json and builds a 3D scene:
  - walls_consolidated: extruded boxes along centerline (thickness x height 2.70m)
  - rooms: thin polygon-extruded floor slabs (height 0.05m)
  - furniture: simple cubes at approx_center

Uses an arbitrary scale (0.01) instead of the official PT->M conversion
so the result is visible/manageable at typical OBJ viewer scales.

Output:
  runs/final_planta_74/generated_from_consensus.obj
  runs/final_planta_74/generated_from_consensus.mtl
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import trimesh

ROOT = Path(r"E:/Claude/sketchup-mcp-exp-dedup")
CONSENSUS = ROOT / "runs" / "final_planta_74" / "consensus_model.json"
OUT_OBJ = ROOT / "runs" / "final_planta_74" / "generated_from_consensus.obj"

SCALE = 0.01            # 1 pt -> 0.01 (arbitrary, makes thing viewable)
WALL_HEIGHT_M = 2.70
FLOOR_THICK_M = 0.05
FURNITURE_SIZE_M = 0.5

# Material colors (RGBA 0-1)
COLOR_WALL = (0.85, 0.85, 0.82, 1.0)
COLOR_ROOM = (0.55, 0.70, 0.85, 1.0)
COLOR_FURNITURE = (0.90, 0.55, 0.30, 1.0)
COLOR_DOOR = (0.40, 0.25, 0.15, 1.0)
COLOR_WINDOW = (0.30, 0.65, 0.85, 1.0)


def wall_box(start_pt, end_pt, thickness_pt) -> trimesh.Trimesh:
    """Build an oriented box from a centerline segment + thickness, extruded WALL_HEIGHT."""
    sx, sy = start_pt
    ex, ey = end_pt
    dx, dy = ex - sx, ey - sy
    length_pt = math.hypot(dx, dy)
    if length_pt < 1e-6:
        return None
    angle = math.atan2(dy, dx)
    cx = (sx + ex) * 0.5 * SCALE
    cy = (sy + ey) * 0.5 * SCALE
    cz = WALL_HEIGHT_M * 0.5
    # Box centered at origin: (length, thickness, height) all in meters
    box = trimesh.creation.box(
        extents=(length_pt * SCALE, thickness_pt * SCALE, WALL_HEIGHT_M)
    )
    # Rotate around Z by angle, then translate to centerline midpoint
    R = trimesh.transformations.rotation_matrix(angle, [0, 0, 1])
    T = trimesh.transformations.translation_matrix([cx, cy, cz])
    box.apply_transform(T @ R)
    return box


def room_floor(polygon_pts) -> trimesh.Trimesh:
    """Extrude a 2D polygon (list of [x,y] pts) into a thin floor slab."""
    if len(polygon_pts) < 3:
        return None
    pts = np.array(polygon_pts, dtype=float) * SCALE
    try:
        poly = trimesh.path.polygons.Polygon(pts)
        if not poly.is_valid or poly.area < 1e-6:
            poly = poly.buffer(0)
        mesh = trimesh.creation.extrude_polygon(poly, height=FLOOR_THICK_M)
        # extrude_polygon places the base at z=0; that's fine
        return mesh
    except Exception as exc:
        print(f"  [room] skipping invalid polygon ({len(polygon_pts)} pts): {exc}")
        return None


def furniture_cube(center_xy) -> trimesh.Trimesh:
    cx, cy = center_xy[0] * SCALE, center_xy[1] * SCALE
    box = trimesh.creation.box(extents=(FURNITURE_SIZE_M,) * 3)
    T = trimesh.transformations.translation_matrix([cx, cy, FURNITURE_SIZE_M * 0.5])
    box.apply_transform(T)
    return box


def opening_marker(opening) -> trimesh.Trimesh:
    cx, cy = opening["center"]
    chord_pt = opening.get("chord_pt", 80.0)
    kind = opening.get("kind", "door")
    if kind == "window":
        # Slim vertical strip in mid wall
        ext = (chord_pt * SCALE, 0.10, 1.20)
        z = 1.10
    else:
        ext = (chord_pt * SCALE, 0.10, 2.10)
        z = 1.05
    box = trimesh.creation.box(extents=ext)
    T = trimesh.transformations.translation_matrix([cx * SCALE, cy * SCALE, z])
    box.apply_transform(T)
    return box, kind


def main():
    print(f"[load] {CONSENSUS}")
    data = json.loads(CONSENSUS.read_text(encoding="utf-8"))

    walls = data.get("walls_consolidated", [])
    rooms = data.get("rooms", [])
    furniture = data.get("furniture", [])
    openings = data.get("openings", [])

    print(f"[input] walls_consolidated={len(walls)} rooms={len(rooms)} "
          f"furniture={len(furniture)} openings={len(openings)}")

    # Build per-category meshes, concatenate inside each category, set color, then dump.
    wall_meshes = []
    for w in walls:
        m = wall_box(w["centerline_start"], w["centerline_end"], w["thickness_pt"])
        if m is not None:
            wall_meshes.append(m)

    room_meshes = []
    for r in rooms:
        m = room_floor(r["polygon"])
        if m is not None:
            room_meshes.append(m)

    furn_meshes = []
    for f in furniture:
        center = f.get("approx_center_cubicasa_resized") or f.get("center")
        if center is None:
            continue
        furn_meshes.append(furniture_cube(center))

    door_meshes, window_meshes = [], []
    for o in openings:
        m, kind = opening_marker(o)
        (window_meshes if kind == "window" else door_meshes).append(m)

    scene = trimesh.Scene()

    def add_group(meshes, name, color_rgba):
        if not meshes:
            return 0, 0
        merged = trimesh.util.concatenate(meshes)
        # Apply a per-face color (uniform)
        rgba255 = [int(c * 255) for c in color_rgba]
        merged.visual.face_colors = np.tile(rgba255, (len(merged.faces), 1))
        scene.add_geometry(merged, geom_name=name, node_name=name)
        return len(merged.vertices), len(merged.faces)

    counts = {}
    counts["walls"] = add_group(wall_meshes, "walls", COLOR_WALL)
    counts["rooms"] = add_group(room_meshes, "rooms", COLOR_ROOM)
    counts["furniture"] = add_group(furn_meshes, "furniture", COLOR_FURNITURE)
    counts["doors"] = add_group(door_meshes, "doors", COLOR_DOOR)
    counts["windows"] = add_group(window_meshes, "windows", COLOR_WINDOW)

    OUT_OBJ.parent.mkdir(parents=True, exist_ok=True)
    # trimesh exports OBJ with inline per-vertex colors. We additionally write
    # a sidecar .mtl with named materials (one per group) for viewers that
    # honor mtllib/usemtl over vertex colors.
    scene.export(file_obj=str(OUT_OBJ), file_type="obj")

    mtl_path = OUT_OBJ.with_suffix(".mtl")
    mtl_lines = [
        "# Generated alongside generated_from_consensus.obj",
        "# 5 materials matching the per-group palette baked into the OBJ vertex colors.",
        "",
    ]
    palette = {
        "walls":     COLOR_WALL,
        "rooms":     COLOR_ROOM,
        "furniture": COLOR_FURNITURE,
        "doors":     COLOR_DOOR,
        "windows":   COLOR_WINDOW,
    }
    for name, (r, g, b, a) in palette.items():
        mtl_lines += [
            f"newmtl mat_{name}",
            f"Ka {r:.4f} {g:.4f} {b:.4f}",
            f"Kd {r:.4f} {g:.4f} {b:.4f}",
            f"Ks 0.1000 0.1000 0.1000",
            f"d {a:.3f}",
            f"illum 2",
            "",
        ]
    mtl_path.write_text("\n".join(mtl_lines), encoding="utf-8")

    # Patch the OBJ to reference the MTL on the first content line
    obj_text = OUT_OBJ.read_text(encoding="utf-8").splitlines()
    obj_text.insert(1, f"mtllib {mtl_path.name}")
    OUT_OBJ.write_text("\n".join(obj_text), encoding="utf-8")

    print()
    print(f"[output] {OUT_OBJ}")
    print(f"[output] {mtl_path}")
    print()
    total_v = total_f = 0
    for name, (v, f) in counts.items():
        print(f"  {name:10s}  vertices={v:6d}  faces={f:6d}")
        total_v += v
        total_f += f
    print(f"  {'TOTAL':10s}  vertices={total_v:6d}  faces={total_f:6d}")
    print(f"[file_size] obj={OUT_OBJ.stat().st_size:,} bytes")
    if mtl_path.exists():
        print(f"[file_size] mtl={mtl_path.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
