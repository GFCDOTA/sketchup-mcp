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
RGB2 = {"gabinete": [148, 140, 128], "tampo_banho": [146, 138, 126], "cuba": [16, 16, 18],
        "espelho": [178, 188, 194], "vaso": [40, 40, 42], "box_vidro": [168, 186, 194],
        "gola": [24, 24, 24], "led": [255, 250, 232], "metal": [28, 28, 30],
        "bronze": [171, 119, 63], "tampo_lavabo": [150, 141, 128],
        "nicho_fundo": [52, 50, 48], "toalha_a": [92, 88, 84], "toalha_b": [64, 62, 60],
        "frasco": [40, 38, 36], "nicho_box": [46, 40, 34],
        # ESTUDIO BANHEIRO 2026-08-05 (referencia GPT, loop 4.4->8.0): metais PRETOS,
        # ouro em 1 ponto (anel da torneira) + moldura champagne do espelho
        "champagne": [178, 148, 96], "dourado": [186, 148, 84]}


# ESTUDIO BANHEIRO: o .skp NAVEGAVEL recebe as MESMAS texturas do render
# (FP-036 interativo) + vidro translucido — sem isso o Felipe abre o modelo e
# ve "outra coisa" (vidro opaco azul, madeira/pedra chapadas).
_KIND_TEX = {"gabinete": ("stone_greige_veins.png", 90),
             "bancada_banho": ("stone_greige_veins.png", 90),
             "kb_parede": ("floor_cimento_queimado.png", 120),
             "kb_parede_pedra": ("stone_antracite_veins.png", 80),
             "kb_piso": ("porcelanato_greige_calmo.png", 80),
             "kb_piso_box": ("antracite_calmo.png", 60)}
_KIND_ALPHA = {"box_vidro": 0.16, "kb_folha": 0.16, "kb_janela_fosco": 0.55}

# ---- TEMA POR CÔMODO (Felipe 2026-08-08: "faz nos outros banheiros mas muda
# o tema deles"). O .skp resolve o material POR PEÇA via `mat_name`
# (place_layout_skp.rb: b['mat_name'] || "ph_<kind>"), então cada cômodo ganha
# pele própria sem colidir com o BANHO 01 — que fica CONGELADO no
# STONE_MONOLITH aprovado (9.6). Regras universais da casa continuam valendo
# em todos: metais preto fosco, dourado zero, cuba under-mount, gabinete
# suspenso, madeira NUNCA na área molhada do box.
BASE_THEME = "stone_monolith"
THEMES = {
    # BANHO 01 (suíte) — CONGELADO: aprovado 9.6 pelo juiz.
    "stone_monolith": {"suffix": "", "rooms": (), "tex": {}, "rgb": {}},
    # BANHO 02 (social) — OAK_SERENO: inverte o 01 (paredes claras / piso
    # grafite), marcenaria em carvalho na área SECA; box em cimento (madeira
    # nunca na área molhada).
    "oak_sereno": {
        "suffix": "oak", "rooms": ("BANHO 02", "BANHO 2"),
        "tex": {"gabinete": ("wood_medium.png", 70),
                "bancada_banho": ("stone_counter.png", 90),
                "kb_parede": ("porcelanato_greige_calmo.png", 140),
                "kb_parede_pedra": ("concrete.png", 110),
                "kb_piso": ("floor_grafite_medio.png", 80),
                "kb_piso_box": ("floor_grafite_medio.png", 60)},
        # carvalho mais claro/natural = protagonista quente (GPT p24)
        "rgb": {"gabinete": [178, 138, 94], "tampo_banho": [196, 190, 179],
                "tampo_lavabo": [196, 190, 179], "nicho_box": [104, 102, 100],
                "toalha_a": [206, 200, 188], "toalha_b": [170, 164, 152]},
    },
    # LAVABO — NERO_ARDOSIA: o cômodo de ousar (a visita vê). Ardósia escura
    # veinada nas paredes + bancada do MESMO material (monólito total), luz do
    # espelho como único protagonista. Sem box, então sem risco de molhado.
    "nero_ardosia": {
        "suffix": "nero", "rooms": ("LAVABO",),
        # GPT p24: NERO forte só na parede da bancada; paredes secundárias e
        # piso abrem ~0.4EV pra não virar caverna. Tampo um valor acima das
        # frentes = tampo/cuba/frente param de se fundir.
        "tex": {"gabinete": ("stone_antracite_veins.png", 85),
                "bancada_banho": ("stone_antracite_veins.png", 85),
                "kb_parede": ("porcelanato_greige_calmo.png", 140),
                "kb_parede_pedra": ("stone_antracite_veins.png", 90),
                "kb_piso": ("porcelanato_greige_calmo.png", 80)},
        "rgb": {"gabinete": [52, 50, 50], "tampo_banho": [86, 83, 82],
                "tampo_lavabo": [86, 83, 82], "toalha_a": [198, 192, 182],
                "toalha_b": [168, 162, 152]},
    },
}


def theme_of(room_name) -> str:
    """Tema da pele a partir do nome do cômodo (BANHO 01 = base congelada)."""
    up = str(room_name or "").upper()
    for key, th in THEMES.items():
        for pat in th.get("rooms", ()):
            if pat in up:
                return key
    return BASE_THEME


def _apply_theme(items, theme_key):
    """Reescreve material/pele das peças conforme o tema do cômodo."""
    th = THEMES.get(theme_key) or THEMES[BASE_THEME]
    suffix, tex, rgb = th["suffix"], th["tex"], th["rgb"]
    if not suffix:
        return items
    for it in items:
        kind = it["kind"]
        it["mat_name"] = f"ph_{kind}_{suffix}"
        if kind in tex:
            it["tex_png"], it["tile_in"] = tex[kind]
        elif kind in _KIND_TEX:
            it.pop("tex_png", None)
            it.pop("tile_in", None)
        if kind in rgb:
            it["rgb"] = list(rgb[kind])
    return items


def _pp(kind, x0, y0, x1, y1, z0_m, z1_m, rgb, module):
    """parte: x/y em POINTS (->inches), z em METROS. module = grupo no .skp."""
    x0, x1 = min(x0, x1), max(x0, x1)
    y0, y1 = min(y0, y1), max(y0, y1)
    extra = {}
    if kind in _KIND_TEX:
        extra["tex_png"], extra["tile_in"] = _KIND_TEX[kind]
    if kind in _KIND_ALPHA:
        extra["alpha"] = _KIND_ALPHA[kind]
    return {**extra, "kind": kind, "x0": x0 * PT_TO_IN, "y0": y0 * PT_TO_IN,
            "x1": x1 * PT_TO_IN, "y1": y1 * PT_TO_IN,
            "corners": [[round(x0 * PT_TO_IN, 2), round(y0 * PT_TO_IN, 2)],
                        [round(x1 * PT_TO_IN, 2), round(y0 * PT_TO_IN, 2)],
                        [round(x1 * PT_TO_IN, 2), round(y1 * PT_TO_IN, 2)],
                        [round(x0 * PT_TO_IN, 2), round(y1 * PT_TO_IN, 2)]],
            "h_in": round((z1_m - z0_m) * 39.3700787402, 2), "z0_in": round(z0_m * 39.3700787402, 2),
            "rgb": rgb, "label": kind, "module": module, "ambiguous": False,
            "decorative": kind in ("kb_moldura", "kb_frasco", "kb_toalha", "kb_trilho", "kb_puxador", "kb_haste", "kb_ducha", "kb_ralo", "kb_misturador", "kb_ducha_manual", "kb_argola", "kb_gancho", "kb_papeleira", "kb_escova", "kb_toalheiro", "kb_tapete", "kb_bandeja", "kb_sabonete", "kb_copo", "kb_botao", "kb_guia", "kb_caixilho")}  # trim/decor fino declarado (kb_moldura decorativa)


def _emit(kind, b, ws, lavabo=False, door_c=None):
    """Geometria CRÍVEL por fixture (substitui a caixa única)."""
    x0, y0, x1, y1 = b.bounds
    w, d = x1 - x0, y1 - y0
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    out = []
    if kind == "vaso":
        # ANATOMIA ROCA THE GAP (curadoria Felipe 2026-08-08: ele MANTEVE o Gap
        # — então o builder tem que TER A CARA do Gap): 650x365x800, linhas
        # RETAS com cantos suaves, caixa slim, SAIA FECHADA até o chão (sem
        # base estreita oval), assento/tampa retos. Rounded-rect, não oval.
        import math as _m

        def _rr(cx_, cy_, hx, hy, rr_, z0_, z1_, kd="vaso"):
            part = _pp(kd, cx_ - hx, cy_ - hy, cx_ + hx, cy_ + hy, z0_, z1_,
                       RGB2["vaso"], "Vaso")
            pts = []
            for ccx, ccy, a0 in ((cx_ + hx - rr_, cy_ + hy - rr_, 0.0),
                                 (cx_ - hx + rr_, cy_ + hy - rr_, _m.pi / 2),
                                 (cx_ - hx + rr_, cy_ - hy + rr_, _m.pi),
                                 (cx_ + hx - rr_, cy_ - hy + rr_, 1.5 * _m.pi)):
                for i in range(6):
                    a = a0 + i * (_m.pi / 2) / 5
                    pts.append([round((ccx + rr_ * _m.cos(a)) * PT_TO_IN, 2),
                                round((ccy + rr_ * _m.sin(a)) * PT_TO_IN, 2)])
            part["corners"] = pts
            part["smooth"] = True
            return part

        if ws is not None:
            wf = ws["face"] + ws["sgn"] * M(0.02)
            sgn = ws["sgn"]
            hw = M(0.1825)                                   # meia-largura 36.5cm
            if ws["orient"] == "v":
                # caixa acoplada slim 36.5x15, z 0.40-0.80 + botao duplo no topo
                ccx = wf + sgn * M(0.075)
                out.append(_rr(ccx, cy, M(0.075), hw, M(0.022), 0.40, 0.80))
                out.append(_pp("kb_botao", ccx - M(0.028), cy - M(0.045),
                               ccx + M(0.028), cy + M(0.045), 0.80, 0.812,
                               RGB2["metal"], "Vaso"))
                # bacia MONOBLOCO com saia fechada ate o chao (Gap: reta+suave)
                bcx = wf + sgn * (M(0.15) + M(0.25))
                out.append(_rr(bcx, cy, M(0.25), hw, M(0.09), 0.013, 0.405))
                # assento + tampa retos, levemente recuados (kind proprio: no
                # render ganham satin p/ SEPARAR da caixa fosca — GPT p22)
                out.append(_rr(bcx, cy, M(0.24), hw - M(0.010), M(0.085), 0.405, 0.425, "kb_tampa"))
                out.append(_rr(bcx - sgn * M(0.008), cy, M(0.235), hw - M(0.016),
                               M(0.082), 0.425, 0.44, "kb_tampa"))
            else:
                ccy = wf + sgn * M(0.075)
                out.append(_rr(cx, ccy, hw, M(0.075), M(0.022), 0.40, 0.80))
                out.append(_pp("kb_botao", cx - M(0.045), ccy - M(0.028),
                               cx + M(0.045), ccy + M(0.028), 0.80, 0.812,
                               RGB2["metal"], "Vaso"))
                bcy = wf + sgn * (M(0.15) + M(0.25))
                out.append(_rr(cx, bcy, hw, M(0.25), M(0.09), 0.013, 0.405))
                out.append(_rr(cx, bcy, hw - M(0.010), M(0.24), M(0.085), 0.405, 0.425, "kb_tampa"))
                out.append(_rr(cx, bcy - sgn * M(0.008), hw - M(0.016), M(0.235),
                               M(0.082), 0.425, 0.44, "kb_tampa"))
        else:
            ins = min(w, d) * 0.12
            out.append(_pp("vaso", x0 + ins, y0 + ins, x1 - ins, y1 - ins,
                           0.28, 0.45, RGB2["vaso"], "Vaso"))
    elif kind == "bancada_banho":
        # GRAMÁTICA DA REFERÊNCIA ChatGPT do Felipe (2026-08-04, "tipo isso"):
        # gavetão nogueira suspenso -> NICHO ABERTO de toalhas com LED -> tampo
        # pedra preta ESPESSO (12cm aparente) com cuba esculpida; torneira DE
        # PAREDE bronze; espelho moldura preta + halo LED.
        # CURADORIA FELIPE 2026-08-08 (front :8788) + consultoria GPT: gabinete
        # linguagem Celite Elite — 2 frentes de gaveta LIMPAS sem puxador,
        # shadow gap 7mm entre elas + gap void sob o tampo, suspenso (fundo
        # ~0.38). SAI o nicho aberto de toalhas. Exterior segue STONE_MONOLITH
        # greige (Elite é só referência de proporção, não MDF aparente).
        ix0, iy0 = x0 + w * 0.04, y0 + d * 0.04
        ix1, iy1 = x1 - w * 0.04, y1 - d * 0.04
        gap0, gap1 = 0.6035, 0.6105                       # shadow gap entre frentes
        out.append(_pp("gabinete", ix0, iy0, ix1, iy1, 0.38, gap0,
                       RGB2["gabinete"], "Bancada"))       # frente inferior (~224mm)
        out.append(_pp("gabinete", ix0, iy0, ix1, iy1, gap1, 0.77,
                       RGB2["gabinete"], "Bancada"))       # frente superior (~160mm)
        rx0, ry0 = x0 + w * 0.06, y0 + d * 0.06
        rx1, ry1 = x1 - w * 0.06, y1 - d * 0.06
        out.append(_pp("kb_sombra", rx0, ry0, rx1, ry1, gap0, gap1,
                       [16, 16, 18], "Bancada"))           # recuo escuro entre frentes
        out.append(_pp("kb_gola", ix0, iy0, ix1, iy1, 0.368, 0.38,
                       RGB2["gola"], "Bancada"))           # gola inferior handleless
        # VERDICT 5.8 P3: tampo 10cm (monólito elegante) + cuba com PROFUNDIDADE
        # lida (anel escuro + poço quase-preto)
        _tampo = RGB2["tampo_lavabo"] if lavabo else RGB2["tampo_banho"]
        out.append(_pp("bancada_banho", x0, y0, x1, y1, 0.78, 0.88, _tampo, "Bancada"))
        # gap superior VOID matte sob o tampo (GPT p20: transição suave, não metal)
        out.append(_pp("kb_sombra", rx0, ry0, rx1, ry1, 0.77, 0.78,
                       [16, 16, 18], "Bancada"))
        # cuba UNDER-MOUNT retangular — anatomia Deca Slim 50x37 (curadoria
        # 2026-08-08: Felipe manteve), borda fina, clampada ao módulo
        cbw, cbd = min(M(0.50), w * 0.72), min(M(0.37), d * 0.62)
        out.append(_pp("cuba", cx - cbw / 2, cy - cbd / 2, cx + cbw / 2, cy + cbd / 2,
                       0.845, 0.879, [32, 32, 35], "Bancada"))                 # poço under-mount
        out.append(_pp("cuba", cx - cbw / 2 + M(0.015), cy - cbd / 2 + M(0.015),
                       cx + cbw / 2 - M(0.015), cy + cbd / 2 - M(0.015),
                       0.845, 0.862, [22, 22, 25], "Bancada"))                 # fundo com queda
        # TORNEIRA — Deca Unic bica baixa Black Matte (curadoria 2026-08-08:
        # Felipe rejeitou a Level; GPT travou a Unic). Corpo 54mm x 152mm,
        # projecao total ~174mm, alavanca monocomando no TOPO (sem manopla
        # lateral), tudo preto fosco.
        t = M(0.015)
        if ws is not None:
            if ws["orient"] == "v":
                fx = ws["face"] + ws["sgn"] * M(0.10)               # deck junto da parede
                out.append(_pp("kb_torneira", fx - M(0.027), cy - M(0.027), fx + M(0.027), cy + M(0.027),
                               0.88, 1.032, RGB2["metal"], "Bancada"))         # corpo 54mm
                out.append(_pp("kb_torneira", fx, cy - M(0.014), fx + ws["sgn"] * M(0.147), cy + M(0.014),
                               1.00, 1.028, RGB2["metal"], "Bancada"))         # bica baixa
                out.append(_pp("kb_torneira", fx - M(0.020), cy - M(0.020), fx + M(0.020), cy + M(0.020),
                               1.032, 1.047, RGB2["metal"], "Bancada"))        # alavanca no topo
            else:
                fy = ws["face"] + ws["sgn"] * M(0.10)
                out.append(_pp("kb_torneira", cx - M(0.027), fy - M(0.027), cx + M(0.027), fy + M(0.027),
                               0.88, 1.032, RGB2["metal"], "Bancada"))
                out.append(_pp("kb_torneira", cx - M(0.014), fy, cx + M(0.014), fy + ws["sgn"] * M(0.147),
                               1.00, 1.028, RGB2["metal"], "Bancada"))
                out.append(_pp("kb_torneira", cx - M(0.020), fy - M(0.020), cx + M(0.020), fy + M(0.020),
                               1.032, 1.047, RGB2["metal"], "Bancada"))
        # ESPELHO: halo LED atrás + espelho + MOLDURA PRETA fina (referência)
        # VERDICT 5.8 P1: espelho GRANDE e LEVE — halo LED fino (1.5cm de aro),
        # moldura preta fina nos 4 lados, superfície reflexiva; nada de "bloco".
        if ws is not None and ws["orient"] == "v":
            wx = (ws["face"] + ws["sgn"] * M(0.04))
            out.append(_pp("kb_led", wx - ws["sgn"] * M(0.004), y0 + d * 0.055, wx + t * ws["sgn"], y1 - d * 0.055,
                           1.06, 2.02, RGB2["led"], "Espelho"))                # halo (aro 1.5cm)
            out.append(_pp("espelho", wx + ws["sgn"] * M(0.006), y0 + d * 0.07,
                           wx + ws["sgn"] * (M(0.006) + t), y1 - d * 0.07,
                           1.08, 2.00, RGB2["espelho"], "Espelho"))            # espelho GRANDE 92cm alto
            for _mz0, _mz1 in ((1.066, 1.08), (2.00, 2.014)):                  # moldura top/bottom
                out.append(_pp("kb_moldura", wx + ws["sgn"] * M(0.008), y0 + d * 0.07,
                               wx + ws["sgn"] * (M(0.008) + t), y1 - d * 0.07,
                               _mz0, _mz1, RGB2["gola"], "Espelho"))
            for _ma, _mb in ((y0 + d * 0.07, y0 + d * 0.095), (y1 - d * 0.095, y1 - d * 0.07)):
                out.append(_pp("kb_moldura", wx + ws["sgn"] * M(0.008), _ma,
                               wx + ws["sgn"] * (M(0.008) + t), _mb,
                               1.08, 2.00, RGB2["gola"], "Espelho"))           # moldura laterais
            # GPT OPÇÃO A (2026-08-08): espelho lia "plano preto" porque
            # refletia a parede antracite sem conteúdo — light slot vertical
            # RASANTE na parede OPOSTA (dentro do cone que o espelho enxerga)
            # dá textura/gradiente real ao reflexo sem clarear o banheiro.
            far_x = x1 - M(0.02) if abs(wx - x0) < abs(wx - x1) else x0 + M(0.02)
            far_sgn = -1.0 if far_x == x1 - M(0.02) else 1.0
            _sc = max(min(cy, y1 - d * 0.10), y0 + d * 0.10)   # rasgo FINO (3cm), ALTO (135cm)
            out.append(_pp("kb_slot_led", far_x, _sc - M(0.015),
                           far_x + far_sgn * M(0.012), _sc + M(0.015),
                           1.15, 2.50, RGB2["led"], "Espelho"))
        elif ws is not None:
            wy = (ws["face"] + ws["sgn"] * M(0.04))
            out.append(_pp("kb_led", x0 + w * 0.055, wy - ws["sgn"] * M(0.004), x1 - w * 0.055, wy + t * ws["sgn"],
                           1.06, 2.02, RGB2["led"], "Espelho"))
            out.append(_pp("espelho", x0 + w * 0.07, wy + ws["sgn"] * M(0.006),
                           x1 - w * 0.07, wy + ws["sgn"] * (M(0.006) + t),
                           1.08, 2.00, RGB2["espelho"], "Espelho"))
            for _mz0, _mz1 in ((1.066, 1.08), (2.00, 2.014)):
                out.append(_pp("kb_moldura", x0 + w * 0.07, wy + ws["sgn"] * M(0.008),
                               x1 - w * 0.07, wy + ws["sgn"] * (M(0.008) + t),
                               _mz0, _mz1, RGB2["gola"], "Espelho"))
            for _ma, _mb in ((x0 + w * 0.07, x0 + w * 0.095), (x1 - w * 0.095, x1 - w * 0.07)):
                out.append(_pp("kb_moldura", _ma, wy + ws["sgn"] * M(0.008),
                               _mb, wy + ws["sgn"] * (M(0.008) + t),
                               1.08, 2.00, RGB2["gola"], "Espelho"))
            far_y = y1 - M(0.02) if abs(wy - y0) < abs(wy - y1) else y0 + M(0.02)
            far_sgn = -1.0 if far_y == y1 - M(0.02) else 1.0
            _sc = max(min(cx, x1 - w * 0.10), x0 + w * 0.10)
            out.append(_pp("kb_slot_led", _sc - M(0.015), far_y,
                           _sc + M(0.015), far_y + far_sgn * M(0.012),
                           1.15, 2.50, RGB2["led"], "Espelho"))
    elif kind == "box":
        # BOX (consultoria GPT 2026-08-05): vidro FIXO + FOLHA DE CORRER
        # sobreposta + trilho superior discreto + puxador vertical; chuveiro de
        # teto com haste + cabeca redonda; misturador na face do fixo (shaft);
        # ducha manual slim; ralo linear. NADA de toalheiro dentro do box.
        gt = M(0.008)
        _pf = M(0.022)
        horiz = (x1 - x0) >= (y1 - y0)          # frente corre no eixo maior
        da, dp = (door_c if door_c is not None else (cx, cy))
        if horiz:
            a0, a1, along_door = x0, x1, da
            front, back = ((y1, y0) if dp >= cy else (y0, y1))
            sin = -1.0 if front > back else 1.0             # interior a partir da frente
            def pane(al, ah, off, z0, z1, kd, rgb):
                return _pp(kd, al, front + sin * M(off), ah,
                           front + sin * (M(off) + gt), z0, z1, rgb, "Box")
        else:
            a0, a1, along_door = y0, y1, dp
            front, back = ((x1, x0) if da >= cx else (x0, x1))
            sin = -1.0 if front > back else 1.0
            def pane(al, ah, off, z0, z1, kd, rgb):
                return _pp(kd, front + sin * M(off), al,
                           front + sin * (M(off) + gt), ah, z0, z1, rgb, "Box")
        span = a1 - a0
        fixw = min(M(0.48), span * 0.45)
        leaf_lo = abs(along_door - a0) <= abs(along_door - a1)
        if leaf_lo:
            lf0, lf1 = a0, a1 - fixw + M(0.05)
            fx0_, fx1_ = a1 - fixw, a1
            free_edge = a0
        else:
            lf0, lf1 = a0 + fixw - M(0.05), a1
            fx0_, fx1_ = a0, a0 + fixw
            free_edge = a1
        out.append(pane(fx0_, fx1_, 0.0, 0.014, 2.44, "box_vidro", RGB2["box_vidro"]))
        out.append(pane(lf0, lf1, 0.065, 0.014, 2.44, "kb_folha", RGB2["box_vidro"]))
        # montante da FOLHA no bordo de sobreposicao — a aresta preta full-height
        # na frente do fixo e o que le "porta de correr" de longe (fixo x folha)
        fe = lf1 if leaf_lo else lf0
        out.append(pane(fe - M(0.011), fe + M(0.011), 0.062, 0.014, 2.44,
                        "kb_perfil", RGB2["gola"]))
        # trilho superior discreto (NAO tampa): so a faixa da frente
        if horiz:
            out.append(_pp("kb_trilho", a0, front - sin * M(0.004), a1,
                           front + sin * M(0.065), 2.44, 2.462, RGB2["gola"], "Box"))
        else:
            out.append(_pp("kb_trilho", front - sin * M(0.004), a0,
                           front + sin * M(0.065), a1, 2.44, 2.462, RGB2["gola"], "Box"))
        # montantes finos nas duas pontas da frente
        for ae in (a0, a1):
            if horiz:
                out.append(_pp("kb_perfil", ae - _pf / 2, front - _pf / 2, ae + _pf / 2,
                               front + _pf / 2, 0.014, 2.44, RGB2["gola"], "Box"))
            else:
                out.append(_pp("kb_perfil", front - _pf / 2, ae - _pf / 2, front + _pf / 2,
                               ae + _pf / 2, 0.014, 2.44, RGB2["gola"], "Box"))
        # puxador vertical 38cm a ~6cm da borda livre da folha
        ph = free_edge + (M(0.06) if leaf_lo else -M(0.095))
        if horiz:
            out.append(_pp("kb_puxador", ph, front + sin * M(0.075), ph + M(0.045),
                           front + sin * M(0.11), 0.95, 1.42, RGB2["gola"], "Box"))
        else:
            out.append(_pp("kb_puxador", front + sin * M(0.075), ph,
                           front + sin * M(0.11), ph + M(0.045), 0.95, 1.42, RGB2["gola"], "Box"))
        # GUIA inferior minima da folha (auditoria: sistema de correr legivel)
        if horiz:
            out.append(_pp("kb_guia", lf0, front + sin * M(0.06), lf1,
                           front + sin * M(0.085), 0.014, 0.028, RGB2["gola"], "Box"))
            out.append(_pp("kb_piso_box", a0 + M(0.01), min(front, back) + M(0.01),
                           a1 - M(0.01), max(front, back) - M(0.01),
                           0.0125, 0.016, [52, 51, 53], "Box"))
        else:
            out.append(_pp("kb_guia", front + sin * M(0.06), lf0,
                           front + sin * M(0.085), lf1, 0.014, 0.028, RGB2["gola"], "Box"))
            out.append(_pp("kb_piso_box", min(front, back) + M(0.01), a0 + M(0.01),
                           max(front, back) - M(0.01), a1 - M(0.01),
                           0.0125, 0.016, [52, 51, 53], "Box"))
        # CHUVEIRO DE PAREDE — Deca Flex Max Ø22 Black Matte (curadoria
        # 2026-08-08: Felipe aboliu o de teto, "zoado"). Braco horizontal
        # ~31cm saindo da parede interna a ~2.28m; cabeca redonda com face
        # inferior ~2.13; queda curta liga braco e cabeca.
        sx_ = (a1 - M(0.33)) if leaf_lo else (a0 + M(0.33))     # eixo do ralo
        sp_ = front + sin * M(0.38)
        import math as _m
        _r = M(0.11)
        if ws is not None:
            wf0 = ws["face"]
            if ws["orient"] == "v":
                hx_, hy_ = wf0 + ws["sgn"] * M(0.31), cy
                out.append(_pp("kb_haste", wf0, cy - M(0.012), hx_, cy + M(0.012),
                               2.267, 2.29, RGB2["metal"], "Box"))       # braco de parede
            else:
                hx_, hy_ = cx, wf0 + ws["sgn"] * M(0.31)
                out.append(_pp("kb_haste", cx - M(0.012), wf0, cx + M(0.012), hy_,
                               2.267, 2.29, RGB2["metal"], "Box"))
            out.append(_pp("kb_haste", hx_ - M(0.012), hy_ - M(0.012), hx_ + M(0.012),
                           hy_ + M(0.012), 2.156, 2.29, RGB2["metal"], "Box"))
        else:
            hx_, hy_ = (sx_, sp_) if horiz else (sp_, sx_)
            out.append(_pp("kb_haste", hx_ - M(0.012), hy_ - M(0.012), hx_ + M(0.012),
                           hy_ + M(0.012), 2.156, 2.50, RGB2["metal"], "Box"))
        cab = _pp("kb_ducha", hx_ - _r, hy_ - _r, hx_ + _r, hy_ + _r, 2.13, 2.156,
                  RGB2["metal"], "Box")
        cab["corners"] = [[round((hx_ + _r * _m.cos(_a)) * PT_TO_IN, 2),
                           round((hy_ + _r * _m.sin(_a)) * PT_TO_IN, 2)]
                          for _a in [_m.pi / 24 + i * _m.pi / 12 for i in range(24)]]
        cab["smooth"] = True
        out.append(cab)
        # misturador (placa 14cm) + ducha manual slim na face interna do painel FIXO
        mf = fx1_ - M(0.02) if not leaf_lo else fx0_ + M(0.02)
        msgn = -1.0 if not leaf_lo else 1.0
        mid_p = back + (M(0.45) if back < front else -M(0.45))
        if horiz:
            out.append(_pp("kb_misturador", mf, mid_p - M(0.07), mf + msgn * M(0.015),
                           mid_p + M(0.07), 1.02, 1.16, RGB2["metal"], "Box"))
            out.append(_pp("kb_ducha_manual", mf, mid_p + M(0.11), mf + msgn * M(0.05),
                           mid_p + M(0.16), 1.12, 1.34, RGB2["metal"], "Box"))
        else:
            out.append(_pp("kb_misturador", mid_p - M(0.07), mf, mid_p + M(0.07),
                           mf + msgn * M(0.015), 1.02, 1.16, RGB2["metal"], "Box"))
            out.append(_pp("kb_ducha_manual", mid_p + M(0.11), mf, mid_p + M(0.16),
                           mf + msgn * M(0.05), 1.12, 1.34, RGB2["metal"], "Box"))
        # ralo linear escuro junto a parede do fundo
        rlo = back + (M(0.09) if back < front else -M(0.14))
        rhi = rlo + M(0.05)
        if horiz:
            out.append(_pp("kb_ralo", sx_ - M(0.35), min(rlo, rhi), sx_ + M(0.35),
                           max(rlo, rhi), 0.014, 0.018, RGB2["gola"], "Box"))
        else:
            out.append(_pp("kb_ralo", min(rlo, rhi), sx_ - M(0.35), max(rlo, rhi),
                           sx_ + M(0.35), 0.014, 0.018, RGB2["gola"], "Box"))
        if ws is not None:
            # NICHO iluminado com 3 frascos (unica coisa na parede interna do box)
            if ws["orient"] == "v":
                wf = ws["face"] + ws["sgn"] * M(0.02)
                nx = wf + ws["sgn"] * M(0.03)
                out.append(_pp("kb_nicho_box", wf, cy - M(0.33), nx, cy + M(0.33),
                               1.10, 1.40, RGB2["nicho_box"], "Box"))
                out.append(_pp("kb_led", wf, cy - M(0.31), nx + ws["sgn"] * M(0.004), cy + M(0.31),
                               1.355, 1.385, RGB2["led"], "Box"))
                for _fx, _fh in ((cy - M(0.22), 0.16), (cy - M(0.05), 0.12), (cy + M(0.12), 0.14)):
                    out.append(_pp("kb_frasco", nx, _fx, nx + ws["sgn"] * M(0.05), _fx + M(0.05),
                                   1.10, 1.10 + _fh, RGB2["frasco"], "Box"))
            else:
                wf = ws["face"] + ws["sgn"] * M(0.02)
                ny = wf + ws["sgn"] * M(0.03)
                out.append(_pp("kb_nicho_box", cx - M(0.33), wf, cx + M(0.33), ny,
                               1.10, 1.40, RGB2["nicho_box"], "Box"))
                out.append(_pp("kb_led", cx - M(0.31), wf, cx + M(0.31), ny + ws["sgn"] * M(0.004),
                               1.355, 1.385, RGB2["led"], "Box"))
                for _fx, _fh in ((cx - M(0.22), 0.16), (cx - M(0.05), 0.12), (cx + M(0.12), 0.14)):
                    out.append(_pp("kb_frasco", _fx, ny, _fx + M(0.05), ny + ws["sgn"] * M(0.05),
                                   1.10, 1.10 + _fh, RGB2["frasco"], "Box"))
    return out


def _skin_parts(cell, ws_by_kind, zones_u, win_zone=None):
    """PELE do banheiro (Estudio Banheiro 2026-08-05): o que faltava entre o
    laboratorio 8.0/10 e a planta — piso de pedra grafite + revestimento das
    paredes que hospedam as pecas (cimento queimado; pedra antracite atras do
    box/ducha). Paineis desviam de porta/janela via difference (shapely)."""
    from shapely.geometry import box as _sbox
    out = []

    def _clean_ring_corners(poly):
        """Corners prontos pro Ruby `add_face` (place_layout_skp.rb): buffer()
        com join_style default (round) aproxima cada canto CONVEXO por um
        arco de varios segmentos quase-colineares — num poligono de comodo
        nao-retangular (varios vertices/degrau) isso produz uma boundary que
        o add_face do SketchUp as vezes rejeita (self-intersecting/degenerada
        apos triangulacao), e o `rescue StandardError` do .rb engole a falha
        em silencio: a peca some (kb_teto vira 'ceu vazando' num canto). Fix:
        `simplify` colapsa os quase-colineares E buffer(0) garante anel valido
        antes de exportar os corners — mesmo poligono geometrico, boundary
        limpa pro add_face."""
        cleaned = poly.buffer(0).simplify(M(0.01), preserve_topology=True)
        if cleaned.is_empty or cleaned.geom_type != "Polygon":
            cleaned = poly   # fallback: nunca perder a peca por causa do clean
        return [[round(px * PT_TO_IN, 2), round(py * PT_TO_IN, 2)]
                for px, py in list(cleaned.exterior.coords)[:-1]]

    piso = cell.buffer(-M(0.004), join_style=2)
    if not piso.is_empty:
        p = _pp("kb_piso", *piso.bounds, 0.001, 0.012, [66, 62, 58], "Pele")
        p["corners"] = _clean_ring_corners(piso)
        p["decorative"] = True   # recortado ao comodo (mesmo precedente do tapete)
        out.append(p)
    # TETO do banho (fecha o comodo pro V-Ray interior — sem ele o ceu lava a
    # cena; modulo proprio pra KA_HIDE nos renders dollhouse)
    laje = cell.buffer(M(0.14), join_style=2)   # cobre a espessura das paredes (sem fresta de sol);
    # join_style=2 (mitre) evita a curva-arco do round nos cantos convexos —
    # menos pontos quase-colineares pro add_face brigar com concavidade real.
    if not laje.is_empty:
        t = _pp("kb_teto", *laje.bounds, 2.50, 2.56, [58, 54, 50], "PeleTeto")
        t["corners"] = _clean_ring_corners(laje)
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
    # JANELA como elemento de projeto (auditoria: 'buraco branco'): caixilho
    # preto fino + vidro FOSCO translucido no vao, na face interna da parede
    if win_zone is not None and not win_zone.is_empty:
        wzx0, wzy0, wzx1, wzy1 = win_zone.bounds
        minx, miny, maxx, maxy = cell.bounds
        zs, zh = 1.32, 2.04
        cands = [(abs(wzy0 - miny), 'S'), (abs(maxy - wzy1), 'N'),
                 (abs(wzx0 - minx), 'W'), (abs(maxx - wzx1), 'E')]
        side = min(cands)[1]
        fr = M(0.035)
        if side in ('S', 'N'):
            fy = miny if side == 'S' else maxy
            sgn = 1.0 if side == 'S' else -1.0
            a0w, a1w = max(wzx0, minx) + M(0.02), min(wzx1, maxx) - M(0.02)
            g0, g1 = fy + sgn * M(0.006), fy + sgn * M(0.014)
            pane = _pp("kb_janela_fosco", a0w, min(g0, g1), a1w, max(g0, g1),
                       zs, zh, [214, 219, 223], "Pele")
            out.append(pane)
            f0, f1 = fy + sgn * M(0.004), fy + sgn * M(0.018)
            for za, zb in ((zs - 0.035, zs), (zh, zh + 0.035)):
                out.append(_pp("kb_caixilho", a0w - fr, min(f0, f1), a1w + fr,
                               max(f0, f1), za, zb, [24, 24, 26], "Pele"))
            for aa, ab in ((a0w - fr, a0w), (a1w, a1w + fr)):
                out.append(_pp("kb_caixilho", aa, min(f0, f1), ab, max(f0, f1),
                               zs, zh, [24, 24, 26], "Pele"))
        else:
            fx = minx if side == 'W' else maxx
            sgn = 1.0 if side == 'W' else -1.0
            a0w, a1w = max(wzy0, miny) + M(0.02), min(wzy1, maxy) - M(0.02)
            g0, g1 = fx + sgn * M(0.006), fx + sgn * M(0.014)
            out.append(_pp("kb_janela_fosco", min(g0, g1), a0w, max(g0, g1), a1w,
                           zs, zh, [214, 219, 223], "Pele"))
            f0, f1 = fx + sgn * M(0.004), fx + sgn * M(0.018)
            for za, zb in ((zs - 0.035, zs), (zh, zh + 0.035)):
                out.append(_pp("kb_caixilho", min(f0, f1), a0w - fr, max(f0, f1),
                               a1w + fr, za, zb, [24, 24, 26], "Pele"))
            for aa, ab in ((a0w - fr, a0w), (a1w, a1w + fr)):
                out.append(_pp("kb_caixilho", min(f0, f1), aa, max(f0, f1), ab,
                               zs, zh, [24, 24, 26], "Pele"))
    return out





def _enxoval_parts(cell, ws_by_kind, bb_by_kind, door_c, lavabo):
    """ENXOVAL fora do box (consultoria GPT 2026-08-05): toalheiro na parede do
    box (lado de fora), argola de rosto junto ao gabinete, papeleira ao lado do
    vaso, 2 ganchos perto da porta, lixeira, escova, tapete diante do box e
    acessorios de bancada. Alturas em metros conforme a consultoria."""
    out = []
    comodo = cell.buffer(M(0.02))
    from shapely.geometry import box as _sb

    def _ok(p):
        return comodo.contains(_sb(p["x0"] / PT_TO_IN, p["y0"] / PT_TO_IN,
                                   p["x1"] / PT_TO_IN, p["y1"] / PT_TO_IN))

    def _add(p):
        if _ok(p):
            out.append(p)

    pia_bb = bb_by_kind.get("bancada_banho")
    vaso_bb = bb_by_kind.get("vaso")
    box_bb = bb_by_kind.get("box")
    pia_ws = ws_by_kind.get("bancada_banho")
    vaso_ws = ws_by_kind.get("vaso")
    box_ws = ws_by_kind.get("box") or ws_by_kind.get("ducha")

    # --- toalheiro barra 55cm na parede do box, LADO DE FORA (z 1.10-1.15)
    if box_bb is not None and box_ws is not None and door_c is not None:
        bx0, by0, bx1, by1 = box_bb
        if box_ws["orient"] == "v":
            wf = box_ws["face"] + box_ws["sgn"] * M(0.03)
            frente = by1 if door_c[1] >= (by0 + by1) / 2 else by0
            sgn_out = 1.0 if frente == by1 else -1.0
            t0 = frente + sgn_out * M(0.14)
            _add(_pp("kb_toalheiro", wf, t0, wf + box_ws["sgn"] * M(0.022),
                     t0 + sgn_out * M(0.55), 1.10, 1.14, RGB2["metal"], "Enxoval"))
        else:
            wf = box_ws["face"] + box_ws["sgn"] * M(0.03)
            frente = bx1 if door_c[0] >= (bx0 + bx1) / 2 else bx0
            sgn_out = 1.0 if frente == bx1 else -1.0
            t0 = frente + sgn_out * M(0.14)
            _add(_pp("kb_toalheiro", t0, wf, t0 + sgn_out * M(0.55),
                     wf + box_ws["sgn"] * M(0.022), 1.10, 1.14, RGB2["metal"], "Enxoval"))

    # --- argola/barra curta de rosto ao lado do gabinete (z ~1.00)
    if pia_bb is not None and pia_ws is not None:
        px0, py0, px1, py1 = pia_bb
        if pia_ws["orient"] == "v":
            wf = pia_ws["face"] + pia_ws["sgn"] * M(0.03)
            a0 = py1 + M(0.10)
            _add(_pp("kb_argola", wf, a0, wf + pia_ws["sgn"] * M(0.022), a0 + M(0.28),
                     0.99, 1.02, RGB2["metal"], "Enxoval"))
        else:
            wf = pia_ws["face"] + pia_ws["sgn"] * M(0.03)
            a0 = px1 + M(0.10)
            _add(_pp("kb_argola", a0, wf, a0 + M(0.28), wf + pia_ws["sgn"] * M(0.022),
                     0.99, 1.02, RGB2["metal"], "Enxoval"))

        # --- acessorios de bancada sobre o tampo (z 0.90+): bandeja + sabonete + copo
        bcx, bcy = (px0 + px1) / 2, (py0 + py1) / 2
        if pia_ws["orient"] == "v":
            offx = pia_ws["face"] + pia_ws["sgn"] * M(0.16)
            _add(_pp("kb_bandeja", offx - M(0.07), bcy + M(0.26), offx + M(0.07),
                     bcy + M(0.50), 0.90, 0.915, RGB2["gola"], "Enxoval"))
            _add(_pp("kb_sabonete", offx - M(0.04), bcy + M(0.30), offx + M(0.03),
                     bcy + M(0.38), 0.915, 0.945, RGB2["frasco"], "Enxoval"))
            _add(_pp("kb_copo", offx - M(0.03), bcy + M(0.41), offx + M(0.03),
                     bcy + M(0.47), 0.915, 0.995, RGB2["frasco"], "Enxoval"))
        else:
            offy = pia_ws["face"] + pia_ws["sgn"] * M(0.16)
            _add(_pp("kb_bandeja", bcx + M(0.26), offy - M(0.07), bcx + M(0.50),
                     offy + M(0.07), 0.90, 0.915, RGB2["gola"], "Enxoval"))
            _add(_pp("kb_sabonete", bcx + M(0.30), offy - M(0.04), bcx + M(0.38),
                     offy + M(0.03), 0.915, 0.945, RGB2["frasco"], "Enxoval"))
            _add(_pp("kb_copo", bcx + M(0.41), offy - M(0.03), bcx + M(0.47),
                     offy + M(0.03), 0.915, 0.995, RGB2["frasco"], "Enxoval"))

        # --- lixeira 5-7L no chao entre gabinete e box
        if pia_ws["orient"] == "v":
            lf = pia_ws["face"] + pia_ws["sgn"] * M(0.06)
            _add(_pp("kb_lixeira", lf, py0 - M(0.30), lf + pia_ws["sgn"] * M(0.20),
                     py0 - M(0.10), 0.013, 0.31, RGB2["gola"], "Enxoval"))
        else:
            lf = pia_ws["face"] + pia_ws["sgn"] * M(0.06)
            _add(_pp("kb_lixeira", px0 - M(0.30), lf, px0 - M(0.10),
                     lf + pia_ws["sgn"] * M(0.20), 0.013, 0.31, RGB2["gola"], "Enxoval"))

    # --- papeleira ao lado do vaso (z 0.66-0.72) + escova no chao
    if vaso_bb is not None and vaso_ws is not None:
        vx0, vy0, vx1, vy1 = vaso_bb
        if vaso_ws["orient"] == "v":
            wf = vaso_ws["face"] + vaso_ws["sgn"] * M(0.03)
            _add(_pp("kb_papeleira", wf, vy1 + M(0.08), wf + vaso_ws["sgn"] * M(0.10),
                     vy1 + M(0.22), 0.66, 0.72, RGB2["metal"], "Enxoval"))
            _add(_pp("kb_escova", wf, vy0 - M(0.16), wf + vaso_ws["sgn"] * M(0.10),
                     vy0 - M(0.06), 0.013, 0.40, RGB2["gola"], "Enxoval"))
        else:
            wf = vaso_ws["face"] + vaso_ws["sgn"] * M(0.03)
            _add(_pp("kb_papeleira", vx1 + M(0.08), wf, vx1 + M(0.22),
                     wf + vaso_ws["sgn"] * M(0.10), 0.66, 0.72, RGB2["metal"], "Enxoval"))
            _add(_pp("kb_escova", vx0 - M(0.16), wf, vx0 - M(0.06),
                     wf + vaso_ws["sgn"] * M(0.10), 0.013, 0.40, RGB2["gola"], "Enxoval"))

        # --- 2 ganchos na mesma parede, do outro lado da porta (z 1.66-1.70)
        if door_c is not None:
            wf = vaso_ws["face"] + vaso_ws["sgn"] * M(0.03)
            if vaso_ws["orient"] == "h":
                for gx in (door_c[0] - M(0.28), door_c[0] - M(0.44)):
                    _add(_pp("kb_gancho", gx, wf, gx + M(0.035),
                             wf + vaso_ws["sgn"] * M(0.05), 1.66, 1.70, RGB2["gola"], "Enxoval"))
            else:
                for gy in (door_c[1] - M(0.28), door_c[1] - M(0.44)):
                    _add(_pp("kb_gancho", wf, gy, wf + vaso_ws["sgn"] * M(0.05),
                             gy + M(0.035), 1.66, 1.70, RGB2["gola"], "Enxoval"))

    # --- tapete 50x80 grafite-taupe diante da abertura do box
    if box_bb is not None and door_c is not None:
        bx0, by0, bx1, by1 = box_bb
        bcx = (bx0 + bx1) / 2
        if (bx1 - bx0) >= (by1 - by0):
            frente = by1 if door_c[1] >= (by0 + by1) / 2 else by0
            sgn_out = 1.0 if frente == by1 else -1.0
            t0 = frente + sgn_out * M(0.12)
            _add(_pp("kb_tapete", bcx - M(0.40), min(t0, t0 + sgn_out * M(0.50)),
                     bcx + M(0.40), max(t0, t0 + sgn_out * M(0.50)),
                     0.013, 0.020, [96, 90, 82], "Enxoval"))
        else:
            bcy = (by0 + by1) / 2
            frente = bx1 if door_c[0] >= (bx0 + bx1) / 2 else bx0
            sgn_out = 1.0 if frente == bx1 else -1.0
            t0 = frente + sgn_out * M(0.12)
            _add(_pp("kb_tapete", min(t0, t0 + sgn_out * M(0.50)), bcy - M(0.40),
                     max(t0, t0 + sgn_out * M(0.50)), bcy + M(0.40),
                     0.013, 0.020, [96, 90, 82], "Enxoval"))
    return out



def _directed_pia_vaso(cell, walls, door_c, circ_u, comodo, win_zone, pia_sizes):
    """Layout DIRIGIDO (consultoria GPT 2026-08-05, reprovacao do Felipe):
    entrada -> GABINETE primeiro na parede longa oposta ao lado da folha da
    porta (comecando ~8cm do canto) -> VASO imediatamente ao lado, de LADO pra
    porta (traseira na mesma parede), eixo >=38cm da lateral do gabinete.
    Devolve {"bancada_banho": (box, ws), "vaso": (box, ws)} ou None (fallback
    pro first-fit generico)."""
    from shapely.geometry import box as _sb
    if door_c is None:
        return None
    minx, miny, maxx, maxy = cell.bounds
    if (maxx - minx) >= (maxy - miny):
        return None                      # so trata comodo alongado em Y (caso canonico)
    host_face = maxx if door_c[0] < (minx + maxx) / 2 else minx
    host = None
    for ws in walls:
        if ws["orient"] == "v" and abs(ws["face"] - host_face) < M(0.10):
            host = ws
            break
    if host is None:
        return None
    door_end = maxy if door_c[1] > (miny + maxy) / 2 else miny
    sgn_in = 1.0 if door_end == maxy else -1.0          # sentido porta -> fundo
    tol = 0.02 / PT_TO_M ** 2

    def _try(along0, w_m, d_m):
        a_hi = along0 - sgn_in * M(0.0)
        a_lo = along0 - sgn_in * M(w_m)
        y0_, y1_ = min(a_lo, a_hi), max(a_lo, a_hi)
        x0_ = min(host["face"], host["face"] + host["sgn"] * M(0.03 + d_m))
        x1_ = max(host["face"], host["face"] + host["sgn"] * M(0.03 + d_m))
        bx = _sb(x0_ + M(0.001), y0_, x1_ - M(0.001), y1_)
        if not comodo.contains(bx):
            return None
        if circ_u is not None and bx.intersection(circ_u).area > tol:
            return None
        if win_zone is not None and bx.intersection(win_zone).area > tol:
            return None
        return bx

    # gabinete: comeca 8cm do canto da entrada
    pia = None
    for w_m, d_m in pia_sizes:
        pia = _try(door_end - sgn_in * M(0.08), w_m, d_m)
        if pia is not None:
            pia_w = w_m
            break
    if pia is None:
        return None
    # vaso: logo apos o gabinete (gap 10cm), 38cm de largura ao longo da parede,
    # bacia projetando 66cm pra dentro
    vaso_start = door_end - sgn_in * M(0.08 + pia_w + 0.10)
    vaso = _try(vaso_start, 0.38, 0.63)
    if vaso is None:
        return None
    return {"bancada_banho": (pia, host), "vaso": (vaso, host)}

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
    door_c = ((door_z.centroid.x, door_z.centroid.y) if door_z is not None else None)

    walls = [ws for ws in (_wall_setup(sm, w["id"]) for w in sm["walls"]) if ws is not None]
    walls.sort(key=lambda ws: -(_room_span(ws, cell)[1] - _room_span(ws, cell)[0]))
    if not walls:
        return None, {"result": "NO_VALID_LAYOUT", "room_name": sm.get("room_name"),
                      "reason": "sem parede util"}

    # pia/cuba em CASCATA (GPT 6.3 no banho real: gabinete 0.95-1.05m "nobre";
    # tenta do maior pro menor ate caber — 0.50 fixo deixava o conjunto raquitico)
    pia_sizes = ([(0.78, 0.46), (0.65, 0.44), (0.52, 0.40)]
                 if area < 4.5 else [(0.90, 0.48), (0.78, 0.46), (0.65, 0.44)])
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
    bb_by_kind = {}
    box_ok = False
    directed = _directed_pia_vaso(cell, walls, door_c, circ_u, comodo,
                                  win_zone, pia_sizes)
    for (kind, w_m, d_m), tall in fixtures:
        if directed and kind in directed:
            b, ws = directed[kind]
        elif kind == "bancada_banho":
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
                # atravessa o EIXO CURTO do comodo (faixa no fundo, longe da
                # porta); expandir no eixo longo bloquearia vaso/circulacao.
                from shapely.geometry import box as _sb
                minx, miny, maxx, maxy = cell.bounds
                bx0, by0, bx1, by1 = b.bounds
                if (maxx - minx) <= (maxy - miny):
                    cand = _sb(minx + M(0.005), by0, maxx - M(0.005), by1)
                else:
                    cand = _sb(bx0, miny + M(0.005), bx1, maxy - M(0.005))
                ok_exp = all(cand.intersection(pb).area < M(0.02) ** 2 for pb in placed)
                if ok_exp and circ_u is not None:
                    inter = cand.intersection(circ_u)
                    if inter.area > M(0.04) ** 2:
                        # encurta a faixa AFASTANDO da porta (nunca reverte)
                        ix0, iy0, ix1, iy1 = inter.bounds
                        cx0, cy0, cx1, cy1 = cand.bounds
                        if (maxx - minx) <= (maxy - miny):
                            cand = (_sb(cx0, cy0, cx1, iy0 - M(0.02))
                                    if (by0 + by1) / 2 < (iy0 + iy1) / 2
                                    else _sb(cx0, iy1 + M(0.02), cx1, cy1))
                        else:
                            cand = (_sb(cx0, cy0, ix0 - M(0.02), cy1)
                                    if (bx0 + bx1) / 2 < (ix0 + ix1) / 2
                                    else _sb(ix1 + M(0.02), cy0, cx1, cy1))
                if ok_exp:
                    # SHAFT (Felipe 2026-08-05): recorta ao POLIGONO real do
                    # comodo — o bounding box inclui o notch do shaft e o vidro
                    # invadia a area tecnica (piso nem encosta la)
                    inter = cand.intersection(cell.buffer(-M(0.004)))
                    if not inter.is_empty:
                        rb = _sb(*inter.bounds)
                        if cell.buffer(M(0.02)).contains(rb):
                            cand = rb
                        else:
                            cand = None
                    else:
                        cand = None
                if ok_exp and cand is not None and cand.area > b.area:
                    b = cand
            items.extend(_emit(kind, b, ws, lavabo=lavabo, door_c=door_c))
            placed.append(b)
            ws_by_kind[kind] = ws
            bb_by_kind[kind] = b.bounds
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
    items.extend(_skin_parts(cell, ws_by_kind, unary_union(zones) if zones else None, win_zone))
    items.extend(_enxoval_parts(cell, ws_by_kind, bb_by_kind, door_c, lavabo))
    theme = theme_of(sm.get("room_name"))
    _apply_theme(items, theme)
    kinds = [it["kind"] for it in items]
    return items, {"result": "OK", "room_name": sm.get("room_name"),
                   "theme": theme,
                   "n_pecas": len(items), "pecas": kinds,
                   "tem_vaso": "vaso" in kinds, "tem_box": "box" in kinds}


if __name__ == "__main__":
    import json
    con = json.loads(Path("fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json")
                     .read_text("utf-8"))
    for r in ("r005", "r006", "r007"):
        boxes, out = build_boxes(con, r)
        print(r, out.get("room_name"), out["result"], out.get("pecas"))
