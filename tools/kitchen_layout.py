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


M2IN = 39.3700787402
# cores (FORMA antes de material — tem que ler como cozinha mesmo chapado em cinza/branco)
_KC = {"corpo": [224, 225, 229], "porta": [235, 236, 240], "puxador": [58, 60, 64],
       "tampo": [122, 122, 128], "soculo": [66, 66, 70], "inox": [196, 199, 205],
       "vidro": [28, 28, 32], "boca": [54, 54, 58], "cuba": [176, 180, 187],
       "torneira": [150, 153, 160]}
# nome de MÓDULO planejado (grupo selecionável sozinho no SKP); countertop é separado do base
_MODNAME = {"geladeira": "fridge", "pia": "sink_module", "cooktop": "cooktop_module",
            "aereo": "upper_cabinet_01", "torre": "tall_cabinet", "bancada": "base_cabinet_01"}


def _kp(kind, x0, y0, x1, y1, z0_m, z1_m, rgb):
    """parte: x/y em POINTS (->inches), z em METROS. (frente detalhada)."""
    x0, x1 = min(x0, x1), max(x0, x1)
    y0, y1 = min(y0, y1), max(y0, y1)
    return {"kind": kind, "x0": x0 * PT_TO_IN, "y0": y0 * PT_TO_IN, "x1": x1 * PT_TO_IN, "y1": y1 * PT_TO_IN,
            "corners": [[round(x0 * PT_TO_IN, 2), round(y0 * PT_TO_IN, 2)], [round(x1 * PT_TO_IN, 2), round(y0 * PT_TO_IN, 2)],
                        [round(x1 * PT_TO_IN, 2), round(y1 * PT_TO_IN, 2)], [round(x0 * PT_TO_IN, 2), round(y1 * PT_TO_IN, 2)]],
            "h_in": round((z1_m - z0_m) * M2IN, 2), "z0_in": round(z0_m * M2IN, 2),
            "rgb": rgb, "label": kind, "ambiguous": False, "decorative": False}


def _kmod(kind, shp, h_m, rgb, z0_m, ws):
    """Geometria DETALHADA de um elemento de cozinha (não cubo). Frente = lado do cômodo
    (via ws). Cai pra caixa única se for um kind sem detalhe."""
    x0, y0, x1, y1 = shp.bounds
    vert = bool(ws and ws["orient"] == "v")
    sgn = (ws["sgn"] if ws else 1)
    s = 1 if sgn > 0 else -1
    if vert:
        front, back = (x1 if s > 0 else x0), (x0 if s > 0 else x1)
        a0, a1 = y0, y1
    else:
        front, back = (y1 if s > 0 else y0), (y0 if s > 0 else y1)
        a0, a1 = x0, x1
    W = a1 - a0
    t = M(0.018)

    # cada PAPEL vira um kind próprio (kc_<k>) -> material SU/V-Ray próprio. SEM isto, o
    # cache de material por kind (place_layout pl_material) pinta o módulo todo com a cor
    # da 1ª peça (sóculo escuro) e o puxador some. Papel distinto = contraste = lê planejado.
    def body(za, zb, c, inset_front=0.0, inset_side=0.0, k="corpo"):
        f = front - s * M(inset_front)
        sa0, sa1 = a0 + M(inset_side), a1 - M(inset_side)
        return _kp(f"kc_{k}", min(f, back), sa0, max(f, back), sa1, za, zb, c) if vert \
            else _kp(f"kc_{k}", sa0, min(f, back), sa1, max(f, back), za, zb, c)

    def panel(sa0, sa1, za, zb, c, off=0.0, thick=None, k="porta"):
        f1 = front - s * M(off)
        f0 = f1 - s * (thick or t)
        return _kp(f"kc_{k}", min(f0, f1), sa0, max(f0, f1), za, zb, c) if vert \
            else _kp(f"kc_{k}", sa0, min(f0, f1), sa1, max(f0, f1), za, zb, c)

    out = []
    if kind == "geladeira":
        out.append(body(z0_m, z0_m + h_m - 0.05, _KC["corpo"], inset_side=0.004, k="corpo"))   # corpo + respiro topo
        split = z0_m + h_m * 0.66
        out.append(panel(a0 + M(0.02), a1 - M(0.02), split + 0.01, z0_m + h_m - 0.06, _KC["inox"], k="inox"))  # porta sup
        out.append(panel(a0 + M(0.02), a1 - M(0.02), z0_m + 0.04, split - 0.01, _KC["inox"], k="inox"))        # porta inf
        hp = a1 - M(0.075)
        out.append(panel(hp, hp + M(0.035), split + 0.06, z0_m + h_m - 0.14, _KC["puxador"], off=0.03, k="puxador"))  # puxador sup (barra vertical)
        out.append(panel(hp, hp + M(0.035), z0_m + 0.12, split - 0.06, _KC["puxador"], off=0.03, k="puxador"))        # puxador inf
    elif kind == "bancada":
        tt, sk = 0.04, 0.10
        out.append(body(z0_m, z0_m + sk, _KC["soculo"], inset_front=0.06, k="soculo"))   # sóculo recuado 6cm (toe-kick lê)
        out.append(body(z0_m + sk, z0_m + h_m - tt, _KC["corpo"], k="corpo"))            # gabinete
        nmod = max(1, int(round(W / M(0.50))))
        mw = W / nmod
        for i in range(nmod):                                                          # portas/gavetas + puxador BARRA
            ma0, ma1 = a0 + i * mw + M(0.01), a0 + (i + 1) * mw - M(0.01)
            out.append(panel(ma0, ma1, z0_m + sk + 0.02, z0_m + h_m - tt - 0.02, _KC["porta"], k="porta"))
            out.append(panel(ma0 + M(0.05), ma1 - M(0.05), z0_m + h_m - tt - 0.07, z0_m + h_m - tt - 0.035,
                             _KC["puxador"], off=0.028, k="puxador"))                    # barra horizontal saliente (lê)
        out.append(body(z0_m + h_m - tt, z0_m + h_m, _KC["tampo"], inset_front=-0.025, k="tampo"))  # tampo proud (overhang pedra)
    elif kind == "cooktop":
        out.append(body(z0_m, z0_m + 0.015, _KC["vidro"], inset_side=0.015, k="vidro"))  # vidro preto fino
        cax = [a0 + W * 0.3, a0 + W * 0.7]
        dca = M(0.07)
        dep0, dep1 = (front - s * M(0.10)), (front - s * M(0.34))                       # 2 fileiras de boca
        for ca in cax:
            for dd in (dep0, dep1):
                if vert:   # profundidade=x, largura=y
                    out.append(_kp("kc_boca", dd - dca, ca - dca, dd + dca, ca + dca, z0_m + 0.014, z0_m + 0.022, _KC["boca"]))
                else:      # profundidade=y, largura=x
                    out.append(_kp("kc_boca", ca - dca, dd - dca, ca + dca, dd + dca, z0_m + 0.014, z0_m + 0.022, _KC["boca"]))
    elif kind == "pia":
        out.append(body(z0_m, z0_m + 0.02, _KC["inox"], inset_side=0.01, k="inox"))     # borda da cuba
        out.append(body(z0_m - 0.12, z0_m, _KC["cuba"], inset_front=0.06, inset_side=0.07, k="cuba"))  # bojo recuado
        ta = (a0 + a1) / 2
        out.append(panel(ta - M(0.02), ta + M(0.02), z0_m + 0.02, z0_m + 0.22, _KC["torneira"], off=0.06, thick=M(0.035), k="torneira"))  # torneira
    elif kind == "aereo":
        out.append(body(z0_m, z0_m + h_m, _KC["corpo"], k="corpo"))
        nmod = max(1, int(round(W / M(0.45))))
        mw = W / nmod
        for i in range(nmod):
            ma0, ma1 = a0 + i * mw + M(0.01), a0 + (i + 1) * mw - M(0.01)
            out.append(panel(ma0, ma1, z0_m + 0.02, z0_m + h_m - 0.02, _KC["porta"], k="porta"))
            out.append(panel(ma0 + M(0.05), ma1 - M(0.05), z0_m + 0.03, z0_m + 0.06, _KC["puxador"], off=0.028, k="puxador"))  # barra embaixo
    else:
        out.append(_kp(kind, x0, y0, x1, y1, z0_m, z0_m + h_m, rgb))                    # fallback caixa
    mname = _MODNAME.get(kind, kind)
    for p in out:
        p["module"] = mname   # sub-peças = 1 grupo top-level selecionável (nome planejado)
    if kind == "bancada" and out:
        out[-1]["module"] = "countertop"   # o tampo (último append) é módulo PRÓPRIO (separa do base)
    return out


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

    def add(kind, shp, h_m, rgb, z0_m=0.0, mark=True, ws=None):
        nonlocal placed
        items.extend(_kmod(kind, shp, h_m, rgb, z0_m, ws))   # geometria DETALHADA (não cubo)
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
            add("geladeira", gb, GEL_H, RGB_GELADEIRA, ws=ws)
            cur = cur + M(GEL_W)
    # torre na outra ponta só se sobra >=1.0m p/ bancada
    f_hi_b = f_hi
    if (f_hi - cur) >= M(1.0 + TORRE_W):
        tb = clip(fb(ws, f_hi - M(TORRE_W / 2), TORRE_W, TORRE_D))
        if tb is not None and not near_door(tb):
            add("torre", tb, TORRE_H, RGB_TORRE, ws=ws)
            f_hi_b = f_hi - M(TORRE_W)
    # bancada no meio do run
    b_len = (f_hi_b - cur) / M(1.0)
    if b_len >= 0.5:
        b_center = (cur + f_hi_b) / 2
        bb = clip(fb(ws, b_center, b_len, COUNTER_DEPTH))
        if bb is not None:
            add("bancada", bb, COUNTER_H, RGB_COUNTER, ws=ws)
            pb = clip(fb(ws, cur + M(0.30), PIA_W, PIA_D), carve=False)   # cuba numa ponta
            if pb is not None:
                add("pia", pb, 0.12, RGB_PIA, z0_m=PIA_Z0, mark=False, ws=ws)
            if b_len >= 1.0:                        # cooktop na OUTRA ponta (sem encostar na cuba)
                cb = clip(fb(ws, f_hi_b - M(0.28), COOK_W, COOK_D), carve=False)
                if cb is not None:
                    add("cooktop", cb, 0.08, RGB_COOKTOP, z0_m=COOK_Z0, mark=False, ws=ws)
            ab = fb(ws, b_center, b_len, AEREO_DEPTH)
            if win_zone is not None:
                ab = ab.difference(win_zone)
            if not ab.is_empty:
                if ab.geom_type == "MultiPolygon":
                    ab = max(ab.geoms, key=lambda g: g.area)
                if ab.geom_type == "Polygon" and ab.area >= (0.12 / PT_TO_M ** 2):
                    add("aereo", ab, AEREO_H, RGB_AEREO, z0_m=AEREO_Z0, mark=False, ws=ws)

    # ---------------- 2a parede limpa (L): bancada/cooktop extra carved ----------------
    for ws2, (g_lo, g_hi), run2 in wruns[1:2]:
        g2 = clip(fb(ws2, (g_lo + g_hi) / 2, (g_hi - g_lo) / M(1.0), COUNTER_DEPTH))
        if g2 is not None:
            gx0, gy0, gx1, gy1 = g2.bounds
            if min(gx1 - gx0, gy1 - gy0) / M(1.0) < BANCADA_MIN_DEPTH:
                continue                            # sliver fino (16cm) = inútil, descarta
            add("bancada", g2, COUNTER_H, RGB_COUNTER, ws=ws2)
            if "cooktop" not in [it["kind"] for it in items] and run2 >= 0.6:
                cb2 = clip(fb(ws2, (g_lo + g_hi) / 2, COOK_W, COOK_D), carve=False)
                if cb2 is not None:
                    add("cooktop", cb2, 0.08, RGB_COOKTOP, z0_m=COOK_Z0, mark=False, ws=ws2)

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
