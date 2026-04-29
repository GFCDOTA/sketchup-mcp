"""Render SVG with a 2x2 grid showing openings at each refinement stage.

Usage:
    python scripts/plot_openings_progression.py --out runs/openings_progression.svg
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


STAGES = [
    ("runs/openings_refine_baseline/observed_model.json", "baseline", "#d6604d"),
    ("runs/openings_refine_v1_a/observed_model.json", "+ prune orphan (A)", "#e08214"),
    ("runs/openings_refine_v1_b/observed_model.json", "+ size floor (B)", "#fdb863"),
    ("runs/openings_refine_final/observed_model.json", "+ dedup + roomless (C+D)", "#1b7837"),
]


def _bounds(walls: list[dict]) -> tuple[float, float, float, float]:
    xs, ys = [], []
    for w in walls:
        xs.extend([w["start"][0], w["end"][0]])
        ys.extend([w["start"][1], w["end"][1]])
    return min(xs), min(ys), max(xs), max(ys)


def _panel(model_path: Path, color: str, label: str, panel_w: float, panel_h: float, offset_x: float, offset_y: float) -> list[str]:
    m = json.loads(Path(model_path).read_text(encoding="utf-8"))
    walls = m["walls"]
    openings = m["openings"]

    minx, miny, maxx, maxy = _bounds(walls)
    pad = 40
    plan_w = (maxx - minx) + 2 * pad
    plan_h = (maxy - miny) + 2 * pad
    scale = min(panel_w / plan_w, (panel_h - 60) / plan_h)
    tx = offset_x + (panel_w - plan_w * scale) / 2 - (minx - pad) * scale
    ty = offset_y + 50 + ((panel_h - 60) - plan_h * scale) / 2 - (miny - pad) * scale

    lines = [
        f'<g transform="translate({tx},{ty}) scale({scale})">',
    ]
    # Walls (light gray)
    for w in walls:
        x1, y1 = w["start"]
        x2, y2 = w["end"]
        lines.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#c0c0c0" stroke-width="{1.5/scale}"/>'
        )
    # Openings (colored circles)
    for o in openings:
        cx, cy = o["center"]
        r = o["width"] / 2
        lines.append(
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{color}" fill-opacity="0.55" stroke="{color}" stroke-width="{1.2/scale}"/>'
        )
    lines.append("</g>")

    # Label
    lines.append(
        f'<rect x="{offset_x+10}" y="{offset_y+10}" width="300" height="32" fill="#161b22" stroke="#30363d"/>'
    )
    lines.append(
        f'<text x="{offset_x+22}" y="{offset_y+24}" font-size="13" font-family="ui-monospace,Menlo,monospace" font-weight="600" fill="#e6edf3">{label}</text>'
    )
    lines.append(
        f'<text x="{offset_x+22}" y="{offset_y+38}" font-size="12" font-family="ui-monospace,Menlo,monospace" fill="{color}">{len(openings)} openings</text>'
    )
    return lines


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    # 2 x 2 grid
    panel_w = 560
    panel_h = 380
    gap = 8
    total_w = panel_w * 2 + gap
    total_h = panel_h * 2 + gap

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {total_w} {total_h}" width="1120" style="background:#0e1116">',
        f'<rect x="0" y="0" width="{total_w}" height="{total_h}" fill="#0e1116"/>',
    ]

    for idx, (path, label, color) in enumerate(STAGES):
        col = idx % 2
        row = idx // 2
        ox = col * (panel_w + gap)
        oy = row * (panel_h + gap)
        lines.extend(_panel(Path(path), color, label, panel_w, panel_h, ox, oy))

    lines.append("</svg>")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
