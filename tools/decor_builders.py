"""decor_builders.py — Intent-to-Scene slice 1: builders PROCEDURAIS dos componentes
de decor da sala. Cada build_X(spec) devolve (parts, meta) no MESMO formato do
sofa_builder: parts = caixas em metros {label, kind, x0..z1, rgb} (+ verts8 opcional
p/ peca nao-axis-aligned), frente = -Y, origem no canto (0,0,0).

Sem asset externo, sem 3D Warehouse: formas parametricas leves. O SceneComposer
posiciona estas parts na sala (rotacao 0/90/180/270 + translacao + offset Z) e o
render harness desenha via render_parts_iso / place_layout_skp.rb.
"""
from __future__ import annotations

from tools.decor_anatomy_spec import (AccentSeatSpec, CoffeeTableSpec,   # noqa: F401
                                      CurtainSpec, FloorLampSpec, PlantSpec,
                                      RugSpec, SideTableSpec, WallArtSpec,
                                      decor_spec)


def _p(label, kind, x0, y0, x1, y1, z0, z1, rgb):
    return {"label": label, "kind": kind,
            "x0": round(min(x0, x1), 4), "y0": round(min(y0, y1), 4),
            "x1": round(max(x0, x1), 4), "y1": round(max(y0, y1), 4),
            "z0": round(z0, 4), "z1": round(z1, 4), "rgb": list(rgb)}


def _meta(kind, parts):
    xs = [p["x0"] for p in parts] + [p["x1"] for p in parts]
    ys = [p["y0"] for p in parts] + [p["y1"] for p in parts]
    zs = [p["z0"] for p in parts] + [p["z1"] for p in parts]
    return {"type": kind, "n_parts": len(parts), "front_axis": "-Y",
            "bbox_m": (round(max(xs) - min(xs), 3), round(max(ys) - min(ys), 3),
                       round(max(zs) - min(zs), 3)),
            "kinds": sorted({p["kind"] for p in parts})}


def build_rug(spec: RugSpec):
    """Campo central + borda em moldura (4 tiras), tudo na espessura do tapete."""
    spec.validate()
    W, D, t, b = spec.width, spec.depth, spec.thickness, spec.border_w
    f, br = spec.field_rgb, spec.border_rgb
    parts = [
        _p("field", "rug_field", b, b, W - b, D - b, 0.0, t, f),
        _p("border_s", "rug_border", 0.0, 0.0, W, b, 0.0, t, br),
        _p("border_n", "rug_border", 0.0, D - b, W, D, 0.0, t, br),
        _p("border_w", "rug_border", 0.0, b, b, D - b, 0.0, t, br),
        _p("border_e", "rug_border", W - b, b, W, D - b, 0.0, t, br),
    ]
    return parts, _meta("rug", parts)


def build_coffee_table(spec: CoffeeTableSpec):
    """Tampo-laje pedra + 2 pernas-laje metal recuadas."""
    spec.validate()
    W, D, H, tt = spec.width, spec.depth, spec.height, spec.top_t
    lt, ix, iy = spec.leg_t, spec.leg_inset_x, spec.leg_inset_y
    parts = [
        _p("top", "top", 0.0, 0.0, W, D, H - tt, H, spec.top_rgb),
        _p("leg_left", "leg", ix, iy, ix + lt, D - iy, 0.0, H - tt, spec.leg_rgb),
        _p("leg_right", "leg", W - ix - lt, iy, W - ix, D - iy, 0.0, H - tt, spec.leg_rgb),
    ]
    return parts, _meta("coffee_table", parts)


def build_side_table(spec: SideTableSpec):
    """Tampo disco + haste fina + base disco (discos = caixas finas; le redondo
    no render barato e vira cilindro quando o builder SU evoluir)."""
    spec.validate()
    d, H = spec.diameter, spec.height
    c = d / 2.0
    st, bt = spec.stem_t / 2.0, spec.base_d / 2.0
    parts = [
        _p("base", "base", c - bt, c - bt, c + bt, c + bt, 0.0, spec.base_t, spec.base_rgb),
        _p("stem", "stem", c - st, c - st, c + st, c + st, spec.base_t, H - spec.top_t, spec.stem_rgb),
        _p("top", "top", 0.0, 0.0, d, d, H - spec.top_t, H, spec.top_rgb),
    ]
    return parts, _meta("side_table", parts)


def build_floor_lamp(spec: FloorLampSpec):
    """Base disco + haste fina + cupula tambor AFUNILADA (verts8: boca larga
    embaixo, topo menor — nao le como caixa)."""
    spec.validate()
    H = spec.height
    c = spec.shade_d / 2.0
    bt, st = spec.base_d / 2.0, spec.stem_t / 2.0
    sh0 = H - spec.shade_h
    parts = [
        _p("base", "base", c - bt, c - bt, c + bt, c + bt, 0.0, spec.base_t, spec.base_rgb),
        _p("stem", "stem", c - st, c - st, c + st, c + st, spec.base_t, sh0, spec.stem_rgb),
    ]
    shade = _p("shade", "shade", c - c, c - c, c + c, c + c, sh0, H, spec.shade_rgb)
    r0, r1 = c, spec.shade_top_d / 2.0
    shade["verts8"] = [
        (c - r0, c - r0, sh0), (c + r0, c - r0, sh0), (c + r0, c + r0, sh0), (c - r0, c + r0, sh0),
        (c - r1, c - r1, H), (c + r1, c - r1, H), (c + r1, c + r1, H), (c - r1, c + r1, H),
    ]
    parts.append(shade)
    return parts, _meta("floor_lamp", parts)


def build_wall_art(spec: WallArtSpec):
    """Moldura fina + tela em MOSAICO de colunas (campo quente + faixa escura como
    faixas proprias, sem sobreposicao coplanar — o painter sort do mpl come face
    grande atras de face proud). Plano do quadro = XZ; frente = -Y."""
    spec.validate()
    W, H, Dp, ft = spec.width, spec.height, spec.depth, spec.frame_t
    cd = Dp * 0.55   # tela recuada dentro da moldura
    parts = [
        _p("frame_l", "frame", 0.0, 0.0, ft, Dp, 0.0, H, spec.frame_rgb),
        _p("frame_r", "frame", W - ft, 0.0, W, Dp, 0.0, H, spec.frame_rgb),
        _p("frame_b", "frame", ft, 0.0, W - ft, Dp, 0.0, ft, spec.frame_rgb),
        _p("frame_t", "frame", ft, 0.0, W - ft, Dp, H - ft, H, spec.frame_rgb),
    ]
    # colunas (x0,x1,[faixas (z0,z1,rgb)]): campo quente baixo-esq + barra vertical escura
    cols = [
        (ft, W * 0.12, []),
        (W * 0.12, W * 0.55, [(H * 0.18, H * 0.62, spec.accent_rgb)]),
        (W * 0.55, W * 0.62, []),
        (W * 0.62, W * 0.70, [(H * 0.12, H * 0.88, spec.accent2_rgb)]),
        (W * 0.70, W - ft, []),
    ]
    i = 0
    for x0, x1, bands in cols:
        zcur = ft
        for z0, z1, rgb in bands + [(H - ft, H - ft, None)]:
            if z0 > zcur:
                i += 1
                parts.append(_p(f"canvas_{i}", "canvas", x0, cd, x1, Dp, zcur, z0, spec.canvas_rgb))
            if rgb is not None and z1 > z0:
                i += 1
                parts.append(_p(f"accent_{i}", "art_accent", x0, cd - 0.005, x1, Dp, z0, z1, rgb))
            zcur = max(zcur, z1)
    return parts, _meta("wall_art", parts)


def build_curtain(spec: CurtainSpec):
    """Painel ondulado low-poly: dobras verticais alternando offset em Y + varao.
    Plano da cortina = XZ (corre ao longo de X); frente = -Y. panel_split=2 ->
    dobras so nas 2 pontas (paineis recolhidos de panel_w cada, vao central
    aberto = cortina-moldura); o varao continua varrendo a largura inteira."""
    spec.validate()
    W, H, fw, amp, t = spec.width, spec.height, spec.fold_w, spec.fold_amp, spec.thickness
    if spec.panel_split == 2:
        spans = [(0.0, spec.panel_w), (W - spec.panel_w, W)]
    else:
        spans = [(0.0, W)]
    parts = []
    i = 0
    for x_start, x_end in spans:
        pw = x_end - x_start
        n = max(2, round(pw / fw))
        pfw = pw / n                # dobras exatas, sem sobra
        for j in range(n):
            y0 = amp if j % 2 else 0.0
            i += 1
            parts.append(_p(f"fold_{i}", "panel_fold",
                            x_start + j * pfw, y0, x_start + (j + 1) * pfw, y0 + t,
                            0.0, H, spec.panel_rgb))
    rod = spec.rod_d
    parts.append(_p("rod", "rod", -spec.rod_overhang, amp / 2, W + spec.rod_overhang,
                    amp / 2 + rod, H, H + rod, spec.rod_rgb))
    return parts, _meta("curtain", parts)


def build_plant(spec: PlantSpec):
    """Vaso + tronco + 3 volumes verdes sobrepostos decrescentes (com offsets
    laterais leves = silhueta organica, deterministica)."""
    spec.validate()
    H, pw, ph = spec.height, spec.pot_w, spec.pot_h
    fol = spec.foliage_w
    c = fol / 2.0
    tt = spec.trunk_t / 2.0
    p0 = c - pw / 2.0
    trunk_top = ph + (H - ph) * 0.30
    parts = [
        _p("pot", "pot", p0, p0, p0 + pw, p0 + pw, 0.0, ph, spec.pot_rgb),
        _p("trunk", "trunk", c - tt, c - tt, c + tt, c + tt, ph, trunk_top, spec.trunk_rgb),
    ]
    layers = [   # (largura, z0, z1, dx, dy) — sobrepostos, decrescentes, offsets leves
        (fol, trunk_top - 0.06, ph + (H - ph) * 0.62, 0.0, 0.0),
        (fol * 0.78, ph + (H - ph) * 0.52, ph + (H - ph) * 0.85, -0.04, 0.03),
        (fol * 0.55, ph + (H - ph) * 0.78, H, 0.03, -0.02),
    ]
    g = spec.foliage_rgb
    shades = [g, tuple(min(255, int(v * 1.12)) for v in g), tuple(int(v * 0.88) for v in g)]
    for i, (w, z0, z1, dx, dy) in enumerate(layers):
        h = w / 2.0
        parts.append(_p(f"foliage_{i + 1}", "foliage",
                        c - h + dx, c - h + dy, c + h + dx, c + h + dy, z0, z1, shades[i]))
    return parts, _meta("plant_placeholder", parts)


def build_accent_seat(spec: AccentSeatSpec):
    """4 pes finos recuados + assento + encosto baixo no fundo. Frente = -Y
    (encosto fica em Y alto, igual ao sofa)."""
    spec.validate()
    W, D, H = spec.width, spec.depth, spec.height
    sh, lh, lt, ins, bt = spec.seat_h, spec.leg_h, spec.leg_t, spec.leg_inset, spec.back_t
    parts = []
    for tag, (x0, y0) in (("fl", (ins, ins)), ("fr", (W - ins - lt, ins)),
                          ("bl", (ins, D - ins - lt)), ("br", (W - ins - lt, D - ins - lt))):
        parts.append(_p(f"leg_{tag}", "leg", x0, y0, x0 + lt, y0 + lt, 0.0, lh, spec.leg_rgb))
    parts.append(_p("seat", "seat", 0.0, 0.0, W, D, lh, sh, spec.seat_rgb))
    back_rgb = tuple(int(v * 0.94) for v in spec.seat_rgb)   # encosto um tom abaixo
    parts.append(_p("back", "back", 0.0, D - bt, W, D, sh, H, back_rgb))
    return parts, _meta("accent_seat", parts)


BUILDERS = {
    "rug": (RugSpec, build_rug),
    "coffee_table": (CoffeeTableSpec, build_coffee_table),
    "side_table": (SideTableSpec, build_side_table),
    "floor_lamp": (FloorLampSpec, build_floor_lamp),
    "wall_art": (WallArtSpec, build_wall_art),
    "curtain": (CurtainSpec, build_curtain),
    "plant_placeholder": (PlantSpec, build_plant),
    "accent_seat": (AccentSeatSpec, build_accent_seat),
}


def build_decor(kind, **overrides):
    """Atalho: build_decor('rug', width=3.2) -> (parts, meta)."""
    cls, fn = BUILDERS[kind]
    s = cls()
    for k, v in overrides.items():
        setattr(s, k, v)
    return fn(s.validate())


if __name__ == "__main__":
    for kind in BUILDERS:
        parts, meta = build_decor(kind)
        print(f"{kind:18} {meta['n_parts']:2}p bbox={meta['bbox_m']} kinds={meta['kinds']}")
