"""Render a human-friendly annotation helper PNG + YAML template.

Takes a pipeline ``observed_model.json`` and produces:
  - a large dark-theme PNG with walls in gray and openings numbered,
    color-coded by kind, with offset labels so nothing overlaps, a
    faint grid, coordinate tick labels, legend and title;
  - a side-by-side YAML template pre-filled with all detections as
    candidates (TP/FP/FN markup instructions in comments) for the
    human (Felipe) to review and rewrite as ground truth.

The PNG is a *visual judge* that makes it cheap for the human to look
at the plan and decide, per detection, whether to keep, drop or
rewrite into a real GT entry.

Usage:
    python scripts/annotate_openings_helper.py \\
        --model runs/<name>/observed_model.json \\
        --out   runs/<name>/annotation_helper.png

The YAML template is written next to ``--out`` as
``annotation_template.yaml`` (same directory, fixed name). Override
with ``--template`` if needed.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

# Support running as ``python scripts/annotate_openings_helper.py`` from
# the repo root (no package install required).
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.render_openings_conclusion_png import (  # noqa: E402
    load_font,
    load_font_mono,
    plan_bounds,
)


CANVAS_W = 3000
CANVAS_H = 2000

BG = (14, 17, 22)
PANEL_BG = (22, 27, 34)
PANEL_EDGE = (48, 54, 61)
GRID = (38, 44, 52)
TEXT = (230, 237, 243)
TEXT_DIM = (139, 148, 158)
WALL = (168, 168, 168)

KIND_COLORS: dict[str, tuple[int, int, int]] = {
    "door": (88, 166, 255),        # blue
    "passage": (188, 140, 255),    # purple
    "window": (121, 192, 255),     # cyan
}
KIND_DEFAULT = (200, 200, 200)


def _kind_color(kind: str) -> tuple[int, int, int]:
    return KIND_COLORS.get(kind, KIND_DEFAULT)


def _norm_orientation(o: str) -> str:
    o = (o or "").strip().lower()
    if o.startswith("h"):
        return "horizontal"
    if o.startswith("v"):
        return "vertical"
    return o or "horizontal"


# ---------- label placement ----------

def _offset_for_index(idx: int, radius: int) -> tuple[int, int]:
    """Pick a label offset in one of 8 directions rotating by index.

    Simple deterministic round-robin — prevents labels from piling up
    on top of each other for nearby detections without needing a
    full collision-avoidance solver.
    """
    directions = [
        (1, -1), (1, 0), (1, 1),
        (0, 1), (-1, 1), (-1, 0),
        (-1, -1), (0, -1),
    ]
    dx, dy = directions[idx % len(directions)]
    dist = radius + 18
    return dx * dist, dy * dist


# ---------- PNG rendering ----------

def render_png(
    model: dict[str, Any],
    out_path: Path,
) -> None:
    walls = model.get("walls") or []
    openings = model.get("openings") or []
    source = model.get("source") or {}
    thickness = float(source.get("stroke_width_median", 6.25))
    svg_name = str(source.get("filename", "?"))

    img = Image.new("RGB", (CANVAS_W, CANVAS_H), BG)
    draw = ImageDraw.Draw(img)

    font_title = load_font(40)
    font_legend = load_font(24)
    font_label = load_font(20)
    font_mono = load_font_mono(16)
    font_hero_num = load_font(22)
    font_tick = load_font_mono(14)

    # Title
    n = len(openings)
    title = (
        f"annotate_openings_helper | {n} detections | "
        f"thickness={thickness:g} | SVG: {svg_name}"
    )
    draw.text((40, 28), title, font=font_title, fill=TEXT)
    draw.text(
        (40, 80),
        "Walls in gray. Openings numbered and colored by kind. "
        "Edit the YAML template (same folder) to rewrite as ground truth.",
        font=font_mono,
        fill=TEXT_DIM,
    )

    # Plan panel
    header_h = 130
    pax0, pay0 = 40, header_h
    pax1, pay1 = CANVAS_W - 40, CANVAS_H - 40

    # Panel background
    draw.rectangle([pax0, pay0, pax1, pay1], fill=PANEL_BG, outline=PANEL_EDGE, width=2)

    if not walls:
        draw.text((pax0 + 20, pay0 + 20), "(no walls in model)", font=font_title, fill=TEXT_DIM)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(out_path, "PNG", optimize=True)
        return

    minx, miny, maxx, maxy = plan_bounds(walls)
    pad = 40
    plan_w = (maxx - minx) + 2 * pad
    plan_h = (maxy - miny) + 2 * pad
    inner_w = (pax1 - pax0) - 20
    inner_h = (pay1 - pay0) - 20
    scale = min(inner_w / plan_w, inner_h / plan_h)
    draw_w = plan_w * scale
    draw_h = plan_h * scale
    tx = pax0 + 10 + (inner_w - draw_w) / 2
    ty = pay0 + 10 + (inner_h - draw_h) / 2

    def P(x: float, y: float) -> tuple[int, int]:
        return (int(tx + (x - minx + pad) * scale), int(ty + (y - miny + pad) * scale))

    # ---- Grid (every 50 plan-units) ----
    grid_step = 50.0
    gx = math.floor(minx / grid_step) * grid_step
    while gx <= maxx + 0.5:
        p0 = P(gx, miny)
        p1 = P(gx, maxy)
        draw.line([p0, p1], fill=GRID, width=1)
        draw.text((p0[0] + 2, pay1 - 22), f"x={gx:g}", font=font_tick, fill=TEXT_DIM)
        gx += grid_step

    gy = math.floor(miny / grid_step) * grid_step
    while gy <= maxy + 0.5:
        p0 = P(minx, gy)
        p1 = P(maxx, gy)
        draw.line([p0, p1], fill=GRID, width=1)
        draw.text((pax0 + 8, p0[1] + 2), f"y={gy:g}", font=font_tick, fill=TEXT_DIM)
        gy += grid_step

    # ---- Walls ----
    for wall in walls:
        p0 = P(*wall["start"])
        p1 = P(*wall["end"])
        draw.line([p0, p1], fill=WALL, width=2)

    # ---- Openings ----
    per_kind_count: dict[str, int] = {}
    for idx, o in enumerate(openings, start=1):
        cx, cy = o["center"]
        kind = str(o.get("kind", "door"))
        per_kind_count[kind] = per_kind_count.get(kind, 0) + 1
        color = _kind_color(kind)

        rr = max(8, int((float(o.get("width", 0.0)) / 2) * scale))
        ox, oy = P(cx, cy)
        # Circle
        draw.ellipse(
            [ox - rr, oy - rr, ox + rr, oy + rr],
            outline=color,
            width=3,
        )
        # Center tick
        draw.line([(ox - 4, oy), (ox + 4, oy)], fill=color, width=2)
        draw.line([(ox, oy - 4), (ox, oy + 4)], fill=color, width=2)

        # Label with offset so nearby labels don't overlap
        off_x, off_y = _offset_for_index(idx - 1, rr)
        lbl = f"#{idx} ({int(round(float(o.get('width', 0)))):d}px {kind})"
        lx = ox + off_x
        ly = oy + off_y
        # Text shadow for legibility over grid/walls
        tb = draw.textbbox((lx, ly), lbl, font=font_label)
        pad_x, pad_y = 6, 3
        draw.rectangle(
            [tb[0] - pad_x, tb[1] - pad_y, tb[2] + pad_x, tb[3] + pad_y],
            fill=(22, 27, 34, 200),
            outline=color,
            width=1,
        )
        draw.text((lx, ly), lbl, font=font_label, fill=TEXT)

        # Thin leader from label anchor back to circle edge
        leader_x = tb[0] - pad_x if off_x > 0 else tb[2] + pad_x
        leader_y = (tb[1] + tb[3]) // 2
        draw.line([(ox, oy), (leader_x, leader_y)], fill=color, width=1)

    # ---- Legend (top-right) ----
    legend_w = 340
    legend_h = 40 + 36 * (len(per_kind_count) + 1)
    lx0 = CANVAS_W - legend_w - 40
    ly0 = header_h + 20
    draw.rectangle(
        [lx0, ly0, lx0 + legend_w, ly0 + legend_h],
        fill=PANEL_BG, outline=PANEL_EDGE, width=2,
    )
    draw.text((lx0 + 16, ly0 + 10), "Legend", font=font_legend, fill=TEXT)

    row_y = ly0 + 46
    for kind in sorted(per_kind_count):
        color = _kind_color(kind)
        draw.ellipse([lx0 + 18, row_y + 4, lx0 + 38, row_y + 24], outline=color, width=3)
        draw.text(
            (lx0 + 52, row_y + 2),
            f"{kind}: {per_kind_count[kind]}",
            font=font_legend,
            fill=TEXT,
        )
        row_y += 34
    draw.text(
        (lx0 + 18, row_y + 6),
        f"total: {n}",
        font=font_hero_num,
        fill=TEXT,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG", optimize=True)


# ---------- YAML template ----------

def _yaml_escape(s: str) -> str:
    s = str(s).replace("\\", "\\\\").replace('"', '\\"')
    return s


def render_yaml_template(model: dict[str, Any], template_path: Path) -> None:
    """Write a pre-filled YAML template for manual GT curation.

    We emit YAML by hand (not via ``yaml.safe_dump``) so we can keep
    the guidance comments above the entries — ``safe_dump`` would
    strip them.
    """
    openings = model.get("openings") or []
    source = model.get("source") or {}
    thickness = float(source.get("stroke_width_median", 6.25))
    svg_name = str(source.get("filename", "?"))
    n = len(openings)

    lines: list[str] = []
    lines.append("meta:")
    lines.append(f'  source: "{_yaml_escape(svg_name)}"')
    lines.append(f"  thickness: {thickness:g}")
    lines.append('  annotator: "Felipe (manual)"')
    lines.append("openings:")
    lines.append("  # ====================================================")
    lines.append("  # EDIT THIS: mark each detection as true/false/modify")
    lines.append("  # ====================================================")
    lines.append("  # TP (keep as-is, confirm it's a real opening):")
    lines.append("  # - id: <rename to descriptive>")
    lines.append("  #   center: [x, y]")
    lines.append("  #   width: N")
    lines.append("  #   orientation: horizontal|vertical")
    lines.append("  #   kind: door|window|passage")
    lines.append('  #   notes: "<what this represents>"')
    lines.append("  #")
    lines.append("  # FP (remove from GT — not a real opening):")
    lines.append("  # - <delete the entry>")
    lines.append("  #")
    lines.append("  # FN (add new entries for real openings not detected):")
    lines.append("  # - id: suite_window")
    lines.append("  #   center: [240, 280]")
    lines.append("  #   width: 40")
    lines.append("  #   orientation: horizontal")
    lines.append("  #   kind: window")
    lines.append('  #   notes: "Janela de suite master — nao detectada"')
    lines.append("  #")
    lines.append(f"  # Below are all {n} detections, pre-filled as candidates:")
    lines.append("")

    for idx, o in enumerate(openings, start=1):
        oid = str(o.get("opening_id") or f"opening-{idx}")
        cx, cy = o.get("center") or [0.0, 0.0]
        width = float(o.get("width", 0.0))
        orientation = _norm_orientation(str(o.get("orientation", "horizontal")))
        kind = str(o.get("kind", "door"))
        lines.append(f"  - id: {oid}")
        lines.append(f"    center: [{float(cx):.3f}, {float(cy):.3f}]")
        lines.append(f"    width: {width:g}")
        lines.append(f"    orientation: {orientation}")
        lines.append(f"    kind: {kind}")
        lines.append('    notes: ""')

    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------- CLI ----------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", required=True, type=Path,
                        help="path to observed_model.json")
    parser.add_argument("--out", required=True, type=Path,
                        help="output PNG path")
    parser.add_argument("--template", type=Path, default=None,
                        help="output YAML template path "
                             "(default: <out dir>/annotation_template.yaml)")
    args = parser.parse_args(argv)

    model = json.loads(args.model.read_text(encoding="utf-8"))

    render_png(model, args.out)
    template_path = args.template or (args.out.parent / "annotation_template.yaml")
    render_yaml_template(model, template_path)

    n = len(model.get("openings") or [])
    print(f"wrote PNG:      {args.out}")
    print(f"wrote template: {template_path} ({n} candidates)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
