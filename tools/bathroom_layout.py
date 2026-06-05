"""bathroom_layout.py — brain de BANHO/LAVABO (rough v1): bancada/pia + vaso como
placeholders, encostados nas paredes limpas. Plugga em furnish_apartment via
build_boxes (formato place_layout). v1 simples (pia + vaso); box/chuveiro num
refino. Espelha kitchen_layout (clip ao comodo). Felipe 2026-06-05. NAO 3DW.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shapely.ops import unary_union   # noqa: E402
from tools.bedroom_layout import M, _fbox, _wall_setup   # noqa: E402
from tools.spatial_model import PT_TO_M, build_spatial_model   # noqa: E402

PT_TO_IN = (0.19 / 5.4) * 39.3700787402
DOOR_KINDS = {"interior_door", "interior_passage", "glazed_balcony"}
COUNTER_DEPTH = 0.50          # bancada de banho mais rasa que cozinha
VASO = (0.40, 0.65)           # largura, profundidade
RGB = {"bancada_banho": [205, 205, 212], "vaso": [238, 240, 245]}
H_M = {"bancada_banho": 0.90, "vaso": 0.40}


def _to_box(kind, shp):
    x0, y0, x1, y1 = shp.bounds
    corners = [[round(px * PT_TO_IN, 2), round(py * PT_TO_IN, 2)]
               for px, py in list(shp.exterior.coords)[:-1]]
    return {"kind": kind, "x0": x0 * PT_TO_IN, "y0": y0 * PT_TO_IN,
            "x1": x1 * PT_TO_IN, "y1": y1 * PT_TO_IN, "corners": corners,
            "h_in": H_M[kind] * 39.3700787402, "rgb": RGB[kind], "label": kind,
            "ambiguous": False, "decorative": False}


def build_boxes(con, room_id):
    sm = build_spatial_model(con, room_id)
    cell = sm["_geom"]["cell"]
    circ_u = unary_union(sm["_geom"]["circ"]) if sm["_geom"]["circ"] else None
    comodo = cell.buffer(M(0.06))
    tol_circ = 0.02 / PT_TO_M ** 2
    by = {}
    for o in sm["openings"]:
        by.setdefault(o["wall_id"], []).append(o["kind"])
    clean = [w for w in sm["walls"]
             if not any(k in DOOR_KINDS for k in by.get(w["id"], [])) and w["length_m"] >= 0.8]
    clean.sort(key=lambda w: -w["length_m"])
    if not clean:
        return None, {"result": "NO_VALID_LAYOUT", "room_name": sm.get("room_name"),
                      "reason": "sem parede limpa p/ louca"}
    items, placed = [], None
    # pia/bancada na parede limpa mais longa, recortada pelo comodo + fora da circ
    ws = _wall_setup(sm, clean[0]["id"])
    if ws is not None:
        strip = _fbox(ws["orient"], ws["face"], ws["sgn"], ws["along_c"],
                      M(0.03), M(clean[0]["length_m"] + 0.6), M(COUNTER_DEPTH))
        inside = strip.intersection(cell)
        if circ_u is not None:
            inside = inside.difference(circ_u)
        if inside.geom_type == "MultiPolygon":
            inside = max(inside.geoms, key=lambda g: g.area)
        if not inside.is_empty and inside.geom_type == "Polygon" and inside.area > (0.18 / PT_TO_M ** 2):
            items.append(_to_box("bancada_banho", inside))
            placed = inside
    # vaso centralizado numa OUTRA parede limpa, encostado, fora da circ e da pia
    for w in clean[1:] + clean[:1]:
        vs = _wall_setup(sm, w["id"])
        if vs is None:
            continue
        vbox = _fbox(vs["orient"], vs["face"], vs["sgn"], vs["along_c"],
                     M(0.03), M(VASO[0]), M(VASO[1]))
        if (comodo.contains(vbox)
                and not (circ_u is not None and vbox.intersection(circ_u).area > tol_circ)
                and (placed is None or vbox.intersection(placed).area <= 0)):
            items.append(_to_box("vaso", vbox))
            break
    if not items:
        return None, {"result": "NO_VALID_LAYOUT", "room_name": sm.get("room_name"),
                      "reason": "nada coube"}
    return items, {"result": "OK", "room_name": sm.get("room_name"), "n_pecas": len(items)}


if __name__ == "__main__":
    import json
    con = json.loads(Path("fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json")
                     .read_text("utf-8"))
    for r in ("r005", "r006", "r007"):
        boxes, out = build_boxes(con, r)
        print(r, out.get("room_name"), out["result"], len(boxes) if boxes else 0, "pecas")
