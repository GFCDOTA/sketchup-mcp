#!/usr/bin/env python3
"""Top-down PDF<->consensus overlay + deterministic fidelity verifier (gap #1).

Draws consensus geometry (walls, rooms, openings) on the high-res PDF raster
(everything in pdf-points, trivially mappable), and measures the PDF's own door
SWING ARCS (vector bezier paths) to compare against each opening's width. This
turns the `NEEDS_PDF_OVERLAY` verdicts into CONFIRMED/FALSE without needing the
SKP-render<->PDF camera calibration: the SKP is built from the consensus, so if
the consensus lands on the PDF, the geometry is faithful.

PDF is ground truth. No fabrication: door width comes from the PDF arc bbox.
"""
from __future__ import annotations
import json, math
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PDF_SCALE = 3.0


def _consensus(fix="planta_74"):
    return json.loads((REPO/"fixtures"/fix/"consensus_with_human_walls_and_soft_barriers.json").read_text("utf-8"))


def door_arcs_from_pdf(pdf_path: Path):
    """Return list of (cx, cy, radius_pts) for door-swing arcs (bezier paths)."""
    import pypdfium2 as pdfium
    import pypdfium2.raw as C
    pdf = pdfium.PdfDocument(str(pdf_path)); page = pdf[0]
    arcs = []
    for o in page.get_objects():
        if o.type != C.FPDF_PAGEOBJ_PATH:
            continue
        # does it contain a bezier segment (=> curve/arc, not a straight wall)?
        try:
            n = C.FPDFPath_CountSegments(o.raw)
        except Exception:
            continue
        has_bezier = False
        for i in range(n):
            seg = C.FPDFPath_GetPathSegment(o.raw, i)
            if seg and C.FPDFPathSegment_GetType(seg) == C.FPDF_SEGMENT_BEZIERTO:
                has_bezier = True; break
        if not has_bezier:
            continue
        try:
            l, b, r, t = o.get_pos()
        except Exception:
            continue
        w, h = r-l, t-b
        rad = max(w, h)
        # door-arc scale (quarter circle bbox ~ radius x radius), reject tiny/huge
        if 12 < rad < 70 and 0.4 < (min(w, h)/max(w, h) if max(w, h) else 0) <= 1.0:
            arcs.append(((l+r)/2, (b+t)/2, rad))
    return arcs


def verify(fix="planta_74"):
    con = _consensus(fix)
    pdf_path = REPO/f"{fix}.pdf"
    PT = 0.19/con["wall_thickness_pts"]
    arcs = door_arcs_from_pdf(pdf_path)
    doors = [o for o in con["openings"] if (o.get("kind_v5") or o.get("kind")) in ("interior_door", "interior_passage")]
    results = []
    for o in doors:
        cx, cy = o["center"]; wpts = o.get("opening_width_pts", 0)
        # nearest arc whose center is within ~ wpts of the opening
        near = sorted(((math.hypot(ax-cx, ay-cy), rad) for ax, ay, rad in arcs))
        cand = [(d, rad) for d, rad in near if d < max(40, wpts*1.5)]
        pdf_w = cand[0][1] if cand else None
        if pdf_w is None:
            v = "INCONCLUSIVE(no_arc)"
        else:
            ratio = pdf_w/wpts if wpts else 0
            v = "FALSE_ALARM(faithful)" if 0.8 <= ratio <= 1.25 else "CONFIRMED_BUG(width_mismatch)"
        results.append({"door": o["id"], "consensus_w_pts": round(wpts, 1),
                        "consensus_w_m": round(wpts*PT, 2),
                        "pdf_arc_w_pts": round(pdf_w, 1) if pdf_w else None,
                        "ratio": round(pdf_w/wpts, 2) if pdf_w and wpts else None,
                        "verdict": v})
    return {"n_pdf_arcs": len(arcs), "doors": results}


def overlay(fix="planta_74"):
    import pypdfium2 as pdfium
    from PIL import ImageDraw
    con = _consensus(fix)
    pdf = pdfium.PdfDocument(str(REPO/f"{fix}.pdf")); page = pdf[0]
    PAGE_W, PAGE_H = page.get_size()
    img = page.render(scale=PDF_SCALE).to_pil().convert("RGB")
    d = ImageDraw.Draw(img, "RGBA")

    def P(x, y):
        return (x*PDF_SCALE, (PAGE_H-y)*PDF_SCALE)
    # rooms (translucent fill)
    pal = [(200, 230, 201, 90), (187, 222, 251, 90), (248, 187, 208, 90), (255, 224, 178, 90),
           (209, 196, 233, 90), (179, 229, 252, 90), (255, 249, 196, 90), (220, 237, 200, 90)]
    for i, rm in enumerate(con.get("rooms", [])):
        poly = rm.get("polygon_pts") or []
        if len(poly) >= 3:
            d.polygon([P(*p) for p in poly], fill=pal[i % len(pal)])
    # walls (blue)
    for w in con["walls"]:
        d.line([P(*w["start"]), P(*w["end"])], fill=(0, 60, 255, 230), width=3)
    # openings (green dot + width bar)
    for o in con["openings"]:
        c = o.get("center"); wp = o.get("opening_width_pts", 0)
        if not c:
            continue
        col = (230, 0, 0, 255) if (o.get("kind_v5") in ("interior_door", "interior_passage")) else (0, 150, 0, 255)
        x, y = P(*c)
        d.ellipse([x-4, y-4, x+4, y+4], outline=col, width=2)
    pr = con.get("planta_region")
    x0, y0, x1, y1 = pr
    crop = img.crop((int(x0*PDF_SCALE), int((PAGE_H-y1)*PDF_SCALE), int(x1*PDF_SCALE), int((PAGE_H-y0)*PDF_SCALE)))
    out = REPO/"runs"/fix/"pdf_overlay_consensus.png"
    crop.save(out)
    return out


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument("--fixture", default="planta_74"); a = ap.parse_args()
    op = overlay(a.fixture); print("overlay:", op.relative_to(REPO))
    res = verify(a.fixture)
    print("pdf_arcs_found:", res["n_pdf_arcs"])
    for r in res["doors"]:
        print(f"  {r['door']}: consensus={r['consensus_w_m']}m pdf_arc={r['pdf_arc_w_pts']}pts ratio={r['ratio']} -> {r['verdict']}")
