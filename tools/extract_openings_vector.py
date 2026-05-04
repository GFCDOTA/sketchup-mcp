"""Vector-first opening detector — doors AND windows.

The vector consensus builder (``build_vector_consensus.py``) extracts
walls from filled paths but emits ``openings: []`` because it
deliberately filters out stroked-only fixtures. Brazilian
sales-brochure PDFs draw openings with two distinct vector idioms:

- **Door arc** — stroked path with at least one cubic Bezier segment,
  bbox roughly square (15-100 PDF pts each side, aspect 0.4..2.5),
  drawn perpendicular to the host wall.
- **Window** — stroked path with zero cubic segments, very elongated
  bbox (one dim ~ wall thickness, the other 25-250 PDF pts), centered
  along a wall.

Both are stroked-only paths in the same pdfium bucket the wall
extractor ignores. This module re-scans that bucket and emits
``openings`` of kind ``"door"`` or ``"window"`` accordingly.

Algorithm
---------
1. Door arcs (``_arc_candidates`` → ``_dedupe_arcs``): aspect-
   constrained stroked paths with cubic Bezier segments. Match each
   to the nearest wall whose perpendicular distance from any arc-
   bbox CORNER is within ``thickness * 1.5``. Hinge corner = the
   bbox vertex sitting on the wall.

2. Windows (``_window_candidates``): stroked paths with **zero**
   cubic segments, bbox elongated (aspect ≥ 3, short side ≤
   thickness*1.5), inside the planta region. Each window must lie
   within ``thickness * 0.6`` of a wall centerline; if so the
   window is projected onto that wall and emitted. Windows are
   deduped against the door arcs already detected (≥ 50 % bbox
   overlap with an arc → drop the window — the arc wins because
   its detection is stricter).

Both stages emit honest data per memory
``feedback_nao_fabricar_sem_medidas``: only paths that the PDF
actually drew become openings.

This module does NOT carve walls or determine room_a/room_b — that
remains a downstream concern for ``tools/consume_consensus.rb``.
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

# Window detector: stroked paths drawn AS the glazing line in the
# wall band, oriented along the wall, no curves.
WINDOW_LONG_MIN = 25.0          # ~30 cm at 1:50 (smallest sensible window width)
WINDOW_LONG_MAX = 250.0         # ~3 m (e.g. a sliding glass door front)
WINDOW_DEPTH_FACTOR = 1.5       # short side <= thickness * this
WINDOW_ASPECT_MIN = 3.0         # must be much more elongated than door arcs
WINDOW_WALL_DIST_FACTOR = 0.6   # bbox center within thickness * this of a wall centerline
WINDOW_DEDUPE_OVERLAP = 0.5     # drop window if it shares >= this fraction of bbox with an arc
WINDOW_WALL_LEN_RATIO_MAX = 0.7 # drop window if its long side >= this fraction of the wall — likely a wall outline stroke


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


@dataclass
class WindowCandidate:
    """Stroked, no-curve, very elongated path that sits along a wall.

    The bbox short side is roughly the wall thickness; the long side
    spans the window opening (typical 30-200 cm).
    """
    bbox: tuple[float, float, float, float]
    n_seg: int

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

    @property
    def long_side(self) -> float:
        return max(self.w, self.h)

    @property
    def short_side(self) -> float:
        return min(self.w, self.h)


def _is_window_shape(bbox: tuple[float, float, float, float],
                     n_cubic: int, thickness: float) -> bool:
    """Pure geometry classifier — stroke type + region filters are
    the caller's job.

    True iff the bbox shape matches the window heuristic: elongated
    (aspect >= WINDOW_ASPECT_MIN), short side close to wall thickness,
    long side in the 25-250 pt range. The aspect filter alone
    excludes door arcs (which are square-ish, aspect 0.4..2.5) so
    presence of cubic Bezier segments is NOT a disqualifier — many
    PDF generators emit cubic primitives even for straight lines.
    The `n_cubic` parameter is accepted for forward compatibility
    with extractors that want to report it; this function ignores it.
    """
    del n_cubic  # accepted for symmetry with the door classifier; unused
    l, b, r, t = bbox
    w, h = r - l, t - b
    long_side = max(w, h)
    short_side = min(w, h)
    if long_side < WINDOW_LONG_MIN or long_side > WINDOW_LONG_MAX:
        return False
    if short_side <= 0 or short_side > thickness * WINDOW_DEPTH_FACTOR:
        return False
    if long_side / short_side < WINDOW_ASPECT_MIN:
        return False
    return True


def _window_candidates(page,
                       region: tuple[float, float, float, float],
                       thickness: float) -> list[WindowCandidate]:
    """Scan stroked paths inside the region; keep ones whose bbox
    matches the window-shape heuristic."""
    rx0, ry0, rx1, ry1 = region
    out: list[WindowCandidate] = []
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
        if not st.value:
            continue   # require stroked

        nseg = pdfium_c.FPDFPath_CountSegments(raw)
        n_cubic = 0
        for i in range(nseg):
            seg = pdfium_c.FPDFPath_GetPathSegment(raw, i)
            if pdfium_c.FPDFPathSegment_GetType(seg) == 2:  # FPDF_SEGMENT_BEZIERTO
                n_cubic += 1

        if not _is_window_shape((l, b, r, t), n_cubic, thickness):
            continue
        out.append(WindowCandidate(bbox=(l, b, r, t), n_seg=nseg))
    return out


def _wall_length(wall: dict) -> float:
    sx, sy = wall["start"]
    ex, ey = wall["end"]
    return math.hypot(ex - sx, ey - sy)


def _window_to_wall(window: WindowCandidate, walls: list[dict],
                    thickness: float) -> tuple[dict | None, tuple[float, float], float]:
    """Find the wall whose centerline runs closest to the window's
    bbox center. Returns ``(wall, projection, distance)`` or
    ``(None, ...)`` if:
      - no wall is within ``thickness * WINDOW_WALL_DIST_FACTOR``, OR
      - the window long side is at least ``WINDOW_WALL_LEN_RATIO_MAX``
        of the matched wall length (suggests it's the wall's stroked
        outline, not a window opening drawn inside the wall band).
    """
    best: tuple[dict | None, tuple[float, float], float] = (None, (0, 0), float("inf"))
    for w in walls:
        ax, ay = w["start"]
        bx, by = w["end"]
        proj, dist = _project_on_segment(window.cx, window.cy, ax, ay, bx, by)
        if dist < best[2]:
            best = (w, proj, dist)
    wall, proj, dist = best
    if wall is None or dist > thickness * WINDOW_WALL_DIST_FACTOR:
        return None, (0, 0), dist
    wall_len = _wall_length(wall)
    if wall_len > 0 and window.long_side / wall_len >= WINDOW_WALL_LEN_RATIO_MAX:
        # Probably the wall's own stroked outline, not a window.
        return None, (0, 0), dist
    return wall, proj, dist


def _window_overlaps_arc(window: WindowCandidate,
                         arc_bboxes: list[tuple[float, float, float, float]],
                         threshold: float = WINDOW_DEDUPE_OVERLAP) -> bool:
    """True iff `window.bbox` shares ≥ `threshold` of the smaller
    bbox area with any arc bbox. Used to drop windows already
    covered by a door arc detection."""
    cand_area = window.w * window.h
    if cand_area <= 0:
        return False
    for ab in arc_bboxes:
        ab_area = (ab[2] - ab[0]) * (ab[3] - ab[1])
        if ab_area <= 0:
            continue
        inter = _bbox_overlap_area(window.bbox, ab)
        small = min(cand_area, ab_area)
        if small > 0 and inter / small >= threshold:
            return True
    return False


def _window_confidence(window: WindowCandidate, dist_to_wall: float,
                       thickness: float) -> float:
    """Confidence for a window detection. Highest when the bbox is
    very elongated, perfectly aligned with the wall centerline, and
    short-side close to (but not exceeding) the wall thickness."""
    aspect = window.long_side / max(window.short_side, 0.001)
    elongation = min(1.0, (aspect - WINDOW_ASPECT_MIN) /
                     max(WINDOW_ASPECT_MIN, 1.0) + 0.5)
    wall_ok = max(0.0, 1.0 - (dist_to_wall /
                              max(thickness * WINDOW_WALL_DIST_FACTOR, 1e-3)))
    depth_ratio = window.short_side / max(thickness, 0.001)
    depth_ok = 1.0 - min(1.0, abs(1.0 - depth_ratio))
    return round(0.4 * elongation + 0.4 * wall_ok + 0.2 * depth_ok, 3)


def _emit_window_opening(window: WindowCandidate, wall: dict,
                         proj: tuple[float, float], dist: float,
                         thickness: float, idx: int) -> dict[str, Any]:
    """Build a single window opening dict. No hinge/swing — windows
    don't have those."""
    return {
        "id":               f"o{idx:03d}",
        "center":           [round(proj[0], 3), round(proj[1], 3)],
        "kind":             "window",
        "geometry_origin":  "svg_segments",
        "confidence":       _window_confidence(window, dist, thickness),
        "wall_id":          wall.get("id"),
        "opening_width_pts": round(window.long_side, 3),
        "window_bbox_pts":  [round(c, 3) for c in window.bbox],
        "window_n_seg":     window.n_seg,
        "wall_dist_pts":    round(dist, 3),
    }


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
    into the consensus.openings array). Doors come first (by
    historical convention), then windows."""
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

    # Windows: very elongated stroked paths along walls. Doors are
    # detected first; windows that overlap an existing arc bbox are
    # dropped to avoid double-counting (the arc detection is stricter
    # and wins by construction).
    #
    # The door loop above uses the ARC INDEX as the id ("o<i>"), which
    # leaves gaps when an arc fails wall-matching. Window ids must
    # start strictly after `len(arcs)` so they never collide with a
    # gap-filling arc id.
    arc_bboxes = [a.bbox for a in arcs]
    windows = _window_candidates(page, region, thickness)
    next_id = len(arcs)
    for cand in windows:
        if _window_overlaps_arc(cand, arc_bboxes):
            continue
        wall, proj, dist = _window_to_wall(cand, walls, thickness)
        if wall is None:
            continue
        openings.append(_emit_window_opening(
            cand, wall, proj, dist, thickness, idx=next_id,
        ))
        next_id += 1

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

    consensus.setdefault("metadata", {})["openings_extractor"] = "vector_arc_window_v1"
    consensus["metadata"]["svg_arc_opening_count"] = sum(
        1 for o in new_openings if o.get("geometry_origin") == "svg_arc"
    )
    consensus["metadata"]["svg_window_opening_count"] = sum(
        1 for o in new_openings if o.get("geometry_origin") == "svg_segments"
    )
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
    window_openings = [o for o in consensus["openings"]
                       if o.get("geometry_origin") == "svg_segments"]
    print(f"[ok] {len(arc_openings)} doors + {len(window_openings)} "
          f"windows detected from {args.pdf.name}")
    for o in arc_openings:
        wall_id = o.get("wall_id") or "?"
        center = o.get("center") or [0, 0]
        width = o.get("opening_width_pts") or 0
        conf = o.get("confidence") or 0
        hinge = o.get("hinge_side") or "?"
        print(f"  {o['id']} door   wall={wall_id:<4} "
              f"center=({center[0]:.1f},{center[1]:.1f}) "
              f"width={width:.1f}pt conf={conf:.2f}  hinge={hinge}")
    for o in window_openings:
        wall_id = o.get("wall_id") or "?"
        center = o.get("center") or [0, 0]
        width = o.get("opening_width_pts") or 0
        conf = o.get("confidence") or 0
        print(f"  {o['id']} window wall={wall_id:<4} "
              f"center=({center[0]:.1f},{center[1]:.1f}) "
              f"width={width:.1f}pt conf={conf:.2f}")

    if not args.dry_run:
        out = args.out or args.consensus
        out.write_text(json.dumps(consensus, indent=2), encoding="utf-8")
        print(f"[wrote] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
