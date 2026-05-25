"""Render 4 isolated layer top-views from a consensus + _shell_polygon.json.

Visual debugging tool for the plan_shell exporter. The user can ask
"which layer is causing this blob?" and get a clean answer without
booting SketchUp.

Layers:
  1. Wall shell only — the union'd plan-shell polygon
  2. Floors only — every room polygon as a filled face
  3. Soft barriers only — each consensus.soft_barriers polyline drawn
     as a thin sweep (3.8 cm thickness ≈ same as the SU exporter)
  4. All combined — wall + floors + soft barriers
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
from matplotlib.path import Path as MplPath

# Same RGB triplets used by the Ruby exporter, scaled to 0-1.
WALL_RGB    = (78 / 255,  78 / 255,  78 / 255)
PARAPET_RGB = (130 / 255, 135 / 255, 140 / 255)
ROOM_PALETTE = [
    (253/255, 226/255, 192/255), (200/255, 230/255, 201/255),
    (187/255, 222/255, 251/255), (248/255, 187/255, 208/255),
    (220/255, 237/255, 200/255), (255/255, 224/255, 178/255),
    (209/255, 196/255, 233/255), (179/255, 229/255, 252/255),
    (255/255, 249/255, 196/255), (245/255, 224/255, 208/255),
    (207/255, 216/255, 220/255),
]

# Same default the Ruby exporter uses (SU inches converted to PDF pts
# at the calibrated scale: 1.5 in × (1/PT_TO_IN) ≈ 1.08 pt). The
# absolute number is intentionally tiny — we want the strip to read
# as a strip, not a slab.
PT_TO_M = 0.19 / 5.4
PT_TO_IN = PT_TO_M * 39.3700787402
SOFT_BARRIER_THICKNESS_IN = 1.5
SOFT_BARRIER_THICKNESS_PT = SOFT_BARRIER_THICKNESS_IN / PT_TO_IN


def draw_shell(ax, shell_payload: dict, color=WALL_RGB) -> None:
    polygons = shell_payload.get("polygons", [])
    for piece in polygons:
        outer = piece["outer"]
        holes = piece.get("holes", [])
        if not outer:
            continue
        verts = list(outer) + [outer[0]]
        codes = [MplPath.MOVETO] + [MplPath.LINETO] * (len(outer) - 1) \
            + [MplPath.CLOSEPOLY]
        for hole in holes:
            if not hole:
                continue
            verts += list(hole) + [hole[0]]
            codes += [MplPath.MOVETO] + [MplPath.LINETO] * (len(hole) - 1) \
                + [MplPath.CLOSEPOLY]
        path = MplPath(verts, codes)
        ax.add_patch(mpatches.PathPatch(
            path, facecolor=color, edgecolor=(0.05, 0.05, 0.05),
            linewidth=0.6,
        ))


def draw_floors(ax, consensus: dict) -> None:
    rooms = consensus.get("rooms", [])
    for i, room in enumerate(rooms):
        pts = room.get("polygon_pts") or []
        if len(pts) < 3:
            continue
        # Dedupe consecutive duplicates, matching the Ruby exporter.
        deduped = [pts[0]]
        for p in pts[1:]:
            if p != deduped[-1]:
                deduped.append(p)
        if len(deduped) < 3:
            continue
        color = ROOM_PALETTE[i % len(ROOM_PALETTE)]
        ax.add_patch(mpatches.Polygon(
            deduped, closed=True,
            facecolor=color, edgecolor=(0.2, 0.2, 0.2),
            linewidth=0.3,
        ))


def draw_soft_barriers(ax, consensus: dict, color=PARAPET_RGB) -> None:
    """Render each soft barrier the way the fixed Ruby exporter does:
    per-segment thin slab perpendicular to the polyline direction.
    """
    barriers = consensus.get("soft_barriers", []) or []
    half_t = SOFT_BARRIER_THICKNESS_PT / 2.0
    for b in barriers:
        pts = b.get("polyline_pts") or b.get("polyline") or []
        for a, c in zip(pts[:-1], pts[1:]):
            if a == c:
                continue
            dx = c[0] - a[0]
            dy = c[1] - a[1]
            length = math.hypot(dx, dy)
            if length < 0.01:
                continue
            nx = -dy / length * half_t
            ny =  dx / length * half_t
            quad = [
                (a[0] + nx, a[1] + ny),
                (c[0] + nx, c[1] + ny),
                (c[0] - nx, c[1] - ny),
                (a[0] - nx, a[1] - ny),
            ]
            ax.add_patch(mpatches.Polygon(
                quad, closed=True,
                facecolor=color, edgecolor=(0.1, 0.1, 0.1),
                linewidth=0.5,
            ))


def main(consensus_path: Path, shell_json: Path, out_png: Path) -> None:
    consensus = json.loads(consensus_path.read_text(encoding="utf-8"))
    shell_payload = json.loads(shell_json.read_text(encoding="utf-8"))

    fig, axes = plt.subplots(2, 2, figsize=(16, 12), dpi=150)
    fig.patch.set_facecolor("white")

    for ax in axes.flat:
        ax.set_facecolor("white")
        ax.set_aspect("equal")
        ax.set_xticks([])
        ax.set_yticks([])
        for sp in ax.spines.values():
            sp.set_visible(False)

    # Panel 1: wall shell only
    draw_shell(axes[0, 0], shell_payload)
    axes[0, 0].set_title("WALL SHELL only — `PlanShell_Group`",
                          fontsize=11, family="monospace")

    # Panel 2: floors only
    draw_floors(axes[0, 1], consensus)
    axes[0, 1].set_title("FLOORS only — `Floor_Group_*`",
                          fontsize=11, family="monospace")

    # Panel 3: soft barriers only
    draw_soft_barriers(axes[1, 0], consensus)
    axes[1, 0].set_title("SOFT BARRIERS only — `SoftBarrier_Group_*` "
                          "(thin slabs along polyline)",
                          fontsize=11, family="monospace")

    # Panel 4: all combined — draw bottom-up so walls stay on top
    draw_floors(axes[1, 1], consensus)
    draw_soft_barriers(axes[1, 1], consensus)
    draw_shell(axes[1, 1], shell_payload)
    axes[1, 1].set_title("ALL LAYERS combined",
                          fontsize=11, family="monospace")

    for ax in axes.flat:
        ax.autoscale_view()

    fig.suptitle(
        "Plan-shell isolated layers — top-down view",
        fontsize=13, family="monospace", y=0.99,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    fig.savefig(out_png, dpi=150, facecolor=fig.get_facecolor())
    print(f"[ok] {out_png}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--consensus", type=Path, required=True)
    ap.add_argument("--shell-json", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    main(args.consensus, args.shell_json, args.out)
