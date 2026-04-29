"""Render a side-by-side N-panel comparison of observed_model.json runs.

Produces a single PNG with N panels (one per run) using the same visual
language as ``scripts/preview/render_preview.render_top`` so dashboard
PNGs from different changes stay consistent: walls as black footprint
polygons, rooms as pastel fills, openings color-coded by kind, junctions
as small colored dots. Each panel has a monospace header with label and
inline metrics; an optional narrative footer captions the whole figure.

Usage:
    python scripts/render_change_comparison.py \\
        --panel runs/baseline/observed_model.json "v1 | antes" \\
        --panel runs/postfix/observed_model.json  "v2 | pos-fix" \\
        --footer "Rooms 30 -> 24 com filter_room_noise. Slivers eliminados." \\
        --title "filter_room_noise enabled on raster path" \\
        --out tools/dashboard/assets/plantas/13_compare.png
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Polygon, Rectangle


BG = "#f5f3ee"
HEADER_BG = "#1f2937"
HEADER_FG = "#e6edf3"
HEADER_LABEL = "#fbbf24"
SUB_FG = "#9ca3af"

ROOM_PALETTE = [
    "#fde2c0", "#c8e6c9", "#bbdefb", "#f8bbd0", "#dcedc8",
    "#ffe0b2", "#d1c4e9", "#b3e5fc", "#fff9c4", "#f5e0d0",
    "#cfd8dc", "#e1bee7", "#ffccbc", "#c5e1a5", "#b2dfdb",
    "#f0f4c3", "#ffe082", "#b39ddb", "#80deea", "#a5d6a7",
    "#ffab91", "#ce93d8", "#90caf9",
]

WALL_FACE = "#3d3325"
WALL_EDGE = "#1a1611"
DOOR_COLOR = "#d97b3b"
PASSAGE_COLOR = "#4a90e2"
WINDOW_COLOR = "#9ad0ec"


@dataclass
class PanelSpec:
    model_path: Path
    label: str


def _wall_footprint(start, end, thickness):
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


def _draw_panel(ax, model: dict, label: str) -> None:
    """Paint one panel into ``ax`` using the render_top visual language."""
    walls = model["walls"]
    rooms = model["rooms"]
    openings = model.get("openings", [])
    junctions = model.get("junctions", [])
    pages = model["bounds"]["pages"]
    if not pages:
        ax.text(0.5, 0.5, "(no walls)", transform=ax.transAxes,
                ha="center", va="center", color=SUB_FG, fontsize=14,
                fontfamily="monospace")
        ax.set_axis_off()
        return
    page = pages[0]

    ax.set_facecolor(BG)

    # Rooms (pastel palette)
    for i, room in enumerate(rooms):
        poly = [(x, -y) for (x, y) in room["polygon"]]
        ax.add_patch(Polygon(
            poly,
            facecolor=ROOM_PALETTE[i % len(ROOM_PALETTE)],
            edgecolor="#5b6770", linewidth=0.6, alpha=0.85, zorder=1,
        ))
        cx, cy = room["centroid"]
        ax.text(cx, -cy, room["room_id"].replace("room-", "R"),
                fontsize=6.5, color="#1a1611",
                ha="center", va="center", fontweight="bold", zorder=4)

    # Walls (footprint polygons)
    for w in walls:
        poly = _wall_footprint(w["start"], w["end"], w["thickness"])
        if poly is None:
            continue
        flipped = [(x, -y) for (x, y) in poly]
        ax.add_patch(Polygon(
            flipped, facecolor=WALL_FACE, edgecolor=WALL_EDGE,
            linewidth=0.3, zorder=3,
        ))

    # Junctions
    for j in junctions:
        kind = j.get("kind", "end")
        if kind == "end":
            color, size = "#c0392b", 1.8
        elif kind == "pass_through":
            color, size = "#7f8c8d", 1.2
        else:
            color, size = "#27ae60", 2.2
        x, y = j["point"]
        ax.add_patch(Circle((x, -y), size, facecolor=color,
                            edgecolor="none", zorder=5, alpha=0.7))

    # Openings
    for op in openings:
        cx, cy = op["center"]
        kind = op["kind"]
        width = op["width"]
        color = {"door": DOOR_COLOR, "window": WINDOW_COLOR}.get(
            kind, PASSAGE_COLOR
        )
        if op.get("orientation") == "horizontal":
            w_w, w_h = width, 8
        else:
            w_w, w_h = 8, width
        ax.add_patch(Rectangle(
            (cx - w_w / 2, -cy - w_h / 2), w_w, w_h,
            facecolor=color, edgecolor=WALL_EDGE,
            linewidth=0.5, zorder=6, alpha=0.95,
        ))

    pad = 30.0
    ax.set_xlim(page["min_x"] - pad, page["max_x"] + pad)
    ax.set_ylim(-page["max_y"] - pad, -page["min_y"] + pad)
    ax.set_aspect("equal")
    ax.set_axis_off()


def _format_metrics_line(model: dict) -> str:
    walls = model["walls"]
    rooms = model["rooms"]
    junctions = model.get("junctions", [])
    openings = model.get("openings", [])
    warnings = model.get("warnings") or []
    scores = model.get("scores", {})
    geom = scores.get("geometry", scores.get("retention", 0.0))
    topo = scores.get("topology", 0.0)
    rooms_score = scores.get("rooms", 0.0)
    conn = (model.get("metadata") or {}).get("connectivity", {}) or {}
    orph = conn.get("orphan_node_count", 0)
    parts = [
        f"walls={len(walls)}",
        f"rooms={len(rooms)}",
        f"juncs={len(junctions)}",
    ]
    if openings:
        parts.append(f"openings={len(openings)}")
    parts.extend([
        f"orphans={orph}",
        f"geom={geom:.3f}",
        f"topo={topo:.2f}",
        f"rooms={rooms_score:.2f}",
        f"warn={warnings if warnings else '[]'}",
    ])
    return "  ".join(parts)


def render_comparison(
    panels: list[PanelSpec],
    out_path: Path,
    *,
    title: str | None = None,
    footer: str | None = None,
    panel_height_in: float = 6.5,
    panel_width_in: float = 10.0,
) -> None:
    n = len(panels)
    if n < 1:
        raise ValueError("need at least one panel")

    title_height = 0.55 if title else 0.0
    header_height = 0.85
    footer_height = 0.65 if footer else 0.0

    fig_w = panel_width_in * n
    fig_h = panel_height_in + title_height + header_height + footer_height

    fig = plt.figure(figsize=(fig_w, fig_h), dpi=150, facecolor=BG)

    # Vertical layout in figure coords (0..1, bottom origin):
    #  [footer_h] [panel_h] [header_h] [title_h]
    # Compute each band's top/bottom fractions.
    title_top = 1.0
    title_bottom = title_top - (title_height / fig_h)
    header_top = title_bottom
    header_bottom = header_top - (header_height / fig_h)
    panel_top = header_bottom
    panel_bottom = footer_height / fig_h
    footer_top = panel_bottom

    if title:
        # Center the title vertically in its band.
        ty = (title_top + title_bottom) / 2.0
        fig.text(
            0.012, ty,
            title, ha="left", va="center",
            fontsize=15, fontweight="bold", color="#1f2937",
            fontfamily="monospace",
        )

    # Pre-load all models so headers show metrics drawn from the same data.
    panel_models = [
        json.loads(spec.model_path.read_text(encoding="utf-8")) for spec in panels
    ]

    for i, (spec, model) in enumerate(zip(panels, panel_models)):
        gap = 0.004
        left = i / n + gap
        right = (i + 1) / n - gap

        # Plot axis (panel band).
        ax = fig.add_axes(
            (left, panel_bottom, right - left, panel_top - panel_bottom),
            facecolor=BG,
        )
        _draw_panel(ax, model, spec.label)

        # Header band on top of the panel.
        header_ax = fig.add_axes(
            (left, header_bottom, right - left, header_top - header_bottom),
            facecolor=HEADER_BG,
        )
        header_ax.set_xticks([])
        header_ax.set_yticks([])
        for s in header_ax.spines.values():
            s.set_visible(False)
        header_ax.set_xlim(0, 1)
        header_ax.set_ylim(0, 1)
        header_ax.add_patch(Rectangle((0, 0), 1, 1, facecolor=HEADER_BG, zorder=0))
        header_ax.text(
            0.012, 0.68, spec.label,
            ha="left", va="center",
            fontsize=12, fontweight="bold",
            color=HEADER_LABEL,
            fontfamily="monospace",
        )
        header_ax.text(
            0.012, 0.28, _format_metrics_line(model),
            ha="left", va="center",
            fontsize=9, color=HEADER_FG,
            fontfamily="monospace",
        )

    if footer:
        fy = (footer_top + 0) / 2.0
        fig.text(
            0.012, fy,
            footer,
            ha="left", va="center",
            fontsize=10, color="#374151",
            fontfamily="monospace",
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, facecolor=BG, bbox_inches=None)
    plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Side-by-side N-panel comparison of observed_model.json runs.",
    )
    parser.add_argument(
        "--panel",
        action="append",
        nargs=2,
        metavar=("MODEL_JSON", "LABEL"),
        required=True,
        help="add a panel with the given model JSON and label. "
             "Pass --panel multiple times in left-to-right order.",
    )
    parser.add_argument("--title", help="optional title above all panels")
    parser.add_argument("--footer", help="optional narrative footer below panels")
    parser.add_argument("--out", required=True, type=Path,
                        help="output PNG path")
    parser.add_argument("--panel-width", type=float, default=10.0,
                        help="panel width in inches (default: 10)")
    parser.add_argument("--panel-height", type=float, default=6.5,
                        help="panel height in inches (default: 6.5)")
    args = parser.parse_args(argv)

    panels = [PanelSpec(model_path=Path(m), label=lbl) for m, lbl in args.panel]
    render_comparison(
        panels,
        out_path=args.out,
        title=args.title,
        footer=args.footer,
        panel_width_in=args.panel_width,
        panel_height_in=args.panel_height,
    )
    print(f"wrote {args.out} ({args.out.stat().st_size} bytes, {len(panels)} panels)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
