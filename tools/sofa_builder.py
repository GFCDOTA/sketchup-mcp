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

PT_TO_IN = 39.3700787402   # m -> in (o shell usa pdf*PT_TO_IN; aqui o sofa e standalone em m)


def _darker(rgb, f):
    return [max(0, int(c * f)) for c in rgb]


def _p(label, kind, x0, y0, x1, y1, z0, z1, rgb):
    return {"label": label, "kind": kind,
            "x0": round(min(x0, x1), 4), "y0": round(min(y0, y1), 4),
            "x1": round(max(x0, x1), 4), "y1": round(max(y0, y1), 4),
            "z0": round(z0, 4), "z1": round(z1, 4), "rgb": list(rgb)}


def _seat_row(kind, prefix, x0, x1, y0, y1, z0, z1, n, gap, rgb):
    """n almofadas SEPARADAS (com vinco) em X[x0,x1]."""
    out = []
    w = (x1 - x0 - gap * (n - 1)) / n
    for i in range(n):
        sx = x0 + i * (w + gap)
        out.append(_p(f"{prefix}_{i + 1}", kind, sx, y0, sx + w, y1, z0, z1, rgb))
    return out


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
    base_rgb = _darker(fab, 0.80)
    cush_rgb = fab
    back_rgb = _darker(fab, 1.0)
    Dtot = D if spec.variant == "straight" else max(D, spec.chaise_depth)
    cw = spec.chaise_width
    base_top = sh - ct
    back_z0 = sh - 0.03
    main_y0 = Dtot - D           # frente do corpo principal (recuado se chaise + fundo)
    seat_back = Dtot - bt        # face frontal do encosto
    seat_front = seat_back - sd
    parts = []

    # --- secoes em X: corpo principal + chaise opcional ---
    if spec.variant == "chaise_right":
        chaise_x = (W - cw, W); main_x = (0.0, W - cw)
        left_arm_y = (main_y0, Dtot); right_arm_y = (0.0, Dtot)   # braco dir = externo da chaise
        main_seat_x = (main_x[0] + aw, main_x[1])
        chaise_seat_x = (chaise_x[0], chaise_x[1] - aw)
    elif spec.variant == "chaise_left":
        chaise_x = (0.0, cw); main_x = (cw, W)
        left_arm_y = (0.0, Dtot); right_arm_y = (main_y0, Dtot)   # braco esq = externo da chaise
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
    if chaise_x:   # 2 pes extra na ponta funda da chaise
        cxl, cxr = chaise_x
        corners += [(cxl + 0.04, 0.04), (cxr - 0.04 - foot, 0.04)]
    for i, (fx, fy) in enumerate(corners):
        parts.append(_p(f"foot_{i + 1}", "foot", fx, fy, fx + foot, fy + foot, fz[0], fz[1], feet))

    # --- bracos (bordas externas) ---
    parts.append(_p("arm_left", "arm", 0.0, left_arm_y[0], aw, left_arm_y[1], fh, ah, fab))
    parts.append(_p("arm_right", "arm", W - aw, right_arm_y[0], W, right_arm_y[1], fh, ah, fab))

    # --- base/plataforma (corpo principal + chaise) ---
    parts.append(_p("base_main", "base", main_seat_x[0], main_y0, main_seat_x[1], Dtot, fh, base_top, base_rgb))
    if chaise_x:
        parts.append(_p("base_chaise", "base", chaise_seat_x[0], 0.0, chaise_seat_x[1], Dtot, fh, base_top, base_rgb))

    # --- assentos SEPARADOS (vinco) ---
    parts += _seat_row("seat_cushion", "seat", main_seat_x[0], main_seat_x[1],
                       seat_front, seat_back, base_top, sh, n, gap, cush_rgb)
    if chaise_x:
        # chaise = assento FUNDO (deita as pernas): 2 almofadas ao longo de Y
        cyl = [(0.0, Dtot * 0.5), (Dtot * 0.5, seat_back)]
        for j, (y0, y1) in enumerate(cyl):
            parts.append(_p(f"seat_chaise_{j + 1}", "seat_cushion", chaise_seat_x[0], y0 + (0.03 if j else 0.0),
                            chaise_seat_x[1], y1, base_top, sh, cush_rgb))

    # --- encostos SEPARADOS (corpo principal + sobre a chaise) ---
    parts += _seat_row("back_cushion", "back", main_seat_x[0], main_seat_x[1],
                       seat_back, Dtot, back_z0, bh, n, gap, back_rgb)
    if chaise_x:
        parts.append(_p("back_chaise", "back_cushion", chaise_seat_x[0], seat_back,
                        chaise_seat_x[1], Dtot, back_z0, bh, back_rgb))

    meta = {"variant": spec.variant, "seats": spec.seats, "n_parts": len(parts),
            "bbox_m": spec.bbox_m(), "front_axis": "-Y",
            "kinds": sorted({p["kind"] for p in parts})}
    return parts, meta


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
