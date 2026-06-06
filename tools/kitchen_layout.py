"""kitchen_layout.py — brain de COZINHA (rough v1): BANCADA (counter) ao longo
das paredes LIMPAS (sem porta), ate 2 paredes (L). Placeholder boxes; plugga em
furnish_apartment via build_boxes (mesmo formato do place_layout). v1 so bancada
(0.60 m prof, 0.90 m alt); eletrodomesticos entram num refino. Felipe 2026-06-05.
NAO usa 3D Warehouse.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shapely.ops import unary_union   # noqa: E402
from tools.bedroom_layout import M, _fbox, _wall_setup   # noqa: E402
from tools.spatial_model import PT_TO_M, build_spatial_model   # noqa: E402

PT_TO_IN = (0.19 / 5.4) * 39.3700787402
COUNTER_DEPTH = 0.60
COUNTER_H = 0.90
TORRE_W, TORRE_D, TORRE_H = 0.60, 0.62, 2.10   # coluna forno+microondas (GPT review)
RGB_COUNTER = [176, 166, 150]
RGB_TORRE = [69, 90, 100]                       # cinza-escuro eletrodoméstico
DOOR_KINDS = {"interior_door", "interior_passage", "glazed_balcony"}


def _to_box(kind, shp, h_m, rgb):
    x0, y0, x1, y1 = shp.bounds
    corners = [[round(px * PT_TO_IN, 2), round(py * PT_TO_IN, 2)]
               for px, py in list(shp.exterior.coords)[:-1]]
    return {"kind": kind, "x0": x0 * PT_TO_IN, "y0": y0 * PT_TO_IN,
            "x1": x1 * PT_TO_IN, "y1": y1 * PT_TO_IN, "corners": corners,
            "h_in": h_m * 39.3700787402, "rgb": rgb, "label": kind,
            "ambiguous": False, "decorative": False}


def build_boxes(con, room_id):
    """Bancada em L nas paredes limpas. Devolve (boxes, out) no formato do
    place_layout (compativel com furnish_apartment)."""
    sm = build_spatial_model(con, room_id)
    cell = sm["_geom"]["cell"]
    circ = sm["_geom"]["circ"]
    circ_u = unary_union(circ) if circ else None
    by = {}
    for o in sm["openings"]:
        by.setdefault(o["wall_id"], []).append(o["kind"])
    clean = [w for w in sm["walls"]
             if not any(k in DOOR_KINDS for k in by.get(w["id"], []))
             and w["length_m"] >= 1.2]
    clean.sort(key=lambda w: -w["length_m"])
    if not clean:
        return None, {"result": "NO_VALID_LAYOUT", "room_name": sm.get("room_name"),
                      "reason": "sem parede limpa p/ bancada"}
    min_area = 0.30 / (PT_TO_M ** 2)             # bancada minima 0.30 m2
    items, used, placed = [], [], None
    for w in clean[:2]:                          # ate 2 paredes (L)
        ws = _wall_setup(sm, w["id"])
        if ws is None:
            continue
        # faixa de bancada ao longo da parede inteira, RECORTADA pelo comodo
        # (segue a borda real), fora do arco de porta e sem overlap com a outra.
        strip = _fbox(ws["orient"], ws["face"], ws["sgn"], ws["along_c"],
                      M(0.03), M(w["length_m"] + 0.6), M(COUNTER_DEPTH))
        inside = strip.intersection(cell)
        if circ_u is not None:
            inside = inside.difference(circ_u)
        if placed is not None:
            inside = inside.difference(placed)
        if inside.is_empty:
            continue
        if inside.geom_type == "MultiPolygon":
            inside = max(inside.geoms, key=lambda g: g.area)
        if inside.geom_type != "Polygon" or inside.area < min_area:
            continue
        items.append(_to_box("bancada", inside, COUNTER_H, RGB_COUNTER))
        used.append(w["id"])
        placed = inside if placed is None else placed.union(inside)
    if not items:
        return None, {"result": "NO_VALID_LAYOUT", "room_name": sm.get("room_name"),
                      "reason": "bancada nao coube dentro do comodo"}

    # TORRE/coluna alta (forno+microondas) numa PONTA da bancada (GPT review: cozinha
    # sem torre fica "blocos de bancada", incompleta). Desliza na parede-bancada com o
    # range RECORTADO ao comodo (parede compartilhada nao joga a torre pra fora),
    # ponta-cega primeiro, dentro do comodo e fora da circulacao.
    n_torre = 0
    minx, miny, maxx, maxy = cell.bounds
    for wid in used:
        ws0 = _wall_setup(sm, wid)
        if ws0 is None:
            continue
        if ws0["orient"] == "v":
            a_lo, a_hi = max(ws0["along_lo"], miny), min(ws0["along_hi"], maxy)
        else:
            a_lo, a_hi = max(ws0["along_lo"], minx), min(ws0["along_hi"], maxx)
        lo, hi = a_lo + M(TORRE_W / 2 + 0.03), a_hi - M(TORRE_W / 2 + 0.03)
        if hi <= lo:
            continue
        n = max(1, int((hi - lo) / M(0.12)))
        mid = (lo + hi) / 2
        spot = None
        for i in sorted(range(n + 1), key=lambda j: -abs((lo + (hi - lo) * j / n) - mid)):
            ac = lo + (hi - lo) * i / n
            t = _fbox(ws0["orient"], ws0["face"], ws0["sgn"], ac, M(0.03),
                      M(TORRE_W), M(TORRE_D)).intersection(cell)
            if t.is_empty:
                continue
            if t.geom_type == "MultiPolygon":
                t = max(t.geoms, key=lambda g: g.area)
            if t.geom_type != "Polygon" or t.area < (0.20 / PT_TO_M ** 2):
                continue
            if circ_u is not None and not t.intersection(circ_u).is_empty:
                continue
            spot = t
            break
        if spot is not None:
            items.append(_to_box("torre", spot, TORRE_H, RGB_TORRE))
            n_torre = 1
            break
    return items, {"result": "OK", "room_name": sm.get("room_name"),
                   "n_counters": len(used), "n_torre": n_torre, "walls": used}


if __name__ == "__main__":
    import json
    con = json.loads(Path("fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json")
                     .read_text("utf-8"))
    boxes, out = build_boxes(con, "r004")
    print(f"COZINHA r004 ('{out.get('room_name')}') | {out['result']} | "
          f"{len(boxes) if boxes else 0} bancada(s) nas paredes {out.get('walls')}")
