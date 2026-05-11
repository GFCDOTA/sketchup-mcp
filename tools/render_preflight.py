"""Render preflight axonometric view from consensus_model.json.

Designed as a visual gate BEFORE consume_consensus.rb / SketchUp:
- if the preflight PNG looks wrong, fix the consensus or pipeline first
- never go to SKP on a faulty preflight

Adds on top of render_axon.py:
- room floors colored by material (wood for living/suites, ceramic for wet)
- door leaves rotated 25 deg open from hinge_corner_pt
- swing arcs (90 deg sector) on the floor at the hinge
- window frames at 1.10..2.10 m + translucent blue glass
- glazed_balcony frames at 0..2.30 m + glass
- soft_barriers as 1.10 m parapets
- companion outputs: side_by_side (PDF + axon), door_audit (top-down with
  D1..D7 labels + swing arrows), preflight_notes.md (validation checklist)

The consensus is read READ-ONLY. Geometry is rendered exactly as detected;
nothing is invented. Discrepancies vs. user intent surface in notes.md as
FAIL/WARN, NEVER as silent corrections.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Polygon as MplPolygon
from matplotlib.patches import Wedge
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

# Reuse constants from render_axon (avoids duplication, single source of truth)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_axon import PARAPET_HEIGHT_M, PT_TO_M, extrude_polygon, wall_box  # noqa: E402

# ---- material palette ---------------------------------------------------
WOOD_LIGHT = "#e8c896"
CERAMIC_LIGHT = "#e8e2d4"
WALL_TOP = "#9a9080"
WALL_SIDE = "#bcb4a4"
WALL_EDGE = "#3d3325"
DOOR_LEAF = "#c89060"
DOOR_LEAF_EDGE = "#7a4a20"
SWING_ARC = "#f97316"
GLASS_FILL = (0.63, 0.78, 0.86, 0.45)
GLASS_FRAME = "#3a3a3a"
PARAPET_COLOR = "#a8c8d8"
ROOM_LABEL_COLOR = "#2a2a2a"

WOOD_ROOMS = {"SALA DE ESTAR", "SALA DE JANTAR", "SUITE 01", "SUITE 02"}

DOOR_HEIGHT_M = 1.05      # lowered from 2.10 to 1.05 — preflight axon
                          # uses doll-house style (wall_height_axon=1.0m)
                          # so doors don't dominate the view
DOOR_LEAF_THICK_M = 0.04
WINDOW_BOTTOM_M = 0.55    # lowered to fit doll-house wall_height_axon=1.0m
WINDOW_TOP_M = 1.00
GLAZED_BALCONY_TOP_M = 1.00
DOOR_OPEN_DEG = 30        # leaf rotated 30 deg open from closed position
WALL_HEIGHT_AXON_M = 1.0  # doll-house style — short walls so we can see in


# ---- helpers ------------------------------------------------------------

def floor_color(name: str | None) -> str:
    n = (name or "").upper().strip()
    return WOOD_LIGHT if n in WOOD_ROOMS else CERAMIC_LIGHT


def opening_swing_vectors(opening: dict, wall: dict) -> tuple[np.ndarray, np.ndarray, tuple[float, float]] | None:
    """Return (along_wall_unit, into_room_unit, hinge_xy_pt) for an opening.

    along_wall_unit: unit vector along the wall axis, pointing AWAY from
        the hinge along the chord (closed-leaf direction).
    into_room_unit: unit vector perpendicular to the wall, pointing into
        the room where the door opens (same side as the arc bbox).
    Returns None if hinge_corner_pt or arc_bbox missing (passages/gaps).
    """
    hinge = opening.get("hinge_corner_pt")
    bbox = opening.get("arc_bbox_pts")
    if not hinge or not bbox:
        return None
    hx, hy = float(hinge[0]), float(hinge[1])
    cx = (float(bbox[0]) + float(bbox[2])) / 2.0
    cy = (float(bbox[1]) + float(bbox[3])) / 2.0
    dx, dy = cx - hx, cy - hy
    if wall["orientation"] == "h":
        along = np.array([np.sign(dx) or 1.0, 0.0])
        into = np.array([0.0, np.sign(dy) or 1.0])
    else:
        along = np.array([0.0, np.sign(dy) or 1.0])
        into = np.array([np.sign(dx) or 1.0, 0.0])
    return along, into, (hx, hy)


def door_leaf_rect_pts(opening: dict, wall: dict) -> tuple[np.ndarray, np.ndarray] | None:
    """Compute the 4 footprint corners of a door leaf rotated DOOR_OPEN_DEG
    open from closed. Returns (xs_pt, ys_pt) of the 4 corners + hinge pt.
    """
    sv = opening_swing_vectors(opening, wall)
    if sv is None:
        return None
    along, into, (hx, hy) = sv
    width = float(opening.get("opening_width_pts") or 30.0)
    rad = math.radians(DOOR_OPEN_DEG)
    # leaf direction at OPEN angle: cos*along + sin*into
    ldir = math.cos(rad) * along + math.sin(rad) * into
    # leaf thickness perpendicular: into rotated 90 deg from ldir
    perp = np.array([-ldir[1], ldir[0]])
    thick_pt = DOOR_LEAF_THICK_M / PT_TO_M
    tip = np.array([hx, hy]) + ldir * width
    p1 = np.array([hx, hy]) - perp * (thick_pt / 2)
    p2 = tip - perp * (thick_pt / 2)
    p3 = tip + perp * (thick_pt / 2)
    p4 = np.array([hx, hy]) + perp * (thick_pt / 2)
    corners = np.array([p1, p2, p3, p4])
    return corners[:, 0], corners[:, 1]


def swing_arc_3d(opening: dict, wall: dict, n_seg: int = 20) -> list[np.ndarray]:
    """Return a triangle-fan of the 90-deg swing wedge at floor level.

    Sector center = hinge, radius = opening width, sweeps from along_wall
    (closed) to into_room (90 deg open).
    """
    sv = opening_swing_vectors(opening, wall)
    if sv is None:
        return []
    along, into, (hx, hy) = sv
    width_pt = float(opening.get("opening_width_pts") or 30.0)
    base_angle = math.atan2(along[1], along[0])
    # Determine rotation direction (CCW or CW) based on cross product
    cross = along[0] * into[1] - along[1] * into[0]
    sweep = math.pi / 2 if cross > 0 else -math.pi / 2
    pts = []
    for i in range(n_seg + 1):
        t = i / n_seg
        a = base_angle + sweep * t
        x = hx + width_pt * math.cos(a)
        y = hy + width_pt * math.sin(a)
        pts.append((x, y))
    # Triangle fan from hinge
    fans = []
    for i in range(n_seg):
        x0, y0 = pts[i]
        x1, y1 = pts[i + 1]
        tri = np.array([
            [hx * PT_TO_M, hy * PT_TO_M, 0.005],
            [x0 * PT_TO_M, y0 * PT_TO_M, 0.005],
            [x1 * PT_TO_M, y1 * PT_TO_M, 0.005],
        ])
        fans.append(tri)
    return fans


def opening_window_quad(opening: dict, wall: dict, t_pt: float) -> np.ndarray | None:
    """Compute the 4 footprint corners of a window/glazed_balcony pane.

    Centered on opening.center, length = width along wall, depth = wall
    thickness, used to draw glass + frame.
    """
    center = opening.get("center")
    if not center:
        return None
    cx, cy = float(center[0]), float(center[1])
    width = float(opening.get("opening_width_pts") or 30.0)
    if wall["orientation"] == "h":
        return np.array([
            [cx - width / 2, cy - t_pt / 2],
            [cx + width / 2, cy - t_pt / 2],
            [cx + width / 2, cy + t_pt / 2],
            [cx - width / 2, cy + t_pt / 2],
        ])
    return np.array([
        [cx - t_pt / 2, cy - width / 2],
        [cx + t_pt / 2, cy - width / 2],
        [cx + t_pt / 2, cy + width / 2],
        [cx - t_pt / 2, cy + width / 2],
    ])


# ---- main render --------------------------------------------------------

def render_axon(consensus: dict, out: Path, dpi: int = 200) -> None:
    walls = consensus["walls"]
    rooms = consensus.get("rooms", [])
    barriers = consensus.get("soft_barriers", [])
    openings = consensus.get("openings", [])
    t_pt = consensus["wall_thickness_pts"]
    walls_by_id = {w["id"]: w for w in walls}

    fig = plt.figure(figsize=(14, 10), dpi=dpi)
    ax = fig.add_subplot(111, projection="3d")
    ax.set_facecolor("#f5f3ee")
    fig.patch.set_facecolor("#f5f3ee")

    # 1) Floors per room, colored by material
    for r in rooms:
        poly = [(p[0] * PT_TO_M, p[1] * PT_TO_M, 0.0) for p in r.get("polygon_pts", [])]
        if len(poly) < 3:
            continue
        color = floor_color(r.get("name"))
        ax.add_collection3d(Poly3DCollection(
            [poly], facecolors=color, edgecolors="#7a6a4a",
            linewidths=0.4, alpha=0.95))
        cx_m = sum(p[0] for p in poly) / len(poly)
        cy_m = sum(p[1] for p in poly) / len(poly)
        ax.text(cx_m, cy_m, 0.05, r.get("name", r["id"]),
                fontsize=6, color=ROOM_LABEL_COLOR,
                ha="center", va="center", zorder=10)

    # 2) Walls extruded full height
    for w in walls:
        xs_pt, ys_pt = wall_box(w, t_pt)
        xs = xs_pt * PT_TO_M
        ys = ys_pt * PT_TO_M
        faces = extrude_polygon(xs, ys, 0.0, WALL_HEIGHT_AXON_M)
        top = faces[0]
        sides = faces[2:]
        ax.add_collection3d(Poly3DCollection(
            [top], facecolors=WALL_TOP, edgecolors=WALL_EDGE, linewidths=0.4))
        ax.add_collection3d(Poly3DCollection(
            sides, facecolors=WALL_SIDE, edgecolors=WALL_EDGE, linewidths=0.3))

    # 3) Soft barriers (parapets)
    for b in barriers:
        pts = b.get("polyline_pts", [])
        if len(pts) < 2:
            continue
        for a, c in zip(pts[:-1], pts[1:]):
            ax_m = (a[0] * PT_TO_M, a[1] * PT_TO_M)
            cx_m = (c[0] * PT_TO_M, c[1] * PT_TO_M)
            dxm = cx_m[0] - ax_m[0]
            dym = cx_m[1] - ax_m[1]
            length = math.hypot(dxm, dym)
            if length < 0.01:
                continue
            tk = 0.03
            nx = -dym / length * tk
            ny = dxm / length * tk
            quad = np.array([
                [ax_m[0] + nx, ax_m[1] + ny],
                [cx_m[0] + nx, cx_m[1] + ny],
                [cx_m[0] - nx, cx_m[1] - ny],
                [ax_m[0] - nx, ax_m[1] - ny],
            ])
            faces = extrude_polygon(quad[:, 0], quad[:, 1], 0.0, PARAPET_HEIGHT_M)
            ax.add_collection3d(Poly3DCollection(
                faces, facecolors=PARAPET_COLOR,
                edgecolors="#5a7a8a", linewidths=0.3, alpha=0.85))

    # 4) Openings: doors get leaf + swing arc, windows get glass pane
    for op in openings:
        wall = walls_by_id.get(op.get("wall_id"))
        if not wall:
            continue
        kind = (op.get("kind_v5") or op.get("kind") or "").lower()
        if kind in ("interior_door",):
            leaf = door_leaf_rect_pts(op, wall)
            if leaf is not None:
                lxs_pt, lys_pt = leaf
                lxs = lxs_pt * PT_TO_M
                lys = lys_pt * PT_TO_M
                leaf_faces = extrude_polygon(lxs, lys, 0.005, DOOR_HEIGHT_M)
                ax.add_collection3d(Poly3DCollection(
                    leaf_faces, facecolors=DOOR_LEAF,
                    edgecolors=DOOR_LEAF_EDGE, linewidths=0.5, alpha=0.95))
            for tri in swing_arc_3d(op, wall):
                ax.add_collection3d(Poly3DCollection(
                    [tri], facecolors=SWING_ARC,
                    edgecolors="none", alpha=0.18))
        elif kind in ("window", "glazed_balcony"):
            quad = opening_window_quad(op, wall, t_pt)
            if quad is None:
                continue
            xs = quad[:, 0] * PT_TO_M
            ys = quad[:, 1] * PT_TO_M
            top_z = GLAZED_BALCONY_TOP_M if kind == "glazed_balcony" else WINDOW_TOP_M
            bot_z = 0.0 if kind == "glazed_balcony" else WINDOW_BOTTOM_M
            # Glass pane (translucent)
            glass = extrude_polygon(xs, ys, bot_z, top_z)
            ax.add_collection3d(Poly3DCollection(
                glass, facecolors=[GLASS_FILL],
                edgecolors=GLASS_FRAME, linewidths=0.6, alpha=0.55))
        elif kind in ("interior_passage",):
            # Just mark with a thin floor strip (no leaf)
            quad = opening_window_quad(op, wall, t_pt)
            if quad is None:
                continue
            xs = quad[:, 0] * PT_TO_M
            ys = quad[:, 1] * PT_TO_M
            faces = extrude_polygon(xs, ys, 0.005, 0.05)
            ax.add_collection3d(Poly3DCollection(
                faces, facecolors="#bbbbbb",
                edgecolors="#666666", linewidths=0.3, alpha=0.7))

    # 5) View setup — isometric
    all_xy_m = []
    for w in walls:
        xs_pt, ys_pt = wall_box(w, t_pt)
        all_xy_m.extend(zip(xs_pt * PT_TO_M, ys_pt * PT_TO_M))
    if all_xy_m:
        xs = [p[0] for p in all_xy_m]
        ys = [p[1] for p in all_xy_m]
        x_span = max(xs) - min(xs)
        y_span = max(ys) - min(ys)
        ax.set_xlim(min(xs) - 0.3, max(xs) + 0.3)
        ax.set_ylim(min(ys) - 0.3, max(ys) + 0.3)
        ax.set_zlim(0, WALL_HEIGHT_AXON_M + 0.3)
        # vertical exaggeration: stretch z to make floor materials and door
        # leaves readable in the doll-house view (real 1m -> drawn ~3m)
        ax.set_box_aspect((x_span, y_span, WALL_HEIGHT_AXON_M * 3))
    ax.set_axis_off()
    ax.view_init(elev=52, azim=-58)
    try:
        ax.set_proj_type("ortho")
    except Exception:
        pass
    plt.tight_layout()
    plt.savefig(out, dpi=dpi, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"[ok] axon -> {out}")


# ---- door audit (top-down with D-labels) -------------------------------

def map_doors_to_d_ids(openings: list[dict]) -> dict[str, dict]:
    """Heuristic mapping of detected openings to D1..D7 conventional IDs.

    Returns {D1: opening_or_None, D2: ..., ...}. None means MISSING.
    Uses greedy assignment: each opening claims at most ONE D-id, prioritizing
    the D-id whose room_a is the smallest cardinality match (banho > suite >
    sala). Prevents D4 and D7 sharing the same opening.
    """
    DOOR_KINDS = {"interior_door", "interior_passage"}
    used: set[str] = set()  # opening ids already claimed
    out: dict[str, dict | None] = {d: None for d in
                                   ["D1", "D2", "D3", "D4", "D5", "D6", "D7"]}

    def cand_for(rname: str, exclude_other: set | None = None) -> list[dict]:
        c = []
        for op in openings:
            if op.get("id") in used:
                continue
            kind = (op.get("kind_v5") or "").lower()
            if kind not in DOOR_KINDS:
                continue
            rooms = {op.get("room_left_name"), op.get("room_right_name")}
            if rname not in rooms:
                continue
            if exclude_other and (rooms - {rname}) & exclude_other:
                continue
            c.append(op)
        return sorted(c, key=lambda o: -(o.get("confidence") or 0.0))

    # D1 = principal entry. Not detected: all openings classified are
    # interior. The PDF planta-padrão draws the front door's arc inside
    # the area comum (not in the apt's planta region), so the extractor
    # leaves it MISSING by design.
    out["D1"] = None

    # D5 BANHO 01: take the highest-conf door that touches BANHO 01.
    cands = cand_for("BANHO 01")
    if cands:
        out["D5"] = cands[0]
        used.add(cands[0].get("id"))

    # D3 LAVABO: highest-conf door touching LAVABO.
    cands = cand_for("LAVABO")
    if cands:
        out["D3"] = cands[0]
        used.add(cands[0].get("id"))

    # D7 BANHO 02: highest-conf door touching BANHO 02 (excluding LAVABO
    # so we don't claim the LAVABO door again — already taken if any).
    cands = cand_for("BANHO 02", exclude_other={"LAVABO"})
    if cands:
        out["D7"] = cands[0]
        used.add(cands[0].get("id"))

    # D4 SUITE 01: door touching SUITE 01, excluding BANHO 01 / 02 / SUITE 02.
    cands = cand_for("SUITE 01",
                     exclude_other={"BANHO 01", "BANHO 02", "SUITE 02"})
    if cands:
        out["D4"] = cands[0]
        used.add(cands[0].get("id"))

    # D6 SUITE 02: door touching SUITE 02, excluding BANHO 02 / SUITE 01.
    cands = cand_for("SUITE 02",
                     exclude_other={"BANHO 02", "SUITE 01"})
    if cands:
        out["D6"] = cands[0]
        used.add(cands[0].get("id"))

    # D2 A.S.: door/passage touching A.S.
    cands = cand_for("A.S.")
    if cands:
        out["D2"] = cands[0]
        used.add(cands[0].get("id"))

    return out


def render_door_audit(consensus: dict, out: Path, dpi: int = 200) -> dict:
    """Top-down view with each opening numbered D1..D7 + swing arrow.

    Returns the d_map for downstream notes.md generation.
    """
    walls = consensus["walls"]
    rooms = consensus.get("rooms", [])
    openings = consensus.get("openings", [])
    barriers = consensus.get("soft_barriers", [])
    t_pt = consensus["wall_thickness_pts"]
    walls_by_id = {w["id"]: w for w in walls}

    d_map = map_doors_to_d_ids(openings)

    fig, ax = plt.subplots(figsize=(14, 10), dpi=dpi, facecolor="#f5f3ee")
    ax.set_facecolor("#f5f3ee")

    # Rooms
    for r in rooms:
        pts = [(p[0] * PT_TO_M, p[1] * PT_TO_M) for p in r.get("polygon_pts", [])]
        if len(pts) < 3:
            continue
        ax.add_patch(MplPolygon(
            pts, closed=True, facecolor=floor_color(r.get("name")),
            edgecolor="#7a6a4a", linewidth=0.6, alpha=0.85))
        cx = np.mean([p[0] for p in pts])
        cy = np.mean([p[1] for p in pts])
        ax.text(cx, cy, r.get("name", r["id"]),
                fontsize=8, ha="center", va="center", color=ROOM_LABEL_COLOR)

    # Walls
    for w in walls:
        xs_pt, ys_pt = wall_box(w, t_pt)
        ax.add_patch(MplPolygon(
            list(zip(xs_pt * PT_TO_M, ys_pt * PT_TO_M)),
            closed=True, facecolor=WALL_TOP,
            edgecolor=WALL_EDGE, linewidth=0.5))

    # Soft barriers
    for b in barriers:
        pts = b.get("polyline_pts", [])
        if len(pts) < 2:
            continue
        xs = [p[0] * PT_TO_M for p in pts]
        ys = [p[1] * PT_TO_M for p in pts]
        ax.plot(xs, ys, color=PARAPET_COLOR, linewidth=1.6, alpha=0.85)

    # Openings — color by kind
    kind_color = {
        "interior_door": "#d97706",
        "interior_passage": "#9ca3af",
        "window": "#0ea5e9",
        "glazed_balcony": "#06b6d4",
    }
    op_to_d = {}
    for d, op in d_map.items():
        if op is not None:
            op_to_d[op.get("id")] = d

    for op in openings:
        wall = walls_by_id.get(op.get("wall_id"))
        if not wall:
            continue
        kind = (op.get("kind_v5") or "").lower()
        col = kind_color.get(kind, "#888")
        quad = opening_window_quad(op, wall, t_pt)
        if quad is None:
            continue
        ax.add_patch(MplPolygon(
            list(zip(quad[:, 0] * PT_TO_M, quad[:, 1] * PT_TO_M)),
            closed=True, facecolor=col, edgecolor="#444",
            linewidth=0.6, alpha=0.85))
        # Draw swing arrow for doors
        if kind == "interior_door":
            sv = opening_swing_vectors(op, wall)
            if sv is not None:
                along, into, (hx, hy) = sv
                width_pt = float(op.get("opening_width_pts") or 30.0)
                # arrow from hinge into the room (perpendicular)
                hxm = hx * PT_TO_M
                hym = hy * PT_TO_M
                tipxm = hxm + into[0] * width_pt * 0.7 * PT_TO_M
                tipym = hym + into[1] * width_pt * 0.7 * PT_TO_M
                ax.annotate(
                    "", xy=(tipxm, tipym), xytext=(hxm, hym),
                    arrowprops=dict(arrowstyle="->", color="#7c2d12",
                                    lw=1.4, alpha=0.85), zorder=20)
                # Draw quarter-circle swing arc
                base_angle = math.degrees(math.atan2(along[1], along[0]))
                cross = along[0] * into[1] - along[1] * into[0]
                t1, t2 = (base_angle, base_angle + 90) if cross > 0 else (base_angle - 90, base_angle)
                ax.add_patch(Wedge(
                    (hxm, hym), width_pt * PT_TO_M, t1, t2,
                    facecolor=SWING_ARC, edgecolor="none", alpha=0.18, zorder=15))

        # Label with D-id if mapped
        d_label = op_to_d.get(op.get("id"))
        if d_label:
            cx = float(op.get("center", [0, 0])[0]) * PT_TO_M
            cy = float(op.get("center", [0, 0])[1]) * PT_TO_M
            ax.text(cx, cy + 0.25, d_label,
                    fontsize=10, fontweight="bold", color="#7c2d12",
                    ha="center", va="bottom",
                    bbox=dict(boxstyle="round,pad=0.2", fc="white",
                              ec="#7c2d12", lw=0.8, alpha=0.9), zorder=25)

    ax.set_aspect("equal")
    ax.autoscale_view()
    ax.set_axis_off()
    ax.set_title("Door audit — D1..D7 mapping (top-down) — "
                 f"{sum(1 for v in d_map.values() if v)}/7 detected",
                 fontsize=11, color="#333", pad=8)

    # Legend
    handles = []
    labels = []
    for k, c in kind_color.items():
        handles.append(plt.Rectangle((0, 0), 1, 1, fc=c, ec="#444", lw=0.6))
        labels.append(k.replace("_", " "))
    ax.legend(handles, labels, loc="upper left", fontsize=8,
              framealpha=0.85, edgecolor="#888")

    plt.tight_layout()
    plt.savefig(out, dpi=dpi, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"[ok] door_audit -> {out}")
    return d_map


# ---- side-by-side (PDF + axon) -----------------------------------------

def render_side_by_side(pdf_path: Path, axon_path: Path, out: Path,
                        dpi: int = 150) -> None:
    """PDF page 1 (left) + axon (right) at 1:1 visual scale."""
    import pypdfium2 as pdfium
    from PIL import Image

    pdf = pdfium.PdfDocument(str(pdf_path))
    page = pdf[0]
    pdf_img = page.render(scale=2).to_pil()
    pdf.close()

    axon_img = Image.open(axon_path)

    # Aspect: pdf_img + axon_img side by side, normalized to same height
    target_h = 1200
    pdf_aspect = pdf_img.width / pdf_img.height
    axon_aspect = axon_img.width / axon_img.height
    pdf_w = int(target_h * pdf_aspect)
    axon_w = int(target_h * axon_aspect)
    pdf_resized = pdf_img.resize((pdf_w, target_h), Image.LANCZOS)
    axon_resized = axon_img.resize((axon_w, target_h), Image.LANCZOS)

    canvas = Image.new("RGB", (pdf_w + axon_w + 30, target_h + 60),
                       (245, 243, 238))
    canvas.paste(pdf_resized, (10, 50))
    canvas.paste(axon_resized, (pdf_w + 20, 50))

    # Add titles via PIL ImageDraw
    from PIL import ImageDraw
    try:
        from PIL import ImageFont
        font = ImageFont.truetype("arial.ttf", 18)
    except Exception:
        font = None
    draw = ImageDraw.Draw(canvas)
    draw.text((10, 10), "PDF original (planta 74,93 m²)", fill=(40, 40, 40), font=font)
    draw.text((pdf_w + 30, 10), "Preflight axon (consensus)",
              fill=(40, 40, 40), font=font)

    canvas.save(out, "PNG")
    print(f"[ok] side_by_side -> {out}")


# ---- preflight notes ----------------------------------------------------

def write_notes(consensus: dict, d_map: dict, pdf_path: Path,
                consensus_path: Path, out: Path) -> None:
    """Write skp_preflight_notes.md with the user's checklist + verdict."""
    rooms_by_name = {r.get("name"): r for r in consensus.get("rooms", [])}
    openings = consensus.get("openings", [])

    def rooms_of(op):
        return {op.get("room_left_name"), op.get("room_right_name")}

    def banho02_doors():
        return [o for o in openings
                if "BANHO 02" in rooms_of(o)
                and (o.get("kind_v5") or "").lower() == "interior_door"]

    def suite02_doors():
        return [o for o in openings
                if "SUITE 02" in rooms_of(o)
                and (o.get("kind_v5") or "").lower() in ("interior_door", "interior_passage")]

    def lavabo_doors():
        return [o for o in openings if "LAVABO" in rooms_of(o)]

    def hinge_inside_room(op, room_name):
        room = rooms_by_name.get(room_name)
        if not room or not op.get("hinge_corner_pt"):
            return None
        try:
            from shapely.geometry import Point
            from shapely.geometry import Polygon as ShPoly
            poly = ShPoly(room["polygon_pts"])
            return poly.contains(Point(op["hinge_corner_pt"][0],
                                       op["hinge_corner_pt"][1]))
        except Exception:
            return None

    def opens_into(op, room_name):
        """True if hinge is on/near room_name boundary AND arc bbox center
        lies inside room_name polygon."""
        room = rooms_by_name.get(room_name)
        bbox = op.get("arc_bbox_pts")
        if not room or not bbox:
            return None
        try:
            from shapely.geometry import Point
            from shapely.geometry import Polygon as ShPoly
            poly = ShPoly(room["polygon_pts"])
            cx = (bbox[0] + bbox[2]) / 2
            cy = (bbox[1] + bbox[3]) / 2
            return poly.contains(Point(cx, cy))
        except Exception:
            return None

    lines = []
    lines.append("# Preflight notes — apto 74,93 m²")
    lines.append("")
    lines.append(f"- **PDF**: `{pdf_path.name}`")
    lines.append(f"- **Consensus**: `{consensus_path}`")
    lines.append(f"- **Walls**: {len(consensus.get('walls', []))}")
    lines.append(f"- **Rooms**: {len(consensus.get('rooms', []))}")
    lines.append(f"- **Openings**: {len(openings)}")
    lines.append("")
    lines.append("## D1..D7 mapping")
    lines.append("")
    lines.append("| ID | Detected? | Opening | Wall | Rooms | Hinge | Confidence |")
    lines.append("|----|-----------|---------|------|-------|-------|------------|")
    for d, op in d_map.items():
        if op is None:
            lines.append(f"| {d} | ❌ MISSING | — | — | — | — | — |")
        else:
            cf = op.get("confidence")
            cstr = f"{cf:.2f}" if cf else "n/a"
            lines.append(
                f"| {d} | ✅ | {op.get('id')} | {op.get('wall_id')} | "
                f"{op.get('room_left_name', '?')} ↔ {op.get('room_right_name', '?')} | "
                f"{op.get('hinge_side', 'n/a')} | {cstr} |"
            )
    lines.append("")
    lines.append("## Validation checklist (user criterion)")
    lines.append("")

    b02 = banho02_doors()
    s02 = suite02_doors()
    lav = lavabo_doors()

    def yn(b):
        return "✅ PASS" if b else ("❌ FAIL" if b is False else "⚠️ N/A")

    # 1. Banho 02 tem porta?
    lines.append(f"- **Banho 02 tem porta?** {yn(len(b02) > 0)} "
                 f"({len(b02)} interior_door(s) detectada(s))")

    # 2. Lateral esquerda/oeste do Banho 02?
    if b02 and "BANHO 02" in rooms_by_name:
        b02_room = rooms_by_name["BANHO 02"]
        b02_centroid = b02_room.get("centroid", [0, 0])
        west_doors = [o for o in b02 if o.get("center", [0, 0])[0] < b02_centroid[0]
                      and consensus["walls"][[w["id"] for w in consensus["walls"]].index(o["wall_id"])]["orientation"] == "v"]
        lines.append(f"- **Porta D7 na lateral oeste (parede vertical, x < centroid)?** "
                     f"{yn(len(west_doors) > 0)} "
                     f"({len(west_doors)} de {len(b02)} portas; "
                     f"BANHO 02 centroid x={b02_centroid[0]:.1f})")
    else:
        lines.append("- **Porta D7 na lateral oeste?** ⚠️ N/A — sem porta detectada no Banho 02")

    # 3. Mais para cima do Banho 02?
    if b02 and "BANHO 02" in rooms_by_name:
        b02_centroid = rooms_by_name["BANHO 02"].get("centroid", [0, 0])
        upper_doors = [o for o in b02 if o.get("center", [0, 0])[1] > b02_centroid[1]]
        lines.append(f"- **Porta D7 mais pra cima (y > centroid)?** "
                     f"{yn(len(upper_doors) > 0)} "
                     f"({len(upper_doors)} de {len(b02)})")

    # 4. Abre pra dentro do Banho 02?
    if b02:
        opens_in_b02 = [o for o in b02 if opens_into(o, "BANHO 02")]
        lines.append(f"- **Banho 02 abre pra dentro?** {yn(len(opens_in_b02) > 0)} "
                     f"({len(opens_in_b02)}/{len(b02)})")

    # 5. Vão real no Banho 02?
    if b02:
        # Vão real = wall_id válido + opening_width_pts > 0
        lines.append(f"- **Vão real no Banho 02?** "
                     f"{yn(all(o.get('wall_id') and o.get('opening_width_pts', 0) > 10 for o in b02))} "
                     f"(wall_id + width_pts > 10 em todas)")

    # 6. Lavabo abre pra dentro?
    if lav:
        lav_doors = [o for o in lav if (o.get('kind_v5') or '').lower() == 'interior_door']
        opens_in_lav = [o for o in lav_doors if opens_into(o, "LAVABO")]
        lines.append(f"- **Lavabo abre pra dentro?** "
                     f"{yn(len(opens_in_lav) > 0)} "
                     f"({len(opens_in_lav)}/{len(lav_doors)})")
    else:
        lines.append("- **Lavabo abre pra dentro?** ⚠️ N/A — sem porta no LAVABO")

    # 7. Suíte 02 só uma porta?
    lines.append(f"- **Suíte 02 tem só 1 porta de entrada?** "
                 f"{yn(len(s02) == 1)} ({len(s02)} doors+passages)")

    # 8. Parede fechada atrás de porta?
    closed_walls = [op for op in openings
                    if (op.get("kind_v5") or "").lower() == "interior_door"
                    and (not op.get("wall_id") or op.get("opening_width_pts", 0) < 10)]
    lines.append(f"- **Parede fechada atrás de porta?** "
                 f"{yn(len(closed_walls) == 0)} "
                 f"({len(closed_walls)} portas com vão < 10pt ou sem wall)")

    # 9. Porta inventada?
    invented = [op for op in openings
                if op.get("geometry_origin") not in ("svg_arc", "wall_gap")]
    lines.append(f"- **Sem porta inventada?** {yn(len(invented) == 0)} "
                 f"({len(invented)} openings sem geometry_origin oficial)")

    # 10. Texto bugado?
    names = [r.get("name", "") for r in consensus.get("rooms", [])]
    dups = [n for n in set(names) if names.count(n) > 1]
    lines.append(f"- **Sem texto duplicado nos rótulos?** "
                 f"{yn(len(dups) == 0)} (duplicados: {dups})")

    # Verdict
    lines.append("")
    lines.append("## Verdict")
    lines.append("")
    missing_d = [d for d, v in d_map.items() if v is None]
    if missing_d:
        lines.append(f"⚠️ **PARTIAL** — D-ids faltando: {', '.join(missing_d)}")
        lines.append("")
        lines.append("**Causa provável**: o pipeline V7 só detecta portas com arcos de "
                     "porta visíveis no PDF (svg_arc) ou gaps colineares (wall_gap). "
                     "A porta principal D1 — entrada do apto pela área comum — fica em "
                     "parede de fronteira que não desenha arco no PDF da planta-padrão "
                     "(é desenhada apenas no projeto executivo). É um gap esperado e não "
                     "um bug do extractor.")
    else:
        lines.append("✅ **OK** — todas as D-ids mapeadas. Render e consensus alinhados; "
                     "liberado para `consume_consensus.rb`.")

    lines.append("")
    lines.append("## Detalhes por opening detectada")
    lines.append("")
    lines.append("| ID | kind_v5 | rooms | hinge | conf | decision |")
    lines.append("|----|---------|-------|-------|------|----------|")
    for op in openings:
        cf = op.get("confidence")
        cstr = f"{cf:.2f}" if cf is not None else "n/a"
        lines.append(
            f"| {op.get('id')} | {op.get('kind_v5')} | "
            f"{op.get('room_left_name', '?')} ↔ {op.get('room_right_name', '?')} | "
            f"{op.get('hinge_side', 'n/a')} | {cstr} | "
            f"{op.get('decision', 'n/a')} |"
        )

    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"[ok] notes -> {out}")


# ---- CLI ---------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("consensus", type=Path)
    ap.add_argument("--pdf", type=Path, required=True,
                    help="Source PDF (for side-by-side render)")
    ap.add_argument("--out-fidelity", type=Path, required=True)
    ap.add_argument("--out-side-by-side", type=Path, default=None)
    ap.add_argument("--out-door-audit", type=Path, default=None)
    ap.add_argument("--out-notes", type=Path, default=None)
    ap.add_argument("--dpi", type=int, default=200)
    args = ap.parse_args()

    consensus = json.loads(args.consensus.read_text(encoding="utf-8"))

    args.out_fidelity.parent.mkdir(parents=True, exist_ok=True)
    render_axon(consensus, args.out_fidelity, dpi=args.dpi)

    d_map = None
    if args.out_door_audit:
        d_map = render_door_audit(consensus, args.out_door_audit, dpi=args.dpi)

    if args.out_side_by_side:
        render_side_by_side(args.pdf, args.out_fidelity, args.out_side_by_side)

    if args.out_notes and d_map is not None:
        write_notes(consensus, d_map, args.pdf, args.consensus, args.out_notes)


if __name__ == "__main__":
    main()
