"""bed_placement_gate.py — GATE de PLACEMENT do QUARTO (Fase 2; espelha sofa_placement_gate).
Valida a POSICAO/ORIENTACAO de cama + guarda-roupa + criados (nao a anatomia, que e dos
builders/gates). Reusa o FurniturePlacementBrain base (cell/keepout/affordance).

Dimensoes (schema GPT Modo B):
  BED_PLACEMENT  — cama ANCORADA (cabeceira encosta) + cabeceira em parede LIMPA +
                   nao bloqueia porta + frente p/ dentro do quarto (orientacao nao-aleatoria)
  WARDROBE_PLACEMENT — guarda-roupa ancorado + FRENTE LIVRE (clearance) + nao bloqueia porta
  NIGHTSTANDS    — criados flanqueiam a cama (ao lado da cabeceira)
  CIRCULATION    — nada cruza a circulacao/giro de porta
  ORIENTATION    — cama de frente p/ o espaco livre, eixo limpo

-> {verdict, bed_placement, wardrobe_placement, nightstands, circulation, orientation, issues}.
Deterministico, sem SU. Fixtures de erro provam (cama bloqueando porta/sem cabeceira limpa/
rotacionada/circulacao; guarda-roupa bloqueando porta/sem frente livre = FAIL; quarto valido = PASS).

Uso: python -m interior.validators.bed_placement_gate [room_id]
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from shapely.geometry import Point, Polygon            # noqa: E402
from interior.planners.placement_brain import FurniturePlacementBrain  # noqa: E402
from tools.bedroom_layout import M, _door_zones, _wall_setup  # noqa: E402
from tools.spatial_model import PT_TO_M                  # noqa: E402

PT_TO_IN = (0.19 / 5.4) * 39.3700787402
ANCHOR_MAX_M = 0.50
CLEAR_M = 0.55         # folga de uso na frente do guarda-roupa
AREA_TOL = 0.05        # m2 de tolerancia de interseccao


def _oriented_poly(center_in, facing, w_m, l_m):
    """bbox orientada (pdf pts): largura W perp ao facing, comprimento L ao longo do facing."""
    cx, cy = center_in[0] / PT_TO_IN, center_in[1] / PT_TO_IN
    fx, fy = facing
    n = math.hypot(fx, fy) or 1.0
    fx, fy = fx / n, fy / n
    px, py = -fy, fx
    hw, hl = M(w_m) / 2, M(l_m) / 2
    pts = [(cx + px * hw * sw + fx * hl * sl, cy + py * hw * sw + fy * hl * sl)
           for sw, sl in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    return Polygon(pts), (cx, cy), (fx, fy)


def _wall_dist(ws, px, py):
    """Distancia (pdf pts) de um ponto ate a linha da parede (dentro do span)."""
    if ws["orient"] == "h":
        d = abs(py - ws["face"])
        if not (ws["along_lo"] <= px <= ws["along_hi"]):
            d = math.hypot(d, min(abs(px - ws["along_lo"]), abs(px - ws["along_hi"])))
    else:
        d = abs(px - ws["face"])
        if not (ws["along_lo"] <= py <= ws["along_hi"]):
            d = math.hypot(d, min(abs(py - ws["along_lo"]), abs(py - ws["along_hi"])))
    return d


def _nearest_wall(brain, px, py):
    best, bd = None, 1e18
    for w in brain.affordance["walls"]:
        ws = _wall_setup(brain.sm, w["wall_id"])
        if ws is None:
            continue
        d = _wall_dist(ws, px, py)
        if d < bd:
            best, bd = w, d
    return best, bd * PT_TO_M


def _front_strip(center, facing, w_m, l_m):
    """Faixa CLEAR_M a frente do movel (uso)."""
    cx, cy = center
    fx, fy = facing
    px, py = -fy, fx
    hw = M(w_m * 0.7) / 2
    inner, outer = M(l_m) / 2, M(l_m) / 2 + M(CLEAR_M)
    return Polygon([(cx + px * hw * s + fx * inner, cy + py * hw * s + fy * inner) for s in (-1, 1)]
                   + [(cx + px * hw * s + fx * outer, cy + py * hw * s + fy * outer) for s in (1, -1)])


def bed_placement_gate(con, room_id, layout):
    """layout = {bed:{center_in,facing,w_m,l_m}, wardrobe:{...}|None, nightstands:[{center_in}],
    justification:str}."""
    brain = FurniturePlacementBrain(con, room_id)
    cell, keepout = brain.cell, brain.keepout
    dz = _door_zones(brain.sm)
    issues, dims = [], {}

    bed = layout["bed"]
    bpoly, (cx, cy), (fx, fy) = _oriented_poly(bed["center_in"], bed["facing"], bed["w_m"], bed["l_m"])
    head = (cx - fx * M(bed["l_m"]) / 2, cy - fy * M(bed["l_m"]) / 2)
    # ANCORADO: cabeceira encosta numa parede
    anchored = cell.exterior.distance(Point(*head)) * PT_TO_M <= ANCHOR_MAX_M
    # CABECEIRA EM PAREDE LIMPA
    hw_wall, hw_d = _nearest_wall(brain, *head)
    head_clean = bool(hw_wall and hw_wall["clean"] and hw_d <= ANCHOR_MAX_M)
    # NAO BLOQUEIA PORTA
    bed_door = (bpoly.intersection(dz).area * PT_TO_M ** 2) if dz is not None else 0.0
    # ORIENTACAO: facing eixo-alinhado (quarto) + aponta p/ dentro (anchored cobre)
    axis_aligned = abs(fx) < 0.08 or abs(fy) < 0.08
    if not anchored:
        issues.append("cama flutuando (cabeceira longe da parede)")
    if not head_clean:
        issues.append("cabeceira NAO em parede limpa (porta/janela atras)")
    if bed_door > AREA_TOL:
        issues.append(f"cama bloqueia porta ({bed_door:.2f} m2)")
    if not axis_aligned:
        issues.append("cama rotacionada fora do eixo (aleatoria)")
    dims["BED_PLACEMENT"] = "PASS" if (anchored and head_clean and bed_door <= AREA_TOL) else "FAIL"
    dims["ORIENTATION"] = "PASS" if (anchored and axis_aligned) else "FAIL"

    # CIRCULACAO (cama nao cruza keepout)
    bed_circ = (bpoly.intersection(keepout).area * PT_TO_M ** 2) if keepout is not None else 0.0
    circ_ok = bed_circ <= AREA_TOL

    # WARDROBE
    wd = layout.get("wardrobe")
    if wd:
        wpoly, wc, wf = _oriented_poly(wd["center_in"], wd["facing"], wd["w_m"], wd["d_m"])
        w_back = Point(wc[0] - wf[0] * M(wd["d_m"]) / 2, wc[1] - wf[1] * M(wd["d_m"]) / 2)
        w_anchored = cell.exterior.distance(w_back) * PT_TO_M <= ANCHOR_MAX_M
        w_door = (wpoly.intersection(dz).area * PT_TO_M ** 2) if dz is not None else 0.0
        strip = _front_strip(wc, wf, wd["w_m"], wd["d_m"])
        free_front = cell.buffer(M(0.06)).contains(strip) and (
            keepout is None or strip.intersection(keepout).area * PT_TO_M ** 2 < AREA_TOL)
        if not w_anchored:
            issues.append("guarda-roupa boiando (fundo longe da parede)")
        if w_door > AREA_TOL:
            issues.append(f"guarda-roupa bloqueia porta ({w_door:.2f} m2)")
        if not free_front:
            issues.append("guarda-roupa sem frente livre (clearance)")
        wcirc = (wpoly.intersection(keepout).area * PT_TO_M ** 2) if keepout is not None else 0.0
        circ_ok = circ_ok and wcirc <= AREA_TOL
        dims["WARDROBE_PLACEMENT"] = "PASS" if (w_anchored and w_door <= AREA_TOL and free_front) else "FAIL"
    else:
        dims["WARDROBE_PLACEMENT"] = "WARN"  # sem guarda-roupa no layout

    # NIGHTSTANDS: flanqueiam a cama (perto da cabeceira, nas laterais)
    ns = layout.get("nightstands", [])
    flanking = 0
    for n in ns:
        nx, ny = n["center_in"][0] / PT_TO_IN, n["center_in"][1] / PT_TO_IN
        if bpoly.buffer(M(0.45)).contains(Point(nx, ny)):
            flanking += 1
    if ns:
        dims["NIGHTSTANDS"] = "PASS" if flanking == len(ns) else "WARN"
        if flanking < len(ns):
            issues.append(f"{len(ns) - flanking} criado(s) solto(s) (longe da cama)")
    else:
        dims["NIGHTSTANDS"] = "WARN"

    dims["CIRCULATION"] = "PASS" if circ_ok else "FAIL"
    if not circ_ok:
        issues.append(f"movel cruza circulacao (cama {bed_circ:.2f} m2)")

    hard = ("BED_PLACEMENT", "CIRCULATION", "ORIENTATION")
    soft_fail = dims.get("WARDROBE_PLACEMENT") == "FAIL"
    if any(dims[k] == "FAIL" for k in hard):
        verdict = "FAIL"
    elif soft_fail or any(v == "WARN" for v in dims.values()):
        verdict = "WARN"
    else:
        verdict = "PASS"
    return {"verdict": verdict, **dims, "issues": issues,
            "head_clean_wall": (hw_wall["wall_id"] if hw_wall else None)}


# ------------------------------------------------------------------ layout real + fixtures
def real_layout(con, room_id):
    """Extrai o layout do bedroom_designer (placement real do quarto)."""
    from tools import bedroom_designer
    _, out = bedroom_designer.run(con, room_id, minimalist=True)
    if out.get("result") != "OK":
        return None
    items = out["_winner_items"]
    pt_m = PT_TO_M
    pt_in = PT_TO_IN

    def cen_in(b):
        x0, y0, x1, y1 = b.bounds
        return [(x0 + x1) / 2 * pt_in, (y0 + y1) / 2 * pt_in]

    bed = next((it for it in items if it["type"] == "bed"), None)
    if bed is None:
        return None
    bx0, by0, bx1, by1 = bed["box"].bounds
    fx, fy = bed["facing"]
    if abs(fy) >= abs(fx):
        w_m, l_m = (bx1 - bx0) * pt_m, (by1 - by0) * pt_m
    else:
        w_m, l_m = (by1 - by0) * pt_m, (bx1 - bx0) * pt_m
    lay = {"bed": {"center_in": cen_in(bed["box"]), "facing": [float(fx), float(fy)],
                   "w_m": round(w_m, 3), "l_m": round(l_m, 3)},
           "nightstands": [{"center_in": cen_in(it["box"])} for it in items if it["type"] == "nightstand"],
           "justification": "bedroom_designer minimalista"}
    wd = next((it for it in items if it["type"] == "wardrobe"), None)
    if wd:
        wx0, wy0, wx1, wy1 = wd["box"].bounds
        wfx, wfy = wd.get("facing", (0.0, 1.0))
        if abs(wfy) >= abs(wfx):
            ww, wdp = (wx1 - wx0) * pt_m, (wy1 - wy0) * pt_m
        else:
            ww, wdp = (wy1 - wy0) * pt_m, (wx1 - wx0) * pt_m
        lay["wardrobe"] = {"center_in": cen_in(wd["box"]), "facing": [float(wfx), float(wfy)],
                           "w_m": round(ww, 3), "d_m": round(wdp, 3)}
    return lay


def _clone(d):
    return json.loads(json.dumps(d))


def _fixtures(con, room_id="r000"):
    """valido(real) + erros sinteticos p/ CADA ramo do gate (cama/guarda-roupa/criado).
    Devolve [(nome, layout, expect_verdict)]. expect = verdict GLOBAL:
      - problema de cama (hard) -> FAIL; problema so de guarda-roupa/criado (soft) -> WARN."""
    brain = FurniturePlacementBrain(con, room_id)
    real = real_layout(con, room_id)
    out = []
    dz = _door_zones(brain.sm)
    cc = brain.cell.centroid
    if not real:
        return out
    out.append(("quarto valido (designer)", real, "PASS"))
    # --- CAMA (hard -> FAIL) ---
    rot = _clone(real); rot["bed"]["facing"] = [0.7, 0.7]
    out.append(("cama rotacionada aleatoria", rot, "FAIL"))
    flo = _clone(real); flo["bed"]["center_in"] = [cc.x * PT_TO_IN, cc.y * PT_TO_IN]
    out.append(("cama flutuando no centro", flo, "FAIL"))
    if dz is not None:
        p = dz.representative_point()
        bd = _clone(real); bd["bed"]["center_in"] = [p.x * PT_TO_IN, p.y * PT_TO_IN]
        out.append(("cama bloqueando porta", bd, "FAIL"))
    # --- GUARDA-ROUPA (soft -> WARN; bloquear porta tambem fere circulacao -> FAIL) ---
    if real.get("wardrobe"):
        if dz is not None:
            p = dz.representative_point()
            wb = _clone(real); wb["wardrobe"]["center_in"] = [p.x * PT_TO_IN, p.y * PT_TO_IN]
            out.append(("guarda-roupa bloqueando porta", wb, "FAIL"))
        wf = _clone(real)
        wf["wardrobe"]["facing"] = [-real["wardrobe"]["facing"][0], -real["wardrobe"]["facing"][1]]
        out.append(("guarda-roupa sem frente livre", wf, "WARN"))
    # --- CRIADO solto (soft -> WARN) ---
    if real.get("nightstands"):
        nl = _clone(real); nl["nightstands"][0]["center_in"] = [cc.x * PT_TO_IN, cc.y * PT_TO_IN]
        out.append(("criado solto (longe da cama)", nl, "WARN"))
    return out


if __name__ == "__main__":
    con = json.loads((ROOT / "fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json")
                     .read_text("utf-8"))
    rid = sys.argv[1] if len(sys.argv) > 1 else "r000"
    print(f"=== BedPlacementGate fixtures ({rid}) ===")
    ok = True
    for name, lay, expect in _fixtures(con, rid):
        r = bed_placement_gate(con, rid, lay)
        hit = r["verdict"] == expect or (expect == "FAIL" and r["verdict"] == "FAIL")
        ok = ok and hit
        flag = {"PASS": "OK ", "WARN": "/!\\", "FAIL": "XXX"}[r["verdict"]]
        mark = "[ok]" if hit else f"[X ESPERAVA {expect}]"
        print(f"  {flag} {name:28} -> {r['verdict']:4} {mark} "
              f"(bed={r['BED_PLACEMENT']} circ={r['CIRCULATION']} orient={r['ORIENTATION']})")
        if r["issues"]:
            print(f"        issues: {'; '.join(r['issues'][:3])}")
    print(f"\n{'TODOS OK' if ok else 'FALHOU: gate nao bate com esperado'}")
    sys.exit(0 if ok else 1)
