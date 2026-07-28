"""kitchen_layout.py — brain de COZINHA LINEAR (galley). A parede principal é
SEGMENTADA sem sobreposicao: geladeira numa ponta -> bancada no meio (pia + cooktop
EMBUTIDOS) -> torre/coluna na outra ponta; armario aereo SO sobre a bancada. 2a parede
limpa (L) recebe bancada extra carved. Sem movel em cima de movel
(tools/furniture_overlap_gate). Pratico: bancada continua, fluxo geladeira->pia->cooktop.
Placeholder boxes; plugga em furnish_apartment via build_boxes. NAO usa 3D Warehouse.
"""
from __future__ import annotations

import math
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
AEREO_DEPTH, AEREO_Z0, AEREO_H = 0.33, 1.50, 0.60   # clearance bancada->aéreo = 60cm (ergonomia 50-60)
PIA_W, PIA_D, PIA_Z0 = 0.50, 0.46, 0.90         # cuba UNDERMOUNT: abertura escura lê de cima; bojo recua p/ baixo
COOK_W, COOK_D, COOK_Z0 = 0.46, 0.50, 0.898     # cooktop: vidro FINO proud <=8mm acima do plano do tampo (0.90)
TOE_KICK, TAMPO_THK = 0.12, 0.03                # sóculo recuado 12cm (10-15) / tampo fino 3cm
BANCADA_MIN_DEPTH = 0.35                         # abaixo disso = sliver inútil, descarta
RGB_COUNTER = [30, 29, 32]                      # porcelanato preto-dourado MATE (DesignDirective BLACK_WOOD_GOLD)
RGB_TORRE = [38, 39, 40]                        # torre grafite fosco (matte_black_cabinetry)
RGB_AEREO = [108, 80, 58]                       # nogueira quente (acento anti-caverna)
RGB_GELADEIRA = [36, 36, 38]                    # preto fosco antidigital (D8 — NUNCA inox claro)
RGB_PIA = [33, 32, 34]                          # cuba composto preto satin (D5)
RGB_COOKTOP = [22, 22, 26]                      # vitrocerâmico preto (D1)
DOOR_KINDS = {"interior_door", "interior_passage", "glazed_balcony"}
# pia da cozinha = ponto HIDRÁULICO fixo do PDF (parede OESTE/esquerda). NÃO mover de
# parede sem reforma hidráulica. Validado por tools/kitchen_validation.py.
KITCHEN_SINK_ANCHOR = "KITCHEN_SINK_ANCHOR"
KITCHEN_SINK_SIDE = "W"
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
# cores (FORMA antes de material — tem que ler como cozinha mesmo chapado)
# PALETA BLACK_WOOD_GOLD moody premium (DesignDirectiveSpec 2026-07-27, ancorada em
# references/tokens/{matte_black_cabinetry,coordinated_medium_dark_wood_base,
# dark_stainless_appliance,discreet_bronze_hardware} + KITCHEN_DECISIONS D1-D9):
# base=grafite fosco · aéreos=nogueira (acento anti-caverna) · tampo/backsplash=
# porcelanato preto-dourado mate · eletros=preto fosco · bronze SÓ na torneira (D4).
_KC = {
    "corpo": [38, 39, 40], "porta": [38, 39, 40], "gaveta": [41, 42, 43],          # base GRAFITE fosco (nunca [0,0,0] chapado = caverna)
    "corpo_sup": [108, 80, 58], "porta_sup": [112, 84, 61],                        # aéreo NOGUEIRA quente até o teto — o anti-caverna do conjunto
    "filler": [38, 39, 40],                                                         # painel lateral da torre = mesmo grafite (coluna coesa)
    "tampo": [30, 29, 32], "backsplash": [32, 30, 33],                             # porcelanato preto-dourado MATE (veio sutil = textura V-Ray)
    "niche_wood": [126, 82, 48],                                                   # nicho quente (hot_tower_niche)
    "soculo": [24, 24, 24],                                                        # sóculo preto profundo (shadow line)
    "inox": [82, 84, 84],                                                          # dark stainless satin (não inox claro)
    "geladeira": [36, 36, 38],                                                     # preto fosco antidigital, pega embutida (D8)
    "vidro": [22, 22, 26], "boca": [55, 55, 58], "anel": [120, 120, 124],          # vitro preto + disco + anel serigrafado
    "cuba": [33, 32, 34], "torneira": [28, 28, 30],                                # cuba composto preta / torneira preto fosco PVD
    "bronze": [171, 119, 63],                                                      # o ÚNICO ponto de ouro do ambiente (D4)
    "puxador": [24, 24, 24],                                                       # gola/cava preta — sem barra, sem bronze no hardware
    "led": [255, 250, 232],                                                        # fita LED 2700K sob o aéreo (highlight pontual permitido)
    "board": [126, 82, 48], "vaso_d": [70, 68, 66], "tempero": [96, 94, 90],       # tábua quente + cerâmica grafite (zero objeto branco)
    "ralo": [50, 50, 53],                                                          # ralo/válvula da cuba
    "coifa": [38, 39, 40],                                                         # coifa slim preta — coadjuvante (D3)
}
# nome de MÓDULO planejado (grupo selecionável sozinho no SKP); countertop é separado do base
_MODNAME = {"geladeira": "fridge", "pia": "sink_module", "cooktop": "cooktop_module",
            "aereo": "upper_cabinet_01", "aereo_fridge": "upper_cabinet_02",
            "torre": "tall_cabinet", "bancada": "base_cabinet_01", "coifa": "hood"}


def _kp(kind, x0, y0, x1, y1, z0_m, z1_m, rgb):
    """parte: x/y em POINTS (->inches), z em METROS. (frente detalhada)."""
    x0, x1 = min(x0, x1), max(x0, x1)
    y0, y1 = min(y0, y1), max(y0, y1)
    return {"kind": kind, "x0": x0 * PT_TO_IN, "y0": y0 * PT_TO_IN, "x1": x1 * PT_TO_IN, "y1": y1 * PT_TO_IN,
            "corners": [[round(x0 * PT_TO_IN, 2), round(y0 * PT_TO_IN, 2)], [round(x1 * PT_TO_IN, 2), round(y0 * PT_TO_IN, 2)],
                        [round(x1 * PT_TO_IN, 2), round(y1 * PT_TO_IN, 2)], [round(x0 * PT_TO_IN, 2), round(y1 * PT_TO_IN, 2)]],
            "h_in": round((z1_m - z0_m) * M2IN, 2), "z0_in": round(z0_m * M2IN, 2),
            "rgb": rgb, "label": kind, "ambiguous": False, "decorative": False}


def _koct(kind, cx, cy, r, z0_m, z1_m, rgb):
    """Disco OCTOGONAL flat (x/y em POINTS): leitura circular low-poly sem custo de
    malha — boca/anel de cooktop (diretriz: 'discos, não caixotes')."""
    pts = [(cx + r * math.cos(a), cy + r * math.sin(a))
           for a in (math.pi / 8 + i * math.pi / 4 for i in range(8))]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return {"kind": kind, "x0": min(xs) * PT_TO_IN, "y0": min(ys) * PT_TO_IN,
            "x1": max(xs) * PT_TO_IN, "y1": max(ys) * PT_TO_IN,
            "corners": [[round(px * PT_TO_IN, 2), round(py * PT_TO_IN, 2)] for px, py in pts],
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
        return _kp(f"kc_{k}", min(f0, f1), sa0, max(f0, f1), sa1, za, zb, c) if vert \
            else _kp(f"kc_{k}", sa0, min(f0, f1), sa1, max(f0, f1), za, zb, c)

    def backpanel(sa0, sa1, za, zb, c, thick=0.025):
        """painel fino contra a PAREDE (backsplash/rodabanca)."""
        f0, f1 = back, back + s * M(thick)
        return _kp("kc_backsplash", min(f0, f1), sa0, max(f0, f1), sa1, za, zb, c) if vert \
            else _kp("kc_backsplash", sa0, min(f0, f1), sa1, max(f0, f1), za, zb, c)

    out = []
    if kind == "geladeira":
        out.append(body(z0_m + 0.03, z0_m + h_m - 0.06, _KC["geladeira"], inset_side=0.014, k="geladeira"))   # corpo INOX + respiro lateral/superior
        out.append(panel(a0 + M(0.02), a1 - M(0.02), z0_m + h_m - 0.055, z0_m + h_m - 0.035, _KC["soculo"], off=0.0, k="soculo"))  # reveal de respiro no topo
        split = z0_m + h_m * 0.62                                                       # freezer no topo (~38%)
        out.append(panel(a0 + M(0.018), a1 - M(0.018), split + 0.022, z0_m + h_m - 0.055, _KC["geladeira"], k="geladeira"))  # porta freezer
        out.append(panel(a0 + M(0.018), a1 - M(0.018), z0_m + 0.05, split - 0.022, _KC["geladeira"], k="geladeira"))         # porta geladeira
        out.append(panel(a0 + M(0.018), a1 - M(0.018), split - 0.02, split + 0.02, _KC["soculo"], off=0.002, k="soculo"))    # REVEAL escuro da divisão freezer/fridge
        hp = a1 - M(0.10)                                                               # puxadores = BARRAS VERTICAIS longas (cava)
        out.append(panel(hp, hp + M(0.04), split + 0.06, z0_m + h_m - 0.10, _KC["puxador"], off=0.03, k="puxador"))          # freezer
        out.append(panel(hp, hp + M(0.04), z0_m + 0.12, split - 0.06, _KC["puxador"], off=0.03, k="puxador"))                # geladeira (barra longa)
    elif kind == "bancada":
        tt, sk = TAMPO_THK, TOE_KICK                                                   # tampo fino + sóculo (constantes ergonômicas)
        out.append(body(z0_m, z0_m + sk, _KC["soculo"], inset_front=0.08, k="soculo"))   # sóculo recuado 8cm (toe-kick lê)
        out.append(body(z0_m + sk, z0_m + h_m - tt, _KC["corpo"], k="corpo"))            # gabinete (carcaça)
        zd0, zd1 = z0_m + sk + 0.02, z0_m + h_m - tt - 0.02
        nmod = max(1, int(round(W / M(0.50))))
        mw = W / nmod
        for i in range(nmod):
            ma0, ma1 = a0 + i * mw + M(0.018), a0 + (i + 1) * mw - M(0.018)   # reveal de junta planejada (shadow gap)
            if i == 0 and nmod >= 2:                # 1º módulo = GAVETEIRO (3 gavetas) -> lê marcenaria
                for d in range(3):
                    dz0 = zd0 + d * (zd1 - zd0) / 3 + 0.006
                    dz1 = zd0 + (d + 1) * (zd1 - zd0) / 3 - 0.006
                    out.append(panel(ma0, ma1, dz0, dz1, _KC["gaveta"], k="gaveta"))
                    out.append(panel(ma0 + M(0.06), ma1 - M(0.06), dz1 - 0.034, dz1 - 0.012, _KC["puxador"], off=0.026, k="puxador"))
            else:                                   # porta + barra de puxar no topo
                out.append(panel(ma0, ma1, zd0, zd1, _KC["porta"], k="porta"))
                out.append(panel(ma0 + M(0.05), ma1 - M(0.05), zd1 - 0.07, zd1 - 0.035, _KC["puxador"], off=0.028, k="puxador"))
        out.append(body(z0_m + h_m - tt, z0_m + h_m, _KC["tampo"], inset_front=-0.03, k="tampo"))  # tampo CONTÍNUO proud (pedra)
        out.append(backpanel(a0 + M(0.004), a1 - M(0.004), z0_m + h_m, z0_m + h_m + 0.50, _KC["backsplash"], thick=0.04))  # backsplash (até o aéreo)
    elif kind == "cooktop":
        # VITROCERÂMICO (D1): vidro FINO (7mm) proud <=8mm do plano do tampo; o
        # inset maior que o rasgo faz o shadow gap perimetral (vidro != pedra).
        out.append(body(z0_m, z0_m + 0.007, _KC["vidro"], inset_front=0.012, inset_side=0.012, k="vidro"))
        cax = [a0 + W * 0.30, a0 + W * 0.70]
        rr = M(0.095)                                                               # zonas r~9.5cm (diretriz 9-11)
        dep0, dep1 = (front - s * M(0.14)), (front - s * M(0.36))                   # grid 2x2
        zt = z0_m + 0.007
        for ca in cax:
            for dd in (dep0, dep1):
                cx, cy = (dd, ca) if vert else (ca, dd)
                out.append(_koct("kc_anel", cx, cy, rr + M(0.009), zt, zt + 0.0006, _KC["anel"]))   # anel serigrafado fino
                out.append(_koct("kc_boca", cx, cy, rr, zt + 0.0004, zt + 0.0015, _KC["boca"]))     # disco flat (sem volume)
        fb0, fb1 = front - s * M(0.045), front - s * M(0.075)                       # faixa de controle na borda frontal
        cm0, cm1 = (a0 + a1) / 2 - M(0.10), (a0 + a1) / 2 + M(0.10)
        if vert:
            out.append(_kp("kc_anel", min(fb0, fb1), cm0, max(fb0, fb1), cm1, zt, zt + 0.0008, _KC["anel"]))
        else:
            out.append(_kp("kc_anel", cm0, min(fb0, fb1), cm1, max(fb0, fb1), zt, zt + 0.0008, _KC["anel"]))
    elif kind == "pia":
        # UNDERMOUNT sem aro (D5): a leitura de cima é a ABERTURA ESCURA na pedra —
        # placa da cuba 2mm acima do plano do tampo; a pedra faz a borda, não inox.
        out.append(body(z0_m - 0.004, z0_m + 0.002, _KC["cuba"], inset_front=0.055, inset_side=0.06, k="cuba"))
        out.append(body(z0_m - 0.20, z0_m - 0.004, _KC["cuba"], inset_front=0.06, inset_side=0.065, k="cuba"))   # bojo FUNDO (20cm, sombra interna)
        out.append(body(z0_m - 0.205, z0_m - 0.19, _KC["cuba"], inset_front=0.05, inset_side=0.055, k="cuba"))   # fundo visível
        out.append(body(z0_m - 0.205, z0_m - 0.193, _KC["ralo"], inset_front=0.19, inset_side=0.205, k="ralo"))  # RALO no fundo do bojo
        # torneira em L preto fosco PVD, ATRÁS da cuba; aro bronze = o ÚNICO ouro (D4)
        ta = (a0 + a1) / 2
        post_off = PIA_D - 0.075                                                    # montante ~7.5cm da parede
        out.append(panel(ta - M(0.015), ta + M(0.015), z0_m + 0.002, z0_m + 0.30, _KC["torneira"], off=post_off, thick=M(0.03), k="torneira"))  # montante vertical 30cm
        sp1 = front - s * M(post_off)
        sp0 = front - s * M(post_off - 0.20)                                        # bica horizontal 20cm sobre a cuba
        if vert:
            out.append(_kp("kc_torneira", min(sp0, sp1), ta - M(0.013), max(sp0, sp1), ta + M(0.013), z0_m + 0.27, z0_m + 0.30, _KC["torneira"]))
        else:
            out.append(_kp("kc_torneira", ta - M(0.013), min(sp0, sp1), ta + M(0.013), max(sp0, sp1), z0_m + 0.27, z0_m + 0.30, _KC["torneira"]))
        out.append(panel(ta - M(0.018), ta + M(0.018), z0_m + 0.135, z0_m + 0.165, _KC["bronze"], off=post_off - 0.002, thick=M(0.034), k="bronze"))  # aro bronze no montante
    elif kind in ("aereo", "aereo_fridge"):
        out.append(body(z0_m + 0.04, z0_m + h_m, _KC["corpo_sup"], k="corpo_sup"))     # carcaça OFF-WHITE
        out.append(body(z0_m + 0.018, z0_m + 0.04, _KC["soculo"], inset_front=0.04, k="soculo"))  # valance grafite recuada
        out.append(panel(a0 + M(0.02), a1 - M(0.02), z0_m + 0.0, z0_m + 0.022, _KC["led"], off=0.006, thick=M(0.025), k="led"))  # FITA LED quente (mais legível)
        nmod = max(2, int(round(W / M(0.60))))                                         # portas MAIORES (premium, menos blocão)
        mw = W / nmod
        niche = (nmod - 1) if (kind == "aereo" and nmod >= 3) else -1                  # 1 bay ABERTA = nicho de ASSINATURA
        for i in range(nmod):
            ma0, ma1 = a0 + i * mw + M(0.022), a0 + (i + 1) * mw - M(0.022)            # reveal de junta planejada (shadow gap)
            if i == niche:
                # NICHO DE ASSINATURA: fundo + prateleira em MADEIRA -> quebra o blocão off-white
                out.append(panel(ma0, ma1, z0_m + 0.04, z0_m + h_m - 0.03, _KC["niche_wood"], off=AEREO_DEPTH - 0.025, thick=M(0.02), k="niche_wood"))  # fundo madeira
                out.append(panel(ma0, ma1, z0_m + h_m * 0.5 - 0.012, z0_m + h_m * 0.5 + 0.012, _KC["niche_wood"], off=0.04, k="niche_wood"))  # prateleira madeira
            else:
                out.append(panel(ma0, ma1, z0_m + 0.06, z0_m + h_m - 0.018, _KC["porta_sup"], k="porta_sup"))
                # GOLA = sombra FINA recuada no rodapé da porta (handle-less, não domina)
                out.append(panel(ma0 + M(0.02), ma1 - M(0.02), z0_m + 0.046, z0_m + 0.056, _KC["torneira"], off=0.0, thick=M(0.01), k="gola"))
    elif kind == "coifa":
        if h_m <= 0.20:                                                                # coifa SLIM under-cabinet preta (D3) — coadjuvante
            out.append(body(z0_m, z0_m + h_m, _KC["coifa"], inset_side=0.008, inset_front=0.012, k="coifa"))
            out.append(body(z0_m, z0_m + h_m * 0.45, _KC["vidro"], inset_front=0.05, inset_side=0.07, k="vidro"))     # grelha de sucção escura embaixo
        else:
            out.append(body(z0_m, z0_m + 0.16, _KC["coifa"], k="coifa"))               # corpo de captura preto fosco
            out.append(body(z0_m + 0.16, z0_m + h_m, _KC["coifa"], inset_front=0.27, inset_side=0.13, k="coifa"))  # chaminé
    else:
        out.append(_kp(kind, x0, y0, x1, y1, z0_m, z0_m + h_m, rgb))                    # fallback caixa
    mname = _MODNAME.get(kind, kind)
    for p in out:
        p["module"] = mname   # sub-peças = 1 grupo top-level selecionável (nome planejado)
        if p["kind"] == "kc_tampo":
            p["module"] = "countertop"     # tampo = módulo próprio (separa do base)
        elif p["kind"] == "kc_backsplash":
            p["module"] = "backsplash"     # backsplash = módulo próprio
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

    # ============ ANCHOR HIDRÁULICO DA PIA (PDF) ============
    # O PDF (planta de vendas) mostra a cuba na parede OESTE (esquerda) da cozinha,
    # sobre a bancada vertical hidráulica. O consensus NÃO traz símbolo hidráulico NEM
    # o segmento dessa parede (extração faltou o muro a x=minx), então ancoramos a
    # cozinha na BORDA OESTE do polígono do cômodo (minx). A pia é PONTO FIXO: não muda
    # de parede sem flag de reforma hidráulica. Geladeira/cooktop/armários giram em torno.
    minx, miny, maxx, maxy = cell.bounds
    wt = float(sm["_geom"]["con"]["wall_thickness_pts"])
    ws = {"id": KITCHEN_SINK_ANCHOR, "orient": "v", "sgn": 1, "face": minx + wt / 2,
          "along_c": (miny + maxy) / 2, "along_lo": miny, "along_hi": maxy,
          "depth": maxx - minx}
    strip = fb(ws, ws["along_c"], (maxy - miny) / M(1.0) + 0.3, COUNTER_DEPTH)
    run = _shp_run(strip, "v")
    if run is None:
        return None, {"result": "NO_VALID_LAYOUT", "room_name": sm.get("room_name"),
                      "reason": "parede oeste (pia) sem run livre"}
    f_lo, f_hi = run
    run_m = (f_hi - f_lo) / M(1.0)

    # Geladeira na ponta SUPERIOR (alto y) — a INFERIOR tem porta (giro entra na cozinha),
    # geladeira funda (0.66) encostaria no giro. PIA logo abaixo dela = upper-middle do PDF.
    g_end = None
    gel_c = None
    for cand, tag in ((f_hi - M(GEL_W / 2), "hi"), (f_lo + M(GEL_W / 2), "lo")):
        if run_m < GEL_W + 0.6:
            break
        gb_full = fb(ws, cand, GEL_W, GEL_D)                 # box CHEIO (geladeira não pode ser recortada pela porta)
        if (not gb_full.is_empty and cell.buffer(2).contains(gb_full)
                and (circ_u is None or gb_full.intersection(circ_u).area < AREA_MIN)
                and not near_door(gb_full)):
            add("geladeira", gb_full, GEL_H, RGB_GELADEIRA, ws=ws)
            g_end = tag
            gel_c = cand
            break
    b_lo = f_lo + (M(GEL_W) if g_end == "lo" else 0.0)
    b_hi = f_hi - (M(GEL_W) if g_end == "hi" else 0.0)

    # bancada CONTÍNUA na parede oeste (resto do run)
    b_len = (b_hi - b_lo) / M(1.0)
    if b_len >= 0.5:
        b_center = (b_lo + b_hi) / 2
        bb = clip(fb(ws, b_center, b_len, COUNTER_DEPTH))
        if bb is not None:
            add("bancada", bb, COUNTER_H, RGB_COUNTER, ws=ws)
            # PIA no ANCHOR: upper-middle (logo abaixo da geladeira no topo), como no PDF
            sink_c = (b_hi - M(0.35)) if g_end != "lo" else (b_lo + M(0.35))
            pb = clip(fb(ws, sink_c, PIA_W, PIA_D), carve=False)
            if pb is not None:
                add("pia", pb, 0.12, RGB_PIA, z0_m=PIA_Z0, mark=False, ws=ws)
            # cooktop EMBUTIDO na bancada, metade inferior (longe do ponto da pia)
            cook_c = None
            if b_len >= 1.0:
                cook_c = (b_lo + M(0.32)) if g_end != "lo" else (b_hi - M(0.32))
                cb = clip(fb(ws, cook_c, COOK_W, COOK_D), carve=False)
                if cb is not None:
                    add("cooktop", cb, 0.08, RGB_COOKTOP, z0_m=COOK_Z0, mark=False, ws=ws)
            # aéreo CONTÍNUO off-white sobre a bancada (evita janela)
            ab = fb(ws, b_center, b_len, AEREO_DEPTH)
            if win_zone is not None:
                ab = ab.difference(win_zone)
            if not ab.is_empty:
                if ab.geom_type == "MultiPolygon":
                    ab = max(ab.geoms, key=lambda g: g.area)
                if ab.geom_type == "Polygon" and ab.area >= (0.12 / PT_TO_M ** 2):
                    add("aereo", ab, AEREO_H, RGB_AEREO, z0_m=AEREO_Z0, mark=False, ws=ws)
            # COIFA SLIM integrada sob o aéreo, sobre o cooktop (depurador embutido)
            if cook_c is not None:
                hb = clip(fb(ws, cook_c, COOK_W + 0.06, AEREO_DEPTH - 0.01), carve=False)   # depurador embutido off-white + grelha
                if hb is not None:
                    add("coifa", hb, 0.055, RGB_TORRE, z0_m=AEREO_Z0 - 0.055, mark=False, ws=ws)
            # DECORAÇÃO funcional MÍNIMA na bancada (poucas coisas, sem bagunça) — sobre o tampo
            dec_c = (b_lo + b_hi) / 2
            db = clip(fb(ws, dec_c - M(0.12), 0.32, 0.22), carve=False)
            if db is not None:
                add("decor_board", db, 0.02, _KC["board"], z0_m=COUNTER_H, mark=False, ws=ws)   # tábua de corte
            vb = fb(ws, dec_c + M(0.20), 0.13, 0.13).intersection(cell)   # direto (footprint pequeno cai no AREA_MIN do clip)
            if not vb.is_empty:
                if vb.geom_type == "MultiPolygon":
                    vb = max(vb.geoms, key=lambda g: g.area)
                add("decor_vaso", vb, 0.17, _KC["vaso_d"], z0_m=COUNTER_H, mark=False, ws=ws)    # vasinho de tempero

    # ARMÁRIO sobre a geladeira -> alinha o TOPO com o aéreo (linha superior contínua)
    aereo_top = AEREO_Z0 + AEREO_H
    if gel_c is not None and (aereo_top - GEL_H) > 0.20:
        # começa no TOPO da geladeira (sem fenda) -> torre integrada, não caixinha solta
        tcb = clip(fb(ws, gel_c, GEL_W, GEL_D), carve=False)
        if tcb is not None:
            add("aereo_fridge", tcb, aereo_top - (GEL_H - 0.05), RGB_AEREO, z0_m=GEL_H - 0.05, mark=False, ws=ws)
    # FILLER vertical (painel-gable) na junção bancada/coluna-geladeira -> fecha o gap diagonal
    # até o TOPO. Direto via fb (footprint fino cai abaixo do AREA_MIN no clip).
    if gel_c is not None:
        junc = b_hi if g_end != "lo" else b_lo
        fil = fb(ws, junc, 0.16, GEL_D).intersection(cell)   # painel-gable 16cm (ergonomia filler 15-18)
        if not fil.is_empty:
            if fil.geom_type == "MultiPolygon":
                fil = max(fil.geoms, key=lambda g: g.area)
            add("filler", fil, aereo_top - 0.08, _KC["filler"], z0_m=0.08, mark=False, ws=ws)

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
