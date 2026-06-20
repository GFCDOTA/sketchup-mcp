"""bathroom_layout.py — brain de BANHO/LAVABO (v3): pia + vaso + box/chuveiro
como placeholders. Apos review do GPT (2026-06-05): LAVABO precisa pia+vaso (so
pia = reprovado); BANHO precisa box/chuveiro (zoneamento molhado/seco).

v3: posiciona louca em QUALQUER parede do comodo (nao so as limpas) com o range
ao-longo RECORTADO ao comodo (parede compartilhada longa nao joga movel pra
fora), longe do vao/giro da porta (circ) e sem cobrir janela. Felipe. NAO 3DW.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shapely.ops import unary_union   # noqa: E402
from tools.bedroom_layout import (M, _door_zones, _fbox, _wall_setup,   # noqa: E402
                                  _window_zones)
from tools.spatial_model import PT_TO_M, build_spatial_model   # noqa: E402

from core.scale import PT_TO_IN  # noqa: E402  (fonte unica de escala; nao redefinir)
BOX_MIN_AREA_M2 = 4.0
VASO = ("vaso", 0.40, 0.65)
BOX = ("box", 0.90, 0.90)
RGB = {"bancada_banho": [205, 205, 212], "vaso": [238, 240, 245], "box": [170, 210, 230]}
H_M = {"bancada_banho": 0.90, "vaso": 0.40, "box": 2.00}


def _to_box(kind, shp):
    x0, y0, x1, y1 = shp.bounds
    corners = [[round(px * PT_TO_IN, 2), round(py * PT_TO_IN, 2)]
               for px, py in list(shp.exterior.coords)[:-1]]
    return {"kind": kind, "x0": x0 * PT_TO_IN, "y0": y0 * PT_TO_IN,
            "x1": x1 * PT_TO_IN, "y1": y1 * PT_TO_IN, "corners": corners,
            "h_in": H_M[kind] * 39.3700787402, "rgb": RGB[kind], "label": kind,
            "ambiguous": False, "decorative": False}


# ---- fixtures MULTI-PEÇA (MVP banheiro de verdade, não caixa pelada) ----
RGB2 = {"gabinete": [86, 64, 48], "tampo_banho": [196, 196, 202], "cuba": [236, 239, 243],
        "espelho": [188, 206, 216], "vaso": [240, 242, 246], "box_vidro": [176, 208, 224]}


def _pp(kind, x0, y0, x1, y1, z0_m, z1_m, rgb, module):
    """parte: x/y em POINTS (->inches), z em METROS. module = grupo no .skp."""
    x0, x1 = min(x0, x1), max(x0, x1)
    y0, y1 = min(y0, y1), max(y0, y1)
    return {"kind": kind, "x0": x0 * PT_TO_IN, "y0": y0 * PT_TO_IN,
            "x1": x1 * PT_TO_IN, "y1": y1 * PT_TO_IN,
            "corners": [[round(x0 * PT_TO_IN, 2), round(y0 * PT_TO_IN, 2)],
                        [round(x1 * PT_TO_IN, 2), round(y0 * PT_TO_IN, 2)],
                        [round(x1 * PT_TO_IN, 2), round(y1 * PT_TO_IN, 2)],
                        [round(x0 * PT_TO_IN, 2), round(y1 * PT_TO_IN, 2)]],
            "h_in": round((z1_m - z0_m) * 39.3700787402, 2), "z0_in": round(z0_m * 39.3700787402, 2),
            "rgb": rgb, "label": kind, "module": module, "ambiguous": False, "decorative": False}


def _emit(kind, b, ws):
    """Geometria CRÍVEL por fixture (substitui a caixa única)."""
    x0, y0, x1, y1 = b.bounds
    w, d = x1 - x0, y1 - y0
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    out = []
    if kind == "vaso":
        # vaso SUSPENSO (sem caixa acoplada): bacia afunilada off-floor + assento
        ins = min(w, d) * 0.12
        bowl = _pp("vaso", x0 + ins, y0 + ins, x1 - ins, y1 - ins, 0.28, 0.42, RGB2["vaso"], "Vaso")
        bowl["verts8"] = [(x0 + ins * 1.7, y0 + ins * 1.7, 0.28), (x1 - ins * 1.7, y0 + ins * 1.7, 0.28),
                          (x1 - ins * 1.7, y1 - ins * 1.7, 0.28), (x0 + ins * 1.7, y1 - ins * 1.7, 0.28),
                          (x0 + ins, y0 + ins, 0.42), (x1 - ins, y0 + ins, 0.42),
                          (x1 - ins, y1 - ins, 0.42), (x0 + ins, y1 - ins, 0.42)]
        out.append(bowl)
        out.append(_pp("vaso", x0 + ins, y0 + ins, x1 - ins, y1 - ins, 0.42, 0.45, RGB2["vaso"], "Vaso"))
    elif kind == "bancada_banho":
        out.append(_pp("gabinete", x0 + w * 0.04, y0 + d * 0.04, x1 - w * 0.04, y1 - d * 0.04,
                       0.10, 0.78, RGB2["gabinete"], "Bancada"))               # gabinete madeira
        out.append(_pp("bancada_banho", x0, y0, x1, y1, 0.78, 0.86, RGB2["tampo_banho"], "Bancada"))  # tampo pedra
        cwid = min(w, d) * 0.46
        out.append(_pp("cuba", cx - cwid / 2, cy - cwid / 2, cx + cwid / 2, cy + cwid / 2,
                       0.86, 1.0, RGB2["cuba"], "Bancada"))                    # cuba de apoio
        # espelho na PAREDE acima (usa ws p/ achar o lado da parede): thin, spanning o longo
        t = M(0.015)
        if ws is not None and ws["orient"] == "v":
            wx = (ws["face"] + ws["sgn"] * M(0.04))
            out.append(_pp("espelho", wx, y0 + d * 0.12, wx + t * ws["sgn"], y1 - d * 0.12,
                           1.05, 1.75, RGB2["espelho"], "Espelho"))
        elif ws is not None:
            wy = (ws["face"] + ws["sgn"] * M(0.04))
            out.append(_pp("espelho", x0 + w * 0.12, wy, x1 - w * 0.12, wy + t * ws["sgn"],
                           1.05, 1.75, RGB2["espelho"], "Espelho"))
    elif kind == "box":
        out.append(_pp("box_vidro", x0, y0, x1, y1, 0.0, 2.0, RGB2["box_vidro"], "Box"))
    return out


def _room_span(ws, cell):
    """Range ao-longo da parede que faz fronteira com o comodo (clipa ao bbox do
    cell — parede compartilhada longa nao posiciona fora do comodo)."""
    minx, miny, maxx, maxy = cell.bounds
    if ws["orient"] == "v":
        return max(ws["along_lo"], miny), min(ws["along_hi"], maxy)
    return max(ws["along_lo"], minx), min(ws["along_hi"], maxx)


def _place_fixture(sm, walls, w_m, d_m, placed, circ_u, comodo, cell, win_zone, tall):
    """1o spot valido pra um movel (w_m x d_m) encostado, deslizando ao longo de
    cada parede (range recortado ao comodo). tall=True -> nao pode cobrir janela."""
    tol = 0.02 / PT_TO_M ** 2
    for ws in walls:
        lo_r, hi_r = _room_span(ws, cell)
        lo = lo_r + M(w_m / 2 + 0.05)
        hi = hi_r - M(w_m / 2 + 0.05)
        if hi <= lo:
            continue
        n = max(1, int((hi - lo) / M(0.12)))
        for i in range(n + 1):
            ac = lo + (hi - lo) * i / n
            b = _fbox(ws["orient"], ws["face"], ws["sgn"], ac, M(0.03), M(w_m), M(d_m))
            if not comodo.contains(b):
                continue
            if circ_u is not None and b.intersection(circ_u).area > tol:
                continue
            if tall and win_zone is not None and b.intersection(win_zone).area > tol:
                continue
            if any(b.intersection(p).area > 0 for p in placed):
                continue
            return b, ws
    return None, None


def build_boxes(con, room_id):
    sm = build_spatial_model(con, room_id)
    cell = sm["_geom"]["cell"]
    area = sm["area_m2"]
    comodo = cell.buffer(M(0.06))
    # circ = giro de porta; tambem soma o vao da porta (nada de louca na porta)
    circ = list(sm["_geom"]["circ"] or [])
    door_z = _door_zones(sm)
    if door_z is not None:
        circ.append(door_z)
    circ_u = unary_union(circ) if circ else None
    win_zone = _window_zones(sm)

    walls = [ws for ws in (_wall_setup(sm, w["id"]) for w in sm["walls"]) if ws is not None]
    walls.sort(key=lambda ws: -(_room_span(ws, cell)[1] - _room_span(ws, cell)[0]))
    if not walls:
        return None, {"result": "NO_VALID_LAYOUT", "room_name": sm.get("room_name"),
                      "reason": "sem parede util"}

    # pia/cuba (menor em lavabo p/ caber pia+vaso) + vaso SEMPRE; box so com area
    pia = ("bancada_banho", 0.50, 0.40) if area < 4.5 else ("bancada_banho", 0.80, 0.50)
    fixtures = [(pia, False), (VASO, False)]
    if area >= BOX_MIN_AREA_M2:
        fixtures.append((BOX, True))

    items, placed = [], []
    for (kind, w_m, d_m), tall in fixtures:
        b, ws = _place_fixture(sm, walls, w_m, d_m, placed, circ_u, comodo, cell, win_zone, tall)
        if b is not None:
            items.extend(_emit(kind, b, ws))   # geometria CRÍVEL multi-peça
            placed.append(b)
    if not items:
        return None, {"result": "NO_VALID_LAYOUT", "room_name": sm.get("room_name"),
                      "reason": "nenhuma louca coube"}
    kinds = [it["kind"] for it in items]
    return items, {"result": "OK", "room_name": sm.get("room_name"),
                   "n_pecas": len(items), "pecas": kinds,
                   "tem_vaso": "vaso" in kinds, "tem_box": "box" in kinds}


if __name__ == "__main__":
    import json
    con = json.loads(Path("fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json")
                     .read_text("utf-8"))
    for r in ("r005", "r006", "r007"):
        boxes, out = build_boxes(con, r)
        print(r, out.get("room_name"), out["result"], out.get("pecas"))
