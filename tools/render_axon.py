"""Render an axonometric (SketchUp-style) PNG from consensus_model.json.

Walls extruded to WALL_HEIGHT_M, rooms as colored floors, soft barriers
as low parapets. Pure matplotlib — no SketchUp dependency.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPolygon
import numpy as np
from mpl_toolkits.mplot3d.art3d import Poly3DCollection


PT_TO_M = 0.19 / 5.4   # 5.4 pt wall = 19 cm real -> 0.0352 m/pt
WALL_HEIGHT_M = 2.70
PARAPET_HEIGHT_M = 1.10

ROOM_COLORS = [
    "#fde2c0", "#c8e6c9", "#bbdefb", "#f8bbd0", "#dcedc8",
    "#ffe0b2", "#d1c4e9", "#b3e5fc", "#fff9c4", "#f5e0d0",
    "#cfd8dc", "#e1bee7", "#ffccbc",
]
WALL_TOP = "#5a4a32"
WALL_SIDE = "#8e7656"
PARAPET_COLOR = "#a8c8d8"


def wall_box(w: dict, t: float) -> tuple[np.ndarray, np.ndarray]:
    s, e = w["start"], w["end"]
    if w["orientation"] == "h":
        x0, x1 = sorted([s[0], e[0]])
        cy = s[1]
        corners = np.array([
            [x0, cy - t / 2], [x1, cy - t / 2],
            [x1, cy + t / 2], [x0, cy + t / 2],
        ])
    else:
        cx = s[0]
        y0, y1 = sorted([s[1], e[1]])
        corners = np.array([
            [cx - t / 2, y0], [cx + t / 2, y0],
            [cx + t / 2, y1], [cx - t / 2, y1],
        ])
    return corners[:, 0], corners[:, 1]


def extrude_polygon(xs: np.ndarray, ys: np.ndarray, z0: float, z1: float
                    ) -> list[np.ndarray]:
    """Returns the 4-side + top + bottom faces of a prism."""
    n = len(xs)
    bottom = np.column_stack([xs, ys, np.full(n, z0)])
    top = np.column_stack([xs, ys, np.full(n, z1)])
    faces = [top, bottom[::-1]]
    for i in range(n):
        j = (i + 1) % n
        faces.append(np.array([bottom[i], bottom[j], top[j], top[i]]))
    return faces


DOOR_HEIGHT_M = 2.10        # standard door clearance
DOOR_COLOR = "#f97316"      # orange — same as PDF overlay
DOOR_FRAME_COLOR = "#c2410c"


def _opening_chord(opening: dict, wall: dict, t_pt: float
                   ) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """Return (start_xy_pt, end_xy_pt) of the opening's chord on its
    host wall, in PDF point coords. Used to mark the door footprint."""
    if not opening.get("center"):
        return None
    cx, cy = opening["center"]
    width_pt = float(opening.get("opening_width_pts") or 30.0)
    s, e = wall["start"], wall["end"]
    if wall["orientation"] == "h":
        return (cx - width_pt / 2, s[1]), (cx + width_pt / 2, s[1])
    return (s[0], cy - width_pt / 2), (s[0], cy + width_pt / 2)


def render(consensus_path: Path, out: Path, mode: str = "axon",
           dpi: int = 200) -> None:
    d = json.loads(consensus_path.read_text())
    walls = d["walls"]
    rooms = d.get("rooms", [])
    barriers = d.get("soft_barriers", [])
    openings = d.get("openings", [])
    t_pt = d["wall_thickness_pts"]
    walls_by_id = {w["id"]: w for w in walls}

    # Convert PDF pt -> meters for sensible aspect
    def conv_xy(x: float, y: float) -> tuple[float, float]:
        return x * PT_TO_M, y * PT_TO_M

    if mode == "axon":
        fig = plt.figure(figsize=(12, 9), dpi=dpi)
        ax = fig.add_subplot(111, projection="3d")
        ax.set_facecolor("#f5f3ee")
        fig.patch.set_facecolor("#f5f3ee")

        # Floor faces (rooms) at z=0
        for i, r in enumerate(rooms):
            color = ROOM_COLORS[i % len(ROOM_COLORS)]
            poly = [(p[0] * PT_TO_M, p[1] * PT_TO_M, 0.0)
                    for p in r["polygon_pts"]]
            if len(poly) < 3:
                continue
            pc = Poly3DCollection([poly], facecolors=color, edgecolors="#7a6a4a",
                                  linewidths=0.5, alpha=0.85)
            ax.add_collection3d(pc)
            cx = sum(p[0] for p in poly) / len(poly)
            cy = sum(p[1] for p in poly) / len(poly)
            ax.text(cx, cy, 0.05, r.get("name", r["id"]),
                    fontsize=7, color="#2a2a2a", ha="center", va="center")

        # Walls extruded
        for w in walls:
            xs_pt, ys_pt = wall_box(w, t_pt)
            xs = xs_pt * PT_TO_M
            ys = ys_pt * PT_TO_M
            faces = extrude_polygon(xs, ys, 0.0, WALL_HEIGHT_M)
            top = faces[0]
            sides = faces[2:]
            ax.add_collection3d(Poly3DCollection([top], facecolors=WALL_TOP,
                                                  edgecolors="#3d3325", linewidths=0.4))
            ax.add_collection3d(Poly3DCollection(sides, facecolors=WALL_SIDE,
                                                  edgecolors="#3d3325", linewidths=0.3))

        # Soft barriers (parapets) at PARAPET_HEIGHT_M
        for b in barriers:
            pts = b.get("polyline_pts", [])
            if len(pts) < 2:
                continue
            for a, c in zip(pts[:-1], pts[1:]):
                ax_m = a[0] * PT_TO_M, a[1] * PT_TO_M
                cx_m = c[0] * PT_TO_M, c[1] * PT_TO_M
                dx = cx_m[0] - ax_m[0]
                dy = cx_m[1] - ax_m[1]
                length = (dx * dx + dy * dy) ** 0.5
                if length < 0.01:
                    continue
                # 3-cm thick parapet
                tk = 0.03
                nx = -dy / length * tk
                ny = dx / length * tk
                quad = np.array([
                    [ax_m[0] + nx, ax_m[1] + ny],
                    [cx_m[0] + nx, cx_m[1] + ny],
                    [cx_m[0] - nx, cx_m[1] - ny],
                    [ax_m[0] - nx, ax_m[1] - ny],
                ])
                faces = extrude_polygon(quad[:, 0], quad[:, 1],
                                        0.0, PARAPET_HEIGHT_M)
                ax.add_collection3d(Poly3DCollection(faces, facecolors=PARAPET_COLOR,
                                                      edgecolors="#5a7a8a", linewidths=0.3,
                                                      alpha=0.85))

        # Openings — draw a flat orange rectangle at floor level on the
        # wall surface, marking where consume_consensus.rb will carve a
        # doorway. This keeps the wall extrusion visually intact (the
        # .skp on disk still has full-height walls until rebuilt) while
        # making the detected door positions immediately legible.
        for op in openings:
            wall = walls_by_id.get(op.get("wall_id"))
            if not wall:
                continue
            chord = _opening_chord(op, wall, t_pt)
            if not chord:
                continue
            (sx_pt, sy_pt), (ex_pt, ey_pt) = chord
            sx, sy = sx_pt * PT_TO_M, sy_pt * PT_TO_M
            ex, ey = ex_pt * PT_TO_M, ey_pt * PT_TO_M
            # door footprint as a thin floor rectangle
            tk = t_pt * PT_TO_M
            if wall["orientation"] == "h":
                quad = np.array([[sx, sy - tk / 2], [ex, sy - tk / 2],
                                 [ex, sy + tk / 2], [sx, sy + tk / 2]])
            else:
                quad = np.array([[sx - tk / 2, sy], [sx + tk / 2, sy],
                                 [sx + tk / 2, ey], [sx - tk / 2, ey]])
            xs, ys = quad[:, 0], quad[:, 1]
            # tiny lift off floor (z=0.005) to avoid z-fighting with rooms
            faces = extrude_polygon(xs, ys, 0.005, DOOR_HEIGHT_M)
            ax.add_collection3d(Poly3DCollection(
                faces, facecolors=DOOR_COLOR,
                edgecolors=DOOR_FRAME_COLOR, linewidths=0.6, alpha=0.55))

        # View setup: tight footprint, isometric-ish camera
        all_xy = []
        for w in walls:
            xs_pt, ys_pt = wall_box(w, t_pt)
            all_xy.extend(zip(xs_pt, ys_pt))
        if all_xy:
            xs = [p[0] * PT_TO_M for p in all_xy]
            ys = [p[1] * PT_TO_M for p in all_xy]
            x_span = max(xs) - min(xs)
            y_span = max(ys) - min(ys)
            ax.set_xlim(min(xs) - 0.3, max(xs) + 0.3)
            ax.set_ylim(min(ys) - 0.3, max(ys) + 0.3)
            ax.set_zlim(0, WALL_HEIGHT_M + 0.3)
            # Real-world aspect: 1m on each axis the same drawn size
            ax.set_box_aspect((x_span, y_span, WALL_HEIGHT_M))
        ax.set_axis_off()
        # SketchUp-style isometric: elev=30, azim=-55
        ax.view_init(elev=30, azim=-55)
        try:
            ax.set_proj_type("ortho")
        except Exception:
            pass
        plt.tight_layout()
        plt.savefig(out, dpi=dpi, bbox_inches="tight",
                    facecolor=fig.get_facecolor())
        plt.close(fig)

    elif mode == "top":
        # 2D top-down with walls + rooms
        fig, ax = plt.subplots(figsize=(12, 9), dpi=dpi,
                                facecolor="#f5f3ee")
        ax.set_facecolor("#f5f3ee")
        for i, r in enumerate(rooms):
            color = ROOM_COLORS[i % len(ROOM_COLORS)]
            poly = MplPolygon([(p[0] * PT_TO_M, p[1] * PT_TO_M)
                              for p in r["polygon_pts"]],
                              closed=True, facecolor=color,
                              edgecolor="#7a6a4a", linewidth=0.6, alpha=0.8)
            ax.add_patch(poly)
            cx = np.mean([p[0] for p in r["polygon_pts"]]) * PT_TO_M
            cy = np.mean([p[1] for p in r["polygon_pts"]]) * PT_TO_M
            ax.text(cx, cy, r.get("name", r["id"]),
                    fontsize=8, ha="center", va="center", color="#2a2a2a")
        for w in walls:
            xs_pt, ys_pt = wall_box(w, t_pt)
            poly = MplPolygon(list(zip(xs_pt * PT_TO_M, ys_pt * PT_TO_M)),
                              closed=True, facecolor=WALL_TOP,
                              edgecolor="#3d3325", linewidth=0.5)
            ax.add_patch(poly)
        # openings: orange swatches over the wall they sit on
        for op in openings:
            wall = walls_by_id.get(op.get("wall_id"))
            if not wall:
                continue
            chord = _opening_chord(op, wall, t_pt)
            if not chord:
                continue
            (sx_pt, sy_pt), (ex_pt, ey_pt) = chord
            sx, sy = sx_pt * PT_TO_M, sy_pt * PT_TO_M
            ex, ey = ex_pt * PT_TO_M, ey_pt * PT_TO_M
            tk = t_pt * PT_TO_M
            if wall["orientation"] == "h":
                quad = [(sx, sy - tk / 2), (ex, sy - tk / 2),
                        (ex, sy + tk / 2), (sx, sy + tk / 2)]
            else:
                quad = [(sx - tk / 2, sy), (sx + tk / 2, sy),
                        (sx + tk / 2, ey), (sx - tk / 2, ey)]
            ax.add_patch(MplPolygon(quad, closed=True, facecolor=DOOR_COLOR,
                                    edgecolor=DOOR_FRAME_COLOR, linewidth=0.7,
                                    alpha=0.85))
        for b in barriers:
            pts = b.get("polyline_pts", [])
            if len(pts) < 2:
                continue
            xs = [p[0] * PT_TO_M for p in pts]
            ys = [p[1] * PT_TO_M for p in pts]
            ax.plot(xs, ys, color=PARAPET_COLOR, linewidth=1.2)
        ax.set_aspect("equal")
        ax.autoscale_view()
        ax.set_axis_off()
        plt.tight_layout()
        plt.savefig(out, dpi=dpi, bbox_inches="tight",
                    facecolor=fig.get_facecolor())
        plt.close(fig)

    print(f"[ok] {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("consensus", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--mode", choices=["axon", "top"], default="axon")
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--no-history", action="store_true",
                    help="Skip png_history manifest registration")
    ap.add_argument("--skp", type=Path, default=None,
                    help="Source .skp path to record in manifest source.skp")
    ap.add_argument("--pdf", type=Path, default=None,
                    help="Source PDF path to record in manifest source.pdf")
    args = ap.parse_args()
    render(args.consensus, args.out, args.mode, args.dpi)
    if not args.no_history:
        try:
            from png_history import register
        except ImportError:
            import sys
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from png_history import register
        register(
            args.out,
            kind=f"axon_{args.mode}",
            source={"consensus": args.consensus, "skp": args.skp, "pdf": args.pdf},
            generator="tools/render_axon.py",
            params={"mode": args.mode, "dpi": args.dpi},
        )
