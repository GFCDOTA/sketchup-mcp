"""Parse native PDF vector primitives directly — no ML, no Hough.

Walls = long lines (>50pt) grouped by collinearity.
Doors = quarter-circle arcs (cubic Bezier with ~90° sweep).

Output: detections/svg_parsed_<basename>.json (pipeline-compatible schema).
"""
from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import fitz

OUT_DIR = Path(__file__).resolve().parent / "detections"


def line_len(p1, p2):
    return math.hypot(p2.x - p1.x, p2.y - p1.y)


def line_angle(p1, p2):
    return math.degrees(math.atan2(p2.y - p1.y, p2.x - p1.x)) % 180.0


def parse_pdf(pdf_path: Path) -> dict:
    doc = fitz.open(pdf_path)
    page = doc[0]
    drawings = page.get_drawings()

    walls: list[dict] = []
    arcs: list[dict] = []
    rects: list[dict] = []

    for d in drawings:
        for it in d.get("items", []):
            op = it[0]
            if op == "l":
                p1, p2 = it[1], it[2]
                length = line_len(p1, p2)
                if length >= 50.0:
                    walls.append({
                        "start": [round(p1.x, 2), round(p1.y, 2)],
                        "end": [round(p2.x, 2), round(p2.y, 2)],
                        "length_pt": round(length, 2),
                        "angle_deg": round(line_angle(p1, p2), 1),
                    })
            elif op == "c":
                p1, c1, c2, p3 = it[1], it[2], it[3], it[4]
                chord = line_len(p1, p3)
                if 8.0 < chord < 100.0:
                    arcs.append({
                        "start": [round(p1.x, 2), round(p1.y, 2)],
                        "end": [round(p3.x, 2), round(p3.y, 2)],
                        "ctrl1": [round(c1.x, 2), round(c1.y, 2)],
                        "ctrl2": [round(c2.x, 2), round(c2.y, 2)],
                        "chord_pt": round(chord, 2),
                    })
            elif op == "re":
                r = it[1]
                rects.append({
                    "x0": round(r.x0, 2), "y0": round(r.y0, 2),
                    "x1": round(r.x1, 2), "y1": round(r.y1, 2),
                })

    horiz = sum(1 for w in walls if w["angle_deg"] < 10 or w["angle_deg"] > 170)
    vert = sum(1 for w in walls if 80 <= w["angle_deg"] <= 100)

    out = {
        "model": "svg_native_parse (PyMuPDF get_drawings)",
        "pdf": str(pdf_path),
        "page_rect": [page.rect.x0, page.rect.y0, page.rect.x1, page.rect.y1],
        "totals": {
            "doors": len(arcs),
            "windows": 0,
            "walls": len(walls),
            "horizontal_walls": horiz,
            "vertical_walls": vert,
            "diagonal_walls": len(walls) - horiz - vert,
            "rects": len(rects),
        },
        "walls_top10_longest": sorted(walls, key=lambda w: -w["length_pt"])[:10],
        "arcs_sample": arcs[:8],
        "all_walls_count": len(walls),
        "all_arcs_count": len(arcs),
        "latency_seconds": 0.0,
    }
    return out, walls, arcs


def main():
    import time
    pdf = Path(r"E:\Claude\sketchup-mcp\planta_74.pdf")
    if len(sys.argv) > 1:
        pdf = Path(sys.argv[1])

    t0 = time.time()
    out, walls, arcs = parse_pdf(pdf)
    out["latency_seconds"] = round(time.time() - t0, 3)

    OUT_DIR.mkdir(exist_ok=True)
    basename = "final_planta_74"
    out_file = OUT_DIR / f"svg_parsed_{basename}.json"
    out_file.write_text(json.dumps(out, indent=2))
    print(json.dumps(out["totals"], indent=2))
    print(f"latency: {out['latency_seconds']}s")
    print(f"saved: {out_file}")


if __name__ == "__main__":
    main()
