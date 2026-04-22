"""Render SVG overlay showing dropped vs kept openings.

Usage (from repo root):
    python scripts/plot_openings_comparison.py \\
        --before runs/openings_refine_baseline/observed_model.json \\
        --after  runs/openings_refine_v1_a/observed_model.json \\
        --out    runs/openings_refine_v1_a/openings_diff.svg
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def _bounds(walls: list[dict]) -> tuple[float, float, float, float]:
    xs, ys = [], []
    for w in walls:
        xs.extend([w["start"][0], w["end"][0]])
        ys.extend([w["start"][1], w["end"][1]])
    return min(xs), min(ys), max(xs), max(ys)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", required=True, type=Path)
    parser.add_argument("--after", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    before = json.loads(args.before.read_text(encoding="utf-8"))
    after = json.loads(args.after.read_text(encoding="utf-8"))

    before_openings = {o["opening_id"]: o for o in before["openings"]}
    after_ids = {o["opening_id"] for o in after["openings"]}
    dropped_ids = set(before_openings.keys()) - after_ids

    walls = after["walls"]
    minx, miny, maxx, maxy = _bounds(walls)
    pad = 20
    vb_x, vb_y = minx - pad, miny - pad
    vb_w, vb_h = (maxx - minx) + 2 * pad, (maxy - miny) + 2 * pad

    lines = []
    lines.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb_x} {vb_y} {vb_w} {vb_h}" '
        f'width="1000" style="background:#ffffff">'
    )

    # Walls (gray)
    for w in walls:
        x1, y1 = w["start"]
        x2, y2 = w["end"]
        lines.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#aaaaaa" stroke-width="1"/>'
        )

    # Dropped first (red, under)
    for oid in dropped_ids:
        o = before_openings[oid]
        cx, cy = o["center"]
        r = o["width"] / 2
        lines.append(
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="#d6604d" fill-opacity="0.55" '
            f'stroke="#67001f" stroke-width="1"/>'
        )

    # Kept on top (green)
    for oid, o in before_openings.items():
        if oid in dropped_ids:
            continue
        cx, cy = o["center"]
        r = o["width"] / 2
        lines.append(
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" '
            f'stroke="#1b7837" stroke-width="2"/>'
        )

    # Legend
    lx, ly = vb_x + 10, vb_y + 20
    lines.append(
        f'<rect x="{lx}" y="{ly}" width="180" height="48" fill="white" stroke="#333" stroke-width="0.5"/>'
    )
    lines.append(
        f'<circle cx="{lx+12}" cy="{ly+14}" r="6" fill="none" stroke="#1b7837" stroke-width="2"/>'
    )
    lines.append(
        f'<text x="{lx+25}" y="{ly+18}" font-size="10" fill="#333">kept: {len(before_openings)-len(dropped_ids)}</text>'
    )
    lines.append(
        f'<circle cx="{lx+12}" cy="{ly+34}" r="6" fill="#d6604d" fill-opacity="0.55" stroke="#67001f" stroke-width="1"/>'
    )
    lines.append(
        f'<text x="{lx+25}" y="{ly+38}" font-size="10" fill="#333">dropped (orphan): {len(dropped_ids)}</text>'
    )

    lines.append("</svg>")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines), encoding="utf-8")
    kept = len(before_openings) - len(dropped_ids)
    print(f"wrote {args.out} (kept={kept}, dropped={len(dropped_ids)})")


if __name__ == "__main__":
    main()
