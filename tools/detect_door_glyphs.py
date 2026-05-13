"""Detect door glyphs in the PDF and emit a diagnostic JSON.

Architectural insight (user mandate 2026-05-11):
> "Portas no PDF são facilmente identificáveis pelo glyph de porta:
>   - linha reta representa a folha;
>   - arco/quarto de círculo representa o swing/giro;
>   - centro/pivô do arco indica a dobradiça;
>   - vão na parede é a abertura real.
>  Portanto, para door detection, o pipeline não deve depender
>  apenas de colinear gaps entre walls."

This module wraps the existing ``tools.extract_openings_vector._arc_candidates``
arc detector and adds:

1. Hinge/chord inference per arc — which bbox corner is the pivot
   (closest to a consensus wall) vs the chord endpoint.
2. Door-width + swing direction derived from the arc's bbox + the
   pivot-corner geometry.
3. Cross-reference against the human openings list — flag each glyph as:
     matched_human    : a human opening within `match_tol_pts` of the glyph
     unmatched_glyph  : glyph detected but no human opening near
     glyph_without_host_wall : glyph exists but consensus.walls has no
                               wall to host it (this is the
                               door_glyph_detected_but_host_wall_missing
                               classification the user mandated)
4. List of glyphs whose hinge-corner has no wall within wall_match_tol.

Emits:
- door_glyph_candidates.json — full glyph list + cross-ref labels
- door_glyph_summary.md      — human-readable per-glyph table

The detector does NOT mutate the consensus. It is a pure diagnostic
surface: use it to confirm h_o005-style openings are real
architecture (door arc visible in the PDF) even when the host wall
is missing from stage-1 extraction.

Companion: ``tools/render_door_glyph_overlay.py``.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import pypdfium2 as pdfium

THIS = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS))


@dataclass
class DoorGlyph:
    id: str
    bbox_pts: list[float]    # (l, b, r, t)
    n_seg: int
    n_cubic: int
    hinge_corner_pt: list[float]   # the corner closest to a wall (pivot)
    chord_corner_pt: list[float]   # opposite corner (door leaf endpoint when closed)
    door_width_pts: float          # max(bbox w, bbox h) — chord length
    nearest_wall_id: str | None
    nearest_wall_dist_pts: float | None
    cross_ref: str             # matched_human | unmatched_glyph | glyph_without_host_wall
    matched_human_opening_id: str | None
    matched_human_kind: str | None
    match_distance_pts: float | None


def _bbox_corners(b: tuple[float, float, float, float]) -> list[tuple[float, float]]:
    x0, y0, x1, y1 = b
    return [(x0, y0), (x1, y0), (x0, y1), (x1, y1)]


def _point_to_segment_dist(px: float, py: float,
                            ax: float, ay: float,
                            bx: float, by: float) -> float:
    dx, dy = bx - ax, by - ay
    seg_sq = dx * dx + dy * dy
    if seg_sq < 1e-6:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg_sq))
    cx, cy = ax + t * dx, ay + t * dy
    return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5


def _nearest_wall(point: tuple[float, float],
                   walls: list[dict],
                   thickness: float) -> tuple[str | None, float]:
    px, py = point
    best_id: str | None = None
    best_d = float("inf")
    for w in walls:
        s = w.get("start")
        e = w.get("end")
        if not s or not e:
            continue
        d = _point_to_segment_dist(px, py, s[0], s[1], e[0], e[1])
        if d < best_d:
            best_d = d
            best_id = w.get("id")
    return best_id, best_d


def detect(pdf_path: Path,
            consensus_path: Path,
            match_tol_pts: float = 30.0,
            wall_match_tol_pts: float = 12.0) -> dict:
    """Run the arc detector on the PDF + cross-reference with the
    consensus's human openings."""
    from extract_openings_vector import _arc_candidates

    consensus = json.loads(consensus_path.read_text())
    region = tuple(consensus.get("planta_region",
                                   (0.0, 0.0, 595.0, 842.0)))
    walls = consensus.get("walls", [])
    thickness = float(consensus.get("wall_thickness_pts", 5.4))
    human_openings = [op for op in consensus.get("openings", [])
                      if op.get("geometry_origin") == "human_annotation"]

    pdf = pdfium.PdfDocument(str(pdf_path))
    page = pdf[0]
    arcs = _arc_candidates(page, region)
    pdf.close()

    glyphs: list[DoorGlyph] = []
    for i, arc in enumerate(arcs):
        bbox = (float(arc.bbox[0]), float(arc.bbox[1]),
                 float(arc.bbox[2]), float(arc.bbox[3]))
        corners = _bbox_corners(bbox)
        # Identify hinge corner: the bbox corner whose distance to the
        # NEAREST wall is minimal. The other corner along that diagonal
        # is the chord endpoint.
        best_corner = None
        best_wall_dist = float("inf")
        best_wall_id = None
        for c in corners:
            wid, d = _nearest_wall(c, walls, thickness)
            if d < best_wall_dist:
                best_wall_dist = d
                best_corner = c
                best_wall_id = wid
        if best_corner is None:
            best_corner = corners[0]
        # Chord corner: diagonally opposite
        cx, cy = best_corner
        diag_x = bbox[2] if cx == bbox[0] else bbox[0]
        diag_y = bbox[3] if cy == bbox[1] else bbox[1]
        chord = (diag_x, diag_y)
        door_width = max(bbox[2] - bbox[0], bbox[3] - bbox[1])

        # Cross-reference with human openings
        glyph_center = ((bbox[0] + bbox[2]) / 2.0,
                         (bbox[1] + bbox[3]) / 2.0)
        match_op: dict | None = None
        match_d = float("inf")
        for op in human_openings:
            c = op.get("center")
            if not c:
                continue
            d = ((glyph_center[0] - c[0]) ** 2
                  + (glyph_center[1] - c[1]) ** 2) ** 0.5
            if d < match_d:
                match_d = d
                match_op = op
        if match_op is None or match_d > match_tol_pts:
            cross_ref = "unmatched_glyph"
            matched_id = None
            matched_kind = None
            match_dist = float("inf")
        else:
            matched_id = match_op["id"]
            matched_kind = match_op.get("kind_v5") or match_op.get("kind")
            match_dist = match_d
            # Even if matched, check whether wall_id is null → host missing
            if best_wall_dist > wall_match_tol_pts or best_wall_id is None:
                cross_ref = "glyph_without_host_wall"
            else:
                cross_ref = "matched_human"

        glyphs.append(DoorGlyph(
            id=f"dg_{i:03d}",
            bbox_pts=list(bbox),
            n_seg=int(arc.n_seg),
            n_cubic=int(arc.n_cubic),
            hinge_corner_pt=list(best_corner),
            chord_corner_pt=list(chord),
            door_width_pts=round(door_width, 3),
            nearest_wall_id=best_wall_id,
            nearest_wall_dist_pts=(round(best_wall_dist, 3)
                                    if best_wall_dist != float("inf") else None),
            cross_ref=cross_ref,
            matched_human_opening_id=matched_id,
            matched_human_kind=matched_kind,
            match_distance_pts=(round(match_dist, 3)
                                 if match_dist != float("inf") else None),  # type: ignore[arg-type]
        ))

    # Build the human-opening match map (reverse cross-reference)
    glyphs_by_human: dict[str, list[str]] = {}
    for g in glyphs:
        if g.matched_human_opening_id:
            glyphs_by_human.setdefault(
                g.matched_human_opening_id, []
            ).append(g.id)
    human_without_glyph: list[str] = []
    for op in human_openings:
        if op["id"] not in glyphs_by_human:
            human_without_glyph.append(op["id"])

    summary = {
        "n_glyphs": len(glyphs),
        "n_walls_in_consensus": len(walls),
        "n_human_openings": len(human_openings),
        "by_cross_ref": {
            "matched_human": sum(1 for g in glyphs if g.cross_ref == "matched_human"),
            "unmatched_glyph": sum(1 for g in glyphs if g.cross_ref == "unmatched_glyph"),
            "glyph_without_host_wall": sum(1 for g in glyphs if g.cross_ref == "glyph_without_host_wall"),
        },
        "glyphs_per_human_opening": glyphs_by_human,
        "human_openings_without_glyph": human_without_glyph,
    }

    return {
        "schema_version": "1.0",
        "pdf_path": str(pdf_path),
        "consensus_path": str(consensus_path),
        "match_tol_pts": match_tol_pts,
        "wall_match_tol_pts": wall_match_tol_pts,
        "summary": summary,
        "glyphs": [asdict(g) for g in glyphs],
    }


def _write_summary_md(report: dict, out_md: Path) -> None:
    lines = []
    pdf = Path(report["pdf_path"]).name
    lines.append(f"# Door glyph candidates — `{pdf}`")
    lines.append("")
    s = report["summary"]
    lines.append(f"- glyphs detected: **{s['n_glyphs']}**")
    lines.append(f"- consensus walls: {s['n_walls_in_consensus']}")
    lines.append(f"- human openings: {s['n_human_openings']}")
    lines.append("")
    lines.append("## Cross-reference summary")
    lines.append("")
    lines.append(f"- matched_human: **{s['by_cross_ref']['matched_human']}** (glyph + nearby human opening + host wall)")
    lines.append(f"- glyph_without_host_wall: **{s['by_cross_ref']['glyph_without_host_wall']}** "
                 f"(glyph + human opening, but NO wall to host — paint a human_wall)")
    lines.append(f"- unmatched_glyph: **{s['by_cross_ref']['unmatched_glyph']}** "
                 f"(glyph detected but no human opening within {report['match_tol_pts']}pt)")
    lines.append("")
    if s["human_openings_without_glyph"]:
        lines.append("## Human openings WITHOUT a matching glyph")
        lines.append("")
        lines.append("(may be windows/balconies — glyphs are doors only)")
        lines.append(f"- {', '.join(s['human_openings_without_glyph'])}")
        lines.append("")
    lines.append("## Per-glyph table")
    lines.append("")
    lines.append("| id | bbox_pts | door_width | nearest_wall | wall_dist | matched_human | match_dist | cross_ref |")
    lines.append("|---|---|---:|---|---:|---|---:|---|")
    for g in report["glyphs"]:
        b = g["bbox_pts"]
        bs = f"({b[0]:.0f},{b[1]:.0f},{b[2]:.0f},{b[3]:.0f})"
        wid = g["nearest_wall_id"] or "—"
        wd = (f"{g['nearest_wall_dist_pts']:.1f}"
              if g["nearest_wall_dist_pts"] is not None else "—")
        mh = g["matched_human_opening_id"] or "—"
        if g["matched_human_kind"]:
            mh = f"{mh} ({g['matched_human_kind']})"
        md = (f"{g['match_distance_pts']:.1f}"
              if g["match_distance_pts"] is not None else "—")
        lines.append(f"| {g['id']} | {bs} | {g['door_width_pts']:.1f} | "
                     f"{wid} | {wd} | {mh} | {md} | {g['cross_ref']} |")
    out_md.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", type=Path, required=True)
    ap.add_argument("--consensus", type=Path, required=True)
    ap.add_argument("--out-json", type=Path, required=True)
    ap.add_argument("--out-summary", type=Path, default=None)
    ap.add_argument("--match-tol-pts", type=float, default=30.0,
                    help="Max distance for a glyph to match a human opening.")
    ap.add_argument("--wall-match-tol-pts", type=float, default=12.0,
                    help="Max distance from glyph hinge to a wall (above = glyph_without_host_wall).")
    args = ap.parse_args()
    report = detect(args.pdf, args.consensus,
                     args.match_tol_pts, args.wall_match_tol_pts)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(report, indent=2))
    print(f"[ok] glyphs -> {args.out_json}")
    if args.out_summary:
        args.out_summary.parent.mkdir(parents=True, exist_ok=True)
        _write_summary_md(report, args.out_summary)
        print(f"[ok] summary -> {args.out_summary}")

    s = report["summary"]
    print()
    print("=== glyph summary ===")
    print(f"  detected:                  {s['n_glyphs']}")
    print(f"  matched_human:             {s['by_cross_ref']['matched_human']}")
    print(f"  glyph_without_host_wall:   {s['by_cross_ref']['glyph_without_host_wall']}  <-- evidence for human_walls")
    print(f"  unmatched_glyph:           {s['by_cross_ref']['unmatched_glyph']}")
    if s["human_openings_without_glyph"]:
        print(f"  human openings without glyph: {s['human_openings_without_glyph']}")


if __name__ == "__main__":
    main()
