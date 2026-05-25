"""Diagnostic audit of every soft_barrier in a consensus.

READ-ONLY. Does NOT modify the consensus, the exporter, or any shared
threshold. Produces:

  1. A structured JSON report classifying each soft_barrier as
     ``keep`` / ``warn`` / ``reject`` per the user-mandated conservative
     rules (see ``classify`` below).
  2. Three overlay PNGs (planta_74 PDF underlay + room outlines + the
     soft_barriers coloured by decision) so the user can visually
     audit which barriers stay/warn/go.

Per the user's directive: FP-006 classifies, NOT deletes. The decision
column is advisory; nothing in this tool removes a soft_barrier from
the consensus. The reviewer remains the source of truth.

The ``overlap_fraction_with_walls`` and ``overlaps_wall_shell`` columns
replicate the FP-006 3-sample filter in
``tools/consume_consensus.rb#_segment_overlaps_wall?`` (lines 145-165)
and ``tools/build_plan_shell_skp.py``. Tolerance is ``tol_in = 1.0``
inches, matching the Ruby ground truth.

Usage:
    python -m tools.audit_soft_barriers <consensus.json> \\
      --out runs/planta_74_plan_shell/soft_barrier_audit_report.json \\
      --pdf planta_74.pdf \\
      --overlays-dir runs/planta_74_plan_shell
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pypdfium2 as pdfium  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from matplotlib.patches import Polygon as MplPolygon  # noqa: E402
from shapely.geometry import LineString, Polygon, box  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

# ---- constants (mirror Ruby ground truth) ---------------------------

# PT_TO_M = 0.19 / 5.4 ≈ 0.0351851851... — same calibration as
# consume_consensus.rb line 15 ("wall thickness 5.4 pt -> 19 cm").
PT_TO_M = 0.19 / 5.4
M_TO_IN = 39.3700787
PT_TO_IN = PT_TO_M * M_TO_IN

# Soft-barrier extruded thickness (matches Ruby add_parapet default).
SOFT_BARRIER_THICKNESS_IN = 1.5
SOFT_BARRIER_THICKNESS_PT = SOFT_BARRIER_THICKNESS_IN / PT_TO_IN

# FP-006 tolerance, in INCHES (Ruby convention). When projecting the
# 3 SB sample points onto the wall footprint inflated by tol_in, the
# Ruby filter REJECTS the segment if ANY sample lands inside.
OVERLAP_TOL_IN = 1.0
OVERLAP_TOL_PT = OVERLAP_TOL_IN / PT_TO_IN

# Room-interior crossing threshold (spec: "intersection length > 0.3 m").
INTERIOR_CROSS_MIN_M = 0.3

# Window/balcony nearness threshold (spec: "within 0.5 m of opening
# position").
NEAR_OPENING_RADIUS_M = 0.5

# Sampling resolution along an SB polyline when computing the
# overlap-fraction-with-walls metric. We walk every segment in
# OVERLAP_SAMPLE_STEP_PT increments and count how much of the
# polyline lies inside the inflated wall union. 1.0pt ~ 3.5mm in real
# coords — finer than the FP-006 tolerance so the fraction is honest.
OVERLAP_SAMPLE_STEP_PT = 1.0

PARAPET_HEIGHT_M = 1.10


# ---- geometry helpers -----------------------------------------------


def _wall_footprint_pt(wall: dict, default_thickness: float) -> Polygon:
    """Return the wall's 2D footprint in PDF-points, matching the
    Ruby _wall_footprints_in convention (axis-aligned only)."""
    t = wall.get("thickness", default_thickness)
    half = t / 2.0
    sx, sy = wall["start"]
    ex, ey = wall["end"]
    ori = wall.get("orientation")
    if ori == "h":
        x0, x1 = min(sx, ex), max(sx, ex)
        return box(x0, sy - half, x1, sy + half)
    if ori == "v":
        y0, y1 = min(sy, ey), max(sy, ey)
        return box(sx - half, y0, sx + half, y1)
    # Unknown / oblique — fall back to a thin rectangle along the segment.
    # We do not raise: a few human walls might not declare orientation.
    return LineString([(sx, sy), (ex, ey)]).buffer(half, cap_style=2)


def _wall_centerline_distance_pt(point: tuple[float, float],
                                  walls: list[dict]) -> float:
    """Min euclidean distance from ``point`` to any wall centerline."""
    px, py = point
    best = math.inf
    for w in walls:
        sx, sy = w["start"]
        ex, ey = w["end"]
        # Closest distance from (px,py) to segment (sx,sy)-(ex,ey).
        vx, vy = ex - sx, ey - sy
        seg_len2 = vx * vx + vy * vy
        if seg_len2 == 0.0:
            d2 = (px - sx) ** 2 + (py - sy) ** 2
        else:
            t = ((px - sx) * vx + (py - sy) * vy) / seg_len2
            t = max(0.0, min(1.0, t))
            qx = sx + t * vx
            qy = sy + t * vy
            d2 = (px - qx) ** 2 + (py - qy) ** 2
        if d2 < best:
            best = d2
    return math.sqrt(best)


def _segment_overlaps_wall_fp006(p1: tuple[float, float],
                                  p2: tuple[float, float],
                                  footprints: list[tuple[float, float,
                                                          float, float]],
                                  tol_pt: float) -> bool:
    """Faithful Python port of ``_segment_overlaps_wall?`` in
    consume_consensus.rb (3 samples, ANY-inside rule).

    Inputs are in PDF-points; the Ruby version uses inches because it
    runs after the SU coordinate conversion. The math is identical
    because we inflate the footprint by the same tolerance expressed
    in PDF-points (tol_pt = tol_in / PT_TO_IN).
    """
    pts = [
        p1,
        ((p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0),
        p2,
    ]
    for x0, y0, x1, y1 in footprints:
        for px, py in pts:
            if (
                x0 - tol_pt <= px <= x1 + tol_pt
                and y0 - tol_pt <= py <= y1 + tol_pt
            ):
                return True
    return False


def _polyline_segments(polyline: list[list[float]]
                       ) -> list[tuple[tuple[float, float],
                                        tuple[float, float]]]:
    """Yield (a, b) for each consecutive pair, skipping degenerate."""
    out: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for i in range(len(polyline) - 1):
        a = (float(polyline[i][0]), float(polyline[i][1]))
        b = (float(polyline[i + 1][0]), float(polyline[i + 1][1]))
        if a == b:
            continue
        out.append((a, b))
    return out


def _polyline_length_pt(polyline: list[list[float]]) -> float:
    total = 0.0
    for a, b in _polyline_segments(polyline):
        total += math.hypot(b[0] - a[0], b[1] - a[1])
    return total


def _polyline_bbox(polyline: list[list[float]]
                   ) -> tuple[tuple[float, float], tuple[float, float]]:
    xs = [p[0] for p in polyline]
    ys = [p[1] for p in polyline]
    return (min(xs), min(ys)), (max(xs), max(ys))


def _top_face_area_m2(polyline: list[list[float]]) -> float:
    """Per-segment swept rectangle of thickness SOFT_BARRIER_THICKNESS_IN,
    unioned via shapely. Areas in m² (PDF-points -> m via PT_TO_M)."""
    if len(polyline) < 2:
        return 0.0
    half_t = SOFT_BARRIER_THICKNESS_PT / 2.0
    rects = []
    for a, b in _polyline_segments(polyline):
        ls = LineString([a, b])
        # cap_style=2 (flat): no rounded ends; matches the rectangular
        # sweep used by Ruby add_parapet.
        rects.append(ls.buffer(half_t, cap_style=2))
    if not rects:
        return 0.0
    union = unary_union(rects)
    return float(union.area) * (PT_TO_M ** 2)


def _overlap_fraction_with_walls(polyline: list[list[float]],
                                  wall_footprints_pt: list[Polygon],
                                  tol_pt: float) -> float:
    """Fraction of the polyline length whose points lie within
    ``tol_pt`` of any wall footprint. Computed by step-sampling at
    ``OVERLAP_SAMPLE_STEP_PT`` along each segment.

    A fraction > 0.50 is the FP-006 reject threshold; lower values are
    legitimate "skirts" along a wall (peitoril offset by a few cm),
    which the Ruby midpoint filter would also accept.
    """
    if not wall_footprints_pt:
        return 0.0
    walls_union = unary_union([w.buffer(tol_pt) for w in wall_footprints_pt])
    total = 0.0
    inside = 0.0
    for a, b in _polyline_segments(polyline):
        seg_len = math.hypot(b[0] - a[0], b[1] - a[1])
        if seg_len < 1e-9:
            continue
        # Walk along the segment in step_pt increments
        n_steps = max(1, int(round(seg_len / OVERLAP_SAMPLE_STEP_PT)))
        step_len = seg_len / n_steps
        dx = (b[0] - a[0]) / n_steps
        dy = (b[1] - a[1]) / n_steps
        for k in range(n_steps):
            # Use the segment midpoint of each substep
            mx = a[0] + (k + 0.5) * dx
            my = a[1] + (k + 0.5) * dy
            total += step_len
            if walls_union.contains(_pt_geom(mx, my)):
                inside += step_len
    if total == 0:
        return 0.0
    return inside / total


# Shapely 2.x's `.contains(Point)` is fast enough for our O(N_steps)
# calls; the wrapper hides the import and gives a small allocation
# helper.

from shapely.geometry import Point as _Point  # noqa: E402


def _pt_geom(x: float, y: float) -> _Point:
    return _Point(x, y)


# ---- decision rule --------------------------------------------------


def classify(sb_metrics: dict) -> tuple[str, str]:
    """User-mandated conservative rules (FP-006 classifies, doesn't delete).

    reject — overlap_fraction_with_walls > 0.50 (mostly covers a wall;
             FP-006 hard case the Ruby filter would also reject)
    keep   — short (length_m < 6.0) AND simple (segment_count < 15)
             AND useful (near a window/balcony opening OR near a wall
             within 0.5 m)
    warn   — everything else; flagged for human review, NOT removed

    Returns: (decision, reason).
    """
    of = sb_metrics["overlap_fraction_with_walls"]
    L = sb_metrics["length_m"]
    n = sb_metrics["segment_count"]
    nw = sb_metrics["near_window_or_balcony_edge"]
    d_wall_m = sb_metrics["distance_to_nearest_wall_m"]

    if of > 0.50:
        pct = round(of * 100)
        return ("reject",
                f"reject: {pct}% overlap with wall axis (FP-006)")

    if L < 6.0 and n < 15 and (nw or d_wall_m < 0.5):
        if nw:
            tag = f"near {nw[0]} (window/balcony)"
        else:
            tag = f"close-to-wall {d_wall_m:.2f}m"
        return ("keep",
                f"keep: {L:.1f}m / {n} segs / {tag}")

    # warn — reason should be specific
    bits = []
    if L >= 6.0:
        bits.append(f"{L:.1f}m polyline")
    if n >= 15:
        bits.append(f"{n} segs")
    if not nw:
        bits.append("not near any window/balcony")
    if d_wall_m >= 0.5:
        bits.append(f"{d_wall_m:.2f}m from nearest wall")
    if not bits:
        bits = ["no rule applied"]
    return ("warn", "warn: " + " / ".join(bits))


# ---- per-SB metrics --------------------------------------------------


def _nearest_openings(polyline: list[list[float]],
                      openings: list[dict],
                      radius_m: float) -> list[str]:
    """Return opening ids of {window, glazed_balcony} whose
    ``center`` (PDF-pt) is within ``radius_m`` of the closest point on
    the polyline."""
    if len(polyline) < 1:
        return []
    radius_pt = radius_m / PT_TO_M
    ls = LineString(polyline) if len(polyline) >= 2 else None
    found: list[str] = []
    for op in openings:
        if op.get("kind") not in ("window", "glazed_balcony"):
            continue
        c = op.get("center")
        if not c:
            continue
        cx, cy = c
        if ls is not None:
            d = ls.distance(_pt_geom(cx, cy))
        else:
            ax, ay = polyline[0]
            d = math.hypot(cx - ax, cy - ay)
        if d <= radius_pt:
            found.append(op.get("id", ""))
    return [x for x in found if x]


def _crosses_room_interior(polyline: list[list[float]],
                            rooms: list[dict],
                            min_m: float) -> list[str]:
    """Return room ids whose polygon's interior is crossed by the
    polyline with intersection length > min_m."""
    if len(polyline) < 2:
        return []
    ls = LineString(polyline)
    min_pt = min_m / PT_TO_M
    out = []
    for r in rooms:
        pts = r.get("polygon_pts") or []
        if len(pts) < 3:
            continue
        try:
            poly = Polygon(pts)
            if not poly.is_valid:
                poly = poly.buffer(0)
            if not poly.is_valid:
                continue
        except Exception:
            continue
        if not ls.intersects(poly):
            continue
        inter = ls.intersection(poly)
        # length attribute is 0 for non-1D, so skip empty
        if hasattr(inter, "length") and inter.length > min_pt:
            out.append(r.get("id", ""))
    return [x for x in out if x]


def metrics_for_sb(sb: dict,
                   walls: list[dict],
                   wall_footprints_pt: list[Polygon],
                   wall_footprints_inches: list[tuple[float, float,
                                                       float, float]],
                   openings: list[dict],
                   rooms: list[dict]) -> dict[str, Any]:
    pl = sb.get("polyline_pts") or []
    segments = _polyline_segments(pl)
    n_segs = len(segments)
    length_pt = _polyline_length_pt(pl)
    length_m = length_pt * PT_TO_M

    if pl:
        (minx, miny), (maxx, maxy) = _polyline_bbox(pl)
        bbox_m = {
            "min": [minx * PT_TO_M, miny * PT_TO_M],
            "max": [maxx * PT_TO_M, maxy * PT_TO_M],
        }
    else:
        bbox_m = {"min": [0.0, 0.0], "max": [0.0, 0.0]}

    top_area = _top_face_area_m2(pl)

    # distance_to_nearest_wall (3-point sample)
    if pl:
        sample_pts: list[tuple[float, float]] = [
            (float(pl[0][0]), float(pl[0][1])),
            (float(pl[len(pl) // 2][0]), float(pl[len(pl) // 2][1])),
            (float(pl[-1][0]), float(pl[-1][1])),
        ]
        dmin_pt = min(_wall_centerline_distance_pt(p, walls)
                       for p in sample_pts)
        dmin_m = dmin_pt * PT_TO_M
    else:
        dmin_m = 0.0

    # FP-006 3-sample overlap: True if ANY segment passes the 3-sample
    # ANY-inside rule against any wall footprint (in inches = pt-eq).
    overlaps_shell = False
    for a, b in segments:
        a_in = (a[0] * PT_TO_IN, a[1] * PT_TO_IN)
        b_in = (b[0] * PT_TO_IN, b[1] * PT_TO_IN)
        if _segment_overlaps_wall_fp006(a_in, b_in,
                                          wall_footprints_inches,
                                          OVERLAP_TOL_IN):
            overlaps_shell = True
            break

    overlap_frac = _overlap_fraction_with_walls(
        pl, wall_footprints_pt, OVERLAP_TOL_PT)

    crosses_rooms = _crosses_room_interior(pl, rooms, INTERIOR_CROSS_MIN_M)
    near_openings = _nearest_openings(pl, openings, NEAR_OPENING_RADIUS_M)

    payload = {
        "id": sb.get("id"),
        "polyline_points_pt": [[float(x), float(y)] for x, y in pl],
        "segment_count": n_segs,
        "length_m": round(length_m, 4),
        "bbox_m": {
            "min": [round(bbox_m["min"][0], 4),
                    round(bbox_m["min"][1], 4)],
            "max": [round(bbox_m["max"][0], 4),
                    round(bbox_m["max"][1], 4)],
        },
        "top_face_area_m2": round(top_area, 4),
        "distance_to_nearest_wall_m": round(dmin_m, 4),
        "overlaps_wall_shell": bool(overlaps_shell),
        "overlap_fraction_with_walls": round(overlap_frac, 4),
        "crosses_room_interior": crosses_rooms,
        "near_window_or_balcony_edge": near_openings,
    }
    decision, reason = classify(payload)
    payload["decision"] = decision
    payload["reason"] = reason
    return payload


# ---- overlay rendering ---------------------------------------------


def _render_pdf_underlay(pdf_path: Path, ax,
                         alpha: float = 0.55) -> tuple[float, float]:
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        page = pdf[0]
        page_w, page_h = page.get_size()
        img = page.render(scale=2).to_pil()
    finally:
        pdf.close()
    ax.imshow(img, extent=(0, page_w, 0, page_h),
              origin="upper", alpha=alpha,
              aspect="equal", zorder=0)
    return float(page_w), float(page_h)


def _compute_view_bbox(consensus: dict, results: list[dict],
                        page_w: float, page_h: float,
                        pad_pt: float = 25.0
                        ) -> tuple[float, float, float, float]:
    """Tight bbox around rooms + SBs + walls, with padding. Falls
    back to the full page if no geometry."""
    xs: list[float] = []
    ys: list[float] = []
    for r in consensus.get("rooms") or []:
        for x, y in (r.get("polygon_pts") or []):
            xs.append(float(x))
            ys.append(float(y))
    for sb in results:
        for x, y in (sb.get("polyline_points_pt") or []):
            xs.append(float(x))
            ys.append(float(y))
    for w in consensus.get("walls") or []:
        for key in ("start", "end"):
            p = w.get(key) or []
            if len(p) == 2:
                xs.append(float(p[0]))
                ys.append(float(p[1]))
    if not xs:
        return (0.0, 0.0, page_w, page_h)
    x0 = max(0.0, min(xs) - pad_pt)
    x1 = min(page_w, max(xs) + pad_pt)
    y0 = max(0.0, min(ys) - pad_pt)
    y1 = min(page_h, max(ys) + pad_pt)
    return (x0, y0, x1, y1)


def _draw_rooms_gray(ax, rooms: list[dict]) -> None:
    for r in rooms:
        pts = r.get("polygon_pts") or []
        if len(pts) < 3:
            continue
        ax.add_patch(MplPolygon(
            pts, closed=True, facecolor="none",
            edgecolor="#9e9e9e", linewidth=0.8, alpha=0.65, zorder=2,
        ))


def _polyline_xy(pl: list[list[float]]) -> tuple[list[float], list[float]]:
    return [p[0] for p in pl], [p[1] for p in pl]


def _midpoint(pl: list[list[float]]) -> tuple[float, float]:
    if not pl:
        return (0.0, 0.0)
    if len(pl) == 1:
        return (pl[0][0], pl[0][1])
    return (pl[len(pl) // 2][0], pl[len(pl) // 2][1])


def render_all(pdf_path: Path,
                consensus: dict,
                results: list[dict],
                out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(12, 10))
    page_w, page_h = _render_pdf_underlay(pdf_path, ax)
    _draw_rooms_gray(ax, consensus.get("rooms") or [])
    for sb in results:
        pl = sb.get("polyline_points_pt") or []
        if len(pl) < 1:
            continue
        xs, ys = _polyline_xy(pl)
        ax.plot(xs, ys, color="#1565c0", linewidth=1.6,
                alpha=0.95, zorder=6)
        mx, my = _midpoint(pl)
        ax.text(mx, my + 6, sb["id"], fontsize=7,
                ha="center", va="bottom", color="#0d47a1",
                bbox=dict(boxstyle="round,pad=0.2", fc="#e3f2fd",
                           ec="#0d47a1", lw=0.5, alpha=0.85),
                zorder=10)
    x0, y0, x1, y1 = _compute_view_bbox(consensus, results,
                                          page_w, page_h)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    ax.set_axis_off()
    ax.set_title(f"All {len(results)} soft_barriers (raw, pre-audit)",
                  fontsize=11, pad=8)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(out_path, dpi=150, bbox_inches="tight",
                facecolor="white")
    plt.close(fig)


def render_keep(pdf_path: Path,
                 consensus: dict,
                 results: list[dict],
                 out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(12, 10))
    page_w, page_h = _render_pdf_underlay(pdf_path, ax)
    _draw_rooms_gray(ax, consensus.get("rooms") or [])
    keeps = [r for r in results if r["decision"] == "keep"]
    for sb in keeps:
        pl = sb["polyline_points_pt"]
        if len(pl) < 1:
            continue
        xs, ys = _polyline_xy(pl)
        ax.plot(xs, ys, color="#2e7d32", linewidth=2.2,
                alpha=0.95, zorder=6)
        mx, my = _midpoint(pl)
        # Trim reason to keep the chip readable
        reason = sb["reason"]
        if len(reason) > 38:
            reason = reason[:35] + "..."
        ax.text(mx, my + 6, f"{sb['id']}\n{reason}",
                fontsize=6.5,
                ha="center", va="bottom", color="#1b5e20",
                bbox=dict(boxstyle="round,pad=0.25", fc="#c8e6c9",
                           ec="#2e7d32", lw=0.5, alpha=0.9),
                zorder=10)
    x0, y0, x1, y1 = _compute_view_bbox(consensus, results,
                                          page_w, page_h)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    ax.set_axis_off()
    ax.set_title(f"Soft barriers KEEP — {len(keeps)} of {len(results)}",
                  fontsize=11, pad=8)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(out_path, dpi=150, bbox_inches="tight",
                facecolor="white")
    plt.close(fig)


def render_reject_warn(pdf_path: Path,
                        consensus: dict,
                        results: list[dict],
                        out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(12, 10))
    page_w, page_h = _render_pdf_underlay(pdf_path, ax)
    _draw_rooms_gray(ax, consensus.get("rooms") or [])

    # First draw context (decision != warn|reject)
    for sb in results:
        if sb["decision"] in ("warn", "reject"):
            continue
        pl = sb["polyline_points_pt"]
        if len(pl) < 1:
            continue
        xs, ys = _polyline_xy(pl)
        ax.plot(xs, ys, color="#bdbdbd", linewidth=0.8,
                alpha=0.7, zorder=4)

    warns = [r for r in results if r["decision"] == "warn"]
    rejects = [r for r in results if r["decision"] == "reject"]

    for sb in warns:
        pl = sb["polyline_points_pt"]
        if len(pl) < 1:
            continue
        xs, ys = _polyline_xy(pl)
        ax.plot(xs, ys, color="#ef6c00", linewidth=1.5,
                alpha=0.95, zorder=6)
        mx, my = _midpoint(pl)
        reason = sb["reason"]
        if len(reason) > 42:
            reason = reason[:39] + "..."
        ax.text(mx, my + 6, f"WARN {sb['id']}\n{reason}",
                fontsize=6.5,
                ha="center", va="bottom", color="#bf360c",
                bbox=dict(boxstyle="round,pad=0.25", fc="#ffe0b2",
                           ec="#ef6c00", lw=0.5, alpha=0.9),
                zorder=10)

    for sb in rejects:
        pl = sb["polyline_points_pt"]
        if len(pl) < 1:
            continue
        xs, ys = _polyline_xy(pl)
        ax.plot(xs, ys, color="#c62828", linewidth=2.0,
                alpha=0.95, zorder=7)
        mx, my = _midpoint(pl)
        reason = sb["reason"]
        if len(reason) > 42:
            reason = reason[:39] + "..."
        ax.text(mx, my + 6, f"REJECT {sb['id']}\n{reason}",
                fontsize=6.5,
                ha="center", va="bottom", color="#b71c1c",
                bbox=dict(boxstyle="round,pad=0.25", fc="#ffcdd2",
                           ec="#c62828", lw=0.6, alpha=0.95),
                zorder=11)

    legend = [
        Patch(facecolor="#ffe0b2", edgecolor="#ef6c00",
              label=f"WARN ({len(warns)})"),
        Patch(facecolor="#ffcdd2", edgecolor="#c62828",
              label=f"REJECT ({len(rejects)})"),
        Patch(facecolor="none", edgecolor="#bdbdbd",
              label=f"context (keep, {len(results) - len(warns) - len(rejects)})"),
    ]
    ax.legend(handles=legend, loc="lower left", fontsize=9,
              framealpha=0.95)

    x0, y0, x1, y1 = _compute_view_bbox(consensus, results,
                                          page_w, page_h)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    ax.set_axis_off()
    ax.set_title(
        f"Soft barriers WARN/REJECT — {len(warns)} warn, {len(rejects)} reject",
        fontsize=11, pad=8,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(out_path, dpi=150, bbox_inches="tight",
                facecolor="white")
    plt.close(fig)


# ---- top-level pipeline ---------------------------------------------


def audit(consensus_path: Path, pdf_path: Path,
          out_json: Path, overlays_dir: Path) -> dict[str, Any]:
    consensus = json.loads(consensus_path.read_text(encoding="utf-8"))
    walls = consensus.get("walls", [])
    soft_barriers = consensus.get("soft_barriers", [])
    openings = consensus.get("openings", [])
    rooms = consensus.get("rooms", [])
    default_thickness = consensus.get("wall_thickness_pts",
                                       5.4)  # planta_74 calibration

    # Pre-compute wall footprints in both PDF-pt (for shapely-based
    # overlap fraction) and inches (for the FP-006 axis-aligned
    # bbox check that mirrors the Ruby logic).
    wall_footprints_pt: list[Polygon] = []
    wall_footprints_in: list[tuple[float, float, float, float]] = []
    for w in walls:
        poly = _wall_footprint_pt(w, default_thickness)
        wall_footprints_pt.append(poly)
        x0, y0, x1, y1 = poly.bounds
        wall_footprints_in.append((x0 * PT_TO_IN, y0 * PT_TO_IN,
                                    x1 * PT_TO_IN, y1 * PT_TO_IN))

    results: list[dict[str, Any]] = []
    for sb in soft_barriers:
        m = metrics_for_sb(sb, walls, wall_footprints_pt,
                           wall_footprints_in, openings, rooms)
        results.append(m)

    decisions = [r["decision"] for r in results]
    summary = {
        "total": len(results),
        "keep": sum(1 for d in decisions if d == "keep"),
        "warn": sum(1 for d in decisions if d == "warn"),
        "reject": sum(1 for d in decisions if d == "reject"),
        "rejected_ids": [r["id"] for r in results
                          if r["decision"] == "reject"],
        "warn_ids": [r["id"] for r in results
                      if r["decision"] == "warn"],
        "keep_ids": [r["id"] for r in results
                      if r["decision"] == "keep"],
    }

    report = {
        "schema_version": "1.0.0",
        "tool": "audit_soft_barriers",
        "generated_at": datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"),
        "consensus_path": str(consensus_path),
        "pdf_path": str(pdf_path),
        "constants": {
            "PT_TO_M": PT_TO_M,
            "PARAPET_HEIGHT_M": PARAPET_HEIGHT_M,
            "SOFT_BARRIER_THICKNESS_IN": SOFT_BARRIER_THICKNESS_IN,
            "OVERLAP_TOL_IN": OVERLAP_TOL_IN,
            "INTERIOR_CROSS_MIN_M": INTERIOR_CROSS_MIN_M,
            "NEAR_OPENING_RADIUS_M": NEAR_OPENING_RADIUS_M,
        },
        "soft_barriers": results,
        "summary": summary,
    }

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2),
                         encoding="utf-8")

    overlays_dir.mkdir(parents=True, exist_ok=True)
    render_all(pdf_path, consensus, results,
                overlays_dir / "soft_barriers_all.png")
    render_keep(pdf_path, consensus, results,
                 overlays_dir / "soft_barriers_keep.png")
    render_reject_warn(pdf_path, consensus, results,
                        overlays_dir / "soft_barriers_reject_warn.png")
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="audit_soft_barriers",
        description=(
            "Diagnostic audit of every soft_barrier in a consensus. "
            "READ-ONLY: classifies as keep/warn/reject per the "
            "user-mandated conservative rules; never deletes."
        ),
    )
    ap.add_argument("consensus", type=Path,
                    help="consensus_model.json path")
    ap.add_argument("--out", type=Path, required=True,
                    help="output JSON path for the audit report")
    ap.add_argument("--pdf", type=Path, required=True,
                    help="source PDF for the overlay underlay")
    ap.add_argument("--overlays-dir", type=Path, required=True,
                    help="directory to write the three overlay PNGs")
    args = ap.parse_args(argv)

    report = audit(args.consensus.resolve(), args.pdf.resolve(),
                    args.out.resolve(), args.overlays_dir.resolve())
    s = report["summary"]
    print(f"[audit] total={s['total']} keep={s['keep']} "
          f"warn={s['warn']} reject={s['reject']}")
    print(f"[audit] report -> {args.out}")
    print(f"[audit] overlays -> {args.overlays_dir}/soft_barriers_*.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
