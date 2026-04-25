"""
render_logical_walls.py
=======================

Renders the consolidated LOGICAL walls (walls_consolidated, ~91 entries) of
the consensus_model as filled rectangles using the real centerline + thickness.

Output: <run_dir>/logical_walls_overlay.png

Color scheme matches the production dashboard convention:
  - walls confirmed by V13 (sources_pooled includes 'pipeline_v13') -> #b41e1e
  - walls only seen in svg_native -> #dc6464

Usage:
    E:/Python312/python.exe render_logical_walls.py [run_dir]

Defaults to runs/final_planta_74/.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

DEFAULT_RUN = Path(__file__).resolve().parent.parent / "runs" / "final_planta_74"

COLOR_AGREED = (180, 30, 30)        # #b41e1e
COLOR_SVG_ONLY = (220, 100, 100)    # #dc6464
COLOR_OUTLINE = (60, 60, 60)
BG = (252, 252, 250)
HEADER_BG = (245, 245, 240)
HEADER_FG = (40, 40, 40)
PAD = 30
SCALE = 3.0
HEADER_H = 70


def _font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _wall_rect(start, end, thickness):
    """Return the 4 corner points of an oriented rectangle around the
    centerline, in the same coord space as `start`/`end` (PDF points)."""
    sx, sy = start
    ex, ey = end
    dx, dy = ex - sx, ey - sy
    L = math.hypot(dx, dy) or 1.0
    # unit tangent
    tx, ty = dx / L, dy / L
    # unit normal (left-hand)
    nx, ny = -ty, tx
    half = thickness / 2.0
    p1 = (sx + nx * half, sy + ny * half)
    p2 = (ex + nx * half, ey + ny * half)
    p3 = (ex - nx * half, ey - ny * half)
    p4 = (sx - nx * half, sy - ny * half)
    return [p1, p2, p3, p4]


def render(run_dir: Path) -> Path:
    src = run_dir / "consensus_model.json"
    if not src.exists():
        raise SystemExit(f"[render_logical_walls] not found: {src}")
    consensus = json.loads(src.read_text(encoding="utf-8"))

    cwalls = consensus.get("walls_consolidated") or []
    if not cwalls:
        raise SystemExit(
            "[render_logical_walls] consensus_model.json has no "
            "walls_consolidated array. Run consolidate_walls.py first."
        )

    # Derive bounds from the actual wall geometry. The metadata.page_bounds
    # in this run is in the cropped-PDF space and does not match the wall
    # coordinate space, so we ignore it here.
    xs = [p for w in cwalls for p in (w["centerline_start"][0], w["centerline_end"][0])]
    ys = [p for w in cwalls for p in (w["centerline_start"][1], w["centerline_end"][1])]
    g_minx, g_maxx = min(xs), max(xs)
    g_miny, g_maxy = min(ys), max(ys)
    minx, miny = g_minx - PAD, g_miny - PAD
    w_pt = (g_maxx - g_minx) + 2 * PAD
    h_pt = (g_maxy - g_miny) + 2 * PAD
    canvas_w = int(w_pt * SCALE)
    canvas_h = int(h_pt * SCALE) + HEADER_H

    img = Image.new("RGB", (canvas_w, canvas_h), BG)
    draw = ImageDraw.Draw(img)
    font_lg = _font(18)
    font_sm = _font(11)

    def to_canvas(pt):
        return ((pt[0] - minx) * SCALE, HEADER_H + (pt[1] - miny) * SCALE)

    # ----- header band -----
    draw.rectangle([(0, 0), (canvas_w, HEADER_H)], fill=HEADER_BG)
    n_total = len(cwalls)
    n_v13 = sum(1 for w in cwalls if "pipeline_v13" in (w.get("sources_pooled") or []))
    n_svg_only = n_total - n_v13
    n_face = sum(int(w.get("source_face_count", 1)) for w in cwalls)
    avg_thk = sum(float(w.get("thickness_pt", 0.0)) for w in cwalls) / max(n_total, 1)
    header = (
        f"LOGICAL WALLS (consolidated)  -  {n_total} walls   "
        f"|  V13 confirmed: {n_v13}  (red)   "
        f"|  SVG only: {n_svg_only}  (light red)   "
        f"|  source faces pooled: {n_face}   "
        f"|  avg thickness: {avg_thk:.1f} pt"
    )
    draw.text((12, 12), header, fill=HEADER_FG, font=font_lg)
    draw.text(
        (12, 36),
        "Each rectangle uses the real centerline_start->centerline_end and thickness_pt from walls_consolidated.",
        fill=(90, 90, 90),
        font=font_sm,
    )

    # ----- walls -----
    # Sort so V13-agreed walls render last (on top)
    ordered = sorted(
        cwalls,
        key=lambda w: ("pipeline_v13" in (w.get("sources_pooled") or [])),
    )
    for w in ordered:
        sources = w.get("sources_pooled") or []
        if "pipeline_v13" in sources:
            fill = COLOR_AGREED
        else:
            fill = COLOR_SVG_ONLY
        thk = float(w.get("thickness_pt", 4.0))
        # always draw at least 2 pt thick so single-face drywall shows up
        thk_draw = max(thk, 2.5)
        rect_pts = _wall_rect(
            tuple(w["centerline_start"]),
            tuple(w["centerline_end"]),
            thk_draw,
        )
        canvas_rect = [to_canvas(p) for p in rect_pts]
        draw.polygon(canvas_rect, fill=fill, outline=COLOR_OUTLINE)
        # tiny wall_id label at the centerline midpoint, only for substantial walls
        length = float(w.get("length_pt") or 0.0)
        if length >= 60.0:
            mx = 0.5 * (w["centerline_start"][0] + w["centerline_end"][0])
            my = 0.5 * (w["centerline_start"][1] + w["centerline_end"][1])
            cx, cy = to_canvas((mx, my))
            wid = str(w.get("wall_id", ""))
            draw.text((cx + 3, cy - 7), wid, fill=(30, 30, 30), font=font_sm)

    # ----- footer micro-legend -----
    lg_y = canvas_h - 22
    draw.rectangle([(12, lg_y), (32, lg_y + 12)], fill=COLOR_AGREED, outline=COLOR_OUTLINE)
    draw.text((36, lg_y - 2), "V13 + SVG agreement", fill=(60, 60, 60), font=font_sm)
    draw.rectangle([(220, lg_y), (240, lg_y + 12)], fill=COLOR_SVG_ONLY, outline=COLOR_OUTLINE)
    draw.text((244, lg_y - 2), "SVG only (drywall / unconfirmed)", fill=(60, 60, 60), font=font_sm)

    out = run_dir / "logical_walls_overlay.png"
    img.save(out, "PNG", optimize=True)
    return out


def main(argv: list[str]) -> int:
    run_dir = Path(argv[1]) if len(argv) > 1 else DEFAULT_RUN
    out = render(run_dir)
    size = out.stat().st_size
    print(f"[render_logical_walls] wrote {out}  ({size/1024:.1f} KB)")
    if size < 50_000:
        print(
            f"[render_logical_walls] WARNING: file is {size} B (< 50 KB target)",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
