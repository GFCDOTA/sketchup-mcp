"""Vector-first opening detector.

The vector consensus builder (``build_vector_consensus.py``) extracts
walls from filled paths but emits ``openings: []`` because it
deliberately filters out stroked-only fixtures. Door arcs in Brazilian
sales-brochure PDFs are stroked-only paths with cubic Bezier segments
— the same bucket the wall extractor ignores. This module re-scans
that bucket for door-arc shapes and emits openings.

Algorithm (v0)
--------------
1. Iterate every page object; keep stroked-only paths inside the planta
   region whose bbox is roughly square (15-100 PDF pts on each side,
   aspect 0.4..2.5) and which contain at least one cubic Bezier segment.
   Door arcs in Brazilian residential plantas (~70-90 cm doors) project
   to ~30-60 PDF pts at typical 1:50/1:100 scales.
2. For each arc candidate, find the nearest wall whose perpendicular
   distance from the arc's bbox center is within ``wall_thickness * 1.5``.
3. Project the arc center onto that wall and emit an opening:
       center      = projection on the wall's centerline
       chord_pt    = arc's bbox-side touching the wall (door's hinge edge)
       kind        = "door" if cubic_count >= 1 else "passage"
       geometry_origin = "svg_arc"
       confidence  = derived from bbox aspect, segment count, wall match
       hinge_side  = "near" if arc is on the host wall side closest to
                     the room interior, else "far" (best-effort)
       swing_deg   = 90 (default; arc geometry could be analyzed later)

This v0 does NOT carve walls or determine room_a/room_b. Those are
downstream concerns for ``consume_consensus.rb``. We only fill the
``openings`` array honestly per memory ``feedback_nao_fabricar_sem_medidas``:
emit ONLY where the PDF actually drew an arc.

Invariant: if ``--no-arc-fallback`` is passed and zero arcs are found,
the openings list stays empty. We never invent doors from gap heuristics
in this module.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import math
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c


# ----- candidate detection -----------------------------------------------

ARC_BBOX_MIN = 15      # PDF pts (~15-30 cm doors should be filtered out)
ARC_BBOX_MAX = 100     # PDF pts (~3 m max door + arc envelope)
ARC_ASPECT_MIN = 0.4
ARC_ASPECT_MAX = 2.5

WALL_MATCH_FACTOR = 1.5  # arc center must be within thickness * this


@dataclass
class ArcCandidate:
    bbox: tuple[float, float, float, float]   # l, b, r, t in PDF pts
    n_seg: int
    n_cubic: int

    @property
    def w(self) -> float:
        return self.bbox[2] - self.bbox[0]

    @property
    def h(self) -> float:
        return self.bbox[3] - self.bbox[1]

    @property
    def cx(self) -> float:
        return (self.bbox[0] + self.bbox[2]) / 2

    @property
    def cy(self) -> float:
        return (self.bbox[1] + self.bbox[3]) / 2


def _arc_candidates(page, region: tuple[float, float, float, float]) -> list[ArcCandidate]:
    rx0, ry0, rx1, ry1 = region
    out: list[ArcCandidate] = []
    for obj in page.get_objects():
        if obj.type != 2:
            continue
        l, b, r, t = obj.get_pos()
        cx, cy = (l + r) / 2, (b + t) / 2
        if not (rx0 <= cx <= rx1 and ry0 <= cy <= ry1):
            continue

        raw = obj.raw
        fm = ctypes.c_int(0)
        st = ctypes.c_int(0)
        pdfium_c.FPDFPath_GetDrawMode(raw, ctypes.byref(fm), ctypes.byref(st))
        if fm.value != 0 or not st.value:
            continue   # skip filled or no-stroke paths

        w, h = r - l, t - b
        if not (ARC_BBOX_MIN <= w <= ARC_BBOX_MAX and ARC_BBOX_MIN <= h <= ARC_BBOX_MAX):
            continue
        ratio = w / max(h, 0.001)
        if not (ARC_ASPECT_MIN <= ratio <= ARC_ASPECT_MAX):
            continue

        nseg = pdfium_c.FPDFPath_CountSegments(raw)
        n_cubic = 0
        for i in range(nseg):
            seg = pdfium_c.FPDFPath_GetPathSegment(raw, i)
            if pdfium_c.FPDFPathSegment_GetType(seg) == 2:  # FPDF_SEGMENT_BEZIERTO
                n_cubic += 1

        if n_cubic == 0:
            continue   # arcs require at least one cubic Bezier

        out.append(ArcCandidate(bbox=(l, b, r, t), n_seg=nseg, n_cubic=n_cubic))

    return out


# ----- wall projection ----------------------------------------------------

def _project_on_segment(px: float, py: float,
                        ax: float, ay: float,
                        bx: float, by: float) -> tuple[tuple[float, float], float]:
    """Return (closest_point_on_segment, distance)."""
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 < 1e-9:
        return (ax, ay), math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / L2
    t = max(0.0, min(1.0, t))
    qx, qy = ax + t * dx, ay + t * dy
    return (qx, qy), math.hypot(px - qx, py - qy)


def _nearest_wall(arc: ArcCandidate, walls: list[dict],
                  thickness: float) -> tuple[dict | None, tuple[float, float], float, tuple[float, float]]:
    """Find the wall closest to ANY corner of the arc bbox.

    A door arc's bbox covers the swing envelope; the hinge sits at one
    of the four bbox corners and that corner is what touches the wall.
    Matching corners-to-wall is therefore far more robust than matching
    the bbox center.

    Returns ``(wall, projection_on_wall, distance, hinge_corner)``.
    """
    l, b, r, t = arc.bbox
    corners = [(l, b), (l, t), (r, b), (r, t)]

    best: tuple[dict | None, tuple[float, float], float, tuple[float, float]] = \
        (None, (0, 0), float("inf"), (0, 0))
    for w in walls:
        ax, ay = w["start"]
        bx, by = w["end"]
        for cx, cy in corners:
            proj, dist = _project_on_segment(cx, cy, ax, ay, bx, by)
            if dist < best[2]:
                best = (w, proj, dist, (cx, cy))
    if best[0] is None or best[2] > thickness * WALL_MATCH_FACTOR:
        return None, (0, 0), best[2], (0, 0)
    return best


# ----- opening synthesis --------------------------------------------------

def _confidence(arc: ArcCandidate, dist_to_wall: float, thickness: float) -> float:
    # geometric prior + wall closeness
    aspect = arc.w / max(arc.h, 0.001)
    geom = 1.0 - min(1.0, abs(1.0 - aspect))           # closer to square = higher
    seg_ok = 1.0 if arc.n_cubic >= 1 else 0.4
    wall_ok = max(0.0, 1.0 - (dist_to_wall / max(thickness * WALL_MATCH_FACTOR, 1e-3)))
    return round(0.4 * geom + 0.3 * seg_ok + 0.3 * wall_ok, 3)


def _hinge_side(arc: ArcCandidate, wall: dict, proj: tuple[float, float]) -> str:
    """Best-effort: is the arc center on the +normal or -normal side of
    the host wall? Returns ``"left"`` or ``"right"`` (relative to wall
    direction start->end). Downstream consumers can map to room sides."""
    ax, ay = wall["start"]
    bx, by = wall["end"]
    dx, dy = bx - ax, by - ay
    # left-normal = (-dy, dx)
    nx, ny = -dy, dx
    L = math.hypot(nx, ny)
    if L < 1e-9:
        return "unknown"
    nx, ny = nx / L, ny / L
    cx_rel, cy_rel = arc.cx - proj[0], arc.cy - proj[1]
    return "left" if (nx * cx_rel + ny * cy_rel) >= 0 else "right"


def _bbox_overlap_area(a, b) -> float:
    al, ab, ar, at = a
    bl, bb, br, bt = b
    iw = max(0.0, min(ar, br) - max(al, bl))
    ih = max(0.0, min(at, bt) - max(ab, bb))
    return iw * ih


def _dedupe_arcs(arcs: list[ArcCandidate]) -> list[ArcCandidate]:
    """A real door is often drawn as TWO paths: the leaf rectangle and
    the swing arc. They occupy nearly the same bbox. Cluster candidates
    by significant bbox overlap and keep the one with the most cubic
    Bezier segments (the actual arc, not the leaf rectangle).
    """
    arcs = sorted(arcs, key=lambda a: -(a.w * a.h))   # largest first
    kept: list[ArcCandidate] = []
    for arc in arcs:
        merged = False
        for k in kept:
            inter = _bbox_overlap_area(arc.bbox, k.bbox)
            small = min(arc.w * arc.h, k.w * k.h)
            if small > 0 and inter / small > 0.5:
                # Keep the candidate richer in cubic segments (= the swing arc)
                if (arc.n_cubic, arc.w * arc.h) > (k.n_cubic, k.w * k.h):
                    kept.remove(k)
                    kept.append(arc)
                merged = True
                break
        if not merged:
            kept.append(arc)
    return kept


def detect_openings(pdf_path: Path,
                    walls: list[dict],
                    region: tuple[float, float, float, float],
                    thickness: float) -> list[dict[str, Any]]:
    """Return a list of openings (dicts ready to be JSON-serialized
    into the consensus.openings array)."""
    pdf = pdfium.PdfDocument(str(pdf_path))
    page = pdf[0]
    arcs = _dedupe_arcs(_arc_candidates(page, region))

    openings: list[dict[str, Any]] = []
    for i, arc in enumerate(arcs):
        wall, proj, dist, hinge = _nearest_wall(arc, walls, thickness)
        if wall is None:
            continue   # arc not associated to any wall — drop, don't fabricate
        # door width = arc envelope long side; the hinge corner is at
        # the wall, so the door swings out to the opposite corner.
        opening_w = max(arc.w, arc.h)
        side = _hinge_side(arc, wall, proj)
        confidence = _confidence(arc, dist, thickness)
        openings.append({
            "id":               f"o{i:03d}",
            "center":           [round(proj[0], 3), round(proj[1], 3)],
            "chord_pt":         [round(arc.cx, 3), round(arc.cy, 3)],
            "kind":             "door",
            "geometry_origin":  "svg_arc",
            "confidence":       confidence,
            "hinge_side":       side,
            "hinge_corner_pt":  [round(hinge[0], 3), round(hinge[1], 3)],
            "swing_deg":        90,
            "wall_id":          wall.get("id"),
            "opening_width_pts": round(opening_w, 3),
            "arc_bbox_pts":     [round(c, 3) for c in arc.bbox],
            "arc_n_seg":        arc.n_seg,
            "arc_n_cubic":      arc.n_cubic,
            "wall_dist_pts":    round(dist, 3),
        })

    return openings


# ----- enrichment helper for build_vector_consensus.py --------------------

def enrich_consensus(consensus: dict, pdf_path: Path,
                     *, mode: str = "merge") -> dict:
    """Add svg_arc openings to an existing consensus in-place.

    ``mode``:
      ``"replace"`` — drop everything in consensus.openings, write only
                      svg_arc openings.
      ``"merge"``   — keep existing openings (e.g. pipeline_gap bridges
                      from polygonize_rooms) and ADD svg_arc openings,
                      tagging each with a unique id.
    """
    walls = consensus.get("walls", [])
    region = tuple(consensus.get("planta_region") or (0, 0, 0, 0))
    thickness = float(consensus.get("wall_thickness_pts") or 5.0)
    if not walls or len(region) != 4:
        return consensus
    new_openings = detect_openings(pdf_path, walls, region, thickness)

    if mode == "replace" or not consensus.get("openings"):
        consensus["openings"] = new_openings
    else:
        existing = list(consensus.get("openings", []))
        offset = len(existing)
        for i, op in enumerate(new_openings):
            op["id"] = f"o{offset + i:03d}"
            existing.append(op)
        consensus["openings"] = existing

    consensus.setdefault("metadata", {})["openings_extractor"] = "vector_arc_v0"
    consensus["metadata"]["svg_arc_opening_count"] = len(new_openings)
    return consensus


# ----- CLI ----------------------------------------------------------------

def _cli() -> int:
    ap = argparse.ArgumentParser(description="Detect door openings from PDF arc paths")
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--consensus", type=Path,
                    default=Path("runs/vector/consensus_model.json"),
                    help="existing consensus to enrich")
    ap.add_argument("--out", type=Path, default=None,
                    help="write enriched JSON here (default: overwrite --consensus)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print openings to stdout, don't write")
    ap.add_argument("--mode", choices=["merge", "replace"], default="merge",
                    help="merge with existing consensus.openings (default) or replace")
    args = ap.parse_args()

    consensus = json.loads(args.consensus.read_text(encoding="utf-8"))
    enrich_consensus(consensus, args.pdf, mode=args.mode)
    arc_openings = [o for o in consensus["openings"]
                    if o.get("geometry_origin") == "svg_arc"]
    print(f"[ok] {len(arc_openings)} openings detected from {args.pdf.name}")
    for o in arc_openings:
        wall_id = o.get("wall_id") or "?"
        center = o.get("center") or [0, 0]
        width = o.get("opening_width_pts") or 0
        conf = o.get("confidence") or 0
        hinge = o.get("hinge_side") or "?"
        print(f"  {o['id']}  wall={wall_id:<4} "
              f"center=({center[0]:.1f},{center[1]:.1f}) "
              f"width={width:.1f}pt conf={conf:.2f}  hinge={hinge}")

    if not args.dry_run:
        out = args.out or args.consensus
        out.write_text(json.dumps(consensus, indent=2), encoding="utf-8")
        print(f"[wrote] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
