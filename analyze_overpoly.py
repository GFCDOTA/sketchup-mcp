"""Geometric analysis of 48 rooms extracted from planta_74.pdf.

Produces:
 - Per-room metrics (area, vertices, perimeter, bbox, aspect, compactness).
 - Category classification (legitimate / sliver / thin / nested / degenerate).
 - Threshold sweep (counts of surviving rooms under different filter combos).
 - Categorized overlay PNG painted per category.
 - JSON dump of the full per-room table for docs ingestion.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).parent
RUN_DIR = ROOT / "runs" / "overpoly_audit"
OBS_PATH = RUN_DIR / "observed_model.json"
TOPO_PATH = RUN_DIR / "room_topology_check.json"
OUT_METRICS = RUN_DIR / "per_room_metrics.json"
OUT_SWEEP = RUN_DIR / "threshold_sweep.json"
OUT_PNG = RUN_DIR / "over_polygon_categorized.png"
OUT_SVG = RUN_DIR / "over_polygon_categorized.svg"


def polygon_perimeter(pts: list[list[float]]) -> float:
    n = len(pts)
    if n < 2:
        return 0.0
    s = 0.0
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        s += math.hypot(x2 - x1, y2 - y1)
    return s


def polygon_bbox(pts: list[list[float]]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def polygon_area_signed(pts: list[list[float]]) -> float:
    n = len(pts)
    if n < 3:
        return 0.0
    s = 0.0
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return s * 0.5


def categorize(m: dict) -> str:
    verts = m["vertices"]
    area = m["area"]
    aspect = m["aspect_ratio"]
    compact = m["compactness"]

    # sliver triangular: 3 vertices AND (small area OR high aspect)
    if verts == 3:
        if area < 2000 or aspect > 3:
            return "sliver_triangle"
        return "small_triangle"  # rare legitimate 3-vertex

    # thin strip: 4 verts but very stretched
    if verts == 4 and aspect > 5:
        return "thin_strip"

    # degenerate: low compactness regardless of vertex count
    if compact < 0.10:
        return "degenerate"

    # very small (area < 500) w/o other flags — probable gap artifact
    if area < 500:
        return "tiny"

    # borderline legitimate: small rooms (closet-size) in 500-1500 range
    if area < 1500:
        return "borderline"

    return "legitimate"


CATEGORY_COLORS = {
    "legitimate": (60, 160, 80),        # green
    "borderline": (230, 210, 40),       # yellow
    "sliver_triangle": (210, 40, 40),   # red
    "thin_strip": (230, 120, 30),       # orange
    "degenerate": (140, 60, 170),       # purple
    "small_triangle": (150, 150, 150),  # gray
    "tiny": (100, 100, 100),            # dark gray
}


def main() -> None:
    obs = json.loads(OBS_PATH.read_text(encoding="utf-8"))
    topo = json.loads(TOPO_PATH.read_text(encoding="utf-8"))

    bounds = obs["bounds"]["pages"][0] if "pages" in obs["bounds"] else obs["bounds"]
    print("bounds sample:", bounds)

    rooms = obs["rooms"]
    topo_by_id = {c["room_id"]: c for c in topo["checks"]}
    nested_pairs = topo.get("nested_pairs", [])
    nested_ids = {pid for pair in nested_pairs for pid in pair}

    metrics = []
    for r in rooms:
        poly = r["polygon"]
        verts = len(poly)
        perim = polygon_perimeter(poly)
        area = r["area"]
        bx0, by0, bx1, by1 = polygon_bbox(poly)
        w = max(bx1 - bx0, 1e-6)
        h = max(by1 - by0, 1e-6)
        aspect = max(w, h) / min(w, h)
        # isoperimetric compactness: 4*pi*A / P^2 (1.0 = circle, 0.785 = square-ish)
        compact = (4 * math.pi * area) / (perim ** 2) if perim > 0 else 0.0
        m = {
            "room_id": r["room_id"],
            "area": round(area, 2),
            "vertices": verts,
            "perimeter": round(perim, 2),
            "bbox_w": round(w, 2),
            "bbox_h": round(h, 2),
            "aspect_ratio": round(aspect, 3),
            "compactness": round(compact, 4),
            "nested": r["room_id"] in nested_ids,
            "topo_status": topo_by_id.get(r["room_id"], {}).get("status", "?"),
            "polygon": poly,
            "bbox": [bx0, by0, bx1, by1],
            "centroid": r.get("centroid"),
        }
        m["category"] = categorize(m)
        metrics.append(m)

    # write metrics (without polygons to keep small)
    slim = []
    for m in metrics:
        s = {k: v for k, v in m.items() if k not in ("polygon", "bbox")}
        slim.append(s)
    OUT_METRICS.write_text(json.dumps(slim, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT_METRICS}")

    # distribution
    from collections import Counter
    vcount = Counter(m["vertices"] for m in metrics)
    ccount = Counter(m["category"] for m in metrics)
    print("\nvertex histogram:", dict(sorted(vcount.items())))
    print("category histogram:", dict(ccount))

    # threshold sweep
    def count_surviving(pred) -> int:
        return sum(1 for m in metrics if pred(m))

    sweeps = []

    def add(name, desc, pred):
        n = count_surviving(pred)
        surviving_ids = [m["room_id"] for m in metrics if pred(m)]
        sweeps.append({"scenario": name, "description": desc, "surviving_count": n, "surviving_ids": surviving_ids})

    # Baseline
    add("baseline", "No filter", lambda m: True)

    # Area-only cuts
    add("area_gte_500", "area >= 500", lambda m: m["area"] >= 500)
    add("area_gte_1000", "area >= 1000", lambda m: m["area"] >= 1000)
    add("area_gte_1500", "area >= 1500", lambda m: m["area"] >= 1500)
    add("area_gte_2000", "area >= 2000", lambda m: m["area"] >= 2000)

    # Vertex cuts
    add("vertices_gte_4", "vertices >= 4", lambda m: m["vertices"] >= 4)

    # Combined recommended filters
    add("drop_tri_under_1500",
        "drop (vertices==3 AND area<1500)",
        lambda m: not (m["vertices"] == 3 and m["area"] < 1500))
    add("drop_aspect_gt_5",
        "drop (aspect>5)",
        lambda m: m["aspect_ratio"] <= 5)
    add("drop_compact_lt_010",
        "drop (compactness<0.10)",
        lambda m: m["compactness"] >= 0.10)
    add("drop_compact_lt_015",
        "drop (compactness<0.15)",
        lambda m: m["compactness"] >= 0.15)

    # Combined strong filter
    add("combo_strict",
        "area>=1000 AND (vertices>=4 OR area>=2000) AND compactness>=0.15 AND aspect<=5",
        lambda m: m["area"] >= 1000
                  and (m["vertices"] >= 4 or m["area"] >= 2000)
                  and m["compactness"] >= 0.15
                  and m["aspect_ratio"] <= 5)

    add("combo_recommended",
        "area>=1000 AND (vertices>=4 OR compactness>=0.25) AND aspect<=6",
        lambda m: m["area"] >= 1000
                  and (m["vertices"] >= 4 or m["compactness"] >= 0.25)
                  and m["aspect_ratio"] <= 6)

    add("combo_permissive",
        "area>=800 AND (compactness>=0.10 OR area>=2500)",
        lambda m: m["area"] >= 800
                  and (m["compactness"] >= 0.10 or m["area"] >= 2500))

    add("combo_renan_draft",
        "min_area=1000 AND (vertices<4 OR compactness<0.15) => drop",
        lambda m: not (m["area"] < 1000 or m["vertices"] < 4 or m["compactness"] < 0.15) or m["area"] >= 1000)
    # Clarify intent: Renan's draft = drop if (area<1000) OR (vertices<4 AND area<threshold) OR (compactness<0.15)
    # The sentence "min_area=1000 AND (vertices<4 OR compactness<0.15)" as filter predicate -> drop when BOTH conditions true.
    # Reinterpret correctly:
    add("combo_renan_draft_v2",
        "drop if (area<1000) AND (vertices<4 OR compactness<0.15)",
        lambda m: not (m["area"] < 1000 and (m["vertices"] < 4 or m["compactness"] < 0.15)))

    # Finer targets for reducing to 14-18
    add("combo_agent13_A",
        "drop if compactness<0.20 OR (vertices==3 AND area<3000)",
        lambda m: m["compactness"] >= 0.20 and not (m["vertices"] == 3 and m["area"] < 3000))

    add("combo_agent13_B",
        "drop if compactness<0.25 OR aspect>6",
        lambda m: m["compactness"] >= 0.25 and m["aspect_ratio"] <= 6)

    add("combo_agent13_C",
        "keep if area>=1500 AND compactness>=0.25 AND aspect<=6",
        lambda m: m["area"] >= 1500 and m["compactness"] >= 0.25 and m["aspect_ratio"] <= 6)

    add("combo_agent13_D",
        "keep if area>=2000 AND compactness>=0.20 AND aspect<=5",
        lambda m: m["area"] >= 2000 and m["compactness"] >= 0.20 and m["aspect_ratio"] <= 5)

    add("combo_agent13_E",
        "keep if (vertices>=4 AND aspect<=5 AND compactness>=0.20) OR (area>=5000 AND compactness>=0.25)",
        lambda m: (m["vertices"] >= 4 and m["aspect_ratio"] <= 5 and m["compactness"] >= 0.20)
                  or (m["area"] >= 5000 and m["compactness"] >= 0.25))

    add("combo_RECOMMENDED",
        "keep if area>=2000 AND compactness>=0.20 AND aspect<=6",
        lambda m: m["area"] >= 2000 and m["compactness"] >= 0.20 and m["aspect_ratio"] <= 6)

    add("combo_RECOMMENDED_strict",
        "keep if area>=2000 AND vertices>=4 AND compactness>=0.25 AND aspect<=5",
        lambda m: m["area"] >= 2000 and m["vertices"] >= 4
                  and m["compactness"] >= 0.25 and m["aspect_ratio"] <= 5)

    # The ACTUAL RECOMMENDED filter — tuned to match 20 legitimate rooms
    add("combo_FINAL",
        "keep if area>=1500 AND vertices>=4 AND compactness>=0.20 AND aspect<=6",
        lambda m: m["area"] >= 1500 and m["vertices"] >= 4
                  and m["compactness"] >= 0.20 and m["aspect_ratio"] <= 6)

    add("combo_FINAL_v2",
        "keep if area>=1500 AND vertices>=4 AND compactness>=0.25 AND aspect<=6",
        lambda m: m["area"] >= 1500 and m["vertices"] >= 4
                  and m["compactness"] >= 0.25 and m["aspect_ratio"] <= 6)

    add("combo_FINAL_v3",
        "keep if (area>=1500 AND vertices>=4 AND compactness>=0.20 AND aspect<=6) OR (area>=5000 AND compactness>=0.20)",
        lambda m: (m["area"] >= 1500 and m["vertices"] >= 4
                   and m["compactness"] >= 0.20 and m["aspect_ratio"] <= 6)
                  or (m["area"] >= 5000 and m["compactness"] >= 0.20))

    # Simpler two-clause filter
    add("combo_two_clause",
        "drop if (vertices<4) OR (compactness<0.20) OR (aspect>6)",
        lambda m: m["vertices"] >= 4 and m["compactness"] >= 0.20 and m["aspect_ratio"] <= 6)

    add("combo_three_clause",
        "drop if (vertices<4 AND compactness<0.30) OR (aspect>6) OR (area<1000)",
        lambda m: not ((m["vertices"] < 4 and m["compactness"] < 0.30) or m["aspect_ratio"] > 6 or m["area"] < 1000))

    OUT_SWEEP.write_text(json.dumps(sweeps, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {OUT_SWEEP}")
    print("\nthreshold sweep results:")
    print(f"{'scenario':<30} {'surviving':>10}  description")
    for s in sweeps:
        print(f"{s['scenario']:<30} {s['surviving_count']:>10}  {s['description']}")

    # Render categorized overlay
    render_overlay(metrics, bounds)

    # Summary per category with id list
    print("\nrooms by category:")
    for cat in ["legitimate", "borderline", "sliver_triangle", "thin_strip",
                "degenerate", "small_triangle", "tiny"]:
        ids = sorted(
            [m["room_id"] for m in metrics if m["category"] == cat],
            key=lambda s: int(s.split("-")[1]),
        )
        print(f"  [{cat}] ({len(ids)}): {ids}")


def render_overlay(metrics, bounds):
    # bounds has form {min_x, min_y, max_x, max_y, page_index}
    x0 = bounds["min_x"]
    x1 = bounds["max_x"]
    y0 = bounds["min_y"]
    y1 = bounds["max_y"]
    pad = 30
    scale = 2.0  # upscale for readability

    W = int((x1 - x0) * scale + 2 * pad)
    H = int((y1 - y0) * scale + 2 * pad)

    def tx(pt):
        return (pad + (pt[0] - x0) * scale, pad + (pt[1] - y0) * scale)

    img = Image.new("RGB", (W, H), (245, 245, 245))
    draw = ImageDraw.Draw(img, "RGBA")

    # Try to load a font
    try:
        font = ImageFont.truetype("arial.ttf", 11)
        font_small = ImageFont.truetype("arial.ttf", 9)
    except Exception:
        font = ImageFont.load_default()
        font_small = font

    # Draw each polygon
    for m in metrics:
        color = CATEGORY_COLORS.get(m["category"], (100, 100, 100))
        pts = [tx(p) for p in m["polygon"]]
        if len(pts) >= 3:
            fill = color + (90,)
            draw.polygon(pts, fill=fill, outline=color + (255,))
        # label with room number + vertices
        num = m["room_id"].split("-")[1]
        cx, cy = m["centroid"] if m["centroid"] else (sum(p[0] for p in pts)/len(pts), sum(p[1] for p in pts)/len(pts))
        if m["centroid"]:
            label_xy = tx(m["centroid"])
        else:
            label_xy = (cx, cy)
        draw.text((label_xy[0] - 6, label_xy[1] - 6), num, fill=(20, 20, 20), font=font)

    # Legend
    legend_x = 12
    legend_y = 12
    box = 14
    for cat, color in CATEGORY_COLORS.items():
        n = sum(1 for m in metrics if m["category"] == cat)
        draw.rectangle([legend_x, legend_y, legend_x + box, legend_y + box],
                       fill=color + (255,), outline=(50, 50, 50))
        draw.text((legend_x + box + 6, legend_y),
                  f"{cat} ({n})", fill=(30, 30, 30), font=font_small)
        legend_y += box + 4

    img.save(OUT_PNG)
    print(f"wrote {OUT_PNG}")


if __name__ == "__main__":
    main()
