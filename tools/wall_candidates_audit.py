"""Audit filled-path classification in build_vector_consensus._identify_wall_paths.

The vector wall extractor picks a single fill-color + thickness cluster
and discards every other filled path silently. Empirically on planta_74
this discards the structural dividers between A.S. / TERRACO SOCIAL /
COZINHA / TERRACO TECNICO (cell merge observed in FP-014 P0 polygonize
output, 4 of 11 rooms collapsed into one cell).

This tool re-runs the same logic with instrumentation: for every filled
path it records the cluster it belongs to, the per-cluster score, and
the exact rejection reason. It emits:

- ``<stem>_audit_report.json`` — full table of candidates + clusters
- ``<stem>_audit_overlay.png`` — PDF page with accepted walls (green),
  rejected wall-like candidates (red), and other filled paths (gray)
- ``<stem>_audit_summary.md`` — human-readable per-cluster summary

The tool does NOT mutate any pipeline output. It is pure diagnostic.

Usage:
    python -m tools.wall_candidates_audit planta_74.pdf \\
        --out-json runs/audit/planta_74_audit.json \\
        --out-overlay runs/audit/planta_74_audit.png \\
        --out-summary runs/audit/planta_74_audit.md

Companion: ``docs/diagnostics/2026-05-09_skp_visual_failure_fp014.md``
§"Stage 1 wall extraction" — the canonical FP-014 P0 root-cause
investigation.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c
from matplotlib.patches import Rectangle

# --- types -------------------------------------------------------------------

@dataclass
class PathRecord:
    path_idx: int
    bbox: tuple[float, float, float, float]   # PDF pts: l, b, r, t
    short_dim: float
    long_dim: float
    fill_rgba: tuple[int, int, int, int]
    fillmode: int
    stroke_on: int
    nseg: int

    # Classification (filled by audit pipeline)
    is_filled_candidate: bool = False
    cluster_id: int | None = None          # group by fill color
    cluster_score: float | None = None
    is_best_cluster: bool = False
    within_thickness_band: bool = False
    long_greater_than_median: bool = False
    accepted: bool = False
    rejection_reason: str = ""


@dataclass
class ClusterRecord:
    cluster_id: int
    fill_rgba: tuple[int, int, int, int]
    member_count: int
    median_thickness: float
    tightness_frac_within_30pct: float
    darkness: float
    score: float
    is_best: bool


# --- reading PDF paths -------------------------------------------------------

def _read_all_filled_paths(page) -> list[PathRecord]:
    """Pull every path object from the page and record its raw attrs.

    Mirrors tools/build_vector_consensus.py:_read_paths but records ALL
    paths (not just the ones the wall classifier would inspect) so the
    audit can show "this was filtered out before color clustering".
    """
    out: list[PathRecord] = []
    for idx, obj in enumerate(page.get_objects()):
        if obj.type != 2:  # path
            continue
        l_, b_, r_, t_ = obj.get_pos()
        raw = obj.raw
        fillmode = ctypes.c_int(0)
        stroke = ctypes.c_int(0)
        pdfium_c.FPDFPath_GetDrawMode(raw, ctypes.byref(fillmode),
                                       ctypes.byref(stroke))
        fr, fg, fb, fa = (ctypes.c_uint() for _ in range(4))
        pdfium_c.FPDFPageObj_GetFillColor(raw, ctypes.byref(fr),
                                           ctypes.byref(fg),
                                           ctypes.byref(fb),
                                           ctypes.byref(fa))
        nseg = pdfium_c.FPDFPath_CountSegments(raw)
        bbox = (l_, b_, r_, t_)
        w = r_ - l_
        h = t_ - b_
        short = min(w, h)
        long_ = max(w, h)
        out.append(PathRecord(
            path_idx=idx,
            bbox=bbox,
            short_dim=short,
            long_dim=long_,
            fill_rgba=(fr.value, fg.value, fb.value, fa.value),
            fillmode=fillmode.value,
            stroke_on=stroke.value,
            nseg=nseg,
        ))
    return out


# --- classification logic (parallel to build_vector_consensus) ---------------

def _cluster_score(items: list[PathRecord]) -> tuple[float, float, float, float]:
    """Return (score, tightness, darkness, median_thickness) — mirrors
    ``build_vector_consensus._identify_wall_paths.score``."""
    if len(items) < 4:
        return 0.0, 0.0, 0.0, 0.0
    ts = [i.short_dim for i in items]
    med = statistics.median(ts)
    if med <= 0:
        return 0.0, 0.0, 0.0, 0.0
    tight = sum(1 for t in ts if abs(t - med) / med <= 0.30) / len(ts)
    r, g, b, _ = items[0].fill_rgba
    darkness = 1.0 - (r + g + b) / (3 * 255.0)
    score = len(items) * tight * (0.5 + 0.5 * darkness)
    return score, tight, darkness, med


def _wall_like_stroke(p: PathRecord, accepted_walls: list[PathRecord],
                      planta_region: tuple[float, float, float, float] | None,
                      min_long: float = 25.0,
                      max_short: float = 3.0,
                      min_aspect: float = 5.0) -> bool:
    """Identify stroked-only paths that LOOK like wall dividers / peitoris.

    Heuristic:
    - long_dim > min_long (excludes dimension ticks)
    - short_dim < max_short (excludes fixtures)
    - aspect long/short > min_aspect (excludes square objects)
    - bbox CENTER inside planta_region (excludes title block / legend
      lines outside the floor plan area)
    - bbox NOT contained within any accepted wall by > 50% area
      (excludes dimension lines drawn next to walls)
    """
    if p.fillmode != 0 or not p.stroke_on:
        return False
    if p.long_dim < min_long:
        return False
    if p.short_dim > max_short:
        return False
    short = max(p.short_dim, 0.001)
    if p.long_dim / short < min_aspect:
        return False
    bl, bb, br, bt = p.bbox
    # Center inside planta_region (when provided)
    if planta_region is not None:
        cx = (bl + br) / 2.0
        cy = (bb + bt) / 2.0
        rx0, ry0, rx1, ry1 = planta_region
        if not (rx0 <= cx <= rx1 and ry0 <= cy <= ry1):
            return False
    # Reject if it sits inside an accepted wall (likely a stroke
    # outline drawn around the same wall rectangle).
    barea = max(0.0, (br - bl) * (bt - bb))
    if barea > 0:
        for w in accepted_walls:
            wl, wb, wr, wt = w.bbox
            ix0 = max(bl, wl)
            iy0 = max(bb, wb)
            ix1 = min(br, wr)
            iy1 = min(bt, wt)
            if ix1 > ix0 and iy1 > iy0:
                inter = (ix1 - ix0) * (iy1 - iy0)
                if inter / barea > 0.50:
                    return False
    return True


def audit(pdf_path: Path) -> dict[str, Any]:
    """Re-run the wall classifier with instrumentation. Returns a dict
    with full per-path classification plus per-cluster summary."""
    pdf = pdfium.PdfDocument(str(pdf_path))
    page = pdf[0]
    page_w = page.get_size()[0]
    page_h = page.get_size()[1]
    paths = _read_all_filled_paths(page)
    pdf.close()

    # Step 1: filled-only filter (parallels build_vector_consensus line 99-100)
    for p in paths:
        if p.fillmode != 0 and p.stroke_on == 0:
            p.is_filled_candidate = True
        else:
            if p.fillmode == 0:
                p.rejection_reason = "not_filled (fillmode==0)"
            elif p.stroke_on:
                p.rejection_reason = "has_stroke (stroke_on!=0)"

    candidates = [p for p in paths if p.is_filled_candidate]

    # Step 2: drop too-small (long_dim < 5 pt). Parallels line 114.
    for p in candidates:
        if p.long_dim < 5.0:
            p.rejection_reason = (
                f"long_dim_too_small (long={p.long_dim:.2f}<5.0)"
            )

    candidates = [p for p in candidates if p.long_dim >= 5.0]

    # Step 3: cluster by fill color. Parallels lines 112-116.
    by_color: dict[tuple[int, int, int, int], list[PathRecord]] = {}
    for p in candidates:
        by_color.setdefault(p.fill_rgba, []).append(p)

    clusters: list[ClusterRecord] = []
    for cid, (color, items) in enumerate(sorted(by_color.items())):
        score, tight, dark, med = _cluster_score(items)
        for p in items:
            p.cluster_id = cid
            p.cluster_score = score
        clusters.append(ClusterRecord(
            cluster_id=cid,
            fill_rgba=color,
            member_count=len(items),
            median_thickness=med,
            tightness_frac_within_30pct=tight,
            darkness=dark,
            score=score,
            is_best=False,
        ))

    # Step 4: pick best-scoring cluster. Parallels line 137.
    if clusters:
        best = max(clusters, key=lambda c: c.score)
        best.is_best = True
        for p in candidates:
            if p.cluster_id == best.cluster_id:
                p.is_best_cluster = True
            else:
                p.rejection_reason = (
                    f"not_best_color_cluster (cluster={p.cluster_id} "
                    f"score={p.cluster_score:.2f}, "
                    f"best={best.cluster_id} score={best.score:.2f})"
                )

        # Step 5: within best cluster, thickness ±30% + long > median.
        # Parallels lines 140-145.
        pool = [p for p in candidates if p.is_best_cluster]
        if pool:
            ts = [p.short_dim for p in pool]
            med = statistics.median(ts)
            for p in pool:
                within = abs(p.short_dim - med) / med <= 0.30
                long_ok = p.long_dim > med
                p.within_thickness_band = within
                p.long_greater_than_median = long_ok
                if within and long_ok:
                    p.accepted = True
                elif not within:
                    p.rejection_reason = (
                        f"thickness_outside_band "
                        f"(short={p.short_dim:.2f}, med={med:.2f}, "
                        f"delta={abs(p.short_dim-med)/med:.1%}>30%)"
                    )
                else:
                    p.rejection_reason = (
                        f"long_dim_below_median "
                        f"(long={p.long_dim:.2f}, med={med:.2f})"
                    )

    # Step 6 (NEW for audit): identify stroked-only paths that LOOK like
    # wall dividers / peitoris missed by the filled-path-only classifier.
    # Restrict to the planta_region (computed from accepted-wall bboxes)
    # so legend / title-block stroked lines don't pollute the result.
    accepted_walls_list = [p for p in paths if p.accepted]
    if accepted_walls_list:
        xs = [c for w in accepted_walls_list for c in (w.bbox[0], w.bbox[2])]
        ys = [c for w in accepted_walls_list for c in (w.bbox[1], w.bbox[3])]
        margin = 10.0
        planta_region: tuple[float, float, float, float] | None = (
            min(xs) - margin, min(ys) - margin,
            max(xs) + margin, max(ys) + margin,
        )
    else:
        planta_region = None
    stroked_wall_like: list[dict] = []
    for p in paths:
        if _wall_like_stroke(p, accepted_walls_list, planta_region):
            stroked_wall_like.append({
                "path_idx": p.path_idx,
                "bbox": list(p.bbox),
                "short_dim": p.short_dim,
                "long_dim": p.long_dim,
                "fill_rgba": list(p.fill_rgba),
                "nseg": p.nseg,
            })

    return {
        "pdf_path": str(pdf_path),
        "page_size_pts": [page_w, page_h],
        "total_paths": len(paths),
        "filled_candidates": sum(1 for p in paths if p.is_filled_candidate),
        "accepted_walls": sum(1 for p in paths if p.accepted),
        "rejected_filled_candidates": sum(
            1 for p in paths
            if p.is_filled_candidate and not p.accepted),
        "stroked_wall_like_count": len(stroked_wall_like),
        "stroked_wall_like": stroked_wall_like,
        "clusters": [asdict(c) for c in clusters],
        "paths": [asdict(p) for p in paths],
    }


# --- overlay rendering -------------------------------------------------------

def render_overlay(audit_result: dict, pdf_path: Path, out_png: Path,
                   dpi: int = 200) -> None:
    """Render PDF page 1 with classification overlay.

    Color key:
      green  = accepted wall
      red    = rejected wall-like (filled candidate, not accepted)
      gray   = filled path skipped before clustering (small, no-fill, etc.)
      blue   = stroked-only path (window/door candidates, soft barriers)
      none   = not drawn
    """
    pdf = pdfium.PdfDocument(str(pdf_path))
    page = pdf[0]
    # Page bitmap as background
    bitmap = page.render(scale=2.0).to_pil()
    pdf.close()

    fig, ax = plt.subplots(figsize=(14, 18), dpi=dpi, facecolor="white")
    page_w, page_h = audit_result["page_size_pts"]
    # Bitmap is rendered with y-down; PDF coords are y-up. We'll plot in
    # PDF pts and flip Y after.
    ax.imshow(bitmap, extent=(0, page_w, 0, page_h), aspect="equal", alpha=0.45)

    stroked_wall_like_idx = {p["path_idx"]
                              for p in audit_result.get("stroked_wall_like", [])}

    for p in audit_result["paths"]:
        x0, y0, x1, y1 = p["bbox"]
        w, h = max(x1 - x0, 0.01), max(y1 - y0, 0.01)
        if p.get("accepted"):
            fc, ec, alpha, lw = "#2e7d32", "#1b5e20", 0.55, 1.0
            zorder = 6
        elif p["path_idx"] in stroked_wall_like_idx:
            # Stroked but looks like a wall divider — the headline finding
            fc, ec, alpha, lw = "none", "#ff6f00", 0.95, 1.5
            zorder = 7  # above filled walls so they're visible
        elif p.get("is_filled_candidate") and not p.get("accepted"):
            fc, ec, alpha, lw = "#d32f2f", "#b71c1c", 0.55, 1.0
            zorder = 5
        elif p.get("fillmode", 0) != 0:
            # filled but not a candidate (too small etc)
            fc, ec, alpha, lw = "#9e9e9e", "#616161", 0.30, 0.5
            zorder = 4
        elif p.get("stroke_on"):
            fc, ec, alpha, lw = "none", "#1565c0", 0.30, 0.3
            zorder = 3
        else:
            continue
        ax.add_patch(Rectangle((x0, y0), w, h, facecolor=fc, edgecolor=ec,
                               linewidth=lw, alpha=alpha, zorder=zorder))

    # Legend
    from matplotlib.patches import Patch
    sw = audit_result.get("stroked_wall_like_count", 0)
    legend = [
        Patch(facecolor="#2e7d32", edgecolor="#1b5e20",
              label=f"accepted walls ({audit_result['accepted_walls']})"),
        Patch(facecolor="none", edgecolor="#ff6f00", linewidth=1.5,
              label=f"stroked wall-like (missed dividers? {sw})"),
        Patch(facecolor="#d32f2f", edgecolor="#b71c1c",
              label=f"rejected filled (fixtures/legend) ({audit_result['rejected_filled_candidates']})"),
        Patch(facecolor="#9e9e9e", edgecolor="#616161",
              label="filled pre-filtered (too small)"),
        Patch(facecolor="none", edgecolor="#1565c0",
              label="other stroked (dimension lines, hatch)"),
    ]
    ax.legend(handles=legend, loc="upper left", fontsize=9, framealpha=0.9)

    ax.set_title(f"Wall classification audit — {Path(pdf_path).name}\n"
                 f"page {page_w:.0f}×{page_h:.0f} pt — "
                 f"{audit_result['total_paths']} total paths, "
                 f"{audit_result['filled_candidates']} filled candidates, "
                 f"{audit_result['accepted_walls']} accepted",
                 fontsize=11, color="#222", pad=10)
    ax.set_xlim(0, page_w)
    ax.set_ylim(0, page_h)
    ax.set_aspect("equal")
    ax.set_axis_off()
    plt.tight_layout()
    plt.savefig(out_png, dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"[ok] overlay -> {out_png}")


# --- summary markdown --------------------------------------------------------

def render_summary(audit_result: dict, out_md: Path) -> None:
    pdf_name = Path(audit_result["pdf_path"]).name
    page_w, page_h = audit_result["page_size_pts"]
    lines = []
    lines.append(f"# Wall candidates audit — `{pdf_name}`")
    lines.append("")
    lines.append(f"Page size: {page_w:.0f} × {page_h:.0f} pt")
    lines.append(f"Total paths: {audit_result['total_paths']}")
    lines.append(f"Filled candidates: {audit_result['filled_candidates']}")
    lines.append(f"Accepted walls: {audit_result['accepted_walls']}")
    lines.append(f"Rejected filled wall-like: {audit_result['rejected_filled_candidates']}")
    lines.append(f"**Stroked wall-like (candidate dividers): {audit_result.get('stroked_wall_like_count', 0)}**")
    lines.append("")
    lines.append("## Color clusters (filled candidates ≥ 5pt long)")
    lines.append("")
    lines.append("| cid | RGBA | members | median t | tight ≤30% | darkness | score | best? |")
    lines.append("|---|---|---:|---:|---:|---:|---:|:---:|")
    for c in sorted(audit_result["clusters"], key=lambda x: -x["score"]):
        rgba = c["fill_rgba"]
        rgba_str = f"({rgba[0]},{rgba[1]},{rgba[2]},{rgba[3]})"
        best = "**YES**" if c["is_best"] else ""
        lines.append(
            f"| {c['cluster_id']} | {rgba_str} | {c['member_count']} | "
            f"{c['median_thickness']:.2f} | "
            f"{c['tightness_frac_within_30pct']:.0%} | "
            f"{c['darkness']:.2f} | {c['score']:.2f} | {best} |"
        )
    lines.append("")

    # Rejection-reason histogram
    reasons: dict[str, int] = {}
    for p in audit_result["paths"]:
        if p["accepted"]:
            continue
        reason = p["rejection_reason"] or "uncategorized"
        # Normalize: collapse numeric params for histogram readability
        # ('not_best_color_cluster (cluster=2 ...)' → 'not_best_color_cluster')
        head = reason.split(" (")[0]
        reasons[head] = reasons.get(head, 0) + 1
    lines.append("## Rejection reasons (all paths)")
    lines.append("")
    lines.append("| reason | count |")
    lines.append("|---|---:|")
    for reason, count in sorted(reasons.items(), key=lambda x: -x[1]):
        lines.append(f"| {reason} | {count} |")
    lines.append("")

    # Wall-like rejected: full list with bbox so a reviewer can locate
    # them on the overlay.
    rejected_walllike = [
        p for p in audit_result["paths"]
        if p["is_filled_candidate"] and not p["accepted"]
    ]
    lines.append(f"## Rejected wall-like candidates ({len(rejected_walllike)})")
    lines.append("")
    if rejected_walllike:
        lines.append("Sorted by long_dim descending — longer rejected paths "
                     "are more likely to be missed dividers.")
        lines.append("")
        lines.append("| idx | bbox (l,b,r,t) | short | long | RGBA | cluster | reason |")
        lines.append("|---|---|---:|---:|---|---:|---|")
        for p in sorted(rejected_walllike,
                        key=lambda x: -x["long_dim"])[:50]:
            x0, y0, x1, y1 = p["bbox"]
            bbox_str = f"({x0:.0f},{y0:.0f},{x1:.0f},{y1:.0f})"
            rgba = p["fill_rgba"]
            rgba_str = f"({rgba[0]},{rgba[1]},{rgba[2]},{rgba[3]})"
            head = (p["rejection_reason"] or "").split(" (")[0]
            cluster = p.get("cluster_id", "—")
            lines.append(
                f"| {p['path_idx']} | {bbox_str} | "
                f"{p['short_dim']:.2f} | {p['long_dim']:.2f} | "
                f"{rgba_str} | {cluster} | {head} |"
            )
        lines.append("")
    # Stroked wall-like (the headline finding)
    sw = audit_result.get("stroked_wall_like", [])
    lines.append(f"## Stroked wall-like candidates ({len(sw)})")
    lines.append("")
    lines.append("Stroked-only paths with long_dim ≥ 25pt, short_dim ≤ 3pt, "
                 "aspect ≥ 5, NOT overlapping accepted walls by >50%.")
    lines.append("These are the most likely *missed dividers / peitoris* — "
                 "the existing wall classifier inspects only filled paths.")
    lines.append("")
    if sw:
        lines.append("| idx | bbox (l,b,r,t) | short | long | aspect | nseg | RGBA |")
        lines.append("|---|---|---:|---:|---:|---:|---|")
        for p in sorted(sw, key=lambda x: -x["long_dim"])[:40]:
            x0, y0, x1, y1 = p["bbox"]
            bbox_str = f"({x0:.0f},{y0:.0f},{x1:.0f},{y1:.0f})"
            asp = (p["long_dim"] / max(p["short_dim"], 0.001))
            rgba = p["fill_rgba"]
            rgba_str = f"({rgba[0]},{rgba[1]},{rgba[2]},{rgba[3]})"
            lines.append(
                f"| {p['path_idx']} | {bbox_str} | "
                f"{p['short_dim']:.2f} | {p['long_dim']:.2f} | "
                f"{asp:.1f} | {p['nseg']} | {rgba_str} |"
            )
        lines.append("")
    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(f"[ok] summary -> {out_md}")


# --- CLI ---------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--out-json", type=Path, default=None)
    ap.add_argument("--out-overlay", type=Path, default=None)
    ap.add_argument("--out-summary", type=Path, default=None)
    args = ap.parse_args()

    result = audit(args.pdf)
    stem = args.pdf.stem
    out_json = args.out_json or args.pdf.with_name(f"{stem}_audit.json")
    out_overlay = (args.out_overlay
                   or args.pdf.with_name(f"{stem}_audit_overlay.png"))
    out_summary = (args.out_summary
                   or args.pdf.with_name(f"{stem}_audit.md"))

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(result, indent=2))
    print(f"[ok] json    -> {out_json}")
    render_overlay(result, args.pdf, out_overlay)
    render_summary(result, out_summary)

    print()
    print(f"=== {args.pdf.name} ===")
    print(f"  total paths:       {result['total_paths']}")
    print(f"  filled candidates: {result['filled_candidates']}")
    print(f"  accepted walls:    {result['accepted_walls']}")
    print(f"  rejected wall-like: {result['rejected_filled_candidates']}")
    print(f"  color clusters:    {len(result['clusters'])}")
    best = next((c for c in result['clusters'] if c['is_best']), None)
    if best:
        print(f"  best cluster RGBA: {best['fill_rgba']}, "
              f"members={best['member_count']}, "
              f"score={best['score']:.2f}")


if __name__ == "__main__":
    main()
