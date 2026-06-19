"""kitchen_validation.py — GATE de FIDELIDADE da cozinha ao PDF (Felipe: KITCHEN_PDF_ANCHOR_FIX).

A pia da cozinha é um PONTO HIDRÁULICO FIXO do PDF: parede OESTE (esquerda), sobre a
bancada vertical. Este gate roda ANTES de renderizar e FALHA o build se a pia migrar de
parede (ou cair fora da cozinha / dentro da A.S.). Imprime o relatório KITCHEN_VALIDATION.

Uso: PT_TO_M=0.0259 python -m tools.kitchen_validation [room_id]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TOUCH_TOL_IN = 6.0     # <= isso da face da parede = "encostado" (recuo de marcenaria)


def _modules(boxes):
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    polys = defaultdict(list)
    for b in boxes:
        if b.get("corners"):
            polys[str(b.get("module"))].append(Polygon([(c[0], c[1]) for c in b["corners"]]).buffer(0))
    return {m: unary_union(ps) for m, ps in polys.items()}


def validate(con, room_id="r004"):
    os.environ.setdefault("PT_TO_M", "0.0259")
    from shapely.affinity import scale
    from shapely.ops import unary_union

    from core.scale import PT_TO_IN
    from tools.kitchen_layout import KITCHEN_SINK_SIDE, build_boxes
    from tools.room_type import classify_rooms
    from tools.spatial_model import build_spatial_model

    def to_in(poly):
        return scale(poly, xfact=PT_TO_IN, yfact=PT_TO_IN, origin=(0, 0))

    sm = build_spatial_model(con, room_id)
    cell = to_in(sm["_geom"]["cell"])
    minx, miny, maxx, maxy = cell.bounds
    wt_in = float(sm["_geom"]["con"]["wall_thickness_pts"]) * PT_TO_IN
    west_face = minx + wt_in / 2     # face interna da parede oeste

    # A.S. (área de serviço) — a pia da cozinha NÃO pode cair lá (tanque/máquina ≠ pia)
    as_cell = None
    for r in classify_rooms(con):
        nm = (r.get("name") or "").upper()
        if "A.S" in nm or "SERVI" in nm:
            try:
                as_cell = to_in(build_spatial_model(con, r["id"])["_geom"]["cell"])
            except Exception:  # noqa: BLE001
                pass
            break

    # zonas de porta (giro + vão) — limpeza de circulação
    circ = list(sm["_geom"].get("circ") or [])
    circ_u = to_in(unary_union(circ)) if circ else None

    boxes, meta = build_boxes(con, room_id)
    if not boxes:
        return {"result": "FAIL", "checks": {"build": meta.get("reason", "sem boxes")}, "lines": []}
    mods = _modules(boxes)

    def inside(poly):
        return poly is not None and cell.buffer(2.0).contains(poly)

    def dist_to_walls(poly):
        x0, y0, x1, y1 = poly.bounds
        return {"LEFT": x0 - west_face, "RIGHT": (maxx - wt_in / 2) - x1,
                "TOP": y0 - (miny + wt_in / 2), "BOTTOM": (maxy - wt_in / 2) - y1}

    sink = mods.get("sink_module")
    fridge = mods.get("fridge")
    cooktop = mods.get("cooktop_module")

    c = {}
    if sink is not None:
        d = dist_to_walls(sink)
        sink_wall = min(d, key=lambda k: abs(d[k]))
        c["sink_wall"] = sink_wall
        c["sink_anchor_source"] = "PDF_WEST_WALL"
        c["sink_distance_to_left_wall_in"] = round(d["LEFT"], 1)
        c["sink_touches_left"] = abs(d["LEFT"]) <= TOUCH_TOL_IN
        c["sink_inside_kitchen"] = inside(sink)
        c["sink_not_inside_AS"] = (as_cell is None) or (sink.intersection(as_cell).area < 1.0)
    else:
        c["sink_wall"] = "ABSENT"
    c["fridge_inside_kitchen"] = inside(fridge)
    c["cooktop_inside_kitchen"] = inside(cooktop)
    if circ_u is not None:
        blocked = [m for m, p in mods.items() if p.intersection(circ_u).area > 2.0]
        c["kitchen_door_clearance_ok"] = not blocked
        c["_blocking"] = blocked
    else:
        c["kitchen_door_clearance_ok"] = True
    need = {"fridge", "sink_module", "cooktop_module", "countertop", "base_cabinet_01", "upper_cabinet_01"}
    c["modules_grouped_individually"] = need.issubset(set(mods))

    # REGRA DURA: pia tem que estar na parede ESQUERDA (oeste), encostada, dentro da cozinha
    hard = (c.get("sink_wall") == "LEFT" and c.get("sink_touches_left") and
            c.get("sink_inside_kitchen") and c.get("sink_not_inside_AS") and
            c.get("fridge_inside_kitchen") and c.get("cooktop_inside_kitchen") and
            c.get("kitchen_door_clearance_ok") and c.get("modules_grouped_individually"))
    result = "PASS" if hard else "FAIL"

    lines = ["KITCHEN_VALIDATION:",
             f"- sink_wall = {c.get('sink_wall')}",
             f"- sink_anchor_source = {c.get('sink_anchor_source', '-')}",
             f"- sink_distance_to_left_wall = {c.get('sink_distance_to_left_wall_in', '-')} in "
             f"({'~0/encostado' if c.get('sink_touches_left') else 'LONGE'})",
             f"- sink_inside_kitchen = {str(c.get('sink_inside_kitchen')).lower()}",
             f"- sink_not_inside_AS = {str(c.get('sink_not_inside_AS')).lower()}",
             f"- fridge_inside_kitchen = {str(c.get('fridge_inside_kitchen')).lower()}",
             f"- cooktop_inside_kitchen = {str(c.get('cooktop_inside_kitchen')).lower()}",
             f"- kitchen_door_clearance_ok = {str(c.get('kitchen_door_clearance_ok')).lower()}"
             + (f"  (bloqueando: {c['_blocking']})" if c.get("_blocking") else ""),
             f"- modules_grouped_individually = {str(c.get('modules_grouped_individually')).lower()}"]
    return {"result": result, "room": room_id, "checks": c, "lines": lines}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("room", nargs="?", default="r004")
    a = ap.parse_args()
    con = json.loads((ROOT / "fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json")
                     .read_text("utf-8"))
    res = validate(con, a.room)
    print("\n".join(res["lines"]))
    print(f"\nkitchen_validation => {res['result']}")
    sys.exit(0 if res["result"] == "PASS" else 1)


if __name__ == "__main__":
    main()
