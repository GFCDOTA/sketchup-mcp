#!/usr/bin/env python3
"""geometry_sanity.py — GATE de regressão geométrica determinístico (sem LLM, barato).

Roda ANTES de promover .skp / render / artifact / ambiente mobiliado. Pega regressão
OBJETIVA nas peças/móveis (boxes: x0,y0,x1,y1 + z0_in/h_in + corners):
  underground · degenerada · off-axis · bbox absurda/escala · fora do cômodo.

PASS  = sem regressão geométrica óbvia (NÃO significa bonito/premium).
WARN  = borderline; segue, mas precisa motivo explícito.
FAIL  = regressão objetiva; BLOQUEIA promoção.

NÃO substitui o veredito visual final, NÃO aprova premium — só barra erro objetivo.
Determinístico, geometria axis-aligned (planta retilínea), stdlib pura. Já sofremos com
geometria underground/degenerada/off-axis/caos voltando: este gate impede a regressão.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

# tolerâncias no sistema das caixas (apt_boxes usa POLEGADAS: x/y/z0_in/h_in em in).
DEFAULTS = {
    "z_under_tol_in": -0.5,      # z0_in abaixo disso = underground (embaixo da terra)
    "min_footprint_in2": 1.0,    # footprint menor = degenerada (área ~0)
    "min_height_in": 0.2,        # altura menor = sliver 2D (WARN)
    "max_dim_m": 6.0,            # UMA dimensão de um móvel > isso = escala explodida
    "outside_margin": 1.0,       # margem p/ "fora do cômodo" (mesma unidade das caixas)
}


def _wh(b):
    return (b["x1"] - b["x0"], b["y1"] - b["y0"])


def _axis_aligned(b) -> bool:
    cs = b.get("corners")
    if not cs:
        return True  # sem corners -> assume AABB (x0..y1)
    xs = {round(c[0], 1) for c in cs}
    ys = {round(c[1], 1) for c in cs}
    return len(xs) <= 2 and len(ys) <= 2


def _pt_in_poly(x, y, poly) -> bool:
    inside, n, j = False, len(poly), len(poly) - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi):
            inside = not inside
        j = i
    return inside


def audit(parts, *, rooms=None, to_m=1.0, cfg=None) -> dict:
    """parts: lista de boxes. rooms: lista de polígonos [[x,y],...] NA MESMA UNIDADE das
    caixas (opcional — só então roda fora-do-cômodo). to_m converte dimensões p/ metros
    (apt_boxes em polegadas -> to_m=0.0254). Devolve dict com overall/findings."""
    c = {**DEFAULTS, **(cfg or {})}
    findings = []

    def add(sev, check, b, detail):
        findings.append({"severity": sev, "check": check, "label": b.get("label"),
                         "kind": b.get("kind"), "detail": detail})

    for b in parts:
        w, d = _wh(b)
        z0 = b.get("z0_in")
        if z0 is not None and z0 < c["z_under_tol_in"]:
            add("FAIL", "underground", b, f"z0_in={round(z0, 2)} < {c['z_under_tol_in']}")
        if w * d < c["min_footprint_in2"]:
            add("FAIL", "degenerate_footprint", b, f"footprint={round(w * d, 3)} (w={round(w,2)} d={round(d,2)})")
        h = b.get("h_in")
        if h is not None and 0 < h < c["min_height_in"]:
            add("WARN", "degenerate_height", b, f"h_in={round(h, 3)}")
        if not b.get("decorative") and not _axis_aligned(b):
            # decorativo (tapete/manta) pode ser recortado ao comodo (poligono nao-retangular,
            # cantos arredondados) -> nao e "eixo torto" estrutural. So estrutural checa off_axis.
            add("FAIL", "off_axis", b, "corners nao axis-aligned (eixo torto)")
        for dim, nm in ((w, "w"), (d, "d")):
            if dim * to_m > c["max_dim_m"]:
                add("FAIL", "absurd_bbox", b, f"{nm}={round(dim * to_m, 2)}m > {c['max_dim_m']}m (escala explodida)")
        if rooms:
            cx, cy = (b["x0"] + b["x1"]) / 2, (b["y0"] + b["y1"]) / 2
            if not any(_pt_in_poly(cx, cy, poly) for poly in rooms):
                add("FAIL", "outside_room", b, f"centro ({round(cx)},{round(cy)}) fora de todos os comodos")

    n_fail = sum(1 for f in findings if f["severity"] == "FAIL")
    n_warn = sum(1 for f in findings if f["severity"] == "WARN")
    checks = ["underground", "degenerate_footprint", "degenerate_height", "off_axis", "absurd_bbox"]
    if rooms:
        checks.append("outside_room")
    return {"overall": "FAIL" if n_fail else ("WARN" if n_warn else "PASS"),
            "n_parts": len(parts), "n_fail": n_fail, "n_warn": n_warn,
            "findings": findings, "checks_run": checks,
            "note": "PASS = sem regressao geometrica obvia; NAO julga estetica/premium (isso e o visual review)."}


def summary_line(res) -> str:
    return (f"geometry_sanity: {res['overall']} | parts={res['n_parts']} "
            f"fail={res['n_fail']} warn={res['n_warn']} | checks={','.join(res['checks_run'])}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="geometry_sanity — gate de regressao geometrica (PASS/WARN/FAIL)")
    ap.add_argument("boxes", help="JSON de boxes/parts (lista)")
    ap.add_argument("--consensus", default=None, help="consensus p/ poligonos de comodo (fora-do-comodo); precisa MESMA unidade das caixas")
    ap.add_argument("--to-m", type=float, default=1.0, help="fator unidade->m (apt_boxes polegadas: 0.0254)")
    ap.add_argument("--log-dir", default=None, help="grava o JSON de auditoria aqui (artifact)")
    a = ap.parse_args(argv)
    parts = json.loads(Path(a.boxes).read_text("utf-8"))
    rooms = None
    if a.consensus:
        con = json.loads(Path(a.consensus).read_text("utf-8"))
        rooms = [r.get("polygon_pts") or r.get("polygon") for r in con.get("rooms", [])
                 if r.get("polygon_pts") or r.get("polygon")]
    res = audit(parts, rooms=rooms, to_m=a.to_m)
    print(summary_line(res))
    print(json.dumps(res, ensure_ascii=False))
    if a.log_dir:
        dd = Path(a.log_dir)
        dd.mkdir(parents=True, exist_ok=True)
        res["_ts"] = time.time()
        (dd / "geometry_sanity.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), "utf-8")
    return 0 if res["overall"] == "PASS" else (2 if res["overall"] == "WARN" else 1)


if __name__ == "__main__":
    raise SystemExit(main())
