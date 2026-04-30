"""Render observed_model.json into a 3D PNG via Blender (headless).

Run with:
    "C:/Program Files/Blender Foundation/Blender 5.1/blender.exe" \
        --background --python scripts/preview/render_blender.py -- \
        --run runs/postfix_2026-04-29 --mode axon --out /tmp/blender_axon.png

Mesh policy:
  - Each wall = cuboid (length along wall axis, thickness perpendicular,
    height fixed). Walls keep their actual jitter to match pipeline output.
  - Each room = horizontal floor face at z=0 (only used as a thin slab).
  - Openings are NOT subtracted (kept as overlay marker for now); future
    pass can boolean-cut the wall mesh.

Camera modes:
  top    : orthographic top view (sub for matplotlib top mode)
  frontal: orthographic front view at z=mid
  axon   : 45deg/30deg ortho isometric, the SketchUp-style preview

Coordinates: input is in PDF points (1pt = 1/72 inch). We center the
model on the origin and scale so the bounding box fits in a 20-unit
square (Blender world units), keeping a fixed wall height of 2.5 units
(~3 m equivalent at the chosen scale).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy  # noqa: E402  (only available when running inside Blender)


WALL_HEIGHT = 2.5  # blender units (~ floor-to-ceiling)
TARGET_SPAN = 20.0  # bbox max dimension fits in this many blender units
WALL_DEFAULT_THICKNESS = 0.2  # used when wall.thickness missing


def parse_args() -> argparse.Namespace:
    # Blender forwards args after `--`; everything before belongs to it.
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []
    p = argparse.ArgumentParser()
    p.add_argument("--run", required=True, help="run dir with observed_model.json")
    p.add_argument("--mode", choices=["top", "frontal", "axon"], default="axon")
    p.add_argument("--out", required=True, help="output PNG path")
    p.add_argument("--resolution", type=int, default=1600)
    return p.parse_args(argv)


def reset_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.world = bpy.data.worlds.new("World")
    scene.world.use_nodes = True
    bg = scene.world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.96, 0.95, 0.92, 1.0)  # paper-ish
    bg.inputs["Strength"].default_value = 1.0


def make_material(name: str, rgba: tuple[float, float, float, float]) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = rgba
        if "Roughness" in bsdf.inputs:
            bsdf.inputs["Roughness"].default_value = 0.7
    mat.diffuse_color = rgba
    return mat


def compute_transform(walls: list[dict]) -> tuple[float, float, float]:
    """Return (cx, cy, scale) so the model fits TARGET_SPAN centered at origin."""
    xs, ys = [], []
    for w in walls:
        xs.extend([w["start"][0], w["end"][0]])
        ys.extend([w["start"][1], w["end"][1]])
    if not xs:
        return 0.0, 0.0, 1.0
    cx = (min(xs) + max(xs)) / 2.0
    cy = (min(ys) + max(ys)) / 2.0
    span = max(max(xs) - min(xs), max(ys) - min(ys), 1e-6)
    scale = TARGET_SPAN / span
    return cx, cy, scale


def build_wall(
    name: str,
    start_xy: tuple[float, float],
    end_xy: tuple[float, float],
    thickness: float,
    height: float,
    material: bpy.types.Material,
) -> bpy.types.Object:
    sx, sy = start_xy
    ex, ey = end_xy
    length = math.hypot(ex - sx, ey - sy)
    if length < 1e-6:
        # Skip degenerate; create empty mesh just to keep wall_id alignment.
        mesh = bpy.data.meshes.new(name)
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.collection.objects.link(obj)
        return obj
    cx = (sx + ex) / 2.0
    cy = (sy + ey) / 2.0
    cz = height / 2.0
    angle = math.atan2(ey - sy, ex - sx)

    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(cx, cy, cz))
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = (length, max(thickness, 0.01), height)
    obj.rotation_euler = (0.0, 0.0, angle)
    obj.data.materials.append(material)
    return obj


def build_floor(
    name: str,
    polygon_xy: list[tuple[float, float]],
    material: bpy.types.Material,
) -> bpy.types.Object | None:
    if len(polygon_xy) < 3:
        return None
    mesh = bpy.data.meshes.new(name)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    verts = [(x, y, 0.001) for (x, y) in polygon_xy]  # tiny lift to avoid z-fight
    faces = [list(range(len(verts)))]
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj.data.materials.append(material)
    return obj


def configure_camera(mode: str) -> None:
    scene = bpy.context.scene
    cam_data = bpy.data.cameras.new("Camera")
    cam_data.type = "ORTHO"
    span = TARGET_SPAN * 1.15
    cam_data.ortho_scale = span
    cam_obj = bpy.data.objects.new("Camera", cam_data)
    bpy.context.collection.objects.link(cam_obj)
    scene.camera = cam_obj

    if mode == "top":
        cam_obj.location = (0.0, 0.0, 30.0)
        cam_obj.rotation_euler = (0.0, 0.0, 0.0)
    elif mode == "frontal":
        cam_obj.location = (0.0, -30.0, WALL_HEIGHT / 2.0)
        cam_obj.rotation_euler = (math.radians(90), 0.0, 0.0)
    else:  # axon
        # 45deg yaw, 30deg pitch above horizon
        d = 30.0
        yaw = math.radians(-45.0)
        pitch = math.radians(30.0)
        cam_obj.location = (
            d * math.cos(pitch) * math.sin(yaw),
            -d * math.cos(pitch) * math.cos(yaw),
            d * math.sin(pitch) + WALL_HEIGHT / 2.0,
        )
        cam_obj.rotation_euler = (math.radians(60.0), 0.0, math.radians(-45.0))


def configure_lights(mode: str) -> None:
    # Key sun: strong directional, slightly off-zenith so walls cast soft
    # shadows on the floor (helps reading wall angles in axon).
    key = bpy.data.lights.new("Sun.Key", type="SUN")
    key.energy = 5.0
    key.angle = math.radians(8.0)
    key_obj = bpy.data.objects.new("Sun.Key", key)
    bpy.context.collection.objects.link(key_obj)
    key_obj.location = (10.0, -10.0, 20.0)
    key_obj.rotation_euler = (math.radians(50.0), math.radians(20.0), math.radians(-30.0))

    # Fill: soft hemi-equivalent so the dark sides don't pure-black out.
    fill = bpy.data.lights.new("Sun.Fill", type="SUN")
    fill.energy = 1.5
    fill_obj = bpy.data.objects.new("Sun.Fill", fill)
    bpy.context.collection.objects.link(fill_obj)
    fill_obj.location = (-15.0, 10.0, 10.0)
    fill_obj.rotation_euler = (math.radians(-30.0), math.radians(-20.0), math.radians(120.0))


def render(out: Path, resolution: int) -> None:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in {
        item.identifier for item in scene.render.bl_rna.properties["engine"].enum_items
    } else "BLENDER_EEVEE"
    scene.render.resolution_x = resolution
    scene.render.resolution_y = int(resolution * 0.66)
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(out)
    scene.view_settings.view_transform = "Standard"
    bpy.ops.render.render(write_still=True)


def main() -> None:
    args = parse_args()
    run_dir = Path(args.run)
    json_path = run_dir / "observed_model.json"
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(json_path.read_text(encoding="utf-8"))

    walls = data.get("walls", [])
    rooms = data.get("rooms", [])
    if not walls:
        print("no walls; nothing to render", file=sys.stderr)
        sys.exit(1)

    cx, cy, scale = compute_transform(walls)

    def t(p):
        return ((p[0] - cx) * scale, -(p[1] - cy) * scale)  # flip Y for top-up

    reset_scene()
    wall_mat = make_material("Wall", (0.32, 0.28, 0.24, 1.0))
    floor_mat = make_material("Floor", (0.88, 0.82, 0.72, 1.0))
    # Pastels chosen to read clearly under sun-fill lighting; saturate
    # slightly so 24+ rooms stay distinguishable against beige floor.
    room_palette = [
        (0.62, 0.78, 0.92, 1.0),
        (0.94, 0.72, 0.72, 1.0),
        (0.74, 0.92, 0.72, 1.0),
        (0.96, 0.88, 0.62, 1.0),
        (0.88, 0.72, 0.94, 1.0),
        (0.72, 0.92, 0.92, 1.0),
        (0.94, 0.82, 0.62, 1.0),
        (0.82, 0.94, 0.62, 1.0),
    ]
    room_mats = [make_material(f"Room{i}", rgba) for i, rgba in enumerate(room_palette)]

    for i, w in enumerate(walls):
        s = t(w["start"])
        e = t(w["end"])
        thickness_pdf = w.get("thickness") or 4.0
        thickness_world = max(thickness_pdf * scale, 0.05)
        build_wall(f"Wall.{i:04d}", s, e, thickness_world, WALL_HEIGHT, wall_mat)

    for i, r in enumerate(rooms):
        poly_world = [t(p) for p in r["polygon"]]
        build_floor(f"Room.{i:04d}", poly_world, room_mats[i % len(room_mats)])

    configure_camera(args.mode)
    configure_lights(args.mode)
    render(out, args.resolution)
    print(f"OK {args.mode} -> {out}")


if __name__ == "__main__":
    main()
