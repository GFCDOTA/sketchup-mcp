"""Render an F1 diff PNG: GT / Pipeline / Diff, 3 panels side by side.

Re-runs the matching logic from ``scripts.score_openings.match_openings``
to compute TP / FP / FN, then renders three plan panels:

  Left   Ground Truth      (all blue circles)
  Middle Pipeline detections (all cyan circles)
  Right  Diff              (TP green with leader line GT<->det,
                            FP red, FN orange)

Header at the top shows the SVG filename and the computed F1 score.
Walls are drawn in gray on all panels.

Usage:
    python scripts/render_f1_diff_png.py \\
        --model runs/<name>/observed_model.json \\
        --gt    tests/fixtures/.../planta_74m2_openings_gt.yaml \\
        --out   runs/<name>/f1_diff.png \\
        [--center-tol-mul 2.0]

Observational: does not modify the model or GT.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

# Support running as ``python scripts/render_f1_diff_png.py`` from
# the repo root (no package install required).
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.render_openings_conclusion_png import (  # noqa: E402
    load_font,
    load_font_mono,
    plan_bounds,
)
from scripts.score_openings import (  # noqa: E402
    DetOpening,
    GTOpening,
    MatchResult,
    load_detections,
    load_gt,
    match_openings,
)


CANVAS_W = 2000
CANVAS_H = 1400

BG = (14, 17, 22)
PANEL_BG = (22, 27, 34)
PANEL_EDGE = (48, 54, 61)
TEXT = (230, 237, 243)
TEXT_DIM = (139, 148, 158)
WALL = (140, 140, 140)

COLOR_GT = (88, 166, 255)        # blue
COLOR_PIPELINE = (121, 192, 255) # cyan
COLOR_TP = (63, 185, 80)         # green
COLOR_FP = (248, 81, 73)         # red
COLOR_FN = (255, 165, 0)         # orange


def _collect_points(
    walls: list[dict],
    gts: list[GTOpening],
    dets: list[DetOpening],
) -> tuple[float, float, float, float]:
    xs: list[float] = []
    ys: list[float] = []
    for w in walls:
        s = w.get("start") or [0, 0]
        e = w.get("end") or [0, 0]
        xs.extend([float(s[0]), float(e[0])])
        ys.extend([float(s[1]), float(e[1])])
    for gt in gts:
        xs.append(gt.center[0])
        ys.append(gt.center[1])
    for det in dets:
        xs.append(det.center[0])
        ys.append(det.center[1])
    if not xs:
        return 0.0, 0.0, 1.0, 1.0
    return min(xs), min(ys), max(xs), max(ys)


def _draw_walls(draw: ImageDraw.ImageDraw, walls: list[dict], P) -> None:
    for w in walls:
        s = w.get("start") or [0, 0]
        e = w.get("end") or [0, 0]
        draw.line([P(float(s[0]), float(s[1])), P(float(e[0]), float(e[1]))],
                  fill=WALL, width=1)


def _draw_opening(
    draw: ImageDraw.ImageDraw,
    center: tuple[float, float],
    width: float,
    color: tuple[int, int, int],
    scale: float,
    P,
    filled: bool = True,
) -> None:
    cx, cy = P(*center)
    rr = max(5, int((width / 2) * scale))
    if filled:
        draw.ellipse(
            [cx - rr, cy - rr, cx + rr, cy + rr],
            fill=color,
            outline=TEXT,
            width=1,
        )
    else:
        draw.ellipse(
            [cx - rr, cy - rr, cx + rr, cy + rr],
            outline=color,
            width=3,
        )


def _panel_transform(
    bounds: tuple[float, float, float, float],
    panel_box: tuple[int, int, int, int],
    header_h: int,
    inner_pad: int = 18,
):
    """Return ``(scale, P)`` where P is a function mapping plan -> pixel."""
    minx, miny, maxx, maxy = bounds
    x0, y0, x1, y1 = panel_box
    pad_plan = 25
    plan_w = (maxx - minx) + 2 * pad_plan
    plan_h = (maxy - miny) + 2 * pad_plan
    inner_w = (x1 - x0) - 2 * inner_pad
    inner_h = (y1 - y0) - header_h - inner_pad
    if plan_w <= 0 or plan_h <= 0 or inner_w <= 0 or inner_h <= 0:
        scale = 1.0
    else:
        scale = min(inner_w / plan_w, inner_h / plan_h)
    draw_w = plan_w * scale
    draw_h = plan_h * scale
    tx = x0 + inner_pad + (inner_w - draw_w) / 2
    ty = y0 + header_h + (inner_h - draw_h) / 2

    def P(x: float, y: float) -> tuple[int, int]:
        return (int(tx + (x - minx + pad_plan) * scale),
                int(ty + (y - miny + pad_plan) * scale))

    return scale, P


def _draw_panel_frame(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    title: str,
    subtitle: str,
    font_title,
    font_sub,
) -> int:
    x0, y0, x1, y1 = box
    header_h = 70
    draw.rectangle(box, fill=PANEL_BG, outline=PANEL_EDGE, width=2)
    draw.rectangle([x0, y0, x1, y0 + header_h], fill=(31, 36, 44))
    draw.text((x0 + 16, y0 + 10), title, font=font_title, fill=TEXT)
    draw.text((x0 + 16, y0 + 42), subtitle, font=font_sub, fill=TEXT_DIM)
    return header_h


# ---------- main render ----------

def render(
    out_path: Path,
    walls: list[dict],
    gts: list[GTOpening],
    dets: list[DetOpening],
    result: MatchResult,
    svg_name: str,
) -> None:
    img = Image.new("RGB", (CANVAS_W, CANVAS_H), BG)
    draw = ImageDraw.Draw(img)

    font_hero = load_font(34)
    font_title = load_font(22)
    font_sub = load_font_mono(14)

    # Header
    f1 = result.f1
    draw.text((40, 20), f"F1 diff | {svg_name}", font=font_hero, fill=TEXT)
    draw.text(
        (40, 66),
        f"F1 = {f1:.3f}  "
        f"(TP={result.tp_count}  FP={result.fp_count}  FN={result.fn_count}  "
        f"precision={result.precision:.3f}  recall={result.recall:.3f})",
        font=font_sub,
        fill=TEXT_DIM,
    )

    # Panel layout
    header_total = 110
    gap = 20
    panel_w = (CANVAS_W - 4 * gap) // 3
    panel_h = CANVAS_H - header_total - gap
    py0 = header_total
    boxes = [
        (gap + i * (panel_w + gap), py0, gap + i * (panel_w + gap) + panel_w, py0 + panel_h)
        for i in range(3)
    ]

    # Shared bounds for all 3 panels so plans align visually
    bounds = _collect_points(walls, gts, dets)

    # -- Panel 1: Ground Truth --
    hh = _draw_panel_frame(
        draw, boxes[0],
        "Ground Truth",
        f"{len(gts)} openings",
        font_title, font_sub,
    )
    scale0, P0 = _panel_transform(bounds, boxes[0], hh)
    _draw_walls(draw, walls, P0)
    for gt in gts:
        _draw_opening(draw, gt.center, gt.width, COLOR_GT, scale0, P0, filled=True)

    # -- Panel 2: Pipeline --
    hh = _draw_panel_frame(
        draw, boxes[1],
        "Pipeline",
        f"{len(dets)} detections",
        font_title, font_sub,
    )
    scale1, P1 = _panel_transform(bounds, boxes[1], hh)
    _draw_walls(draw, walls, P1)
    for det in dets:
        _draw_opening(draw, det.center, det.width, COLOR_PIPELINE, scale1, P1, filled=True)

    # -- Panel 3: Diff --
    hh = _draw_panel_frame(
        draw, boxes[2],
        "Diff",
        f"TP={result.tp_count}  FP={result.fp_count}  "
        f"FN={result.fn_count}  F1={f1:.2f}",
        font_title, font_sub,
    )
    scale2, P2 = _panel_transform(bounds, boxes[2], hh)
    _draw_walls(draw, walls, P2)

    # TP: green filled on detection, small open ring on GT, leader line
    for gt, det in result.tp_pairs:
        gtp = P2(*gt.center)
        dp = P2(*det.center)
        draw.line([gtp, dp], fill=COLOR_TP, width=2)
        _draw_opening(draw, det.center, det.width, COLOR_TP, scale2, P2, filled=True)
        # small GT anchor ring
        draw.ellipse([gtp[0] - 4, gtp[1] - 4, gtp[0] + 4, gtp[1] + 4],
                     outline=COLOR_TP, width=2)

    # FP: red filled
    for det in result.fp:
        _draw_opening(draw, det.center, det.width, COLOR_FP, scale2, P2, filled=True)
    # FN: orange ring (hollow) to distinguish "missing" from "found"
    for gt in result.fn:
        _draw_opening(draw, gt.center, gt.width, COLOR_FN, scale2, P2, filled=False)

    # Legend inside diff panel
    _draw_diff_legend(draw, boxes[2], font_sub)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG", optimize=True)


def _draw_diff_legend(
    draw: ImageDraw.ImageDraw,
    panel_box: tuple[int, int, int, int],
    font,
) -> None:
    x0, y0, x1, y1 = panel_box
    lw = 180
    lh = 110
    lx0 = x1 - lw - 12
    ly0 = y1 - lh - 12
    draw.rectangle([lx0, ly0, lx0 + lw, ly0 + lh],
                   fill=(31, 36, 44), outline=PANEL_EDGE, width=1)
    rows = [
        (COLOR_TP, "TP (match)", True),
        (COLOR_FP, "FP (extra)", True),
        (COLOR_FN, "FN (missed)", False),
    ]
    for i, (c, lbl, filled) in enumerate(rows):
        ry = ly0 + 12 + i * 30
        if filled:
            draw.ellipse([lx0 + 12, ry, lx0 + 32, ry + 20], fill=c, outline=TEXT)
        else:
            draw.ellipse([lx0 + 12, ry, lx0 + 32, ry + 20], outline=c, width=3)
        draw.text((lx0 + 42, ry + 2), lbl, font=font, fill=TEXT)


# ---------- CLI ----------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", required=True, type=Path,
                        help="path to observed_model.json")
    parser.add_argument("--gt", required=True, type=Path,
                        help="path to ground-truth YAML")
    parser.add_argument("--out", required=True, type=Path,
                        help="output PNG path")
    parser.add_argument("--center-tol-mul", type=float, default=2.0,
                        help="center distance tolerance as multiple of thickness")
    parser.add_argument("--width-ratio-min", type=float, default=0.5)
    parser.add_argument("--width-ratio-max", type=float, default=2.0)
    args = parser.parse_args(argv)

    thickness, gts = load_gt(args.gt)
    dets, walls = load_detections(args.model)

    result = match_openings(
        gts=gts,
        dets=dets,
        thickness=thickness,
        center_tol_mul=args.center_tol_mul,
        width_ratio_min=args.width_ratio_min,
        width_ratio_max=args.width_ratio_max,
    )

    model = json.loads(args.model.read_text(encoding="utf-8"))
    svg_name = str((model.get("source") or {}).get("filename", args.model.name))

    render(
        out_path=args.out,
        walls=walls,
        gts=gts,
        dets=dets,
        result=result,
        svg_name=svg_name,
    )

    print(
        f"wrote {args.out}  "
        f"F1={result.f1:.3f}  TP={result.tp_count}  "
        f"FP={result.fp_count}  FN={result.fn_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
