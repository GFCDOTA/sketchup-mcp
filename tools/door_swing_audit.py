#!/usr/bin/env python3
"""Auditoria determinística do LADO DE SWING + DOBRADIÇA das portas vs o PDF.

PDF é ground truth (regra do projeto): cada porta tem um arco de swing
vetorial (bezier) na planta. Este audit mede, por opening kind=door do
consensus:

- ``swing_side``: de que lado do wall hospedeiro o arco vive, no eixo
  transversal em pdf-points — ``pos`` (cross maior) ou ``neg`` (cross menor).
  Medida: sinal de (centro do bbox do arco − cross do wall).
- ``hinge_side``: em que extremidade do vão está a dobradiça, na convenção do
  builder (``left`` = along − width/2, ``right`` = along + width/2; para wall
  vertical o along é o eixo y). Medida: dos dois endpoints do path do arco, o
  que NÃO toca a linha do wall é a ponta da folha aberta, cujo along ≈ o
  along da dobradiça.

Uso:
    python -m tools.door_swing_audit                # audita fixture planta_74
    python -m tools.door_swing_audit --fix planta_74 --json

Sem fabricação: porta sem arco casável no PDF → ``UNRESOLVED`` (nunca chuta).
Consumido por tests/test_door_swing_contract.py como gate regressivo.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# match arco<->porta: centro do arco a menos de MATCH_FACTOR * raio do centro
# da opening (o bbox do arco cobre o vão inteiro, então a folga é ~1 raio).
MATCH_FACTOR = 1.6
# raio do arco de porta ≈ largura do vão (folha aberta = quarto de círculo).
RADIUS_WIDTH_TOL = 0.5
# path fechado (oval de cuba/vaso) tem p0≈p1 — não é arco de porta.
CLOSED_PATH_TOL_PT = 1.0


def _consensus(fix: str) -> dict:
    p = REPO / "fixtures" / fix / "consensus_with_human_walls_and_soft_barriers.json"
    return json.loads(p.read_text("utf-8"))


def door_arc_paths_from_pdf(pdf_path: Path):
    """Arcos de swing do PDF: [(cx, cy, radius_pts, endpoints[(x,y),...])]."""
    import pypdfium2 as pdfium
    import pypdfium2.raw as C

    pdf = pdfium.PdfDocument(str(pdf_path))
    page = pdf[0]
    arcs = []
    for o in page.get_objects():
        if o.type != C.FPDF_PAGEOBJ_PATH:
            continue
        try:
            n = C.FPDFPath_CountSegments(o.raw)
        except Exception:
            continue
        pts, has_bezier = [], False
        import ctypes
        for i in range(n):
            seg = C.FPDFPath_GetPathSegment(o.raw, i)
            if not seg:
                continue
            if C.FPDFPathSegment_GetType(seg) == C.FPDF_SEGMENT_BEZIERTO:
                has_bezier = True
            x = ctypes.c_float()
            y = ctypes.c_float()
            if C.FPDFPathSegment_GetPoint(seg, ctypes.byref(x), ctypes.byref(y)):
                pts.append((float(x.value), float(y.value)))
        if not has_bezier or len(pts) < 2:
            continue
        try:
            l, b, r, t = o.get_pos()
        except Exception:
            continue
        # segment points vêm no espaço LOCAL do path — aplicar a matriz do
        # objeto pra levar ao espaço da página (pdf points).
        try:
            m = o.get_matrix()  # (a, b, c, d, e, f)
            a_, b_, c_, d_, e_, f_ = m.get()
            pts = [(a_ * x + c_ * y + e_, b_ * x + d_ * y + f_)
                   for (x, y) in pts]
        except Exception:
            pass
        w, h = r - l, t - b
        rad = max(w, h)
        if not (12 < rad < 70 and 0.4 < (min(w, h) / rad if rad else 0) <= 1.0):
            continue
        # path fechado = oval de louça (cuba/vaso), não arco de swing
        if math.hypot(pts[0][0] - pts[-1][0],
                      pts[0][1] - pts[-1][1]) < CLOSED_PATH_TOL_PT:
            continue
        arcs.append(((l + r) / 2, (b + t) / 2, rad, (pts[0], pts[-1])))
    return arcs


def _wall_basis(wall: dict):
    """(axis_idx, cross_value): axis 0 = wall horizontal (along x)."""
    horiz = abs(wall["start"][1] - wall["end"][1]) < 1e-6
    return (0, wall["start"][1]) if horiz else (1, wall["start"][0])


def audit(fix: str = "planta_74") -> list[dict]:
    con = _consensus(fix)
    walls = {w["id"]: w for w in con["walls"]}
    arcs = door_arc_paths_from_pdf(REPO / f"{fix}.pdf")
    out = []
    for op in con["openings"]:
        if op.get("kind") != "door":
            continue
        wall = walls[op["wall_id"]]
        axis_idx, cross_value = _wall_basis(wall)
        cx, cy = op["center"]
        along = cx if axis_idx == 0 else cy
        half_w = float(op["opening_width_pts"]) / 2.0

        best = None
        for ax, ay, rad, ends in arcs:
            if abs(rad - 2 * half_w) > RADIUS_WIDTH_TOL * 2 * half_w:
                continue  # raio incompatível com a largura deste vão
            d = math.hypot(ax - cx, ay - cy)
            if d < MATCH_FACTOR * rad and (best is None or d < best[0]):
                best = (d, ax, ay, rad, ends)

        row = {
            "id": op["id"],
            "wall_id": op["wall_id"],
            "axis": "H" if axis_idx == 0 else "V",
            "consensus_swing": op.get("swing_side"),
            "consensus_hinge": op.get("hinge_side"),
        }
        if best is None:
            row.update(pdf_swing="UNRESOLVED", pdf_hinge="UNRESOLVED",
                       match=None)
            out.append(row)
            continue

        d, ax, ay, rad, (p0, p1) = best
        arc_cross = ay if axis_idx == 0 else ax
        row["pdf_swing"] = "pos" if arc_cross > cross_value else "neg"

        # ponta da folha = endpoint que NÃO toca a linha do wall
        def cross_of(p):
            return p[1] if axis_idx == 0 else p[0]

        def along_of(p):
            return p[0] if axis_idx == 0 else p[1]

        d0 = abs(cross_of(p0) - cross_value)
        d1 = abs(cross_of(p1) - cross_value)
        tip = p0 if d0 > d1 else p1
        # "toca o wall" = está na FACE do wall (meia espessura + folga de traço)
        touch_tol = float(wall.get("thickness", con.get("wall_thickness_pts", 8.0))) / 2.0 + 3.0
        if min(d0, d1) > touch_tol:
            # nenhum endpoint na linha do wall — arco atípico, não chutar
            row["pdf_hinge"] = "UNRESOLVED"
        else:
            hinge_along = along_of(tip)
            row["pdf_hinge"] = ("left" if abs(hinge_along - (along - half_w))
                                <= abs(hinge_along - (along + half_w))
                                else "right")
        row["match"] = {"dist_pt": round(d, 1), "radius_pt": round(rad, 1)}
        row["swing_ok"] = row["consensus_swing"] == row["pdf_swing"]
        row["hinge_ok"] = row["consensus_hinge"] == row["pdf_hinge"]
        out.append(row)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fix", default="planta_74")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    rows = audit(args.fix)
    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
    else:
        for r in rows:
            print(f"{r['id']} {r['axis']} wall={r['wall_id']} "
                  f"pdf(swing={r.get('pdf_swing')}, hinge={r.get('pdf_hinge')}) "
                  f"consensus(swing={r['consensus_swing']}, hinge={r['consensus_hinge']}) "
                  f"swing_ok={r.get('swing_ok')} hinge_ok={r.get('hinge_ok')}")
    bad = [r for r in rows if not (r.get("swing_ok") and r.get("hinge_ok"))]
    print(f"door_swing_audit => {'PASS' if not bad else f'FAIL ({len(bad)}/{len(rows)} divergem)'}")
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
