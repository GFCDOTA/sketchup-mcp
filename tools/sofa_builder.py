"""sofa_builder.py — slice 3: SofaBuilder PARAMETRICO. Gera um sofa como PECAS
semanticas separadas (base, assentos SEPARADOS com vinco, encostos SEPARADOS, bracos,
pes, chaise opcional) a partir de um SofaSpec. NAO e caixa unica e NAO depende de
asset externo. Saida: lista de 'parts' (caixas com z0/z1 em m) e conversao pro formato
boxes do place_layout_skp.rb (corners in inches, h_in, z0_in, rgb, label).

Convencao: X=largura, Y=profundidade (frente=0, encosto=Y maior), Z=altura. Frente
do sofa = -Y (vira a parede-TV ao posicionar). Origem no canto (0,0,0).
"""
from __future__ import annotations

from tools.furniture_anatomy_spec import SofaSpec, sofa_spec   # noqa: F401

from core.scale import M_TO_IN as PT_TO_IN  # noqa: E402  (m->in; sofa standalone em metros)


def _darker(rgb, f):
    return [max(0, int(c * f)) for c in rgb]


def _p(label, kind, x0, y0, x1, y1, z0, z1, rgb):
    return {"label": label, "kind": kind,
            "x0": round(min(x0, x1), 4), "y0": round(min(y0, y1), 4),
            "x1": round(max(x0, x1), 4), "y1": round(max(y0, y1), 4),
            "z0": round(z0, 4), "z1": round(z1, 4), "rgb": list(rgb)}


def _seat_row(kind, prefix, x0, x1, y0, y1, z0, z1, n, gap, rgb, bevel=0.0):
    """n almofadas SEPARADAS (com vinco) em X[x0,x1]. bevel>0: topo INSET (chanfro) ->
    a almofada deixa de ser caixa reta (GPT cycle2: cushion_edge_radius, 'menos cubico').
    Corpo (z0..z1-b) + tampo inset b em x/y (z1-b..z1), MESMO kind -> bbox e gate intactos."""
    out = []
    w = (x1 - x0 - gap * (n - 1)) / n
    b = max(0.0, min(bevel, w / 2 - 0.01, (y1 - y0) / 2 - 0.01, (z1 - z0) / 2))
    for i in range(n):
        sx = x0 + i * (w + gap)
        if b > 0:
            zc = z1 - b
            out.append(_p(f"{prefix}_{i + 1}", kind, sx, y0, sx + w, y1, z0, zc, rgb))
            out.append(_p(f"{prefix}_{i + 1}_top", kind, sx + b, y0 + b, sx + w - b, y1 - b, zc, z1, rgb))
        else:
            out.append(_p(f"{prefix}_{i + 1}", kind, sx, y0, sx + w, y1, z0, z1, rgb))
    return out


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
    base_rgb = _darker(fab, 0.62)        # estrutura/madeira da base: bem mais escura (contraste)
    cush_rgb = fab                       # tecido linho (assentos)
    back_rgb = _darker(fab, 0.88)        # encosto levemente mais escuro (sombra/profundidade)
    Dtot = D if spec.variant == "straight" else max(D, spec.chaise_depth)
    cw = spec.chaise_width
    base_top = sh - ct
    back_z0 = sh - 0.03
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

    # --- pes (4 cantos do footprint em L) ---
    fz = (0.0, fh)
    foot = 0.08
    corners = [(0.04, main_y0 + 0.04), (W - 0.04 - foot, main_y0 + 0.04),
               (0.04, Dtot - 0.04 - foot), (W - 0.04 - foot, Dtot - 0.04 - foot)]
    if chaise_x:   # 2 pes extra na ponta funda da chaise — SOB o deck projetado
        # (chaise_seat_x, nao a borda externa: com a frente aberta o pe na faixa
        # da antiga muralha ficava orfao no ar — gramatica cycle002)
        cxl, cxr = chaise_seat_x
        corners += [(cxl + 0.04, 0.04), (cxr - 0.04 - foot, 0.04)]
    for i, (fx, fy) in enumerate(corners):
        parts.append(_p(f"foot_{i + 1}", "foot", fx, fy, fx + foot, fy + foot, fz[0], fz[1], feet))

    # --- bracos (bordas externas) ---
    # LINGUAGEM de classe (cycle002): arm_relief>0 = braco "flutua" sobre sapata
    # recuada (compensa massa de braco chunky — anti-bunker); arm_cap = tampo fino
    # levemente proud (linguagem formal). relief/cap = 0/False -> braco classico.
    relief, cap = spec.arm_relief, spec.arm_cap
    cap_t, cap_over, shoe_in = 0.04, 0.015, 0.03
    for side, (x0a, x1a), (ya0, ya1) in (("left", (0.0, aw), left_arm_y),
                                         ("right", (W - aw, W), right_arm_y)):
        body_z0 = fh + relief
        body_z1 = ah - (cap_t if cap else 0.0)
        if relief > 0:
            parts.append(_p(f"arm_{side}_shoe", "arm", x0a + shoe_in, ya0 + shoe_in,
                            x1a - shoe_in, ya1 - shoe_in, fh, body_z0, fab))
        parts.append(_p(f"arm_{side}", "arm", x0a, ya0, x1a, ya1, body_z0, body_z1, fab))
        if cap:
            parts.append(_p(f"arm_{side}_cap", "arm", x0a - cap_over, ya0 - cap_over,
                            x1a + cap_over, ya1 + cap_over, body_z1, ah, fab))

    # --- base/plataforma (corpo principal + chaise) ---
    rec = spec.base_recess  # recuo do plinto frontal (hardcode 0.06 PROMOVIDO a classe)
    parts.append(_p("base_main", "base", main_seat_x[0], main_y0 + rec, main_seat_x[1], Dtot, fh, base_top, base_rgb))
    if chaise_x:
        # GRAMATICA de chaise integrada (cycle002): a base da chaise herda o MESMO
        # recuo frontal do corpo (mesma linguagem de plinto, nao bloco ao chao)
        parts.append(_p("base_chaise", "base", chaise_seat_x[0], rec, chaise_seat_x[1], Dtot, fh, base_top, base_rgb))

    # --- assentos SEPARADOS (vinco) ---
    over = spec.seat_overhang   # lounge: almofada projeta sobre a base (sombra horizontal)
    parts += _seat_row("seat_cushion", "seat", main_seat_x[0], main_seat_x[1],
                       seat_front - over, seat_back, base_top, sh, n, gap, cush_rgb, bevel=spec.cushion_bevel)
    if chaise_x:
        # GRAMATICA de chaise integrada (cycle002): o vinco da chaise ALINHA com a
        # linha do assento do corpo (seat_front) — o deck le como UMA superficie
        # continua em L, nao "2 almofadas com split arbitrario no meio"
        cyl = [(0.0 - over, seat_front), (seat_front + 0.03, seat_back)]
        for j, (y0, y1) in enumerate(cyl):
            parts.append(_p(f"seat_chaise_{j + 1}", "seat_cushion", chaise_seat_x[0], y0,
                            chaise_seat_x[1], y1, base_top, sh, cush_rgb))

    # --- encostos SEPARADOS (corpo principal + sobre a chaise) ---
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
            if p["kind"] == "back_cushion":
                v = _shear_y(p, k, back_z0)
                p["verts8"] = v
                ys = [c[1] for c in v]
                p["y0"], p["y1"] = round(min(ys), 4), round(max(ys), 4)

    meta = {"variant": spec.variant, "seats": spec.seats, "n_parts": len(parts),
            "bbox_m": spec.bbox_m(), "front_axis": "-Y",
            "kinds": sorted({p["kind"] for p in parts})}
    return parts, meta


def place_sofa_boxes(parts, center_in, facing):
    """Posiciona o sofa (parts em m, frente=-Y local) na PLANTA: rotaciona pra a
    frente apontar 'facing' (vetor 2D, ex. sofa->TV) e translada pro center_in (em
    inches, coords do shell). Desenha cantos ROTACIONADOS (place_layout_skp.rb usa
    add_face(corners)), entao qualquer angulo funciona."""
    import math
    cx_in, cy_in = center_in
    fx, fy = facing
    nrm = math.hypot(fx, fy) or 1.0
    fx, fy = fx / nrm, fy / nrm
    theta = math.atan2(fx, -fy)        # frente local (0,-1) -> facing
    ct, st = math.cos(theta), math.sin(theta)
    W = max(p["x1"] for p in parts)
    D = max(p["y1"] for p in parts)
    cxl, cyl = W / 2.0, D / 2.0        # centro local do sofa
    boxes = []
    for p in parts:
        corners = []
        for lx, ly in ((p["x0"], p["y0"]), (p["x1"], p["y0"]),
                       (p["x1"], p["y1"]), (p["x0"], p["y1"])):
            rx, ry = lx - cxl, ly - cyl
            wx, wy = rx * ct - ry * st, rx * st + ry * ct
            corners.append([round(cx_in + wx * PT_TO_IN, 2), round(cy_in + wy * PT_TO_IN, 2)])
        xs = [c[0] for c in corners]
        ys = [c[1] for c in corners]
        boxes.append({
            "kind": p["kind"], "x0": min(xs), "y0": min(ys), "x1": max(xs), "y1": max(ys),
            "corners": corners,
            "h_in": round((p["z1"] - p["z0"]) * PT_TO_IN, 2),
            "z0_in": round(p["z0"] * PT_TO_IN, 2),
            "rgb": p["rgb"], "label": p["label"], "ambiguous": False, "decorative": False,
        })
    return boxes


def parts_to_boxes(parts, ox=0.0, oy=0.0):
    """Converte parts (m) pro formato boxes do place_layout_skp.rb (in inches, z0_in,
    h_in, corners). ox/oy desloca o sofa (p/ posicionar varios fixtures lado a lado)."""
    boxes = []
    for p in parts:
        x0, y0, x1, y1 = (p["x0"] + ox) * PT_TO_IN, (p["y0"] + oy) * PT_TO_IN, \
                         (p["x1"] + ox) * PT_TO_IN, (p["y1"] + oy) * PT_TO_IN
        boxes.append({
            "kind": p["kind"], "x0": x0, "y0": y0, "x1": x1, "y1": y1,
            "corners": [[round(x0, 2), round(y0, 2)], [round(x1, 2), round(y0, 2)],
                        [round(x1, 2), round(y1, 2)], [round(x0, 2), round(y1, 2)]],
            "h_in": round((p["z1"] - p["z0"]) * PT_TO_IN, 2),
            "z0_in": round(p["z0"] * PT_TO_IN, 2),
            "rgb": p["rgb"], "label": p["label"], "ambiguous": False, "decorative": False,
        })
    return boxes


if __name__ == "__main__":
    for v in ("straight", "chaise_right", "chaise_left"):
        parts, meta = build_sofa(sofa_spec(v))
        print(f"{v:14} {meta['n_parts']} pecas | kinds={meta['kinds']} | bbox={meta['bbox_m']}")
