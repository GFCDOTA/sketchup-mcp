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

PT_TO_IN = (0.19 / 5.4) * 39.3700787402
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
            return b
    return None


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
        b = _place_fixture(sm, walls, w_m, d_m, placed, circ_u, comodo, cell, win_zone, tall)
        if b is not None:
            items.append(_to_box(kind, b))
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
