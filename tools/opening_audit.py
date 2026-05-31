#!/usr/bin/env python3
"""Opening-audit overlay — door/window fidelity vs the PDF (planta source of truth).

Draws, on the high-res PDF raster (the only authoritative geometric reference):
  - consensus wall segments
  - each consensus opening gap (center +/- opening_width_pts/2 along host wall)
  - the door swing
  - the ACTUAL SKP door/window footprint (geometry_report world bbox, mapped
    back to pdf-points via an affine derived from opening<->group correspondences)
and emits a PASS/FAIL per opening.

This is evidence + the seed of the visual FAIL gate. It does NOT modify the
builder or the .skp. PDF is ground truth; nothing here fabricates geometry.

FAIL criteria (objective):
  - off_wall      : opening center does not project onto its host wall segment
  - oversize_door : door leaf width > MAX_DOOR_M (looks like a panel)
  - crosses_wall  : actual SKP footprint bbox straddles the host wall line by
                    more than the wall half-thickness + tol (door crosses wall)
WARN:
  - full_height_solid_leaf : door built as a solid 2.1 m leaf (should be a thin
                             leaf + 2D swing, not a full-height brown panel)
"""
from __future__ import annotations

import json
import math
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MAX_DOOR_M = 1.0          # a single residential door is ~0.7-0.9 m
PDF_SCALE = 3.0           # raster scale for the overlay


def _pt_to_m(con: dict) -> float:
    return 0.19 / con["wall_thickness_pts"]


def _proj_param(p, a, b):
    """Projection parameter t of point p onto segment a->b (0..1 = on segment)."""
    ax, ay = a; bx, by = b; px, py = p
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return 0.0, math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / L2
    cx, cy = ax + t * dx, ay + t * dy
    return t, math.hypot(px - cx, py - cy)


def _derive_pdf_to_world(con: dict, rep: dict):
    """Axis-aligned affine wx=a*px+b, wy=c*py+d from opening center (pdf) <->
    door/window group bbox center (world m). Returns (a,b,c,d) or None."""
    groups = {g["name"]: g for g in rep.get("groups_diagnostic", [])}
    px, wx, py, wy = [], [], [], []
    for o in con["openings"]:
        oid = o["id"]
        g = groups.get(f"DoorLeaf_Group_{oid}") or groups.get(f"WindowGlass_Group_{oid}") \
            or groups.get(f"GlazedBalcony_Group_{oid}")
        if not g or "center" not in o:
            continue
        bb = g.get("bbox_m", {})
        mn, mx = bb.get("min"), bb.get("max")
        if not mn or not mx:
            continue
        cx, cy = (mn[0] + mx[0]) / 2, (mn[1] + mx[1]) / 2
        px.append(o["center"][0]); wx.append(cx)
        py.append(o["center"][1]); wy.append(cy)
    if len(px) < 2:
        return None

    def fit(xs, ys):
        n = len(xs); sx = sum(xs); sy = sum(ys)
        sxx = sum(x * x for x in xs); sxy = sum(x * y for x, y in zip(xs, ys))
        den = n * sxx - sx * sx
        if abs(den) < 1e-9:
            return None
        a = (n * sxy - sx * sy) / den
        b = (sy - a * sx) / n
        return a, b
    fx, fy = fit(px, wx), fit(py, wy)
    if not fx or not fy:
        return None
    return fx[0], fx[1], fy[0], fy[1]


def audit(fixture: str = "planta_74") -> dict:
    import pypdfium2 as pdfium
    from PIL import Image, ImageDraw

    con = json.loads((REPO_ROOT / "fixtures" / fixture
                      / "consensus_with_human_walls_and_soft_barriers.json").read_text("utf-8"))
    rep = json.loads((REPO_ROOT / "runs" / fixture / "geometry_report.json").read_text("utf-8"))
    pdf_path = REPO_ROOT / f"{fixture}.pdf"
    PT_TO_M = _pt_to_m(con)
    walls = {w["id"]: w for w in con["walls"]}
    groups = {g["name"]: g for g in rep.get("groups_diagnostic", [])}
    tf = _derive_pdf_to_world(con, rep)  # (a,b,c,d) pdf->world; None if can't

    # render PDF page
    pdf = pdfium.PdfDocument(str(pdf_path))
    page = pdf[0]
    PAGE_W, PAGE_H = page.get_size()
    img = page.render(scale=PDF_SCALE).to_pil().convert("RGB")
    draw = ImageDraw.Draw(img, "RGBA")

    def P(x, y):  # pdf-points -> raster pixel (Y flip)
        return (x * PDF_SCALE, (PAGE_H - y) * PDF_SCALE)

    def world_to_pdf(wx, wy):
        a, b, c, d = tf
        return ((wx - b) / a, (wy - d) / c)

    # walls (blue)
    for w in con["walls"]:
        draw.line([P(*w["start"]), P(*w["end"])], fill=(0, 80, 255, 200), width=2)

    findings = []
    for o in con["openings"]:
        oid = o["id"]
        kind = o.get("kind_v5") or o.get("kind")
        w = walls.get(o.get("wall_id"))
        ctr = o.get("center")
        wpts = o.get("opening_width_pts")
        width_m = wpts * PT_TO_M if wpts else None
        reasons = []
        t = dist = None
        if w and ctr:
            # gap-openings legitimately sit beyond a short host segment's end
            # (collinear walls share the line), so judge by PERPENDICULAR
            # distance to the host wall LINE, not the segment-t range.
            t, dist = _proj_param(ctr, w["start"], w["end"])
            (ax, ay), (bx, by) = w["start"], w["end"]
            Lw = math.hypot(bx - ax, by - ay) or 1.0
            perp = abs((bx - ax) * (ay - ctr[1]) - (ax - ctr[0]) * (by - ay)) / Lw
            if perp > w.get("thickness", 6) * 2.0:
                reasons.append(f"off_wall(perp={perp:.1f}pt)")
        else:
            reasons.append("no_wall_or_center")
        is_door = kind in ("interior_door", "interior_passage")
        if is_door and width_m and width_m > MAX_DOOR_M:
            reasons.append(f"oversize_door({width_m:.2f}m>{MAX_DOOR_M})")
        # actual SKP footprint
        g = groups.get(f"DoorLeaf_Group_{oid}") or groups.get(f"WindowGlass_Group_{oid}") \
            or groups.get(f"GlazedBalcony_Group_{oid}")
        leaf_h = g.get("height_m") if g else None
        if is_door and leaf_h and leaf_h > 2.0:
            reasons.append("WARN_full_height_solid_leaf")
        # draw gap (center +/- width/2 along wall dir)
        if w and ctr and wpts:
            (ax, ay), (bx, by) = w["start"], w["end"]
            L = math.hypot(bx - ax, by - ay) or 1
            ux, uy = (bx - ax) / L, (by - ay) / L
            h = wpts / 2
            g0 = (ctr[0] - ux * h, ctr[1] - uy * h)
            g1 = (ctr[0] + ux * h, ctr[1] + uy * h)
            fail = any(not r.startswith("WARN") for r in reasons)
            col = (230, 0, 0, 255) if fail else (0, 170, 0, 255)
            draw.line([P(*g0), P(*g1)], fill=col, width=6)
            draw.ellipse([P(ctr[0] - 2, ctr[1] + 2)[0], P(ctr[0] - 2, ctr[1] + 2)[1],
                          P(ctr[0] + 2, ctr[1] - 2)[0], P(ctr[0] + 2, ctr[1] - 2)[1]],
                         outline=col, width=2)
        # draw actual SKP footprint bbox (orange) mapped world->pdf
        crosses = None
        if g and tf:
            bb = g["bbox_m"]; mn, mx = bb["min"], bb["max"]
            c0 = world_to_pdf(mn[0], mn[1]); c1 = world_to_pdf(mx[0], mx[1])
            xs = [c0[0], c1[0]]; ys = [c0[1], c1[1]]
            draw.rectangle([P(min(xs), max(ys))[0], P(min(xs), max(ys))[1],
                            P(max(xs), min(ys))[0], P(max(xs), min(ys))[1]],
                           outline=(255, 140, 0, 230), width=2)
            if w and ctr and dist is not None:
                # crosses_wall: footprint half-extent perpendicular to wall >> wall half-thk
                fp_perp = max(abs(c1[0] - c0[0]), abs(c1[1] - c0[1]))  # rough
                crosses = fp_perp > (w.get("thickness", 6) * 2 + abs(wpts or 0))
        verdict = "FAIL" if any(not r.startswith("WARN") for r in reasons) else \
                  ("WARN" if reasons else "PASS")
        findings.append({
            "opening": oid, "kind": kind, "host_wall": o.get("wall_id"),
            "opening_width_pts": wpts, "width_m": round(width_m, 3) if width_m else None,
            "leaf_height_m": leaf_h, "on_wall_t": round(t, 3) if t is not None else None,
            "verdict": verdict, "reasons": reasons,
        })

    # crop to plan region
    pr = con.get("planta_region")
    if pr:
        x0, y0, x1, y1 = pr
        crop = img.crop((int(x0 * PDF_SCALE), int((PAGE_H - y1) * PDF_SCALE),
                         int(x1 * PDF_SCALE), int((PAGE_H - y0) * PDF_SCALE)))
    else:
        crop = img
    out_png = REPO_ROOT / "runs" / fixture / "opening_audit_overlay.png"
    crop.save(out_png)

    n_fail = sum(1 for f in findings if f["verdict"] == "FAIL")
    n_warn = sum(1 for f in findings if f["verdict"] == "WARN")
    report = {
        "fixture": fixture, "pt_to_m": round(PT_TO_M, 5),
        "transform_derived": tf is not None,
        "n_openings": len(findings), "n_fail": n_fail, "n_warn": n_warn,
        "overall": "FAIL" if n_fail else ("WARN" if n_warn else "PASS"),
        "overlay_png": str(out_png.relative_to(REPO_ROOT)),
        "openings": findings,
    }
    (REPO_ROOT / "runs" / fixture / "opening_audit_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", "utf-8")
    return report


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", default="planta_74")
    r = audit(ap.parse_args().fixture)
    print(f"[opening-audit] overall={r['overall']} "
          f"openings={r['n_openings']} FAIL={r['n_fail']} WARN={r['n_warn']} "
          f"pt_to_m={r['pt_to_m']} transform={r['transform_derived']}")
    for f in r["openings"]:
        print(f"  {f['opening']:8} {f['kind']:16} wall={f['host_wall']:6} "
              f"w={f['width_m']}m h={f['leaf_height_m']}m t={f['on_wall_t']} "
              f"-> {f['verdict']} {f['reasons']}")
