"""Vector-first consensus builder for architectural-plan PDFs.

Rationale: rasterising a vector PDF and running Hough/morphology fights
contamination that the source vector data already separates cleanly.
For PDFs whose walls are drawn as FILLED paths (the dominant Brazilian
sales-brochure convention), reading the path objects gives wall geometry
with no false positives from floor patterns, fixtures, dimension lines,
text, or door arcs.

Generic policy (no per-PDF tuning):
  * Walls are filled paths with a consistent thin dimension across the
    page (the wall thickness in PDF points). They must have NO stroke
    contribution (filled-only) so we don't mix in outlined fixtures.
  * Among filled paths, the median value of ``min(width, height)`` is
    taken as the wall thickness ``t``. Paths with min-dim within 30%
    of ``t`` AND max-dim greater than ``t`` are walls.
  * The planta region is the union bbox of those wall paths plus a
    small margin. Anything outside is brochure chrome (legends, notes,
    tower diagrams, logos, footer text).

Output: ``consensus_model.json`` with walls in ``pdf_points`` coords,
matching the schema in
``project_pipeline_v6_2_consume_consensus.md`` /
``project_consensus_model_schema.md``.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import math
import statistics
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c


# ----- types --------------------------------------------------------------

@dataclass
class PathInfo:
    bbox: tuple[float, float, float, float]   # left, bottom, right, top (PDF pts)
    fill: tuple[int, int, int, int]
    fillmode: int
    stroke_on: int
    nseg: int


@dataclass
class WallSeg:
    id: str
    start: tuple[float, float]   # PDF points (x, y), y increases upward
    end: tuple[float, float]
    thickness: float             # PDF points (matches wall short-side)
    orientation: str             # 'h' or 'v'


# ----- vector inspection --------------------------------------------------

def _read_paths(page) -> list[tuple[PathInfo, object]]:
    out: list[tuple[PathInfo, object]] = []
    for obj in page.get_objects():
        if obj.type != 2:  # path
            continue
        l, b, r, t = obj.get_pos()
        raw = obj.raw

        fillmode = ctypes.c_int(0)
        stroke = ctypes.c_int(0)
        pdfium_c.FPDFPath_GetDrawMode(raw, ctypes.byref(fillmode), ctypes.byref(stroke))

        fr, fg, fb, fa = (ctypes.c_uint() for _ in range(4))
        pdfium_c.FPDFPageObj_GetFillColor(raw, ctypes.byref(fr), ctypes.byref(fg),
                                          ctypes.byref(fb), ctypes.byref(fa))

        nseg = pdfium_c.FPDFPath_CountSegments(raw)
        out.append((PathInfo(
            bbox=(l, b, r, t),
            fill=(fr.value, fg.value, fb.value, fa.value),
            fillmode=fillmode.value,
            stroke_on=stroke.value,
            nseg=nseg,
        ), obj))
    return out


# ----- wall identification ------------------------------------------------

def _identify_wall_paths(paths: list[tuple[PathInfo, object]]) -> list[PathInfo]:
    """Generic detection: filled-only paths whose min-dim clusters tightly.

    Walls in floor plans share a single drawn thickness across the page.
    We compute the modal min-dim among candidate filled paths, then keep
    the cluster around it.
    """
    candidates = [pi for pi, _ in paths
                  if pi.fillmode != 0 and pi.stroke_on == 0]
    if not candidates:
        return []

    # min-dim per candidate
    short = [min(p.bbox[2] - p.bbox[0], p.bbox[3] - p.bbox[1]) for p in candidates]
    long_ = [max(p.bbox[2] - p.bbox[0], p.bbox[3] - p.bbox[1]) for p in candidates]

    # Find the dominant fill color among slim+long filled paths.
    # Walls are drawn with a single fill across the plan; non-wall filled
    # decoration (e.g. light-gray panel inserts) is rarer and a different
    # shade.
    by_color: dict[tuple[int, int, int, int], list[PathInfo]] = {}
    for p, s, lg in zip(candidates, short, long_):
        if lg < 5.0:
            continue  # too small to be a wall
        by_color.setdefault(p.fill, []).append(p)

    if not by_color:
        return []

    # Pick color with most members and reasonable thickness clustering.
    def score(items: list[PathInfo]) -> float:
        if len(items) < 4:
            return 0.0
        ts = [min(i.bbox[2] - i.bbox[0], i.bbox[3] - i.bbox[1]) for i in items]
        med = statistics.median(ts)
        if med <= 0:
            return 0.0
        # tight cluster bonus: fraction within 30% of median
        tight = sum(1 for t in ts if abs(t - med) / med <= 0.30) / len(ts)
        # Prefer dark fills (real walls are dark gray/black) over very
        # light grays which are often hatching panels.
        r, g, b, _ = items[0].fill
        darkness = 1.0 - (r + g + b) / (3 * 255.0)
        return len(items) * tight * (0.5 + 0.5 * darkness)

    best_color = max(by_color, key=lambda c: score(by_color[c]))
    pool = by_color[best_color]

    # Within selected color, restrict to tight thickness cluster.
    ts = [min(p.bbox[2] - p.bbox[0], p.bbox[3] - p.bbox[1]) for p in pool]
    med = statistics.median(ts)
    walls = [p for p in pool
             if abs(min(p.bbox[2] - p.bbox[0], p.bbox[3] - p.bbox[1]) - med) / med <= 0.30
             and max(p.bbox[2] - p.bbox[0], p.bbox[3] - p.bbox[1]) > med]
    return walls


def _bbox_to_segment(p: PathInfo) -> WallSeg | None:
    l, b, r, t = p.bbox
    w = r - l
    h = t - b
    if w <= 0 or h <= 0:
        return None
    if w >= h:
        # horizontal wall: centerline along y=mid
        cy = (b + t) / 2.0
        return WallSeg(id="", start=(l, cy), end=(r, cy), thickness=h, orientation='h')
    else:
        cx = (l + r) / 2.0
        return WallSeg(id="", start=(cx, b), end=(cx, t), thickness=w, orientation='v')


# ----- planta region ------------------------------------------------------

def _planta_bbox(walls: list[WallSeg], margin: float = 10.0) -> tuple[float, float, float, float]:
    xs = [w.start[0] for w in walls] + [w.end[0] for w in walls]
    ys = [w.start[1] for w in walls] + [w.end[1] for w in walls]
    return (min(xs) - margin, min(ys) - margin, max(xs) + margin, max(ys) + margin)


# ----- main ---------------------------------------------------------------

def _bbox_overlaps_any_wall(bbox: tuple[float, float, float, float],
                             walls: list["WallSeg"], t: float) -> bool:
    """Returns True if the path bbox overlaps any wall rectangle by
    more than 50% of its area. Walls are wider than they are tall (or
    vice versa) — a stroked outline of a wall has the same bbox as the
    wall itself, so we use overlap-fraction not bbox-equality."""
    bl, bb, br, bt = bbox
    barea = max(0.0, (br - bl) * (bt - bb))
    if barea <= 0:
        return False
    for w in walls:
        s, e = w.start, w.end
        if w.orientation == "h":
            x0, x1 = sorted([s[0], e[0]])
            cy = s[1]
            wl, wb, wr, wt = x0, cy - t / 2, x1, cy + t / 2
        else:
            cx = s[0]
            y0, y1 = sorted([s[1], e[1]])
            wl, wb, wr, wt = cx - t / 2, y0, cx + t / 2, y1
        ix0 = max(bl, wl); iy0 = max(bb, wb)
        ix1 = min(br, wr); iy1 = min(bt, wt)
        if ix1 > ix0 and iy1 > iy0:
            inter = (ix1 - ix0) * (iy1 - iy0)
            if inter / barea > 0.50:
                return True
    return False


def _extract_building_outline(page, region: tuple[float, float, float, float],
                               walls: list["WallSeg"], thickness: float,
                               top_n: int = 8) -> list[list[tuple[float, float]]]:
    """Pull peitoril/parapet outline polylines (NON-STRUCTURAL).

    The architect renders the building's exterior boundary as
    STROKED-only paths. We collect top-N stroked paths by bbox area
    and KEEP only those that don't overlap the structural walls — a
    wall-edge stroked path traces the wall and would pollute room
    detection, while the peitoril/grade outline runs along the
    exterior where there are no walls.
    """
    cands = []
    for obj in page.get_objects():
        if obj.type != 2:
            continue
        l, b, r, t = obj.get_pos()
        cx, cy = (l + r) / 2.0, (b + t) / 2.0
        if not (region[0] <= cx <= region[2] and region[1] <= cy <= region[3]):
            continue
        raw = obj.raw
        fm = ctypes.c_int(0)
        st = ctypes.c_int(0)
        pdfium_c.FPDFPath_GetDrawMode(raw, ctypes.byref(fm), ctypes.byref(st))
        if fm.value != 0 or not st.value:
            continue
        nseg = pdfium_c.FPDFPath_CountSegments(raw)
        bbox = (l, b, r, t)
        bbox_area = (r - l) * (t - b)
        if bbox_area < 1500:  # skip small fixtures, dimension lines
            continue
        if _bbox_overlaps_any_wall(bbox, walls, thickness):
            continue
        cands.append({
            "obj": obj, "raw": raw, "bbox": bbox, "bbox_area": bbox_area, "nseg": nseg,
        })
    cands.sort(key=lambda c: -c["bbox_area"])

    polylines: list[list[tuple[float, float]]] = []
    for cand in cands[:top_n]:
        m = cand["obj"].get_matrix()
        ma, mb, mc, md, me, mf = m.get()
        pts: list[tuple[float, float]] = []
        for i in range(cand["nseg"]):
            seg = pdfium_c.FPDFPath_GetPathSegment(cand["raw"], i)
            x = ctypes.c_float(0)
            y = ctypes.c_float(0)
            pdfium_c.FPDFPathSegment_GetPoint(seg, ctypes.byref(x), ctypes.byref(y))
            px = ma * x.value + mc * y.value + me
            py = mb * x.value + md * y.value + mf
            pts.append((px, py))
        polylines.append(pts)
    return polylines


def build(pdf_path: Path, out_path: Path) -> dict:
    pdf = pdfium.PdfDocument(str(pdf_path))
    page = pdf[0]
    page_w, page_h = page.get_size()
    paths = _read_paths(page)
    wall_paths = _identify_wall_paths(paths)

    walls: list[WallSeg] = []
    for i, p in enumerate(wall_paths):
        seg = _bbox_to_segment(p)
        if seg is None:
            continue
        seg.id = f"w{i:03d}"
        walls.append(seg)

    if not walls:
        print("[err] no wall paths detected", file=sys.stderr)
        return {}

    region = _planta_bbox(walls)
    wall_thickness = statistics.median([w.thickness for w in walls])
    soft_barriers = _extract_building_outline(page, region, walls,
                                              wall_thickness, top_n=8)

    consensus = {
        "schema_version": "1.0.0",
        "source": str(pdf_path.name),
        "coordinate_system": "pdf_points",
        "page_size_pts": [page_w, page_h],
        "planta_region": list(region),
        "wall_thickness_pts": statistics.median([w.thickness for w in walls]),
        "walls": [
            {
                "id": w.id,
                "start": list(w.start),
                "end": list(w.end),
                "thickness": w.thickness,
                "orientation": w.orientation,
            }
            for w in walls
        ],
        "openings": [],   # filled in by a downstream gap-detection pass
        "rooms": [],      # filled in by polygonize pass
        "soft_barriers": [
            {"id": f"sb{i:03d}", "polyline_pts": [list(p) for p in pts]}
            for i, pts in enumerate(soft_barriers)
        ],
        "metadata": {
            "extractor": "vector",
            "wall_count": len(walls),
            "soft_barrier_count": len(soft_barriers),
        },
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(consensus, indent=2))
    print(f"[ok] {len(walls)} walls -> {out_path}")
    return consensus


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--out", type=Path, default=Path("runs/vector/consensus_model.json"))
    args = ap.parse_args()
    build(args.pdf, args.out)
