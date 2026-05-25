"""Render a top-view side-by-side: per-wall paradigm vs plan-shell union.

Reads a consensus + the _shell_polygon.json produced by
build_plan_shell_skp.py. Renders:

  LEFT  panel: the 35 wall footprints drawn as INDEPENDENT rectangles
              with edge strokes — the "before" picture that mirrors
              what consume_consensus.rb emits topologically (each
              wall is its own Group, corners overlap and show as
              extra edges).
  RIGHT panel: the union'd plan-shell polygon(s) drawn as a single
              shape with the SAME data — the "after" picture.

No SketchUp involved. matplotlib only.

Usage:
  python -m tools.render_plan_shell_comparison \\
    --consensus fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json \\
    --shell-json runs/planta_74_plan_shell/_shell_polygon.json \\
    --out runs/planta_74_plan_shell/comparison_with_current.png
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
from matplotlib.path import Path as MplPath

from tools.build_plan_shell_skp import wall_footprint


def draw_wall_paradigm(ax, consensus: dict) -> None:
    """Draw each wall as its own filled rectangle with visible edges.

    Mirrors what consume_consensus.rb does topologically: each wall is
    independent, corners overlap as separate cells. The visible edges
    between perpendicular walls at each corner are the visual signature
    of the per-wall-group paradigm.
    """
    walls = consensus.get("walls", [])
    for w in walls:
        box = wall_footprint(w)
        x0, y0, x1, y1 = box.bounds
        rect = mpatches.Rectangle(
            (x0, y0), x1 - x0, y1 - y0,
            facecolor=(78 / 255, 78 / 255, 78 / 255, 0.85),
            edgecolor="#101010",
            linewidth=0.6,
        )
        ax.add_patch(rect)
    ax.set_title(
        f"BEFORE — per-wall paradigm\n"
        f"({len(walls)} independent wall footprints, "
        f"corner overlaps visible as extra edges)",
        fontsize=11, family="monospace",
    )


def draw_plan_shell(ax, shell_payload: dict) -> None:
    """Draw the union'd plan shell as a single shape with holes."""
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
        patch = mpatches.PathPatch(
            path,
            facecolor=(78 / 255, 78 / 255, 78 / 255, 0.85),
            edgecolor="#101010",
            linewidth=0.9,
        )
        ax.add_patch(patch)
    stats = shell_payload.get("stats", {})
    ax.set_title(
        f"AFTER — plan-shell union\n"
        f"({stats.get('shell_pieces_after_sliver_filter', '?')} "
        f"continuous shell piece(s), "
        f"{stats.get('openings_carved', '?')} door gaps carved)",
        fontsize=11, family="monospace",
    )


def main(consensus_path: Path, shell_json: Path, out_png: Path) -> None:
    consensus = json.loads(consensus_path.read_text(encoding="utf-8"))
    shell_payload = json.loads(shell_json.read_text(encoding="utf-8"))

    fig, (ax_left, ax_right) = plt.subplots(
        1, 2, figsize=(16, 9), dpi=150,
    )
    fig.patch.set_facecolor("white")

    for ax in (ax_left, ax_right):
        ax.set_facecolor("white")
        ax.set_aspect("equal")
        ax.set_xticks([])
        ax.set_yticks([])
        for sp in ax.spines.values():
            sp.set_visible(False)

    draw_wall_paradigm(ax_left, consensus)
    draw_plan_shell(ax_right, shell_payload)

    for ax in (ax_left, ax_right):
        ax.autoscale_view()

    fig.suptitle(
        f"plan_shell vs per-wall paradigm — "
        f"{Path(consensus.get('source', '?')).stem}",
        fontsize=13, family="monospace", y=0.98,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(out_png, dpi=150, facecolor=fig.get_facecolor())
    print(f"[ok] {out_png}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--consensus", type=Path, required=True)
    ap.add_argument("--shell-json", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    main(args.consensus, args.shell_json, args.out)
