"""kitchen_layout.py — brain de COZINHA LINEAR (galley). A parede principal é
SEGMENTADA sem sobreposicao: geladeira numa ponta -> bancada no meio (pia + cooktop
EMBUTIDOS) -> torre/coluna na outra ponta; armario aereo SO sobre a bancada. 2a parede
limpa (L) recebe bancada extra carved. Sem movel em cima de movel
(tools/furniture_overlap_gate). Pratico: bancada continua, fluxo geladeira->pia->cooktop.
Placeholder boxes; plugga em furnish_apartment via build_boxes. NAO usa 3D Warehouse.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shapely.ops import unary_union   # noqa: E402
from tools.bedroom_layout import M, _fbox, _wall_setup, _window_zones   # noqa: E402
from tools.spatial_model import PT_TO_M, build_spatial_model   # noqa: E402

from core.scale import PT_TO_IN  # noqa: E402  (fonte unica de escala; nao redefinir)
COUNTER_DEPTH = 0.60
COUNTER_H = 0.90
GEL_W, GEL_D, GEL_H = 0.70, 0.66, 1.80          # geladeira (ponta, full-height)
TORRE_W, TORRE_D, TORRE_H = 0.60, 0.62, 2.10    # coluna forno+microondas (outra ponta)
AEREO_DEPTH, AEREO_Z0, AEREO_H = 0.35, 1.50, 0.70   # armario aereo SOBRE a bancada
PIA_W, PIA_D, PIA_Z0 = 0.50, 0.46, 0.84         # cuba embutida (compacta p/ caber c/ cooktop)
COOK_W, COOK_D, COOK_Z0 = 0.46, 0.50, 0.90      # cooktop 4-bocas compacto embutido
BANCADA_MIN_DEPTH = 0.35                         # abaixo disso = sliver inútil, descarta
RGB_COUNTER = [176, 166, 150]
RGB_TORRE = [69, 90, 100]                       # cinza-escuro eletrodomestico
RGB_AEREO = [150, 140, 124]                     # bege-escuro (madeira)
RGB_GELADEIRA = [201, 203, 207]                 # inox claro
RGB_PIA = [183, 187, 191]                       # cuba inox
RGB_COOKTOP = [44, 44, 48]                      # vidro preto
DOOR_KINDS = {"interior_door", "interior_passage", "glazed_balcony"}
AREA_MIN = 0.035 / (PT_TO_M ** 2)               # area minima de uma peca (m2 -> PT2)


def _to_box(kind, shp, h_m, rgb, z0_m=0.0):
    x0, y0, x1, y1 = shp.bounds
    corners = [[round(px * PT_TO_IN, 2), round(py * PT_TO_IN, 2)]
               for px, py in list(shp.exterior.coords)[:-1]]
    return {"kind": kind, "x0": x0 * PT_TO_IN, "y0": y0 * PT_TO_IN,
            "x1": x1 * PT_TO_IN, "y1": y1 * PT_TO_IN, "corners": corners,
            "h_in": h_m * 39.3700787402, "z0_in": z0_m * 39.3700787402,
            "rgb": rgb, "label": kind, "ambiguous": False, "decorative": False}


def build_boxes(con, room_id):
    """Cozinha LINEAR (galley) sem sobreposicao. Devolve (boxes, out) no formato do
    place_layout (compativel com furnish_apartment)."""
    sm = build_spatial_model(con, room_id)
    cell = sm["_geom"]["cell"]
    circ = sm["_geom"]["circ"]
    circ_u = unary_union(circ) if circ else None
    win_zone = _window_zones(sm)
    minx, miny, maxx, maxy = cell.bounds
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

    door_in = []
    for o in con.get("openings", []):
        if (o.get("kind") or o.get("type")) in DOOR_KINDS:
            p = o.get("position") or o.get("center")
            if p:
                door_in.append((p[0] * PT_TO_IN, p[1] * PT_TO_IN))

    def near_door(shp):
        cx, cy = shp.centroid.x * PT_TO_IN, shp.centroid.y * PT_TO_IN
        return any(((cx - dx) ** 2 + (cy - dy) ** 2) ** 0.5 < 22 for dx, dy in door_in)

    items, placed = [], None

    def _shp_run(shp, orient):
        """along-interval (lo,hi) em PT do maior poligono util de shp; None se vazio."""
        if circ_u is not None:
            shp = shp.difference(circ_u)
        if placed is not None:
            shp = shp.difference(placed)
        if shp.is_empty:
            return None
        if shp.geom_type == "MultiPolygon":
            shp = max(shp.geoms, key=lambda g: g.area)
        if shp.geom_type != "Polygon" or shp.area < AREA_MIN:
            return None
        x0, y0, x1, y1 = shp.bounds
        return (y0, y1) if orient == "v" else (x0, x1)

    def clip(shp, carve=True):
        if circ_u is not None:
            shp = shp.difference(circ_u)
        if carve and placed is not None:
            shp = shp.difference(placed)
        if shp.is_empty:
            return None
        if shp.geom_type == "MultiPolygon":
            shp = max(shp.geoms, key=lambda g: g.area)
        return shp if (shp.geom_type == "Polygon" and shp.area >= AREA_MIN) else None

    def add(kind, shp, h_m, rgb, z0_m=0.0, mark=True):
        nonlocal placed
        items.append(_to_box(kind, shp, h_m, rgb, z0_m=z0_m))
        if mark:
            placed = shp if placed is None else placed.union(shp)

    def fb(ws, center, length_m, depth_m):
        return _fbox(ws["orient"], ws["face"], ws["sgn"], center, M(0.03),
                     M(length_m), M(depth_m)).intersection(cell)

    # escolhe paredes pelo RUN LIVRE real (parede ∩ cômodo − circulação), não pelo
    # comprimento bruto (m013 tem 2.57m mas só 0.83m livre; m011 2.10m é a boa).
    wruns = []
    for w in clean:
        ws = _wall_setup(sm, w["id"])
        if ws is None:
            continue
        strip = fb(ws, ws["along_c"], w["length_m"] + 0.3, COUNTER_DEPTH)
        run = _shp_run(strip, ws["orient"])
        if run:
            wruns.append((ws, run, (run[1] - run[0]) / M(1.0)))
    wruns.sort(key=lambda t: -t[2])
    if not wruns:
        return None, {"result": "NO_VALID_LAYOUT", "room_name": sm.get("room_name"),
                      "reason": "sem run livre p/ bancada"}

    # ---------------- parede PRINCIPAL: galley linear dentro do run livre ----------------
    ws, (f_lo, f_hi), run_m = wruns[0]
    cur = f_lo
    # geladeira numa ponta (só se o run comporta geladeira + bancada mínima)
    if run_m >= GEL_W + 0.45:
        gb = clip(fb(ws, cur + M(GEL_W / 2), GEL_W, GEL_D))
        if gb is not None and not near_door(gb):
            add("geladeira", gb, GEL_H, RGB_GELADEIRA)
            cur = cur + M(GEL_W)
    # torre na outra ponta só se sobra >=1.0m p/ bancada
    f_hi_b = f_hi
    if (f_hi - cur) >= M(1.0 + TORRE_W):
        tb = clip(fb(ws, f_hi - M(TORRE_W / 2), TORRE_W, TORRE_D))
        if tb is not None and not near_door(tb):
            add("torre", tb, TORRE_H, RGB_TORRE)
            f_hi_b = f_hi - M(TORRE_W)
    # bancada no meio do run
    b_len = (f_hi_b - cur) / M(1.0)
    if b_len >= 0.5:
        b_center = (cur + f_hi_b) / 2
        bb = clip(fb(ws, b_center, b_len, COUNTER_DEPTH))
        if bb is not None:
            add("bancada", bb, COUNTER_H, RGB_COUNTER)
            pb = clip(fb(ws, cur + M(0.30), PIA_W, PIA_D), carve=False)   # cuba numa ponta
            if pb is not None:
                add("pia", pb, 0.12, RGB_PIA, z0_m=PIA_Z0, mark=False)
            if b_len >= 1.0:                        # cooktop na OUTRA ponta (sem encostar na cuba)
                cb = clip(fb(ws, f_hi_b - M(0.28), COOK_W, COOK_D), carve=False)
                if cb is not None:
                    add("cooktop", cb, 0.08, RGB_COOKTOP, z0_m=COOK_Z0, mark=False)
            ab = fb(ws, b_center, b_len, AEREO_DEPTH)
            if win_zone is not None:
                ab = ab.difference(win_zone)
            if not ab.is_empty:
                if ab.geom_type == "MultiPolygon":
                    ab = max(ab.geoms, key=lambda g: g.area)
                if ab.geom_type == "Polygon" and ab.area >= (0.12 / PT_TO_M ** 2):
                    add("aereo", ab, AEREO_H, RGB_AEREO, z0_m=AEREO_Z0, mark=False)

    # ---------------- 2a parede limpa (L): bancada/cooktop extra carved ----------------
    for ws2, (g_lo, g_hi), run2 in wruns[1:2]:
        g2 = clip(fb(ws2, (g_lo + g_hi) / 2, (g_hi - g_lo) / M(1.0), COUNTER_DEPTH))
        if g2 is not None:
            gx0, gy0, gx1, gy1 = g2.bounds
            if min(gx1 - gx0, gy1 - gy0) / M(1.0) < BANCADA_MIN_DEPTH:
                continue                            # sliver fino (16cm) = inútil, descarta
            add("bancada", g2, COUNTER_H, RGB_COUNTER)
            if "cooktop" not in [it["kind"] for it in items] and run2 >= 0.6:
                cb2 = clip(fb(ws2, (g_lo + g_hi) / 2, COOK_W, COOK_D), carve=False)
                if cb2 is not None:
                    add("cooktop", cb2, 0.08, RGB_COOKTOP, z0_m=COOK_Z0, mark=False)

    if not items:
        return None, {"result": "NO_VALID_LAYOUT", "room_name": sm.get("room_name"),
                      "reason": "nada coube dentro do comodo"}
    kinds = [it["kind"] for it in items]
    return items, {"result": "OK", "room_name": sm.get("room_name"), "n_items": len(items),
                   "kinds": sorted(set(kinds)), "n_bancadas": kinds.count("bancada")}


if __name__ == "__main__":
    import json
    con = json.loads(Path("fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json")
                     .read_text("utf-8"))
    boxes, out = build_boxes(con, "r004")
    print(f"COZINHA r004 ('{out.get('room_name')}') | {out['result']} | "
          f"{len(boxes) if boxes else 0} pecas | {out.get('kinds')}")
