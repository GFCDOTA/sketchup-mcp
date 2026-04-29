"""Render an observed_model.json into a PNG preview.

Three modes:
  - top      vista de topo (planta arquitetonica 2D)
  - frontal  elevation 2D no plano X-Z, com sombreamento por profundidade
  - axon     axonometria 3D estilo SketchUp (matplotlib mplot3d)

Uso:
  python scripts/preview/render_preview.py \
      --run runs/openings_refine_final \
      --mode top \
      --out docs/preview/top.png

O bridge Ruby/SketchUp (Fase 6 do roadmap) ainda nao foi construido — este
script substitui a renderizacao .skp usando matplotlib.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Polygon, Rectangle, Circle
from mpl_toolkits.mplot3d.art3d import Poly3DCollection


BG = "#f5f3ee"

ROOM_PALETTE = [
    "#fde2c0", "#c8e6c9", "#bbdefb", "#f8bbd0", "#dcedc8",
    "#ffe0b2", "#d1c4e9", "#b3e5fc", "#fff9c4", "#f5e0d0",
    "#cfd8dc", "#e1bee7", "#ffccbc", "#c5e1a5", "#b2dfdb",
    "#f0f4c3", "#ffe082", "#b39ddb", "#80deea", "#a5d6a7",
    "#ffab91", "#ce93d8", "#90caf9",
]

WALL_FACE_TOP = "#3d3325"
WALL_FACE_AXON = "#e6dfd2"
WALL_EDGE = "#7f6f55"
WALL_TOP_LIGHT = "#d6cdba"
WALL_BACK = "#dccbac"
WALL_FRONT = "#7f6f55"
WALL_EDGE_DARK = "#3d3325"

DOOR_COLOR = "#d97b3b"
DOOR_DARK = "#6b3a16"
PASSAGE_COLOR = "#4a90e2"
PASSAGE_DARK = "#2c5b8e"
WINDOW_COLOR = "#9ad0ec"


def lerp_color(c1_hex: str, c2_hex: str, t: float) -> tuple[float, float, float]:
    t = max(0.0, min(1.0, t))
    c1 = tuple(int(c1_hex[i : i + 2], 16) / 255.0 for i in (1, 3, 5))
    c2 = tuple(int(c2_hex[i : i + 2], 16) / 255.0 for i in (1, 3, 5))
    return tuple(c1[i] * (1 - t) + c2[i] * t for i in range(3))


def wall_footprint(start, end, thickness):
    x0, y0 = start
    x1, y1 = end
    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return None
    ux, uy = dx / length, dy / length
    px, py = -uy, ux
    half = thickness / 2.0
    return [
        (x0 + px * half, y0 + py * half),
        (x0 - px * half, y0 - py * half),
        (x1 - px * half, y1 - py * half),
        (x1 + px * half, y1 + py * half),
    ]


def render_top(data: dict, out: Path) -> None:
    walls = data["walls"]
    rooms = data["rooms"]
    openings = data["openings"]
    junctions = data.get("junctions", [])
    page = data["bounds"]["pages"][0]

    fig, ax = plt.subplots(figsize=(16, 11), dpi=150, facecolor=BG)
    ax.set_facecolor(BG)

    for i, room in enumerate(rooms):
        poly = [(x, -y) for (x, y) in room["polygon"]]
        ax.add_patch(Polygon(poly, facecolor=ROOM_PALETTE[i % len(ROOM_PALETTE)],
                             edgecolor="#5b6770", linewidth=0.6, alpha=0.85, zorder=1))
        cx, cy = room["centroid"]
        ax.text(cx, -cy, f"{room['room_id']}\n{room['area']:.0f}",
                fontsize=7, color="#1a1611", ha="center", va="center",
                fontweight="bold", zorder=4)

    for w in walls:
        poly = wall_footprint(w["start"], w["end"], w["thickness"])
        if poly is None:
            continue
        poly_y_flipped = [(x, -y) for (x, y) in poly]
        ax.add_patch(Polygon(poly_y_flipped, facecolor=WALL_FACE_TOP,
                             edgecolor="#1a1611", linewidth=0.3, zorder=3))

    for j in junctions:
        kind = j.get("kind", "end")
        if kind == "end":
            color, size = "#c0392b", 1.8
        elif kind == "pass_through":
            color, size = "#7f8c8d", 1.2
        else:
            color, size = "#27ae60", 2.2
        x, y = j["point"]
        ax.add_patch(Circle((x, -y), size, facecolor=color, edgecolor="none",
                            zorder=5, alpha=0.7))

    for op in openings:
        cx, cy = op["center"]
        kind = op["kind"]
        width = op["width"]
        color = {"door": DOOR_COLOR, "window": WINDOW_COLOR}.get(kind, PASSAGE_COLOR)
        if op["orientation"] == "horizontal":
            w_w, w_h = width, 8
        else:
            w_w, w_h = 8, width
        ax.add_patch(Rectangle((cx - w_w / 2, -cy - w_h / 2), w_w, w_h,
                               facecolor=color, edgecolor="#1a1611",
                               linewidth=0.5, zorder=6, alpha=0.95))

    pad = 30.0
    ax.set_xlim(page["min_x"] - pad, page["max_x"] + pad)
    ax.set_ylim(-page["max_y"] - pad, -page["min_y"] + pad)
    ax.set_aspect("equal")
    ax.set_axis_off()

    fig.suptitle("Preview — vista de topo (planta)", fontsize=20,
                 fontweight="bold", color="#2c3e50", y=0.97)
    fig.text(0.5, 0.93,
             f"walls={len(walls)}  rooms={len(rooms)}  openings={len(openings)}  junctions={len(junctions)}",
             ha="center", fontsize=11, color="#5b6770")

    legend = [("Paredes", WALL_FACE_TOP), ("Cômodos", "#bbdefb"),
              ("Portas", DOOR_COLOR), ("Passagens", PASSAGE_COLOR),
              ("Endpoint", "#c0392b"), ("Junção tee/cross", "#27ae60")]
    for i, (label, color) in enumerate(legend):
        x_pos = 0.04 + i * 0.155
        fig.patches.append(plt.Rectangle((x_pos, 0.06), 0.018, 0.018,
                                         transform=fig.transFigure,
                                         facecolor=color, edgecolor="#444", linewidth=0.6))
        fig.text(x_pos + 0.022, 0.069, label, fontsize=9, color="#2c3e50", va="center")

    fig.subplots_adjust(left=0.02, right=0.98, top=0.91, bottom=0.10)
    fig.savefig(out, dpi=150, facecolor=BG)


def render_frontal(data: dict, out: Path) -> None:
    walls = data["walls"]
    openings = data["openings"]
    page = data["bounds"]["pages"][0]
    WALL_HEIGHT = 90.0
    DOOR_HEIGHT = 62.0

    y_min, y_max = page["min_y"], page["max_y"]
    x_min, x_max = page["min_x"], page["max_x"]
    y_range = max(y_max - y_min, 1.0)

    fig, ax = plt.subplots(figsize=(18, 7), dpi=150, facecolor=BG)
    ax.set_facecolor(BG)

    pad_x = 40
    ax.add_patch(Rectangle((x_min - pad_x, 0), (x_max - x_min) + 2 * pad_x,
                           WALL_HEIGHT * 1.6, facecolor="#eaf2f8", edgecolor="none", zorder=0))
    ax.add_patch(Rectangle((x_min - pad_x, -WALL_HEIGHT * 0.25),
                           (x_max - x_min) + 2 * pad_x, WALL_HEIGHT * 0.25,
                           facecolor="#cbb892", edgecolor="none", zorder=0))

    wall_data = []
    for w in walls:
        ext = wall_footprint(w["start"], w["end"], w["thickness"])
        if ext is None:
            continue
        xs = [p[0] for p in ext]
        ys = [p[1] for p in ext]
        wall_data.append((min(xs), max(xs), sum(ys) / 4.0))
    wall_data.sort(key=lambda t: -t[2])

    for xa, xb, ymid in wall_data:
        depth_t = (y_max - ymid) / y_range
        color = lerp_color(WALL_BACK, WALL_FRONT, depth_t)
        ax.add_patch(Rectangle((xa, 0), xb - xa, WALL_HEIGHT,
                               facecolor=color, edgecolor=WALL_EDGE_DARK,
                               linewidth=0.4, zorder=1 + depth_t))

    ax.plot([x_min - pad_x, x_max + pad_x], [0, 0],
            color="#3d3325", linewidth=1.5, zorder=10)

    for op in openings:
        cx, cy = op["center"]
        width = op["width"]
        kind = op["kind"]
        depth_t = (y_max - cy) / y_range
        if kind == "door":
            z0, z1, face, edge = 0.0, DOOR_HEIGHT, DOOR_DARK, "#3d1f0a"
        elif kind == "window":
            z0, z1, face, edge = 35.0, 70.0, WINDOW_COLOR, "#1f4d6b"
        else:
            z0, z1, face, edge = 0.0, DOOR_HEIGHT * 0.95, PASSAGE_DARK, "#1a3d63"

        x0 = cx - width / 2.0 if op["orientation"] == "horizontal" else cx - 4
        x1 = cx + width / 2.0 if op["orientation"] == "horizontal" else cx + 4
        ax.add_patch(Rectangle((x0, z0), x1 - x0, z1 - z0,
                               facecolor=face, edgecolor=edge, linewidth=0.7,
                               zorder=5 + depth_t, alpha=0.9))

    ax.set_xlim(x_min - pad_x, x_max + pad_x)
    ax.set_ylim(-WALL_HEIGHT * 0.25, WALL_HEIGHT * 1.6)
    ax.set_aspect("equal")
    ax.set_axis_off()

    fig.suptitle("Preview — vista frontal (elevation)", fontsize=20,
                 fontweight="bold", color="#2c3e50", y=0.96)
    fig.text(0.5, 0.91,
             f"walls={len(walls)}  rooms={len(data['rooms'])}  openings={len(openings)}  ·  tom escuro = parede ao sul (frente)",
             ha="center", fontsize=11, color="#5b6770")

    fig.subplots_adjust(left=0.03, right=0.97, top=0.86, bottom=0.10)
    fig.savefig(out, dpi=150, facecolor=BG)


def render_axon(data: dict, out: Path) -> None:
    walls = data["walls"]
    rooms = data["rooms"]
    openings = data["openings"]
    page = data["bounds"]["pages"][0]
    WALL_HEIGHT = 55.0

    fig = plt.figure(figsize=(16, 10), dpi=150, facecolor=BG)
    ax = fig.add_subplot(111, projection="3d")
    ax.set_facecolor(BG)

    floor_faces = []
    floor_colors = []
    for i, room in enumerate(rooms):
        poly = [(x, -y, 0.0) for (x, y) in room["polygon"]]
        floor_faces.append(poly)
        floor_colors.append(ROOM_PALETTE[i % len(ROOM_PALETTE)])
    coll = Poly3DCollection(floor_faces, alpha=0.85, edgecolor="#5b6770", linewidths=0.6)
    coll.set_facecolor(floor_colors)
    ax.add_collection3d(coll)

    side_faces = []
    top_faces = []
    for w in walls:
        fp = wall_footprint(w["start"], w["end"], w["thickness"])
        if fp is None:
            continue
        base = [(x, -y, 0) for (x, y) in fp]
        top = [(x, y, WALL_HEIGHT) for (x, y, _) in base]
        top_faces.append(top)
        side_faces.append(base)
        side_faces.append([base[0], base[1], top[1], top[0]])
        side_faces.append([base[1], base[2], top[2], top[1]])
        side_faces.append([base[2], base[3], top[3], top[2]])
        side_faces.append([base[3], base[0], top[0], top[3]])

    ax.add_collection3d(Poly3DCollection(side_faces, facecolor=WALL_FACE_AXON,
                                          edgecolor=WALL_EDGE, linewidths=0.35, alpha=0.95))
    ax.add_collection3d(Poly3DCollection(top_faces, facecolor=WALL_TOP_LIGHT,
                                          edgecolor=WALL_EDGE, linewidths=0.45))

    op_faces = {}
    for op in openings:
        cx, cy = op["center"]
        width = op["width"]
        thick = walls[0]["thickness"] if walls else 6.25
        if op["orientation"] == "horizontal":
            xh, yh = width / 2.0, thick * 1.6
        else:
            xh, yh = thick * 1.6, width / 2.0
        if op["kind"] == "door":
            z0, z1, color = 0.0, 38.0, DOOR_DARK
        elif op["kind"] == "window":
            z0, z1, color = 22.0, 40.0, WINDOW_COLOR
        else:
            z0, z1, color = 0.0, 36.0, PASSAGE_COLOR
        a = (cx - xh, -(cy - yh))
        b = (cx + xh, -(cy - yh))
        c = (cx + xh, -(cy + yh))
        d = (cx - xh, -(cy + yh))
        bottom = [(*a, z0), (*b, z0), (*c, z0), (*d, z0)]
        top = [(x, y, z1) for (x, y, _) in bottom]
        op_faces.setdefault(color, []).extend([
            bottom, top,
            [bottom[0], bottom[1], top[1], top[0]],
            [bottom[1], bottom[2], top[2], top[1]],
            [bottom[2], bottom[3], top[3], top[2]],
            [bottom[3], bottom[0], top[0], top[3]],
        ])
    for color, faces in op_faces.items():
        ax.add_collection3d(Poly3DCollection(faces, facecolor=color,
                                              edgecolor="#3a3a3a", linewidths=0.25, alpha=0.85))

    pad = 30.0
    ax.set_xlim(page["min_x"] - pad, page["max_x"] + pad)
    ax.set_ylim(-page["max_y"] - pad, -page["min_y"] + pad)
    ax.set_zlim(0, WALL_HEIGHT * 4.0)
    try:
        ax.set_box_aspect(((page["max_x"] - page["min_x"]) + 2 * pad,
                           (page["max_y"] - page["min_y"]) + 2 * pad,
                           WALL_HEIGHT * 1.6))
    except Exception:
        pass
    ax.view_init(elev=32, azim=-58)
    ax.set_axis_off()

    fig.suptitle("Preview — axonometria 3D", fontsize=18, fontweight="bold",
                 color="#2c3e50", y=0.96)
    fig.text(0.5, 0.92,
             f"walls={len(walls)}  rooms={len(rooms)}  openings={len(openings)}",
             ha="center", fontsize=10, color="#5b6770")

    fig.savefig(out, dpi=150, facecolor=BG, bbox_inches="tight")


RENDERERS = {"top": render_top, "frontal": render_frontal, "axon": render_axon}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True,
                        help="diretorio do run OU caminho direto pro observed_model.json")
    parser.add_argument("--mode", choices=list(RENDERERS), default="top",
                        help="modo de render (default: top)")
    parser.add_argument("--out", default=None,
                        help="caminho do PNG de saida (default: docs/preview/<mode>.png)")
    args = parser.parse_args()

    run_path = Path(args.run)
    if run_path.is_dir():
        json_path = run_path / "observed_model.json"
    else:
        json_path = run_path
    if not json_path.exists():
        raise SystemExit(f"observed_model.json nao encontrado em {json_path}")

    out = Path(args.out) if args.out else Path(f"docs/preview/{args.mode}.png")
    out.parent.mkdir(parents=True, exist_ok=True)

    data = json.loads(json_path.read_text(encoding="utf-8"))
    print(f"render {args.mode}: walls={len(data['walls'])}  rooms={len(data['rooms'])}  "
          f"openings={len(data['openings'])}  ->  {out}")
    RENDERERS[args.mode](data, out)
    print(f"PNG gerado: {out}")


if __name__ == "__main__":
    main()
