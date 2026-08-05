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
BOX_MIN_AREA_M2 = 2.8   # banho compacto BR (3.2m² real na planta_74) TEM box 80x80; 4.0 vetava TODOS os banhos na escala canônica 0.0259 (Felipe: 'faltaram os banheiros')
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


# ---- fixtures MULTI-PEÇA na gramática BLACK_WOOD_GOLD (programa apê-inteiro
# 2026-08-03): gabinete suspenso nogueira + pedra quieta + cuba preta + metais
# pretos PVD; bronze SÓ no lavabo (área molhada de uso diário mancha bronze).
RGB2 = {"gabinete": [88, 62, 40], "tampo_banho": [24, 23, 25], "cuba": [16, 16, 18],
        "espelho": [178, 188, 194], "vaso": [40, 40, 42], "box_vidro": [168, 186, 194],
        "gola": [24, 24, 24], "led": [255, 250, 232], "metal": [28, 28, 30],
        "bronze": [171, 119, 63], "tampo_lavabo": [30, 29, 32],
        "nicho_fundo": [56, 42, 30], "toalha_a": [150, 118, 88], "toalha_b": [104, 84, 64],
        "frasco": [40, 38, 36], "nicho_box": [46, 40, 34],
        # ESTUDIO BANHEIRO 2026-08-05 (referencia GPT, loop 4.4->8.0): metais PRETOS,
        # ouro em 1 ponto (anel da torneira) + moldura champagne do espelho
        "champagne": [178, 148, 96], "dourado": [186, 148, 84]}


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
            "rgb": rgb, "label": kind, "module": module, "ambiguous": False,
            "decorative": kind in ("kb_moldura", "kb_frasco", "kb_toalha")}  # trim/decor fino declarado (kb_moldura decorativa)


def _emit(kind, b, ws, lavabo=False):
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
        # GRAMÁTICA DA REFERÊNCIA ChatGPT do Felipe (2026-08-04, "tipo isso"):
        # gavetão nogueira suspenso -> NICHO ABERTO de toalhas com LED -> tampo
        # pedra preta ESPESSO (12cm aparente) com cuba esculpida; torneira DE
        # PAREDE bronze; espelho moldura preta + halo LED.
        # VERDICT 5.8 P2 ("marcenaria boutique"): gavetão REALMENTE suspenso com
        # base oculta recuada (sombra), lâminas de nogueira fechando o nicho.
        out.append(_pp("kb_sombra", x0 + w * 0.10, y0 + d * 0.10, x1 - w * 0.10, y1 - d * 0.10,
                       0.30, 0.32, [18, 18, 20], "Bancada"))                   # base oculta recuada
        out.append(_pp("gabinete", x0 + w * 0.04, y0 + d * 0.04, x1 - w * 0.04, y1 - d * 0.04,
                       0.32, 0.50, RGB2["gabinete"], "Bancada"))               # gavetão nogueira suspenso
        out.append(_pp("kb_gola", x0 + w * 0.10, y0 + d * 0.10, x1 - w * 0.10, y1 - d * 0.10,
                       0.308, 0.32, RGB2["gola"], "Bancada"))
        # NICHO de toalhas: fundo sombra + laterais de LÂMINA nogueira + prateleira + LED
        out.append(_pp("kb_nicho_fundo", x0 + w * 0.05, y0 + d * 0.05, x1 - w * 0.05, y1 - d * 0.05,
                       0.50, 0.78, RGB2["nicho_fundo"], "Bancada"))
        out.append(_pp("gabinete", x0 + w * 0.04, y0 + d * 0.04, x1 - w * 0.04, y1 - d * 0.04,
                       0.50, 0.522, RGB2["gabinete"], "Bancada"))              # prateleira nogueira
        if w >= d:                                                              # lâminas laterais (cheeks)
            out.append(_pp("gabinete", x0 + w * 0.04, y0 + d * 0.04, x0 + w * 0.075, y1 - d * 0.04,
                           0.50, 0.78, RGB2["gabinete"], "Bancada"))
            out.append(_pp("gabinete", x1 - w * 0.075, y0 + d * 0.04, x1 - w * 0.04, y1 - d * 0.04,
                           0.50, 0.78, RGB2["gabinete"], "Bancada"))
        else:
            out.append(_pp("gabinete", x0 + w * 0.04, y0 + d * 0.04, x1 - w * 0.04, y0 + d * 0.075,
                           0.50, 0.78, RGB2["gabinete"], "Bancada"))
            out.append(_pp("gabinete", x0 + w * 0.04, y1 - d * 0.075, x1 - w * 0.04, y1 - d * 0.04,
                           0.50, 0.78, RGB2["gabinete"], "Bancada"))
        _tw = min(w, d) * 0.26
        for _i, (_tc, _th) in enumerate(((cx - _tw * 0.95, 0.10), (cx, 0.12), (cx + _tw * 0.95, 0.09))):
            out.append(_pp("kb_toalha", _tc - _tw / 2, cy - _tw / 2, _tc + _tw / 2, cy + _tw / 2,
                           0.525, 0.525 + _th, RGB2["toalha_a" if _i % 2 == 0 else "toalha_b"], "Bancada"))
        out.append(_pp("kb_led", x0 + w * 0.10, y0 + d * 0.10, x1 - w * 0.10, y1 - d * 0.10,
                       0.755, 0.77, RGB2["led"], "Bancada"))                   # LED do nicho
        # VERDICT 5.8 P3: tampo 10cm (monólito elegante) + cuba com PROFUNDIDADE
        # lida (anel escuro + poço quase-preto)
        _tampo = RGB2["tampo_lavabo"] if lavabo else RGB2["tampo_banho"]
        out.append(_pp("bancada_banho", x0, y0, x1, y1, 0.78, 0.88, _tampo, "Bancada"))
        cbw, cbd = w * 0.52, d * 0.58                                        # cuba RETANGULAR esculpida
        out.append(_pp("cuba", cx - cbw / 2, cy - cbd / 2, cx + cbw / 2, cy + cbd / 2,
                       0.881, 0.884, [34, 32, 34], "Bancada"))                 # anel da abertura
        out.append(_pp("cuba", cx - cbw * 0.42, cy - cbd * 0.42, cx + cbw * 0.42, cy + cbd * 0.42,
                       0.884, 0.887, [6, 6, 8], "Bancada"))                    # poço (profundidade)
        # TORNEIRA DE BANCADA preta com ANEL DOURADO na base — gramatica do
        # ESTUDIO BANHEIRO (loop GPT 8.0/10, 2026-08-05). Sai a bronze de parede:
        # ouro aparece em UM ponto so; corpo/bica/manopla preto fosco.
        t = M(0.015)
        if ws is not None:
            if ws["orient"] == "v":
                fx = ws["face"] + ws["sgn"] * M(0.10)               # deck junto da parede
                out.append(_pp("kb_torneira", fx - M(0.02), cy - M(0.02), fx + M(0.02), cy + M(0.02),
                               0.88, 1.06, RGB2["metal"], "Bancada"))          # corpo vertical
                out.append(_pp("kb_torneira", fx, cy - M(0.015), fx + ws["sgn"] * M(0.16), cy + M(0.015),
                               1.03, 1.06, RGB2["metal"], "Bancada"))          # bica p/ cuba
                out.append(_pp("kb_anel", fx - M(0.024), cy - M(0.024), fx + M(0.024), cy + M(0.024),
                               0.88, 0.905, RGB2["dourado"], "Bancada"))       # anel dourado
                out.append(_pp("kb_torneira", fx - M(0.015), cy + M(0.10), fx + M(0.015), cy + M(0.16),
                               0.90, 0.93, RGB2["metal"], "Bancada"))          # manopla
            else:
                fy = ws["face"] + ws["sgn"] * M(0.10)
                out.append(_pp("kb_torneira", cx - M(0.02), fy - M(0.02), cx + M(0.02), fy + M(0.02),
                               0.88, 1.06, RGB2["metal"], "Bancada"))
                out.append(_pp("kb_torneira", cx - M(0.015), fy, cx + M(0.015), fy + ws["sgn"] * M(0.16),
                               1.03, 1.06, RGB2["metal"], "Bancada"))
                out.append(_pp("kb_anel", cx - M(0.024), fy - M(0.024), cx + M(0.024), fy + M(0.024),
                               0.88, 0.905, RGB2["dourado"], "Bancada"))
                out.append(_pp("kb_torneira", cx + M(0.10), fy - M(0.015), cx + M(0.16), fy + M(0.015),
                               0.90, 0.93, RGB2["metal"], "Bancada"))
        # ESPELHO: halo LED atrás + espelho + MOLDURA PRETA fina (referência)
        # VERDICT 5.8 P1: espelho GRANDE e LEVE — halo LED fino (1.5cm de aro),
        # moldura preta fina nos 4 lados, superfície reflexiva; nada de "bloco".
        if ws is not None and ws["orient"] == "v":
            wx = (ws["face"] + ws["sgn"] * M(0.04))
            out.append(_pp("kb_led", wx - ws["sgn"] * M(0.004), y0 + d * 0.085, wx + t * ws["sgn"], y1 - d * 0.085,
                           1.10, 1.86, RGB2["led"], "Espelho"))                # halo (aro 1.5cm)
            out.append(_pp("espelho", wx + ws["sgn"] * M(0.006), y0 + d * 0.10,
                           wx + ws["sgn"] * (M(0.006) + t), y1 - d * 0.10,
                           1.12, 1.84, RGB2["espelho"], "Espelho"))            # espelho 72cm alto
            for _mz0, _mz1 in ((1.105, 1.12), (1.84, 1.855)):                  # moldura top/bottom
                out.append(_pp("kb_moldura", wx + ws["sgn"] * M(0.008), y0 + d * 0.10,
                               wx + ws["sgn"] * (M(0.008) + t), y1 - d * 0.10,
                               _mz0, _mz1, RGB2["champagne"], "Espelho"))
            for _ma, _mb in ((y0 + d * 0.10, y0 + d * 0.125), (y1 - d * 0.125, y1 - d * 0.10)):
                out.append(_pp("kb_moldura", wx + ws["sgn"] * M(0.008), _ma,
                               wx + ws["sgn"] * (M(0.008) + t), _mb,
                               1.12, 1.84, RGB2["champagne"], "Espelho"))           # moldura laterais
        elif ws is not None:
            wy = (ws["face"] + ws["sgn"] * M(0.04))
            out.append(_pp("kb_led", x0 + w * 0.085, wy - ws["sgn"] * M(0.004), x1 - w * 0.085, wy + t * ws["sgn"],
                           1.10, 1.86, RGB2["led"], "Espelho"))
            out.append(_pp("espelho", x0 + w * 0.10, wy + ws["sgn"] * M(0.006),
                           x1 - w * 0.10, wy + ws["sgn"] * (M(0.006) + t),
                           1.12, 1.84, RGB2["espelho"], "Espelho"))
            for _mz0, _mz1 in ((1.105, 1.12), (1.84, 1.855)):
                out.append(_pp("kb_moldura", x0 + w * 0.10, wy + ws["sgn"] * M(0.008),
                               x1 - w * 0.10, wy + ws["sgn"] * (M(0.008) + t),
                               _mz0, _mz1, RGB2["champagne"], "Espelho"))
            for _ma, _mb in ((x0 + w * 0.10, x0 + w * 0.125), (x1 - w * 0.125, x1 - w * 0.10)):
                out.append(_pp("kb_moldura", _ma, wy + ws["sgn"] * M(0.008),
                               _mb, wy + ws["sgn"] * (M(0.008) + t),
                               1.12, 1.84, RGB2["champagne"], "Espelho"))
    elif kind == "box":
        # box de vidro com PERFIL preto (2 montantes + travessa) + DUCHA preta
        # z0 0.014: nasce ACIMA do overlay de piso-pedra da PELE (sem overlap)
        out.append(_pp("box_vidro", x0, y0, x1, y1, 0.014, 2.48, RGB2["box_vidro"], "Box"))
        _pf = M(0.026)   # perfil 2.6cm (>= min_footprint 1in² do geometry_sanity; 2cm era 'degenerate')
        out.append(_pp("kb_perfil", x0, y0, x0 + _pf, y0 + _pf, 0.014, 2.48, RGB2["gola"], "Box"))
        out.append(_pp("kb_perfil", x1 - _pf, y1 - _pf, x1, y1, 0.014, 2.48, RGB2["gola"], "Box"))
        out.append(_pp("kb_perfil", x0, y0, x1, y1, 2.44, 2.48, RGB2["gola"], "Box"))
        if ws is not None:
            # DUCHA redonda BRONZE (referência) + NICHO DE PAREDE iluminado com amenities
            if ws["orient"] == "v":
                wf = ws["face"] + ws["sgn"] * M(0.02)   # face da PELE de pedra
                hx = wf + ws["sgn"] * M(0.22)
                out.append(_pp("kb_ducha", wf, cy - M(0.012), hx, cy + M(0.012),
                               2.05, 2.08, RGB2["metal"], "Box"))             # braço
                out.append(_pp("kb_ducha", hx - M(0.10), cy - M(0.10), hx + M(0.10), cy + M(0.10),
                               2.03, 2.05, RGB2["metal"], "Box"))             # cabeça
                nx = wf + ws["sgn"] * M(0.03)
                out.append(_pp("kb_nicho_box", wf, cy - M(0.30), nx, cy + M(0.30),
                               1.10, 1.40, RGB2["nicho_box"], "Box"))          # nicho raso
                out.append(_pp("kb_led", wf, cy - M(0.27), nx + ws["sgn"] * M(0.004), cy + M(0.27),
                               1.365, 1.385, RGB2["led"], "Box"))              # fita do nicho
                for _fx in (cy - M(0.14), cy + M(0.06)):
                    out.append(_pp("kb_frasco", nx, _fx, nx + ws["sgn"] * M(0.05), _fx + M(0.05),
                                   1.10, 1.26, RGB2["frasco"], "Box"))
            else:
                wf = ws["face"] + ws["sgn"] * M(0.02)
                hy = wf + ws["sgn"] * M(0.22)
                out.append(_pp("kb_ducha", cx - M(0.012), wf, cx + M(0.012), hy,
                               2.05, 2.08, RGB2["metal"], "Box"))
                out.append(_pp("kb_ducha", cx - M(0.10), hy - M(0.10), cx + M(0.10), hy + M(0.10),
                               2.03, 2.05, RGB2["metal"], "Box"))
                ny = wf + ws["sgn"] * M(0.03)
                out.append(_pp("kb_nicho_box", cx - M(0.30), wf, cx + M(0.30), ny,
                               1.10, 1.40, RGB2["nicho_box"], "Box"))
                out.append(_pp("kb_led", cx - M(0.27), wf, cx + M(0.27), ny + ws["sgn"] * M(0.004),
                               1.365, 1.385, RGB2["led"], "Box"))
                for _fx in (cx - M(0.14), cx + M(0.06)):
                    out.append(_pp("kb_frasco", _fx, ny, _fx + M(0.05), ny + ws["sgn"] * M(0.05),
                                   1.10, 1.26, RGB2["frasco"], "Box"))
    return out


def _skin_parts(cell, ws_by_kind, zones_u):
    """PELE do banheiro (Estudio Banheiro 2026-08-05): o que faltava entre o
    laboratorio 8.0/10 e a planta — piso de pedra grafite + revestimento das
    paredes que hospedam as pecas (cimento queimado; pedra antracite atras do
    box/ducha). Paineis desviam de porta/janela via difference (shapely)."""
    from shapely.geometry import box as _sbox
    out = []
    piso = cell.buffer(-M(0.004))
    if not piso.is_empty:
        p = _pp("kb_piso", *piso.bounds, 0.001, 0.012, [66, 62, 58], "Pele")
        p["corners"] = [[round(px * PT_TO_IN, 2), round(py * PT_TO_IN, 2)]
                        for px, py in list(piso.exterior.coords)[:-1]]
        p["decorative"] = True   # recortado ao comodo (mesmo precedente do tapete)
        out.append(p)
    # TETO do banho (fecha o comodo pro V-Ray interior — sem ele o ceu lava a
    # cena; modulo proprio pra KA_HIDE nos renders dollhouse)
    laje = cell.buffer(M(0.14))   # cobre a espessura das paredes (sem fresta de sol)
    if not laje.is_empty:
        t = _pp("kb_teto", *laje.bounds, 2.50, 2.56, [58, 54, 50], "PeleTeto")
        t["corners"] = [[round(px * PT_TO_IN, 2), round(py * PT_TO_IN, 2)]
                        for px, py in list(laje.exterior.coords)[:-1]]
        t["decorative"] = True
        out.append(t)
    _t = M(0.02)
    done = []
    for kind, ws in ws_by_kind.items():
        if ws is None:
            continue
        key = (ws["orient"], round(ws["face"], 1), ws["sgn"])
        if key in done:
            continue
        done.append(key)
        stone = kind in ("box", "ducha")
        rgb = [40, 38, 40] if stone else [166, 152, 136]
        pk = "kb_parede_pedra" if stone else "kb_parede"
        lo, hi = _room_span(ws, cell)
        if hi - lo < M(0.30):
            continue
        if ws["orient"] == "v":
            panel = _sbox(min(ws["face"], ws["face"] + ws["sgn"] * _t), lo,
                          max(ws["face"], ws["face"] + ws["sgn"] * _t), hi)
        else:
            panel = _sbox(lo, min(ws["face"], ws["face"] + ws["sgn"] * _t),
                          hi, max(ws["face"], ws["face"] + ws["sgn"] * _t))
        geom = panel.difference(zones_u) if zones_u is not None else panel
        geoms = getattr(geom, "geoms", [geom])
        for g in geoms:
            if g.is_empty or g.area < M(0.05) ** 2:
                continue
            gx0, gy0, gx1, gy1 = g.bounds
            out.append(_pp(pk, gx0, gy0, gx1, gy1, 0.012, 2.30, rgb, "Pele"))
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

    # pia/cuba em CASCATA (GPT 6.3 no banho real: gabinete 0.95-1.05m "nobre";
    # tenta do maior pro menor ate caber — 0.50 fixo deixava o conjunto raquitico)
    pia_sizes = ([(1.00, 0.48), (0.80, 0.45), (0.62, 0.42), (0.50, 0.40)]
                 if area < 4.5 else [(1.05, 0.50), (0.85, 0.50), (0.70, 0.45)])
    fixtures = [(("bancada_banho", 0, 0), False), (VASO, False)]
    if area >= BOX_MIN_AREA_M2:
        # tall=False: box é VIDRO — pode ficar sob a janela alta do banho (padrão
        # real; não bloqueia luz). Tamanho adaptativo: 90x90 em banho folgado,
        # 80x80 no compacto (3.2m² da planta_74).
        _box = BOX if area >= 4.0 else ("box", 0.80, 0.80)
        fixtures.append((_box, False))

    lavabo = "LAVABO" in str(sm.get("room_name", "")).upper()
    items, placed = [], []
    ws_by_kind = {}
    box_ok = False
    for (kind, w_m, d_m), tall in fixtures:
        if kind == "bancada_banho":
            b = ws = None
            for w_m, d_m in pia_sizes:
                b, ws = _place_fixture(sm, walls, w_m, d_m, placed, circ_u,
                                       comodo, cell, win_zone, tall)
                if b is not None:
                    break
        else:
            b, ws = _place_fixture(sm, walls, w_m, d_m, placed, circ_u, comodo, cell, win_zone, tall)
        if b is not None:
            if kind == "box" and ws is not None:
                # Felipe 2026-08-05: box de PAREDE A PAREDE (nao "cortado") —
                # expande ao span da parede, recuando onde colide com pecas ja postas
                from shapely.geometry import box as _sb
                lo_r, hi_r = _room_span(ws, cell)
                bx0, by0, bx1, by1 = b.bounds
                if ws["orient"] == "v":
                    cand = _sb(bx0, lo_r + M(0.01), bx1, hi_r - M(0.01))
                else:
                    cand = _sb(lo_r + M(0.01), by0, hi_r - M(0.01), by1)
                for pb in placed:
                    if cand.intersection(pb).area > M(0.01) ** 2:
                        px0, py0, px1, py1 = pb.bounds
                        cx0, cy0, cx1, cy1 = cand.bounds
                        if ws["orient"] == "v":
                            if py0 > by1:
                                cand = _sb(cx0, cy0, cx1, py0 - M(0.02))
                            elif py1 < by0:
                                cand = _sb(cx0, py1 + M(0.02), cx1, cy1)
                        else:
                            if px0 > bx1:
                                cand = _sb(cx0, cy0, px0 - M(0.02), cy1)
                            elif px1 < bx0:
                                cand = _sb(px1 + M(0.02), cy0, cx1, cy1)
                if circ_u is not None and cand.intersection(circ_u).area > M(0.04) ** 2:
                    pass          # porta no caminho -> mantem o box original
                else:
                    b = cand
            items.extend(_emit(kind, b, ws, lavabo=lavabo))   # geometria CRÍVEL multi-peça
            placed.append(b)
            ws_by_kind[kind] = ws
            box_ok = box_ok or kind == "box"
    # BANHO sem box que coube = ducha ABERTA de canto (banheiro sem chuveiro não
    # existe; footprint mínimo 0.30 quase sempre cabe encostado)
    if (not lavabo) and (not box_ok) and area >= BOX_MIN_AREA_M2:
        b, ws = _place_fixture(sm, walls, 0.30, 0.30, placed, circ_u, comodo, cell, win_zone, False)
        if b is not None and ws is not None:
            x0, y0, x1, y1 = b.bounds
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            if ws["orient"] == "v":
                hx = ws["face"] + ws["sgn"] * M(0.20)
                items.append(_pp("kb_ducha", ws["face"], cy - M(0.012), hx, cy + M(0.012),
                                 2.05, 2.08, RGB2["metal"], "Ducha"))
                items.append(_pp("kb_ducha", hx - M(0.10), cy - M(0.10), hx + M(0.10), cy + M(0.10),
                                 2.03, 2.05, RGB2["metal"], "Ducha"))
            else:
                hy = ws["face"] + ws["sgn"] * M(0.20)
                items.append(_pp("kb_ducha", cx - M(0.012), ws["face"], cx + M(0.012), hy,
                                 2.05, 2.08, RGB2["metal"], "Ducha"))
                items.append(_pp("kb_ducha", cx - M(0.10), hy - M(0.10), cx + M(0.10), hy + M(0.10),
                                 2.03, 2.05, RGB2["metal"], "Ducha"))
            placed.append(b)
            ws_by_kind["ducha"] = ws
    if not items:
        return None, {"result": "NO_VALID_LAYOUT", "room_name": sm.get("room_name"),
                      "reason": "nenhuma louca coube"}
    zones = [z for z in (door_z, win_zone) if z is not None]
    items.extend(_skin_parts(cell, ws_by_kind, unary_union(zones) if zones else None))
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
