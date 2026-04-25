"""Detect windows in PDF via SVG-native primitives.

A window in CAD plans is typically a pair of parallel thin lines drawn 4-15pt apart
(representing the two faces of the window glass + frame), embedded in a wall opening,
with length 30-200pt. This script extracts ALL line primitives from the PDF, then
groups them into parallel pairs matching the window signature.

Output schema (canonical):
  {
    "model": "detect_windows_svg",
    "pdf": "...",
    "page_rect": [...],
    "totals": {"windows": N},
    "detections": [
      {"center": [x,y], "bbox": [x0,y0,x1,y1], "width_pt": W,
       "orientation": "h"|"v", "wall_thickness_pt": T,
       "line_a": {"start":[..],"end":[..]}, "line_b": {"start":[..],"end":[..]}}
    ],
    "params": {...}
  }
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import fitz

HERE = Path(__file__).resolve().parent
DET_DIR = HERE / "detections"
PDF_DEFAULT = Path(r"E:\Claude\sketchup-mcp\planta_74.pdf")

# Detection params (tuned for typical CAD window signatures at 1:50/1:100)
PARAMS = {
    "min_pair_dist_pt": 4.0,        # below: just wall line thickness
    "max_pair_dist_pt": 11.0,       # above: probably two separate walls
    "min_window_len_pt": 30.0,      # below: probably tick/dimension marker
    "max_window_len_pt": 180.0,     # above: probably wall itself
    "max_endpoint_offset_pt": 6.0,  # endpoints must be near-aligned (windows are co-extensive)
    "angle_tol_deg": 3.0,           # parallel tolerance
    "axis_lock_deg": 6.0,           # only horizontal/vertical lines (skip diagonals)
    "dedup_center_pt": 10.0,        # merge near-duplicate detections
    "exclude_near_long_wall_pt": 4.0,    # if pair lies within this dist of a wall >250pt, drop it
    "long_wall_threshold_pt": 250.0,
}


def line_angle_mod180(p1, p2):
    return math.degrees(math.atan2(p2[1] - p1[1], p2[0] - p1[0])) % 180.0


def line_len(p1, p2):
    return math.hypot(p2[0] - p1[0], p2[1] - p1[1])


def angle_delta(a, b):
    d = abs(a - b) % 180.0
    return min(d, 180.0 - d)


def perp_distance(line_a_start, line_a_end, point):
    """Perpendicular distance from `point` to infinite line through line_a."""
    x1, y1 = line_a_start
    x2, y2 = line_a_end
    px, py = point
    dx, dy = x2 - x1, y2 - y1
    L = math.hypot(dx, dy)
    if L < 1e-9:
        return math.hypot(px - x1, py - y1)
    return abs((py - y1) * dx - (px - x1) * dy) / L


def extract_lines(pdf_path: Path):
    doc = fitz.open(pdf_path)
    page = doc[0]
    drawings = page.get_drawings()
    lines = []
    for d in drawings:
        for it in d.get("items", []):
            if it[0] != "l":
                continue
            p1, p2 = it[1], it[2]
            s = (p1.x, p1.y)
            e = (p2.x, p2.y)
            length = line_len(s, e)
            if length < 5.0:
                continue
            ang = line_angle_mod180(s, e)
            lines.append({
                "start": s, "end": e, "length": length, "angle": ang,
            })
    return lines, page


def classify_axis(angle: float, tol: float):
    """Return 'h' if near 0/180, 'v' if near 90, else None."""
    if angle < tol or angle > 180.0 - tol:
        return "h"
    if abs(angle - 90.0) < tol:
        return "v"
    return None


def detect_windows(lines):
    p = PARAMS
    # Filter to candidates: axis-locked, in length range
    cand = []
    long_walls = []  # for exclusion
    for ln in lines:
        axis = classify_axis(ln["angle"], p["axis_lock_deg"])
        if axis is None:
            continue
        ln["axis"] = axis
        if ln["length"] >= p["long_wall_threshold_pt"]:
            long_walls.append(ln)
        if ln["length"] < p["min_window_len_pt"] or ln["length"] > p["max_window_len_pt"]:
            continue
        cand.append(ln)

    # Index by axis
    h_lines = [ln for ln in cand if ln["axis"] == "h"]
    v_lines = [ln for ln in cand if ln["axis"] == "v"]

    detections = []

    def pair_lines(group, axis):
        # Sort to make pairing iteration shorter; for axis 'h' sort by y
        coord_idx = 1 if axis == "h" else 0
        group_sorted = sorted(group, key=lambda l: (l["start"][coord_idx] + l["end"][coord_idx]) / 2)
        n = len(group_sorted)
        used = [False] * n
        for i in range(n):
            if used[i]:
                continue
            a = group_sorted[i]
            ay = (a["start"][coord_idx] + a["end"][coord_idx]) / 2
            best = None
            best_dist = None
            for j in range(i + 1, n):
                if used[j]:
                    continue
                b = group_sorted[j]
                by = (b["start"][coord_idx] + b["end"][coord_idx]) / 2
                gap = abs(by - ay)
                if gap < p["min_pair_dist_pt"]:
                    continue
                if gap > p["max_pair_dist_pt"]:
                    break  # sorted, no more candidates close
                # Check parallel
                if angle_delta(a["angle"], b["angle"]) > p["angle_tol_deg"]:
                    continue
                # Check endpoint alignment along the line direction
                main = 0 if axis == "h" else 1
                a_lo = min(a["start"][main], a["end"][main])
                a_hi = max(a["start"][main], a["end"][main])
                b_lo = min(b["start"][main], b["end"][main])
                b_hi = max(b["start"][main], b["end"][main])
                # Need significant overlap along main axis
                overlap_lo = max(a_lo, b_lo)
                overlap_hi = min(a_hi, b_hi)
                overlap = overlap_hi - overlap_lo
                if overlap < p["min_window_len_pt"] * 0.6:
                    continue
                # Endpoints offset roughly small (windows: lines are ~same length & co-extensive)
                if abs(a_lo - b_lo) > p["max_endpoint_offset_pt"]:
                    continue
                if abs(a_hi - b_hi) > p["max_endpoint_offset_pt"]:
                    continue
                # Best candidate = closest gap
                if best is None or gap < best_dist:
                    best = j
                    best_dist = gap
            if best is not None:
                used[i] = True
                used[best] = True
                a = group_sorted[i]
                b = group_sorted[best]
                main = 0 if axis == "h" else 1
                cross = 1 - main
                a_lo = min(a["start"][main], a["end"][main])
                a_hi = max(a["start"][main], a["end"][main])
                b_lo = min(b["start"][main], b["end"][main])
                b_hi = max(b["start"][main], b["end"][main])
                lo = (a_lo + b_lo) / 2
                hi = (a_hi + b_hi) / 2
                ac = (a["start"][cross] + a["end"][cross]) / 2
                bc = (b["start"][cross] + b["end"][cross]) / 2
                cross_center = (ac + bc) / 2
                width_pt = hi - lo
                thickness = abs(bc - ac)
                if axis == "h":
                    cx, cy = (lo + hi) / 2, cross_center
                    bbox = [lo, min(ac, bc), hi, max(ac, bc)]
                else:
                    cx, cy = cross_center, (lo + hi) / 2
                    bbox = [min(ac, bc), lo, max(ac, bc), hi]
                detections.append({
                    "center": [round(cx, 2), round(cy, 2)],
                    "bbox": [round(v, 2) for v in bbox],
                    "width_pt": round(width_pt, 2),
                    "orientation": axis,
                    "wall_thickness_pt": round(thickness, 2),
                    "line_a": {"start": [round(a["start"][0], 2), round(a["start"][1], 2)],
                               "end":   [round(a["end"][0], 2),   round(a["end"][1], 2)]},
                    "line_b": {"start": [round(b["start"][0], 2), round(b["start"][1], 2)],
                               "end":   [round(b["end"][0], 2),   round(b["end"][1], 2)]},
                })

    pair_lines(h_lines, "h")
    pair_lines(v_lines, "v")

    # Filter A: drop detections whose center sits ON a long wall (wall double-lines)
    filtered = []
    for det in detections:
        cx, cy = det["center"]
        on_long_wall = False
        for lw in long_walls:
            if lw["axis"] != det["orientation"]:
                continue
            d = perp_distance(lw["start"], lw["end"], (cx, cy))
            if d > p["exclude_near_long_wall_pt"]:
                continue
            main = 0 if det["orientation"] == "h" else 1
            lo = min(lw["start"][main], lw["end"][main])
            hi = max(lw["start"][main], lw["end"][main])
            cv = cx if main == 0 else cy
            if lo - 5 <= cv <= hi + 5:
                on_long_wall = True
                break
        if not on_long_wall:
            filtered.append(det)

    # Filter B: drop detections that belong to a stack of 3+ near-identical parallel lines
    # (signature of cabinet/fridge/blinds hatching, NOT a window).
    # We look at all axis-aligned candidate lines (not just paired) and count how many
    # share the same main-axis bbox (within 6pt) at stepped cross-axis offsets.
    cand_by_axis = {"h": h_lines, "v": v_lines}
    final = []
    for det in filtered:
        axis = det["orientation"]
        main = 0 if axis == "h" else 1
        cross = 1 - main
        # Cross-axis center of the window pair
        cx = det["center"][cross]
        # Main-axis bbox
        m_lo = det["bbox"][main]
        m_hi = det["bbox"][main + 2]
        # Count parallel lines anywhere in cross-axis ±25pt with similar main-axis span
        siblings = 0
        for ln in cand_by_axis[axis]:
            ln_cross = (ln["start"][cross] + ln["end"][cross]) / 2
            if abs(ln_cross - cx) > 25.0:
                continue
            ln_lo = min(ln["start"][main], ln["end"][main])
            ln_hi = max(ln["start"][main], ln["end"][main])
            if abs(ln_lo - m_lo) <= 6.0 and abs(ln_hi - m_hi) <= 6.0:
                siblings += 1
        # The pair contributes 2; >=3 extra means it's a hatched block
        if siblings <= 3:  # tolerate a small extra (e.g. mullion line)
            final.append(det)

    # Dedup by center proximity
    deduped = []
    for det in final:
        keep = True
        for kd in deduped:
            if math.hypot(det["center"][0] - kd["center"][0],
                          det["center"][1] - kd["center"][1]) < PARAMS["dedup_center_pt"]:
                keep = False
                break
        if keep:
            deduped.append(det)
    return deduped


def main():
    pdf = PDF_DEFAULT
    if len(sys.argv) > 1:
        pdf = Path(sys.argv[1])
    basename = "final_planta_74"

    t0 = time.time()
    lines, page = extract_lines(pdf)
    detections = detect_windows(lines)
    elapsed = round(time.time() - t0, 3)

    out = {
        "model": "detect_windows_svg",
        "pdf": str(pdf),
        "page_rect": [page.rect.x0, page.rect.y0, page.rect.x1, page.rect.y1],
        "totals": {
            "windows": len(detections),
            "lines_extracted": len(lines),
        },
        "detections": detections,
        "params": PARAMS,
        "latency_seconds": elapsed,
    }

    DET_DIR.mkdir(exist_ok=True)
    out_file = DET_DIR / f"windows_svg_native_{basename}.json"
    out_file.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"saved: {out_file}")
    print(f"windows: {len(detections)}  (lines_scanned={len(lines)}, latency={elapsed}s)")
    if detections:
        print("first 3:")
        for d in detections[:3]:
            print(f"  center={d['center']}  width={d['width_pt']}pt  "
                  f"orient={d['orientation']}  thickness={d['wall_thickness_pt']}pt")
    return out


if __name__ == "__main__":
    main()
