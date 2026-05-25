"""Diagnostic: centerline + shapely.polygonize with seed aggregation.

FP-014 §"Opção A" alternative motor. Where ``polygonize_rooms.polygonize_rooms``
models walls as solid boxes and subtracts them from the envelope
(``unary_union(boxes) → env.difference()``), this tool models the floor
plan as a planar line graph (``walls.centerlines + soft_barriers +
door_bridges → shapely.polygonize``).

The two approaches differ:

- Box-difference yields fewer, larger cells. Requires the wall network
  to topologically enclose every room. Misses interior cells when wall
  fragments don't quite touch (or when room dividers are drawn as
  stroked thin lines rather than filled rectangles).
- Centerline polygonize yields more, smaller cells. Tolerant of
  fragmented walls but over-splits rooms when hatching/cerâmica
  patterns intrude. Needs seed-based aggregation: cells adjacent to
  the same seed (and not separated by a wall/barrier/bridge) collapse
  into one room.

This diagnostic does both and reports:
- Cell count + per-cell area for each approach
- For each label seed, the cells that map to it
- An overlay PNG showing the cell decomposition

Pure diagnostic — does NOT mutate any pipeline output. Use as evidence
for the next-cycle threshold/algorithm decision.

Usage:
    python -m tools.centerline_polygonize_diagnostic planta_74.pdf \\
        --out runs/audit/planta_74_centerline_diagnostic.json
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Polygon as MplPolygon
from shapely.geometry import LineString, MultiLineString, Point, Polygon, box
from shapely.ops import polygonize, unary_union

THIS = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS))
from polygonize_rooms import _detect_door_bridges, polygonize_rooms  # noqa: E402, I001


def _run_stage(module: str, args: list[str]) -> str:
    """Run a pipeline stage as subprocess; return stdout. Raises on error."""
    cmd = [sys.executable, "-m", module] + args
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return res.stdout


def build_consensus_and_labels(pdf_path: Path,
                                tmp: Path) -> tuple[dict, list[dict]]:
    """Run stages 1 + 2 of the canonical pipeline against the PDF."""
    c0 = tmp / "c0.json"
    labels_path = tmp / "labels.json"
    _run_stage("tools.build_vector_consensus",
               [str(pdf_path), "--out", str(c0), "--detect-openings"])
    _run_stage("tools.extract_room_labels",
               [str(pdf_path), "--out", str(labels_path)])
    consensus = json.loads(c0.read_text())
    labels = json.loads(labels_path.read_text())
    return consensus, labels


# --- box-difference (existing approach) -------------------------------------

def cells_via_box_diff(consensus: dict,
                       door_max: float = 150.0) -> list[Polygon]:
    """Run polygonize_rooms.polygonize_rooms and return cells as Polygons."""
    raw, _bridges = polygonize_rooms(consensus, door_min_pts=15.0,
                                      door_max_pts=door_max)
    return [Polygon(c["polygon_pts"]) for c in raw]


# --- centerline polygonize (alternative) ------------------------------------

def cells_via_centerline(consensus: dict,
                         door_max: float = 150.0,
                         min_area_factor: float = 12.0) -> list[Polygon]:
    """Use wall centerlines + soft_barriers + door bridges as the line
    graph for shapely.polygonize. Filters cells by min_area + envelope
    containment + heuristic 'cell mostly outside wall_union'.
    """
    walls = consensus["walls"]
    sb = consensus.get("soft_barriers", [])
    t = float(consensus["wall_thickness_pts"])

    lines: list[LineString] = []
    for w in walls:
        lines.append(LineString([w["start"], w["end"]]))
    for b in sb:
        pts = b.get("polyline_pts", [])
        if len(pts) >= 2:
            try:
                lines.append(LineString(pts))
            except Exception:
                continue
    bridges = _detect_door_bridges(walls, t, 15.0, door_max)
    for b in bridges:
        lines.append(LineString([b["start"], b["end"]]))

    if not lines:
        return []

    noded = unary_union(MultiLineString(lines))
    raw_cells = list(polygonize(noded))

    # Filter by envelope containment + min area
    region = consensus.get("planta_region")
    if region:
        env = box(region[0] - 2, region[1] - 2,
                  region[2] + 2, region[3] + 2)
        env_b = env.bounds
    else:
        env_b = None

    min_area = min_area_factor * t * t
    out: list[Polygon] = []
    eps = 1e-3
    for cell in raw_cells:
        if cell.area < min_area:
            continue
        if env_b is not None:
            cb = cell.bounds
            tae = (cb[0] <= env_b[0] + eps and cb[2] >= env_b[2] - eps
                   and cb[1] <= env_b[1] + eps and cb[3] >= env_b[3] - eps)
            if tae:
                continue
        out.append(cell)
    return out


# --- seed → cell mapping ----------------------------------------------------

def map_seeds_to_cells(cells: list[Polygon],
                       labels: list[dict],
                       expected_rooms: set[str] | None,
                       wall_thickness_pts: float) -> dict[str, Any]:
    """Map each label's seed_pt to the cell containing it. Returns
    {label_name: cell_idx | None} plus aggregate stats."""
    if expected_rooms is None:
        expected_rooms = {lb["name"] for lb in labels}
    mapped: dict[str, int | None] = {}
    for lb in labels:
        if lb["name"] not in expected_rooms:
            continue
        sp = lb.get("seed_pt")
        if not sp:
            mapped[lb["name"]] = None
            continue
        pt = Point(float(sp[0]), float(sp[1]))
        found: int | None = None
        for i, cell in enumerate(cells):
            if cell.contains(pt):
                found = i
                break
        if found is None:
            best, best_d = None, float("inf")
            for i, cell in enumerate(cells):
                d = cell.centroid.distance(pt)
                if d < best_d:
                    best_d = d
                    best = i
            if best is not None and best_d <= 3.0 * wall_thickness_pts:
                found = best
        mapped[lb["name"]] = found

    # Aggregate: how many seeds share a cell?
    cell_to_rooms: dict[int, list[str]] = {}
    for name, ci in mapped.items():
        if ci is None:
            continue
        cell_to_rooms.setdefault(ci, []).append(name)
    n_distinct_cells = len(cell_to_rooms)
    n_seeds_mapped = sum(1 for v in mapped.values() if v is not None)
    n_seeds_dropped = sum(1 for v in mapped.values() if v is None)
    merged_cells = {ci: rs for ci, rs in cell_to_rooms.items() if len(rs) > 1}
    return {
        "mapped": mapped,
        "n_expected": len(expected_rooms),
        "n_seeds_mapped": n_seeds_mapped,
        "n_seeds_dropped": n_seeds_dropped,
        "n_distinct_cells": n_distinct_cells,
        "n_merged_cells": len(merged_cells),
        "merged_cells": {str(k): v for k, v in merged_cells.items()},
        "cell_to_rooms": {str(k): v for k, v in cell_to_rooms.items()},
    }


# --- render -----------------------------------------------------------------

def render_comparison(consensus: dict,
                      box_cells: list[Polygon],
                      box_mapping: dict,
                      cl_cells: list[Polygon],
                      cl_mapping: dict,
                      labels: list[dict],
                      out_png: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(20, 12), dpi=150,
                              facecolor="white")
    title_left = (f"box-difference: {len(box_cells)} cells, "
                  f"{box_mapping['n_distinct_cells']} distinct rooms")
    title_right = (f"centerline-polygonize: {len(cl_cells)} cells, "
                   f"{cl_mapping['n_distinct_cells']} distinct rooms")
    for ax, cells, mapping, title in (
        (axes[0], box_cells, box_mapping, title_left),
        (axes[1], cl_cells, cl_mapping, title_right),
    ):
        # Color cells by which seeds they contain
        cell_to_rooms = mapping["cell_to_rooms"]
        cmap = plt.get_cmap("tab20")
        for i, cell in enumerate(cells):
            if cell.is_empty or cell.geom_type != "Polygon":
                continue
            rooms_in_cell = cell_to_rooms.get(str(i), [])
            color = cmap(i % 20) if rooms_in_cell else "#f0f0f0"
            alpha = 0.6 if rooms_in_cell else 0.2
            pts = list(cell.exterior.coords)
            ax.add_patch(MplPolygon(pts, closed=True, facecolor=color,
                                     edgecolor="#444", linewidth=0.6,
                                     alpha=alpha))
            if rooms_in_cell:
                cx = float(np.mean([p[0] for p in pts]))
                cy = float(np.mean([p[1] for p in pts]))
                ax.text(cx, cy, " | ".join(rooms_in_cell), fontsize=6,
                         ha="center", va="center", color="#222",
                         wrap=True)
        # Plot walls as black outlines
        t = consensus["wall_thickness_pts"]
        for w in consensus["walls"]:
            s, e = w["start"], w["end"]
            if w["orientation"] == "h":
                cy = s[1]
                x0, x1 = sorted([s[0], e[0]])
                ax.add_patch(MplPolygon(
                    [(x0, cy - t/2), (x1, cy - t/2),
                     (x1, cy + t/2), (x0, cy + t/2)],
                    closed=True, facecolor="#222", edgecolor="none",
                    alpha=0.7))
            else:
                cx = s[0]
                y0, y1 = sorted([s[1], e[1]])
                ax.add_patch(MplPolygon(
                    [(cx - t/2, y0), (cx + t/2, y0),
                     (cx + t/2, y1), (cx - t/2, y1)],
                    closed=True, facecolor="#222", edgecolor="none",
                    alpha=0.7))
        # Seeds
        for lb in labels:
            sp = lb.get("seed_pt")
            if not sp:
                continue
            ax.plot(sp[0], sp[1], "ro", markersize=4)
        ax.set_aspect("equal")
        ax.autoscale_view()
        ax.set_axis_off()
        ax.set_title(title, fontsize=11, pad=8)
    plt.tight_layout()
    plt.savefig(out_png, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"[ok] comparison -> {out_png}")


# --- main -------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--out", type=Path, default=None,
                    help="Output JSON path (default: <stem>_centerline_diagnostic.json)")
    ap.add_argument("--out-png", type=Path, default=None,
                    help="Output comparison PNG (default: <stem>_centerline_diagnostic.png)")
    ap.add_argument("--door-max", type=float, default=150.0)
    args = ap.parse_args()

    stem = args.pdf.stem
    out_json = args.out or args.pdf.with_name(f"{stem}_centerline_diagnostic.json")
    out_png = (args.out_png
                or args.pdf.with_name(f"{stem}_centerline_diagnostic.png"))
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_png.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        consensus, labels = build_consensus_and_labels(args.pdf, tmp)

    expected_rooms = {lb["name"] for lb in labels
                       if not lb["name"].startswith(("ACARTONADO",
                                                       "CONDICIONADO",
                                                       "SERA "))}
    t = float(consensus["wall_thickness_pts"])

    box_cells = cells_via_box_diff(consensus, door_max=args.door_max)
    cl_cells = cells_via_centerline(consensus, door_max=args.door_max)
    box_mapping = map_seeds_to_cells(box_cells, labels, expected_rooms, t)
    cl_mapping = map_seeds_to_cells(cl_cells, labels, expected_rooms, t)

    box_areas = sorted([c.area for c in box_cells], reverse=True)
    cl_areas = sorted([c.area for c in cl_cells], reverse=True)
    report = {
        "pdf_path": str(args.pdf),
        "expected_rooms": sorted(expected_rooms),
        "wall_thickness_pts": t,
        "door_max_pts": args.door_max,
        "box_difference": {
            "n_cells": len(box_cells),
            "areas_descending": box_areas[:20],
            "area_median": statistics.median(box_areas) if box_areas else 0,
            **box_mapping,
        },
        "centerline_polygonize": {
            "n_cells": len(cl_cells),
            "areas_descending": cl_areas[:20],
            "area_median": statistics.median(cl_areas) if cl_areas else 0,
            **cl_mapping,
        },
    }
    out_json.write_text(json.dumps(report, indent=2))
    print(f"[ok] json -> {out_json}")
    render_comparison(consensus, box_cells, box_mapping,
                       cl_cells, cl_mapping, labels, out_png)

    print()
    print(f"=== {args.pdf.name} ===")
    print(f"  expected rooms: {len(expected_rooms)}")
    print(f"  box-difference: {len(box_cells)} cells, "
          f"{box_mapping['n_distinct_cells']} distinct rooms, "
          f"{box_mapping['n_merged_cells']} merged")
    print(f"  centerline:     {len(cl_cells)} cells, "
          f"{cl_mapping['n_distinct_cells']} distinct rooms, "
          f"{cl_mapping['n_merged_cells']} merged")


if __name__ == "__main__":
    main()
