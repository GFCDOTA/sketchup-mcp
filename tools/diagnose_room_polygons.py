"""Diagnose room polygon merges in a consensus_model.json.

Read-only diagnostic tool. Produces:
  1. JSON report with per-room metrics + summary.
  2. Optional matplotlib overlay PNG for a single room.

NEVER modifies the consensus or any other repo artifact. Intended for
forensic analysis of merged room cells (e.g. the
"A.S. | TERRACO SOCIAL | TERRACO TECNICO" r001 case on planta_74).

Usage:
    python -m tools.diagnose_room_polygons \\
        fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json \\
        --out runs/planta_74_plan_shell/room_polygon_diagnostic_report.json \\
        --pdf planta_74.pdf \\
        --overlay-room r001 \\
        --overlay-out runs/planta_74_plan_shell/r001_overlay.png

Notes:
    PT_TO_M = 0.19 / 5.4 (planta_74 wall-thickness anchor; see
    `tools/render_axon.py:18`).
    Polygons are stored as ``polygon_pts`` in PDF points (y-up).
    Soft barriers are polylines in PDF points (``polyline_pts``).
"""
from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import sys
import unicodedata
from pathlib import Path
from typing import Any

from shapely.geometry import LineString, Polygon
from shapely.validation import explain_validity

# --- constants -------------------------------------------------------------

PT_TO_M = 0.19 / 5.4  # ~0.035185 m / pt (planta_74 wall thickness anchor)
PT2_TO_M2 = PT_TO_M * PT_TO_M

# Threshold for collapsing consecutive identical vertices (PDF points).
DUP_VERTEX_EPS_PTS = 0.5

# Areas below this in m² are considered shared-edge touches, not overlaps.
OVERLAP_AREA_MIN_M2 = 0.1

# Soft barriers count as "crossing" a room only if their intersection with
# the room interior is longer than this in metres.
SB_TOUCH_MIN_M = 0.3

# Concavity ratio above which a polygon is flagged as suspiciously concave.
CONCAVITY_SUSPICIOUS = 0.30


# --- helpers ---------------------------------------------------------------


def _norm(s: str) -> str:
    """ASCII-fold + uppercase + collapse whitespace (for label search)."""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", s.upper().strip())


def _count_duplicate_consecutive(pts: list[list[float]],
                                 eps: float = DUP_VERTEX_EPS_PTS) -> int:
    """Count consecutive vertex pairs closer than ``eps`` (PDF points)."""
    n = 0
    for a, b in zip(pts, pts[1:]):
        if math.dist(a, b) < eps:
            n += 1
    return n


def _build_polygon(pts: list[list[float]]) -> Polygon:
    """Build a shapely Polygon from a list of [x, y] PDF points."""
    if len(pts) < 3:
        return Polygon()
    return Polygon([(p[0], p[1]) for p in pts])


def _polygon_area_m2(poly: Polygon) -> float:
    """Polygon area in m² (input in PDF points, converted via PT_TO_M)."""
    if poly.is_empty:
        return 0.0
    return float(poly.area) * PT2_TO_M2


def _bbox_m(poly: Polygon) -> dict[str, list[float]]:
    if poly.is_empty:
        return {"min": [0.0, 0.0], "max": [0.0, 0.0]}
    minx, miny, maxx, maxy = poly.bounds
    return {
        "min": [minx * PT_TO_M, miny * PT_TO_M],
        "max": [maxx * PT_TO_M, maxy * PT_TO_M],
    }


def _concavity_ratio(poly: Polygon) -> float:
    """1 - area / convex_hull.area. 0 = convex; → 1 = very concave."""
    if poly.is_empty:
        return 0.0
    hull = poly.convex_hull
    if hull.is_empty or hull.area == 0:
        return 0.0
    return 1.0 - (poly.area / hull.area)


# --- core diagnostic -------------------------------------------------------


def diagnose(consensus: dict[str, Any]) -> dict[str, Any]:
    """Run the full diagnostic, return the structured report dict."""
    rooms = consensus.get("rooms", []) or []
    soft_barriers = consensus.get("soft_barriers", []) or []

    # Pre-build per-room polygons.
    room_polys: list[tuple[dict[str, Any], Polygon]] = []
    for r in rooms:
        pts = r.get("polygon_pts") or []
        poly = _build_polygon(pts)
        room_polys.append((r, poly))

    # Pre-build soft-barrier linestrings.
    sb_lines: list[tuple[dict[str, Any], LineString]] = []
    for sb in soft_barriers:
        pts = sb.get("polyline_pts") or []
        if len(pts) < 2:
            line = LineString()
        else:
            line = LineString([(p[0], p[1]) for p in pts])
        sb_lines.append((sb, line))

    # Vertex-count and area medians for "suspicious" thresholds.
    vc_list = [
        len(r.get("polygon_pts") or []) for r, _ in room_polys
        if r.get("polygon_pts")
    ]
    area_list_m2 = [_polygon_area_m2(p) for _, p in room_polys if not p.is_empty]
    median_vc = statistics.median(vc_list) if vc_list else 0.0
    median_area = statistics.median(area_list_m2) if area_list_m2 else 0.0

    per_room: list[dict[str, Any]] = []
    n_suspicious = 0
    n_invalid = 0
    n_self_intx = 0

    for i, (r, poly_a) in enumerate(room_polys):
        rid = r.get("id")
        label = r.get("name")
        pts = r.get("polygon_pts") or []
        vc = len(pts)

        polygon_valid = bool(poly_a.is_valid) if not poly_a.is_empty else False
        self_intx = (not poly_a.is_simple) if not poly_a.is_empty else False
        invalid_reason = (
            None if polygon_valid or poly_a.is_empty
            else explain_validity(poly_a)
        )

        if not polygon_valid and not poly_a.is_empty:
            n_invalid += 1
        if self_intx:
            n_self_intx += 1

        # Pairwise overlaps (area > OVERLAP_AREA_MIN_M2 in m²).
        overlaps: list[str] = []
        if not poly_a.is_empty and poly_a.is_valid:
            for j, (other_r, poly_b) in enumerate(room_polys):
                if j == i or poly_b.is_empty or not poly_b.is_valid:
                    continue
                try:
                    inter_area = poly_a.intersection(poly_b).area * PT2_TO_M2
                except Exception:
                    inter_area = 0.0
                if inter_area > OVERLAP_AREA_MIN_M2:
                    overlaps.append(other_r.get("id"))

        # Soft barriers that cross room interior (>SB_TOUCH_MIN_M).
        touches_sbs: list[str] = []
        if not poly_a.is_empty and poly_a.is_valid:
            for sb, line in sb_lines:
                if line.is_empty:
                    continue
                try:
                    if not line.intersects(poly_a):
                        continue
                    inter = line.intersection(poly_a)
                    length_m = float(inter.length) * PT_TO_M
                except Exception:
                    length_m = 0.0
                if length_m > SB_TOUCH_MIN_M:
                    touches_sbs.append(sb.get("id"))

        concavity = _concavity_ratio(poly_a)
        area_m2 = _polygon_area_m2(poly_a)

        # Suspicious-merge heuristics.
        reasons: list[str] = []
        if label and " | " in label:
            reasons.append("label_pipe_merge")
        if median_vc > 0 and vc > 4 * median_vc:
            reasons.append(
                f"vertex_count_gt_4x_median ({vc} > 4*{median_vc:.0f})"
            )
        if median_area > 0 and area_m2 > 2 * median_area:
            reasons.append(
                f"area_gt_2x_median ({area_m2:.2f} > 2*{median_area:.2f})"
            )
        if concavity > CONCAVITY_SUSPICIOUS:
            reasons.append(
                f"concavity_gt_{CONCAVITY_SUSPICIOUS:.2f} ({concavity:.2f})"
            )

        suspicious = bool(reasons)
        if suspicious:
            n_suspicious += 1

        per_room.append({
            "room_id": rid,
            "label": label,
            "vertex_count": vc,
            "duplicate_consecutive_vertices": _count_duplicate_consecutive(pts),
            "area_m2": round(area_m2, 4),
            "bbox_m": _bbox_m(poly_a),
            "polygon_valid": polygon_valid,
            "polygon_invalid_reason": invalid_reason,
            "self_intersections": bool(self_intx),
            "overlaps_with_other_rooms": overlaps,
            "touches_soft_barriers": touches_sbs,
            "concavity_ratio": round(concavity, 4),
            "suspicious_merge": suspicious,
            "suspicious_merge_reasons": reasons,
        })

    summary = {
        "total_rooms": len(per_room),
        "rooms_with_suspicious_merge": n_suspicious,
        "rooms_with_self_intersections": n_self_intx,
        "rooms_with_invalid_polygon": n_invalid,
        "median_vertex_count": int(median_vc) if median_vc else 0,
        "median_area_m2": round(median_area, 4),
    }

    return {
        "schema_version": "1.0.0",
        "tool": "diagnose_room_polygons",
        "constants": {
            "PT_TO_M": round(PT_TO_M, 6),
            "OVERLAP_AREA_MIN_M2": OVERLAP_AREA_MIN_M2,
            "SB_TOUCH_MIN_M": SB_TOUCH_MIN_M,
            "DUP_VERTEX_EPS_PTS": DUP_VERTEX_EPS_PTS,
            "CONCAVITY_SUSPICIOUS": CONCAVITY_SUSPICIOUS,
        },
        "rooms": per_room,
        "summary": summary,
    }


# --- overlay ---------------------------------------------------------------


def _find_label_positions(pdf_path: Path,
                          target_norms: list[str],
                          planta_region: tuple[float, float, float, float]
                          ) -> dict[str, list[tuple[float, float]]]:
    """Locate PDF text rects whose normalized form contains a target.

    Returns ``{target_norm: [(cx_pt, cy_pt), ...]}``. Searches inside
    ``planta_region`` only so legend/notes don't pollute results.
    """
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(pdf_path))
    out: dict[str, list[tuple[float, float]]] = {t: [] for t in target_norms}
    try:
        page = pdf[0]
        text_page = page.get_textpage()
        n = text_page.count_rects()
        x0, y0, x1, y1 = planta_region
        for i in range(n):
            left, top, right, bot = text_page.get_rect(i)
            cx, cy = (left + right) / 2.0, (top + bot) / 2.0
            if not (x0 <= cx <= x1 and y0 <= cy <= y1):
                continue
            txt = text_page.get_text_bounded(left, top, right, bot).strip()
            nm = _norm(txt)
            for tgt in target_norms:
                if tgt in nm:
                    out[tgt].append((cx, cy))
    finally:
        pdf.close()
    return out


def render_overlay(consensus: dict[str, Any],
                   room_id: str,
                   pdf_path: Path,
                   out_path: Path) -> None:
    """Render a matplotlib overlay PNG for one room vs all soft barriers.

    Highlights:
      - the target room polygon (filled red, edged red);
      - every soft barrier (thin blue, annotated with id);
      - soft barriers that cross the target's interior (THICK green dashed
        — these are split-candidate separators).
      - PDF-extracted A.S. / TERRACO SOCIAL / TERRACO TECNICO label
        positions, as text annotations.
    """
    import matplotlib.pyplot as plt
    import pypdfium2 as pdfium
    from matplotlib.lines import Line2D
    from matplotlib.patches import Polygon as MplPolygon

    rooms = consensus.get("rooms", []) or []
    target = next((r for r in rooms if r.get("id") == room_id), None)
    if target is None:
        raise SystemExit(f"room_id={room_id!r} not found in consensus")
    pts = target.get("polygon_pts") or []
    if len(pts) < 3:
        raise SystemExit(f"room_id={room_id!r} has < 3 polygon_pts")
    poly_target = _build_polygon(pts)

    soft_barriers = consensus.get("soft_barriers", []) or []
    planta_region = consensus.get("planta_region")
    if not planta_region or len(planta_region) < 4:
        planta_region = (0.0, 0.0, 595.0, 842.0)

    # Render PDF underlay at 200 DPI -equivalent.
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        page = pdf[0]
        page_w, page_h = page.get_size()
        img = page.render(scale=200.0 / 72.0).to_pil()
    finally:
        pdf.close()

    fig, ax = plt.subplots(figsize=(12, 10))
    ax.imshow(
        img,
        extent=(0, page_w, 0, page_h),
        origin="upper",
        alpha=0.55,
        aspect="equal",
        zorder=0,
    )

    # Target room polygon — filled red.
    ax.add_patch(MplPolygon(
        [(p[0], p[1]) for p in pts],
        closed=True,
        facecolor="#d32f2f",
        edgecolor="#b71c1c",
        linewidth=1.5,
        alpha=0.35,
        zorder=3,
    ))

    # Soft barriers — classify into "crosses target" vs "not".
    crossing_ids: list[str] = []
    for sb in soft_barriers:
        sb_pts = sb.get("polyline_pts") or []
        if len(sb_pts) < 2:
            continue
        line = LineString([(p[0], p[1]) for p in sb_pts])
        if line.is_empty:
            continue
        crosses = False
        if line.intersects(poly_target):
            try:
                inter = line.intersection(poly_target)
                length_m = float(inter.length) * PT_TO_M
                crosses = length_m > SB_TOUCH_MIN_M
            except Exception:
                crosses = False
        if crosses:
            crossing_ids.append(sb.get("id"))
            ax.plot(
                [p[0] for p in sb_pts],
                [p[1] for p in sb_pts],
                color="#2e7d32",
                linewidth=2.0,
                linestyle="--",
                alpha=0.95,
                zorder=5,
            )
        else:
            ax.plot(
                [p[0] for p in sb_pts],
                [p[1] for p in sb_pts],
                color="#1565c0",
                linewidth=0.8,
                alpha=0.80,
                zorder=4,
            )
        mid_i = len(sb_pts) // 2
        mid = sb_pts[mid_i]
        ax.annotate(
            sb.get("id"),
            xy=(mid[0], mid[1]),
            xytext=(4, 4),
            textcoords="offset points",
            fontsize=6,
            color="#0d47a1",
            zorder=6,
        )

    # PDF text labels.
    label_targets = ["A.S.", "TERRACO SOCIAL", "TERRACO TECNICO",
                     "TERRACO", "SOCIAL", "TECNICO"]
    label_hits = _find_label_positions(pdf_path, label_targets, planta_region)
    annotated_at: set[tuple[int, int]] = set()
    for tgt, hits in label_hits.items():
        if tgt in ("TERRACO", "SOCIAL", "TECNICO"):
            # Drop bare matches if a fuller match already covers the area.
            continue
        for cx, cy in hits:
            key = (int(cx), int(cy))
            if key in annotated_at:
                continue
            annotated_at.add(key)
            ax.scatter([cx], [cy], s=40, marker="*",
                       color="#ffeb3b", edgecolor="#000000",
                       linewidth=0.8, zorder=8)
            ax.annotate(
                tgt,
                xy=(cx, cy),
                xytext=(6, -10),
                textcoords="offset points",
                fontsize=8,
                fontweight="bold",
                color="#000000",
                bbox=dict(boxstyle="round,pad=0.2",
                          fc="#fff59d", ec="#000000",
                          alpha=0.85, linewidth=0.5),
                zorder=9,
            )
    # Also annotate sub-zone labels (split lines) — handy for the user.
    for tgt in ("TERRACO", "SOCIAL", "TECNICO"):
        for cx, cy in label_hits.get(tgt, []):
            key = (int(cx), int(cy))
            if key in annotated_at:
                continue
            annotated_at.add(key)
            ax.scatter([cx], [cy], s=15, marker="x",
                       color="#5d4037", linewidth=0.8, zorder=7)

    # Axes + chrome.
    ax.set_xlim(0, page_w)
    ax.set_ylim(0, page_h)
    ax.invert_yaxis()  # PDF origin top-left for orientation reading
    ax.set_aspect("equal", "box")
    vc = len(pts)
    label = target.get("name") or "(unnamed)"
    ax.set_title(
        f"{room_id} = {label} - {vc} verts - DIAGNOSTIC",
        fontsize=11,
    )

    legend_handles = [
        MplPolygon(
            [(0, 0), (1, 0), (1, 1), (0, 1)],
            facecolor="#d32f2f", edgecolor="#b71c1c",
            alpha=0.35, linewidth=1.5,
            label=f"{room_id} polygon (filled)",
        ),
        Line2D([0], [0], color="#2e7d32", linewidth=2.0, linestyle="--",
               label=f"soft barriers crossing {room_id} (split candidates) "
                     f"[{len(crossing_ids)}]"),
        Line2D([0], [0], color="#1565c0", linewidth=0.8,
               label="other soft barriers"),
        Line2D([0], [0], marker="*", linestyle="None",
               markerfacecolor="#ffeb3b", markeredgecolor="#000000",
               markersize=10,
               label="PDF text labels (sub-zones)"),
    ]
    ax.legend(handles=legend_handles, loc="upper right", fontsize=8,
              framealpha=0.9)

    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


# --- CLI -------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Diagnose room polygon merges in consensus.",
    )
    parser.add_argument("consensus", type=Path,
                        help="Path to consensus_model.json (read-only).")
    parser.add_argument("--out", type=Path, required=True,
                        help="Output JSON report path.")
    parser.add_argument("--pdf", type=Path, default=None,
                        help="Source PDF (required if --overlay-room).")
    parser.add_argument("--overlay-room", type=str, default=None,
                        help="If set, render an overlay PNG for this room.")
    parser.add_argument("--overlay-out", type=Path, default=None,
                        help="Output PNG path for the overlay.")
    args = parser.parse_args(argv)

    if not args.consensus.is_file():
        print(f"consensus not found: {args.consensus}", file=sys.stderr)
        return 2

    consensus = json.loads(args.consensus.read_text(encoding="utf-8"))

    report = diagnose(consensus)
    report["consensus_path"] = str(args.consensus).replace("\\", "/")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"report written: {args.out}")

    if args.overlay_room:
        if not args.pdf or not args.pdf.is_file():
            print("--pdf is required and must exist for --overlay-room",
                  file=sys.stderr)
            return 2
        if not args.overlay_out:
            print("--overlay-out is required when --overlay-room is set",
                  file=sys.stderr)
            return 2
        render_overlay(consensus, args.overlay_room, args.pdf, args.overlay_out)
        print(f"overlay written: {args.overlay_out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
