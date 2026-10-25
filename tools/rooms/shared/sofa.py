"""sofa_builder.py — slice 3: SofaBuilder PARAMETRICO. Gera um sofa como PECAS
semanticas separadas (base, assentos SEPARADOS com vinco, encostos SEPARADOS, bracos,
pes, chaise opcional) a partir de um SofaSpec. NAO e caixa unica e NAO depende de
asset externo. Saida: lista de 'parts' (caixas com z0/z1 em m) e conversao pro formato
boxes do place_layout_skp.rb (corners in inches, h_in, z0_in, rgb, label).

Convencao: X=largura, Y=profundidade (frente=0, encosto=Y maior), Z=altura. Frente
do sofa = -Y (vira a parede-TV ao posicionar). Origem no canto (0,0,0).
"""
from __future__ import annotations

from tools.rooms.shared.anatomy import SofaSpec, sofa_spec   # noqa: F401

from tools.rooms.shared.parts import PT_TO_IN, parts_to_boxes  # noqa: E402,F401  (reexport: nomes antigos)
from tools.rooms.shared.parts import darker as _darker, part as _p  # noqa: E402  (primitivas genericas)
from tools.rooms.shared.parts import place_parts as place_sofa_boxes  # noqa: E402,F401  (reexport: nome antigo)

# Constantes NUMERICAS/MATEMATICAS (nao sao medida de movel): tolerancia, quarto de volta, segmentos de arco, pico da parabola.
_EPS = 1e-4                  # tolerancia geometrica (m)
_MIN_CORE_M = 0.01           # espessura minima do miolo da almofada apos o chanfro (m)
_QUARTER_TURN_DEG = 90.0
_ARC_SEGMENTS = 5
_CROWN_DIV = 6.0               # divisor dos pontos do coroamento (5 pontos interiores)
_PARABOLA_PEAK = 4.0         # 4*t*(1-t) vale 1 em t=0,5


def _seat_row(kind, prefix, x0, x1, y0, y1, z0, z1, n, gap, rgb, bevel=0.0):
    """n almofadas SEPARADAS (com vinco) em X[x0,x1]. bevel>0: topo INSET (chanfro) ->
    a almofada deixa de ser caixa reta (GPT cycle2: cushion_edge_radius, 'menos cubico').
    Corpo (z0..z1-b) + tampo inset b em x/y (z1-b..z1), MESMO kind -> bbox e gate intactos."""
    out = []
    w = (x1 - x0 - gap * (n - 1)) / n
    b = max(0.0, min(bevel, w / 2 - _MIN_CORE_M, (y1 - y0) / 2 - _MIN_CORE_M, (z1 - z0) / 2))
    for i in range(n):
        sx = x0 + i * (w + gap)
        if b > 0:
            zc = z1 - b
            out.append(_p(f"{prefix}_{i + 1}", kind, sx, y0, sx + w, y1, z0, zc, rgb))
            out.append(_p(f"{prefix}_{i + 1}_top", kind, sx + b, y0 + b, sx + w - b, y1 - b, zc, z1, rgb))
        else:
            out.append(_p(f"{prefix}_{i + 1}", kind, sx, y0, sx + w, y1, z0, z1, rgb))
    return out


def _rounded_arm_profile(x0, x1, z0, z1, r, nseg=_ARC_SEGMENTS):
    """Secao (x,z) CCW de um braco com roundover REAL nos 2 cantos superiores:
    retangulo com arcos de raio r (nseg segmentos cada) — FP-SOFA-PREMIUM
    alt_001 (spec 6.2: bevel de geometria, nao soften cosmetico)."""
    import math
    r = max(0.0, min(r, (x1 - x0) / 2 - _EPS, (z1 - z0) / 2 - _EPS))
    if r <= 0:
        return [(x0, z0), (x1, z0), (x1, z1), (x0, z1)]
    cz = z1 - r
    pts = [(x0, z0), (x1, z0), (x1, cz)]
    for i in range(1, nseg + 1):        # canto sup DIREITO: centro (x1-r, cz), 0->90
        a = math.radians(_QUARTER_TURN_DEG * i / nseg)
        pts.append((x1 - r + r * math.cos(a), cz + r * math.sin(a)))
    for i in range(1, nseg + 1):        # canto sup ESQUERDO: centro (x0+r, cz), 90->180
        a = math.radians(_QUARTER_TURN_DEG + _QUARTER_TURN_DEG * i / nseg)
        pts.append((x0 + r + r * math.cos(a), cz + r * math.sin(a)))
    return pts


def _shear_y(p, k, z0pivot):
    """verts8 do box p cisalhado em Y: y += k*(z - z0pivot) (k=tan(rake)). Topo recua
    -> encosto inclinado. Mantem 6 faces (renderer usa verts8)."""
    x0, y0, z0, x1, y1, z1 = p["x0"], p["y0"], p["z0"], p["x1"], p["y1"], p["z1"]
    sb, st = k * (z0 - z0pivot), k * (z1 - z0pivot)
    return [(x0, y0 + sb, z0), (x1, y0 + sb, z0), (x1, y1 + sb, z0), (x0, y1 + sb, z0),
            (x0, y0 + st, z1), (x1, y0 + st, z1), (x1, y1 + st, z1), (x0, y1 + st, z1)]


def build_sofa(spec: SofaSpec):
    """Devolve (parts, meta). parts = pecas (caixas em m, com z0/z1)."""
    spec.validate()
    W, D, H = spec.width, spec.depth, spec.height
    aw, ah, fh = spec.arm_width, spec.arm_height, spec.foot_height
    sh, sd, ct = spec.seat_height, spec.seat_depth, spec.cushion_thickness
    bt = spec.back_thickness
    bh = H
    gap, n = spec.cushion_gap, spec.seats
    fab, feet = tuple(spec.fabric_rgb), tuple(spec.feet_rgb)
    base_rgb = _darker(fab, spec.base_shade)        # estrutura/madeira da base: bem mais escura (contraste)
    cush_rgb = fab                       # tecido linho (assentos)
    back_rgb = _darker(fab, spec.back_shade)        # encosto levemente mais escuro (sombra/profundidade)
    Dtot = D if spec.variant == "straight" else max(D, spec.chaise_depth)
    cw = spec.chaise_width
    base_top = sh - ct
    back_z0 = sh - spec.back_pivot_offset
    main_y0 = Dtot - D           # frente do corpo principal (recuado se chaise + fundo)
    seat_back = Dtot - bt        # face frontal do encosto
    seat_front = seat_back - sd
    parts = []

    # --- secoes em X: corpo principal + chaise opcional ---
    # GRAMATICA de chaise integrada (cycle002, regra do juiz): o braco do lado da
    # chaise acompanha SO o corpo principal (main_y0..Dtot) — a perna projetada da
    # chaise fica ABERTA na frente ("extensao do seat deck, nao modulo colado";
    # antes era muralha full-depth = "caixote anexado").
    if spec.variant == "chaise_right":
        chaise_x = (W - cw, W); main_x = (0.0, W - cw)
        left_arm_y = (main_y0, Dtot); right_arm_y = (main_y0, Dtot)
        main_seat_x = (main_x[0] + aw, main_x[1])
        chaise_seat_x = (chaise_x[0], chaise_x[1] - aw)
    elif spec.variant == "chaise_left":
        chaise_x = (0.0, cw); main_x = (cw, W)
        left_arm_y = (main_y0, Dtot); right_arm_y = (main_y0, Dtot)
        main_seat_x = (main_x[0], main_x[1] - aw)
        chaise_seat_x = (chaise_x[0] + aw, chaise_x[1])
    else:
        chaise_x = None; main_x = (0.0, W)
        left_arm_y = (0.0, Dtot); right_arm_y = (0.0, Dtot)
        main_seat_x = (aw, W - aw)
        chaise_seat_x = None

    # --- suporte: pes de canto (legado) OU plinto recuado (FP-SOFA-PREMIUM) ---
    if getattr(spec, "base_style", "feet") == "plinth":
        # alt_002 (REVISE_CHANGE do GPT): plinto continuo escuro recuado
        # plinth_inset nas 4 faces, altura VISIVEL plinth_visible_h; acima
        # dele um RISER central oculto (inset 2x) sobe ate fh — a cota de
        # apoio de bracos/base fica intacta e o vao vira shadow gap real.
        ins = spec.plinth_inset
        vh = min(spec.plinth_visible_h, fh)
        parts.append(_p("plinth", "foot", ins, main_y0 + ins, W - ins,
                        Dtot - ins, 0.0, vh, feet))
        if fh - vh > _EPS:
            ins2 = max(ins * 2, spec.riser_inset_min)
            parts.append(_p("plinth_riser", "foot", ins2, main_y0 + ins2,
                            W - ins2, Dtot - ins2, vh, fh, _darker(feet, spec.riser_shade)))
        if chaise_x:
            cxl, cxr = chaise_seat_x
            parts.append(_p("plinth_chaise", "foot", cxl + ins, ins, cxr - ins,
                            main_y0 + ins, 0.0, vh, feet))
    else:
        fz = (0.0, fh)
        foot, fi = spec.foot_side, spec.foot_inset
        corners = [(fi, main_y0 + fi), (W - fi - foot, main_y0 + fi),
                   (fi, Dtot - fi - foot), (W - fi - foot, Dtot - fi - foot)]
        if chaise_x:   # 2 pes extra na ponta funda da chaise — SOB o deck projetado
            # (chaise_seat_x, nao a borda externa: com a frente aberta o pe na faixa
            # da antiga muralha ficava orfao no ar — gramatica cycle002)
            cxl, cxr = chaise_seat_x
            corners += [(cxl + fi, fi), (cxr - fi - foot, fi)]
        for i, (fx, fy) in enumerate(corners):
            parts.append(_p(f"foot_{i + 1}", "foot", fx, fy, fx + foot, fy + foot, fz[0], fz[1], feet))

    # --- bracos (bordas externas) ---
    # LINGUAGEM de classe (cycle002): arm_relief>0 = braco "flutua" sobre sapata
    # recuada (compensa massa de braco chunky — anti-bunker); arm_cap = tampo fino
    # levemente proud (linguagem formal). relief/cap = 0/False -> braco classico.
    relief, cap, taper = spec.arm_relief, spec.arm_cap, spec.arm_taper
    cap_t, cap_over, shoe_in = spec.arm_cap_t, spec.arm_cap_over, spec.shoe_inset
    for side, (x0a, x1a), (ya0, ya1) in (("left", (0.0, aw), left_arm_y),
                                         ("right", (W - aw, W), right_arm_y)):
        if getattr(spec, "arm_profile", "box") == "rounded":
            # FP-SOFA-PREMIUM alt_001: braco = PERFIL extrudado com roundover
            # real no topo + recuo frontal (frente do sofa = -Y -> ya0+recess).
            ya0r = ya0 + max(0.0, getattr(spec, "arm_front_recess", 0.0))
            prof = _rounded_arm_profile(x0a, x1a, fh, ah,
                                        getattr(spec, "arm_edge_radius", 0.0))
            p = _p(f"arm_{side}", "arm", x0a, ya0r, x1a, ya1, fh, ah, fab)
            p["profile_xz"] = prof
            parts.append(p)
            continue
        body_z0 = fh + relief
        body_z1 = ah - (cap_t if cap else 0.0)
        if relief > 0:
            parts.append(_p(f"arm_{side}_shoe", "arm", x0a + shoe_in, ya0 + shoe_in,
                            x1a - shoe_in, ya1 - shoe_in, fh, body_z0, fab))
        if taper > 0:
            # cycle003 (juiz: "nao basta sapata"): topo do braco AFINA — terco
            # superior inset na face EXTERNA + frente (braco deixa de ser parede)
            zt = body_z0 + (body_z1 - body_z0) * spec.taper_split
            parts.append(_p(f"arm_{side}", "arm", x0a, ya0, x1a, ya1, body_z0, zt, fab))
            tx0 = x0a + (taper if side == "left" else 0.0)
            tx1 = x1a - (taper if side == "right" else 0.0)
            parts.append(_p(f"arm_{side}_top", "arm", tx0, ya0 + taper, tx1, ya1,
                            zt, body_z1, fab))
        else:
            parts.append(_p(f"arm_{side}", "arm", x0a, ya0, x1a, ya1, body_z0, body_z1, fab))
        if cap:
            parts.append(_p(f"arm_{side}_cap", "arm", x0a - cap_over, ya0 - cap_over,
                            x1a + cap_over, ya1 + cap_over, body_z1, ah, fab))

    # --- base/plataforma (corpo principal + chaise) ---
    rec = spec.base_recess  # recuo do plinto frontal (hardcode 0.06 PROMOVIDO a classe)
    if getattr(spec, "base_rail", "box") == "recessed_rounded":
        # FP-SOFA-PREMIUM alt_005 (REVISE do GPT: 55mm, nao 35): travessa
        # frontal recuada vs a FRENTE DAS ALMOFADAS + raio real no topo-frontal.
        import math as _math
        rr = spec.rail_edge_radius
        cush_front = (Dtot - bt) - sd - spec.seat_overhang
        ry0 = cush_front + spec.rail_recess_from_cushion
        prof = [(ry0, fh), (Dtot, fh), (Dtot, base_top), (ry0 + rr, base_top)]
        for j in range(1, _ARC_SEGMENTS + 1):    # canto topo-frontal: 90->180
            a = _math.radians(_QUARTER_TURN_DEG + _QUARTER_TURN_DEG * j / _ARC_SEGMENTS)
            prof.append((ry0 + rr + rr * _math.cos(a), base_top - rr + rr * _math.sin(a)))
        p = _p("base_main", "base", main_seat_x[0], ry0, main_seat_x[1], Dtot,
               fh, base_top, base_rgb)
        p["profile_yz"] = prof
        parts.append(p)
    else:
        parts.append(_p("base_main", "base", main_seat_x[0], main_y0 + rec, main_seat_x[1], Dtot, fh, base_top, base_rgb))
    if chaise_x:
        # GRAMATICA de chaise integrada (cycle002): a base da chaise herda o MESMO
        # recuo frontal do corpo (mesma linguagem de plinto, nao bloco ao chao)
        parts.append(_p("base_chaise", "base", chaise_seat_x[0], rec, chaise_seat_x[1], Dtot, fh, base_top, base_rgb))
        # TERMINACAO da chaise (cycle003, juiz: frente aberta lia como "buraco
        # construtivo"): painel lateral ESTOFADO ate a altura do deck na faixa
        # externa da perna projetada — sofa-chaise real tem lateral baixa
        # estofada; o braco continua so sobre o corpo
        if spec.chaise_termination == "panel":
            px = (W - aw, W) if spec.variant == "chaise_right" else (0.0, aw)
            parts.append(_p("chaise_side_panel", "base", px[0], rec, px[1],
                            main_y0, fh, sh, cush_rgb))

    # --- assentos SEPARADOS (vinco) ---
    over = spec.seat_overhang   # lounge: almofada projeta sobre a base (sombra horizontal)
    if getattr(spec, "seat_style", "stacked_bevel") == "single_crowned":
        # FP-SOFA-PREMIUM alt_004: cada assento = UMA almofada (perfil (y,z)
        # extrudado em X) com coroamento de 15mm (pico no centro) e raio real
        # na aresta FRONTAL-superior — elimina o tampo inset separado.
        crown = spec.seat_crown
        r = spec.seat_edge_radius
        yF, yB, z1 = seat_front - over, seat_back, sh
        prof = [(yF, base_top), (yB, base_top), (yB, z1)]
        span = yB - (yF + r)
        for j in range(1, 6):                    # coroamento: parabola yB -> yF+r
            t = j / _CROWN_DIV
            prof.append((yB - span * t, z1 + crown * _PARABOLA_PEAK * t * (1.0 - t)))
        import math as _math
        for j in range(0, _ARC_SEGMENTS + 1):    # aresta frontal: arco 90->180
            a = _math.radians(_QUARTER_TURN_DEG + _QUARTER_TURN_DEG * j / _ARC_SEGMENTS)
            prof.append((yF + r + r * _math.cos(a), z1 - r + r * _math.sin(a)))
        wmod = (main_seat_x[1] - main_seat_x[0] - gap * (n - 1)) / n
        for i in range(n):
            sx = main_seat_x[0] + i * (wmod + gap)
            p = _p(f"seat_{i + 1}", "seat_cushion", sx, yF, sx + wmod, yB,
                   base_top, z1 + crown, cush_rgb)
            p["profile_yz"] = prof
            parts.append(p)
    else:
        parts += _seat_row("seat_cushion", "seat", main_seat_x[0], main_seat_x[1],
                           seat_front - over, seat_back, base_top, sh, n, gap, cush_rgb, bevel=spec.cushion_bevel)
    if chaise_x:
        # GRAMATICA de chaise integrada (cycle002): o vinco da chaise ALINHA com a
        # linha do assento do corpo (seat_front) — o deck le como UMA superficie
        # continua em L, nao "2 almofadas com split arbitrario no meio"
        cyl = [(0.0 - over, seat_front), (seat_front + spec.chaise_seat_overlap, seat_back)]
        for j, (y0, y1) in enumerate(cyl):
            parts.append(_p(f"seat_chaise_{j + 1}", "seat_cushion", chaise_seat_x[0], y0,
                            chaise_seat_x[1], y1, base_top, sh, cush_rgb))

    # --- encostos SEPARADOS (corpo principal + sobre a chaise) ---
    if getattr(spec, "back_style", "stacked") == "single_crowned":
        # FP-SOFA-PREMIUM alt_003: cada encosto = UMA almofada (perfil em (y,z)
        # extrudado em X) com coroamento arredondado real no topo; o rake de
        # 10deg vem BAKED nos pontos do perfil (nada de bloco superior separado).
        import math as _math
        kr = _math.tan(_math.radians(spec.backrest_rake or 0.0))
        r = spec.back_edge_radius
        wmod = (main_seat_x[1] - main_seat_x[0] - gap * (n - 1)) / n
        prof0 = _rounded_arm_profile(seat_back, Dtot, back_z0, bh, r)  # (y,z)
        prof = [(y + kr * (z - back_z0), z) for (y, z) in prof0]
        ys = [y for (y, _z) in prof]
        for i in range(n):
            sx = main_seat_x[0] + i * (wmod + gap)
            p = _p(f"back_{i + 1}", "back_cushion", sx, min(ys), sx + wmod,
                   max(ys), back_z0, bh, back_rgb)
            p["profile_yz"] = prof
            parts.append(p)
    else:
        parts += _seat_row("back_cushion", "back", main_seat_x[0], main_seat_x[1],
                           seat_back, Dtot, back_z0, bh, n, gap, back_rgb, bevel=spec.cushion_bevel)
    if chaise_x:
        parts.append(_p("back_chaise", "back_cushion", chaise_seat_x[0], seat_back,
                        chaise_seat_x[1], Dtot, back_z0, bh, back_rgb))

    # rake do encosto (GPT cycle3): cisalha back_cushion em +Y conforme sobe -> recline.
    # verts8 p/ o renderer; x0..z1 viram AABB do cisalhado (gate/parts_to_boxes medem o real).
    import math
    rake = math.radians(spec.backrest_rake or 0.0)
    if rake:
        k = math.tan(rake)
        for p in parts:
            if p["kind"] == "back_cushion" and not p.get("profile_yz"):
                # perfis (alt_003) ja vem com o rake baked nos pontos
                v = _shear_y(p, k, back_z0)
                p["verts8"] = v
                ys = [c[1] for c in v]
                p["y0"], p["y1"] = round(min(ys), 4), round(max(ys), 4)

    meta = {"variant": spec.variant, "seats": spec.seats, "n_parts": len(parts),
            "bbox_m": spec.bbox_m(), "front_axis": "-Y",
            "kinds": sorted({p["kind"] for p in parts})}
    return parts, meta


if __name__ == "__main__":
    for v in ("straight", "chaise_right", "chaise_left"):
        parts, meta = build_sofa(sofa_spec(v))
        print(f"{v:14} {meta['n_parts']} pecas | kinds={meta['kinds']} | bbox={meta['bbox_m']}")
