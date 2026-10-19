"""FP-026 wall-stub diagnostic.

Renders staged debug overlays + emits `wall_stub_report.json` for a
given consensus. Classifies each remaining protrusion in the shell
polygon (post-canonicalise) per the FP-026 heuristic.

Run:

    python -m tools.diagnose_wall_stubs <consensus.json> --plant <name>

Outputs land under ``artifacts/review/<plant>/``.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPoly
from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union

from tools.build_plan_shell_skp import (
    SNAP_EPS_PTS,
    _classify_endpoint_junctions,
    build_shell_polygon,
    opening_carve_rect,
    wall_footprint,
)


# ---- FP-026 detection thresholds ------------------------------------

STUB_MAX_LENGTH_RATIO = 1.5  # × wall_thickness
STUB_WIDTH_TOLERANCE = 0.20  # ±20% of wall_thickness
STUB_MIN_ATTACHED_RATIO = 0.25
SCHEMA = "fp026.wall_stub_report.v1"


@dataclass
class StubCandidate:
    stub_id: str
    stage_detected: str
    bbox: list[float]
    centroid: list[float]
    area_pts2: float
    long_axis_pts: float
    short_axis_pts: float
    touches_wall_ids: list[str]
    near_opening_ids: list[str]
    classification: str
    verdict: str
    evidence: str


def _stage_shells(consensus: dict) -> dict[str, list[Polygon]]:
    """Return per-stage shell snapshots for diagnostic rendering."""
    walls = consensus.get("walls", [])
    openings = consensus.get("openings", [])
    default_thickness = consensus.get("wall_thickness_pts")
    junctions = _classify_endpoint_junctions(walls)

    raw_boxes = [wall_footprint(w, extend_endpoints=False) for w in walls]
    jct_boxes = [
        wall_footprint(
            w,
            extend_start=junctions[w["id"]][0],
            extend_end=junctions[w["id"]][1],
        )
        for w in walls
    ]
    unioned = unary_union(jct_boxes)
    closed = (
        unioned.buffer(SNAP_EPS_PTS, join_style=2, mitre_limit=10.0)
        .buffer(-SNAP_EPS_PTS, join_style=2, mitre_limit=10.0)
    )

    # Carve openings (matching build_shell_polygon's CARVING_ORIGINS rule)
    from tools.build_plan_shell_skp import (
        CARVING_ORIGINS,
        is_window_aperture,
    )

    walls_by_id = {w["id"]: w for w in walls if "id" in w}
    carve_rects = []
    for op in openings:
        wid = op.get("wall_id")
        host = walls_by_id.get(wid)
        if host is None:
            continue
        origin = op.get("geometry_origin", "")
        if origin and origin not in CARVING_ORIGINS:
            continue
        if is_window_aperture(op):
            continue
        try:
            carve_rects.append(opening_carve_rect(op, host, default_thickness))
        except ValueError:
            continue
    carved = closed
    if carve_rects:
        carved = closed.difference(unary_union(carve_rects))

    def _to_list(geom):
        if geom.geom_type == "Polygon":
            return [geom]
        if geom.geom_type == "MultiPolygon":
            return list(geom.geoms)
        return []

    return {
        "raw_boxes": [p for p in _to_list(unary_union(raw_boxes))],
        "junction_boxes": [p for p in _to_list(unary_union(jct_boxes))],
        "unioned": _to_list(unioned),
        "closed": _to_list(closed),
        "carved": _to_list(carved),
    }


def _is_stublike(piece: Polygon, walls: list[dict]) -> dict | None:
    """Return classification dict if piece looks like a stub, else None."""
    if not piece.is_valid:
        return None
    minx, miny, maxx, maxy = piece.bounds
    dx = maxx - minx
    dy = maxy - miny
    if dx <= 0 or dy <= 0:
        return None
    long_axis = max(dx, dy)
    short_axis = min(dx, dy)
    if short_axis < 1e-3:
        return None

    # Average wall thickness reference
    thicknesses = [w["thickness"] for w in walls if "thickness" in w]
    if not thicknesses:
        return None
    typical_t = sum(thicknesses) / len(thicknesses)

    # Heuristic: width close to wall thickness AND length small relative
    width_match = (
        (1 - STUB_WIDTH_TOLERANCE) * typical_t
        <= short_axis
        <= (1 + STUB_WIDTH_TOLERANCE) * typical_t
    )
    length_short = long_axis <= STUB_MAX_LENGTH_RATIO * typical_t

    if width_match and length_short:
        return {
            "long_axis_pts": long_axis,
            "short_axis_pts": short_axis,
            "area_pts2": piece.area,
        }
    return None


def _piece_protrusions(piece: Polygon, walls: list[dict]) -> list[Polygon]:
    """Find small rectangular protrusions on the boundary of `piece`.

    Strategy: walk the simplified outer ring, look for axis-aligned
    spurs (3 short edges sticking out, returning to the main outline).
    Conservative — only flags clear short rectangular bumps.
    """
    if piece.geom_type != "Polygon":
        return []
    coords = list(piece.exterior.coords)
    if len(coords) < 6:
        return []
    # Drop closing dup
    if coords[0] == coords[-1]:
        coords = coords[:-1]
    n = len(coords)
    typical_t = (
        sum(w["thickness"] for w in walls if "thickness" in w)
        / max(1, len([w for w in walls if "thickness" in w]))
    )

    spurs: list[Polygon] = []
    for i in range(n):
        # Look at 4 consecutive vertices a-b-c-d forming a spur if:
        # a-b perpendicular to b-c, b-c perpendicular to c-d, and
        # the short edges have length ~ thickness
        a = coords[i]
        b = coords[(i + 1) % n]
        c = coords[(i + 2) % n]
        d = coords[(i + 3) % n]
        ab = (b[0] - a[0], b[1] - a[1])
        bc = (c[0] - b[0], c[1] - b[1])
        cd = (d[0] - c[0], d[1] - c[1])
        # ab should be axis-aligned (horizontal or vertical)
        ab_h = abs(ab[1]) < 1e-3
        ab_v = abs(ab[0]) < 1e-3
        bc_h = abs(bc[1]) < 1e-3
        bc_v = abs(bc[0]) < 1e-3
        cd_h = abs(cd[1]) < 1e-3
        cd_v = abs(cd[0]) < 1e-3
        if not ((ab_h and bc_v and cd_h) or (ab_v and bc_h and cd_v)):
            continue
        # ab and cd should reverse direction (spur returns to main line)
        if ab_h:
            ab_len = abs(ab[0])
            cd_len = abs(cd[0])
            bc_len = abs(bc[1])
            ab_sign = ab[0] / max(abs(ab[0]), 1e-9)
            cd_sign = cd[0] / max(abs(cd[0]), 1e-9)
        else:
            ab_len = abs(ab[1])
            cd_len = abs(cd[1])
            bc_len = abs(bc[0])
            ab_sign = ab[1] / max(abs(ab[1]), 1e-9)
            cd_sign = cd[1] / max(abs(cd[1]), 1e-9)
        if ab_sign * cd_sign >= 0:  # spur must reverse
            continue
        # Short edges close to wall thickness
        if not (0.5 * typical_t < bc_len < 2.0 * typical_t):
            continue
        # Spur length cap
        if min(ab_len, cd_len) > STUB_MAX_LENGTH_RATIO * typical_t:
            continue
        # Construct spur bbox
        xs = [a[0], b[0], c[0], d[0]]
        ys = [a[1], b[1], c[1], d[1]]
        spurs.append(box(min(xs), min(ys), max(xs), max(ys)))
    return spurs


def detect_candidates(consensus: dict) -> tuple[
    list[StubCandidate], dict[str, list[Polygon]]
]:
    """Run staged diagnostic + return classified candidates."""
    walls = consensus.get("walls", [])
    openings = consensus.get("openings", [])
    stages = _stage_shells(consensus)
    final_pieces, stats = build_shell_polygon(consensus)

    candidates: list[StubCandidate] = []
    # 1) Pieces that LOOK LIKE a stub as a whole (small rectangular)
    for piece in final_pieces:
        info = _is_stublike(piece, walls)
        if not info:
            continue
        cx, cy = piece.centroid.x, piece.centroid.y
        touches = []
        for w in walls:
            if wall_footprint(w).buffer(0.2).intersects(piece):
                touches.append(w["id"])
        # Compute consensus support — does any wall centerline pass
        # through this piece?
        has_centerline_support = False
        for w in walls:
            cl = LineString([w["start"], w["end"]])
            if cl.intersects(piece):
                has_centerline_support = True
                break
        classification = (
            "valid_wall_return" if has_centerline_support else "residual_cap"
        )
        verdict = "PASS" if has_centerline_support else "WARN"
        # If multiple stub-like pieces and none has centerline support -> FAIL
        candidates.append(
            StubCandidate(
                stub_id=f"piece_{len(candidates):03d}",
                stage_detected="post_canonicalise",
                bbox=[piece.bounds[0], piece.bounds[1],
                      piece.bounds[2], piece.bounds[3]],
                centroid=[cx, cy],
                area_pts2=round(piece.area, 4),
                long_axis_pts=round(info["long_axis_pts"], 4),
                short_axis_pts=round(info["short_axis_pts"], 4),
                touches_wall_ids=touches,
                near_opening_ids=[],
                classification=classification,
                verdict=verdict,
                evidence=(
                    "Piece-level stub shape; "
                    + (
                        "consensus centerline passes through it (valid return)."
                        if has_centerline_support
                        else "no consensus centerline support."
                    )
                ),
            )
        )

    # 2) Protrusions (spurs) on larger pieces
    for piece in final_pieces:
        spurs = _piece_protrusions(piece, walls)
        for spur in spurs:
            cx, cy = spur.centroid.x, spur.centroid.y
            spx0, spy0, spx1, spy1 = spur.bounds
            sp_long = max(spx1 - spx0, spy1 - spy0)
            sp_short = min(spx1 - spx0, spy1 - spy0)
            # Touching walls (raw fp intersection)
            touches = []
            for w in walls:
                if wall_footprint(w).buffer(0.2).intersects(spur):
                    touches.append(w["id"])
            # Check consensus support — does any centerline pass through?
            has_support = False
            for w in walls:
                cl = LineString([w["start"], w["end"]])
                if cl.intersects(spur):
                    has_support = True
                    break
            # Check near-opening
            near_ops = []
            for op in openings:
                if "center" in op and "opening_width_pts" in op:
                    op_pt = (op["center"][0], op["center"][1])
                    if (spur.distance(box(op_pt[0] - 2, op_pt[1] - 2,
                                          op_pt[0] + 2, op_pt[1] + 2)) < 5):
                        near_ops.append(op.get("id", "?"))
            if has_support:
                classification = "valid_wall_return"
                verdict = "PASS"
                ev = "spur supported by consensus centerline"
            elif near_ops:
                classification = "opening_carve_residue"
                verdict = "WARN"
                ev = f"spur adjacent to opening(s) {near_ops}"
            else:
                classification = "residual_cap"
                verdict = "WARN"
                ev = "spur unsupported by consensus centerline"
            candidates.append(
                StubCandidate(
                    stub_id=f"spur_{len(candidates):03d}",
                    stage_detected="post_canonicalise",
                    bbox=[spx0, spy0, spx1, spy1],
                    centroid=[cx, cy],
                    area_pts2=round(spur.area, 4),
                    long_axis_pts=round(sp_long, 4),
                    short_axis_pts=round(sp_short, 4),
                    touches_wall_ids=touches,
                    near_opening_ids=near_ops,
                    classification=classification,
                    verdict=verdict,
                    evidence=ev,
                )
            )

    return candidates, stages


def render_overlay(
    stages: dict[str, list[Polygon]],
    candidates: list[StubCandidate],
    out_path: Path,
    walls: list[dict],
) -> None:
    """Render a 5-panel staged overlay PNG."""
    fig, axes = plt.subplots(1, 5, figsize=(28, 8))
    stage_titles = [
        ("raw_boxes", "1. Raw wall boxes (no extension)"),
        ("junction_boxes", "2. Junction-aware boxes (post-#192)"),
        ("unioned", "3. After unary_union"),
        ("carved", "4. After openings carve"),
    ]
    for ax, (key, title) in zip(axes[:4], stage_titles):
        pieces = stages.get(key, [])
        for piece in pieces:
            if piece.geom_type != "Polygon":
                continue
            ax.add_patch(
                MplPoly(
                    list(piece.exterior.coords),
                    facecolor="lightblue",
                    edgecolor="darkblue",
                    linewidth=0.5,
                    alpha=0.7,
                )
            )
            for hole in piece.interiors:
                ax.add_patch(
                    MplPoly(
                        list(hole.coords),
                        facecolor="white",
                        edgecolor="darkblue",
                        linewidth=0.5,
                    )
                )
        ax.set_aspect("equal")
        ax.set_title(title, fontsize=10)

    # Final panel: candidates highlighted on the carved shell
    ax = axes[4]
    for piece in stages.get("carved", []):
        if piece.geom_type != "Polygon":
            continue
        ax.add_patch(
            MplPoly(
                list(piece.exterior.coords),
                facecolor="lightgray",
                edgecolor="black",
                linewidth=0.5,
                alpha=0.7,
            )
        )
    for w in walls:
        s, e = w["start"], w["end"]
        ax.plot([s[0], e[0]], [s[1], e[1]],
                "b-", linewidth=0.5, alpha=0.6)
    fail_count = sum(1 for c in candidates if c.verdict == "FAIL")
    warn_count = sum(1 for c in candidates if c.verdict == "WARN")
    pass_count = sum(1 for c in candidates if c.verdict == "PASS")
    for cand in candidates:
        x0, y0, x1, y1 = cand.bbox
        color = (
            "red" if cand.verdict == "FAIL"
            else "orange" if cand.verdict == "WARN"
            else "green"
        )
        ax.add_patch(
            MplPoly(
                [(x0, y0), (x1, y0), (x1, y1), (x0, y1)],
                facecolor=color, edgecolor="darkred",
                linewidth=1.2, alpha=0.6,
            )
        )
    ax.set_aspect("equal")
    ax.set_title(
        f"5. Candidates: FAIL={fail_count} WARN={warn_count} PASS={pass_count}",
        fontsize=10,
    )

    # Equalize bounds across panels
    all_pts = []
    for piece in stages.get("carved", []):
        if piece.geom_type == "Polygon":
            all_pts.extend(list(piece.exterior.coords))
    if all_pts:
        xs = [p[0] for p in all_pts]
        ys = [p[1] for p in all_pts]
        pad = 30
        xlim = (min(xs) - pad, max(xs) + pad)
        ylim = (min(ys) - pad, max(ys) + pad)
        for ax in axes:
            ax.set_xlim(*xlim)
            ax.set_ylim(*ylim)

    plt.tight_layout()
    plt.savefig(out_path, dpi=110, bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("consensus", type=Path)
    ap.add_argument("--plant", required=True,
                    help="Plant name (e.g. planta_74)")
    ap.add_argument("--pdf", type=Path, default=None,
                    help="Source PDF path (recorded in the report)")
    ap.add_argument("--out", type=Path,
                    default=Path("artifacts/review"),
                    help="Output base dir (default: artifacts/review)")
    args = ap.parse_args()

    consensus = json.loads(args.consensus.read_text(encoding="utf-8"))
    out_dir = (args.out / args.plant)
    out_dir.mkdir(parents=True, exist_ok=True)

    candidates, stages = detect_candidates(consensus)
    fail = sum(1 for c in candidates if c.verdict == "FAIL")
    warn = sum(1 for c in candidates if c.verdict == "WARN")
    pass_ = sum(1 for c in candidates if c.verdict == "PASS")

    report = {
        "schema_version": SCHEMA,
        "fixture": args.plant,
        "source_consensus": str(args.consensus),
        "source_pdf": str(args.pdf) if args.pdf else None,
        "summary": {
            "total_candidates": len(candidates),
            "fail": fail,
            "warn": warn,
            "pass": pass_,
            "stage_breakdown": {"post_canonicalise": len(candidates)},
        },
        "candidates": [asdict(c) for c in candidates],
        "thresholds": {
            "STUB_MAX_LENGTH_RATIO": STUB_MAX_LENGTH_RATIO,
            "STUB_WIDTH_TOLERANCE": STUB_WIDTH_TOLERANCE,
        },
    }

    json_path = out_dir / "wall_stub_report.json"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    overlay_path = out_dir / "wall_stub_debug_overlay.png"
    render_overlay(stages, candidates, overlay_path,
                   consensus.get("walls", []))

    print(f"[fp026] candidates={len(candidates)} "
          f"FAIL={fail} WARN={warn} PASS={pass_}")
    print(f"[fp026] report -> {json_path}")
    print(f"[fp026] overlay -> {overlay_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
