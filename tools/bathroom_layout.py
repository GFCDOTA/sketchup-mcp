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
RGB2 = {"gabinete": [108, 80, 58], "tampo_banho": [24, 23, 25], "cuba": [16, 16, 18],
        "espelho": [150, 158, 164], "vaso": [40, 40, 42], "box_vidro": [168, 186, 194],
        "gola": [24, 24, 24], "led": [255, 250, 232], "metal": [28, 28, 30],
        "bronze": [171, 119, 63], "tampo_lavabo": [30, 29, 32],
        "nicho_fundo": [56, 42, 30], "toalha_a": [150, 118, 88], "toalha_b": [104, 84, 64],
        "frasco": [40, 38, 36], "nicho_box": [46, 40, 34]}


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
        out.append(_pp("gabinete", x0 + w * 0.04, y0 + d * 0.04, x1 - w * 0.04, y1 - d * 0.04,
                       0.26, 0.50, RGB2["gabinete"], "Bancada"))               # gavetão nogueira suspenso
        out.append(_pp("kb_gola", x0 + w * 0.10, y0 + d * 0.10, x1 - w * 0.10, y1 - d * 0.10,
                       0.248, 0.26, RGB2["gola"], "Bancada"))
        # NICHO de toalhas (a assinatura): prateleira nogueira + fundo sombra + LED
        out.append(_pp("kb_nicho_fundo", x0 + w * 0.05, y0 + d * 0.05, x1 - w * 0.05, y1 - d * 0.05,
                       0.50, 0.76, RGB2["nicho_fundo"], "Bancada"))
        out.append(_pp("gabinete", x0 + w * 0.04, y0 + d * 0.04, x1 - w * 0.04, y1 - d * 0.04,
                       0.50, 0.525, RGB2["gabinete"], "Bancada"))              # prateleira nogueira
        _tw = min(w, d) * 0.30
        for _i, _tc in enumerate((cx - _tw * 0.75, cx + _tw * 0.75)):
            out.append(_pp("kb_toalha", _tc - _tw / 2, cy - _tw / 2, _tc + _tw / 2, cy + _tw / 2,
                           0.525, 0.645, RGB2["toalha_a" if _i == 0 else "toalha_b"], "Bancada"))
        out.append(_pp("kb_led", x0 + w * 0.10, y0 + d * 0.10, x1 - w * 0.10, y1 - d * 0.10,
                       0.735, 0.75, RGB2["led"], "Bancada"))                   # LED do nicho
        # tampo ESPESSO com cuba esculpida (abertura escura integrada, sem aro)
        _tampo = RGB2["tampo_lavabo"] if lavabo else RGB2["tampo_banho"]
        out.append(_pp("bancada_banho", x0, y0, x1, y1, 0.76, 0.88, _tampo, "Bancada"))
        cwid = min(w, d) * 0.50
        out.append(_pp("cuba", cx - cwid / 2, cy - cwid / 2, cx + cwid / 2, cy + cwid / 2,
                       0.881, 0.8845, RGB2["cuba"], "Bancada"))                # abertura esculpida
        # TORNEIRA DE PAREDE em BRONZE (bica horizontal + monocomando) — referência
        t = M(0.015)
        if ws is not None:
            if ws["orient"] == "v":
                wxf = ws["face"]
                out.append(_pp("kb_torneira", wxf, cy - M(0.012), wxf + ws["sgn"] * M(0.18), cy + M(0.012),
                               1.05, 1.075, RGB2["bronze"], "Bancada"))        # bica
                out.append(_pp("kb_torneira", wxf, cy + M(0.07), wxf + ws["sgn"] * M(0.045), cy + M(0.13),
                               1.02, 1.08, RGB2["bronze"], "Bancada"))         # monocomando
            else:
                wyf = ws["face"]
                out.append(_pp("kb_torneira", cx - M(0.012), wyf, cx + M(0.012), wyf + ws["sgn"] * M(0.18),
                               1.05, 1.075, RGB2["bronze"], "Bancada"))
                out.append(_pp("kb_torneira", cx + M(0.07), wyf, cx + M(0.13), wyf + ws["sgn"] * M(0.045),
                               1.02, 1.08, RGB2["bronze"], "Bancada"))
        # ESPELHO: halo LED atrás + espelho + MOLDURA PRETA fina (referência)
        if ws is not None and ws["orient"] == "v":
            wx = (ws["face"] + ws["sgn"] * M(0.04))
            out.append(_pp("kb_led", wx - ws["sgn"] * M(0.005), y0 + d * 0.08, wx + t * ws["sgn"], y1 - d * 0.08,
                           1.10, 1.82, RGB2["led"], "Espelho"))
            out.append(_pp("espelho", wx + ws["sgn"] * M(0.006), y0 + d * 0.12,
                           wx + ws["sgn"] * (M(0.006) + t), y1 - d * 0.12,
                           1.13, 1.79, RGB2["espelho"], "Espelho"))
            for _mz0, _mz1 in ((1.11, 1.13), (1.79, 1.81)):
                out.append(_pp("kb_moldura", wx + ws["sgn"] * M(0.008), y0 + d * 0.11,
                               wx + ws["sgn"] * (M(0.008) + t), y1 - d * 0.11,
                               _mz0, _mz1, RGB2["gola"], "Espelho"))
        elif ws is not None:
            wy = (ws["face"] + ws["sgn"] * M(0.04))
            out.append(_pp("kb_led", x0 + w * 0.08, wy - ws["sgn"] * M(0.005), x1 - w * 0.08, wy + t * ws["sgn"],
                           1.10, 1.82, RGB2["led"], "Espelho"))
            out.append(_pp("espelho", x0 + w * 0.12, wy + ws["sgn"] * M(0.006),
                           x1 - w * 0.12, wy + ws["sgn"] * (M(0.006) + t),
                           1.13, 1.79, RGB2["espelho"], "Espelho"))
            for _mz0, _mz1 in ((1.11, 1.13), (1.79, 1.81)):
                out.append(_pp("kb_moldura", x0 + w * 0.11, wy + ws["sgn"] * M(0.008),
                               x1 - w * 0.11, wy + ws["sgn"] * (M(0.008) + t),
                               _mz0, _mz1, RGB2["gola"], "Espelho"))
    elif kind == "box":
        # box de vidro com PERFIL preto (2 montantes + travessa) + DUCHA preta
        out.append(_pp("box_vidro", x0, y0, x1, y1, 0.0, 2.0, RGB2["box_vidro"], "Box"))
        _pf = M(0.026)   # perfil 2.6cm (>= min_footprint 1in² do geometry_sanity; 2cm era 'degenerate')
        out.append(_pp("kb_perfil", x0, y0, x0 + _pf, y0 + _pf, 0.0, 2.0, RGB2["gola"], "Box"))
        out.append(_pp("kb_perfil", x1 - _pf, y1 - _pf, x1, y1, 0.0, 2.0, RGB2["gola"], "Box"))
        out.append(_pp("kb_perfil", x0, y0, x1, y1, 1.98, 2.02, RGB2["gola"], "Box"))
        if ws is not None:
            # DUCHA redonda BRONZE (referência) + NICHO DE PAREDE iluminado com amenities
            if ws["orient"] == "v":
                hx = ws["face"] + ws["sgn"] * M(0.22)
                out.append(_pp("kb_ducha", ws["face"], cy - M(0.012), hx, cy + M(0.012),
                               2.05, 2.08, RGB2["bronze"], "Box"))             # braço
                out.append(_pp("kb_ducha", hx - M(0.10), cy - M(0.10), hx + M(0.10), cy + M(0.10),
                               2.03, 2.05, RGB2["bronze"], "Box"))             # cabeça
                nx = ws["face"] + ws["sgn"] * M(0.03)
                out.append(_pp("kb_nicho_box", ws["face"], cy - M(0.30), nx, cy + M(0.30),
                               1.10, 1.40, RGB2["nicho_box"], "Box"))          # nicho raso
                out.append(_pp("kb_led", ws["face"], cy - M(0.27), nx + ws["sgn"] * M(0.004), cy + M(0.27),
                               1.365, 1.385, RGB2["led"], "Box"))              # fita do nicho
                for _fx in (cy - M(0.14), cy + M(0.06)):
                    out.append(_pp("kb_frasco", nx, _fx, nx + ws["sgn"] * M(0.05), _fx + M(0.05),
                                   1.10, 1.26, RGB2["frasco"], "Box"))
            else:
                hy = ws["face"] + ws["sgn"] * M(0.22)
                out.append(_pp("kb_ducha", cx - M(0.012), ws["face"], cx + M(0.012), hy,
                               2.05, 2.08, RGB2["bronze"], "Box"))
                out.append(_pp("kb_ducha", cx - M(0.10), hy - M(0.10), cx + M(0.10), hy + M(0.10),
                               2.03, 2.05, RGB2["bronze"], "Box"))
                ny = ws["face"] + ws["sgn"] * M(0.03)
                out.append(_pp("kb_nicho_box", cx - M(0.30), ws["face"], cx + M(0.30), ny,
                               1.10, 1.40, RGB2["nicho_box"], "Box"))
                out.append(_pp("kb_led", cx - M(0.27), ws["face"], cx + M(0.27), ny + ws["sgn"] * M(0.004),
                               1.365, 1.385, RGB2["led"], "Box"))
                for _fx in (cx - M(0.14), cx + M(0.06)):
                    out.append(_pp("kb_frasco", _fx, ny, _fx + M(0.05), ny + ws["sgn"] * M(0.05),
                                   1.10, 1.26, RGB2["frasco"], "Box"))
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
        # tall=False: box é VIDRO — pode ficar sob a janela alta do banho (padrão
        # real; não bloqueia luz). Tamanho adaptativo: 90x90 em banho folgado,
        # 80x80 no compacto (3.2m² da planta_74).
        _box = BOX if area >= 4.0 else ("box", 0.80, 0.80)
        fixtures.append((_box, False))

    lavabo = "LAVABO" in str(sm.get("room_name", "")).upper()
    items, placed = [], []
    box_ok = False
    for (kind, w_m, d_m), tall in fixtures:
        b, ws = _place_fixture(sm, walls, w_m, d_m, placed, circ_u, comodo, cell, win_zone, tall)
        if b is not None:
            items.extend(_emit(kind, b, ws, lavabo=lavabo))   # geometria CRÍVEL multi-peça
            placed.append(b)
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
                                 2.05, 2.08, RGB2["bronze"], "Ducha"))
                items.append(_pp("kb_ducha", hx - M(0.10), cy - M(0.10), hx + M(0.10), cy + M(0.10),
                                 2.03, 2.05, RGB2["bronze"], "Ducha"))
            else:
                hy = ws["face"] + ws["sgn"] * M(0.20)
                items.append(_pp("kb_ducha", cx - M(0.012), ws["face"], cx + M(0.012), hy,
                                 2.05, 2.08, RGB2["bronze"], "Ducha"))
                items.append(_pp("kb_ducha", cx - M(0.10), hy - M(0.10), cx + M(0.10), hy + M(0.10),
                                 2.03, 2.05, RGB2["bronze"], "Ducha"))
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
