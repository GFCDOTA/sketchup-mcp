"""bed_builder.py — CAMA parametrica como PECAS semanticas separadas (espelha o
sofa_builder; regra Felipe: NAO bloco unico). A partir de um BedSpec gera: plinto
recuado + estrado (madeira) + colchao (linho) + N travesseiros (cabeceira) + manta
dobrada no pe — cada um com material por papel; as pecas macias ganham bevel no .rb.

Convencao igual ao sofa: X=largura (ao longo da cabeceira), Y=comprimento (PE=Y=0=
frente=-Y; CABECA=Y=L encosta no painel), Z=altura. Origem no canto (0,0,0). A
colocacao na planta reusa place_sofa_boxes (rotaciona -Y -> facing + translada)."""
from __future__ import annotations

from tools.rooms.shared.anatomy import BED_REQUIRED_PARTS, BedSpec, bed_spec  # noqa: F401
from tools.rooms.shared.parts import PT_TO_IN, parts_to_boxes  # noqa: F401
from tools.rooms.shared.parts import darker as _darker, part as _p
from tools.rooms.shared.parts import place_parts as place_bed_boxes      # noqa: F401  (generico)


def build_bed(spec: BedSpec):
    """Devolve (parts, meta). parts = pecas (caixas em m, com z0/z1)."""
    spec.validate()
    W, L = spec.width, spec.length
    bz0, btop, mtop = spec.base_z0, spec.base_top, spec.mattress_top
    estr = tuple(spec.estrado_rgb)
    plinth = _darker(estr, spec.plinth_shade)
    parts = []

    # --- BASE por estilo de classe (cama cycle001): plinto recuado (reveal
    # parametrico) | pes aparentes (underbed aberto) | box flush + saia ---
    rv = spec.reveal
    rail_rgb = _darker(estr, spec.rail_shade)   # cycle002: rail/shadow line — base DESENHADA
    if spec.base_style == "legs":
        lh, sec = spec.leg_height, spec.leg_section
        li = spec.leg_inset
        for i, (fx, fy) in enumerate([(li, li), (W - li - sec, li),
                                      (li, L - li - sec), (W - li - sec, L - li - sec),
                                      (li, L / 2 - sec / 2), (W - li - sec, L / 2 - sec / 2)]):
            parts.append(_p(f"pe_{i + 1}", "estrado", fx, fy, fx + sec, fy + sec,
                            0.0, lh, plinth))
        # rail estrutural (longarina escura) sob o deck = frame desenhado
        rail_h = min(spec.leg_rail_max, (btop - lh) * spec.leg_rail_frac)
        parts.append(_p("rail", "estrado", 0.0, 0.0, W, L, lh, lh + rail_h, rail_rgb))
        parts.append(_p("estrado", "estrado", 0.0, 0.0, W, L, lh + rail_h, btop, estr))
    elif spec.base_style == "box":
        # box com SHADOW LINE: faixa inferior recuada (junta horizontal) — a
        # massa continua inequivoca mas a base le como desenhada, nao caixote
        sl, bi = spec.box_shadow_h, spec.box_shadow_inset
        parts.append(_p("box_shadow", "estrado", bi, bi, W - bi, L - bi,
                        0.0, sl, _darker(estr, spec.box_shadow_shade)))
        parts.append(_p("box_base", "estrado", 0.0, 0.0, W, L, sl, bz0, plinth))
        parts.append(_p("estrado", "estrado", 0.0, 0.0, W, L, bz0, btop, estr))
        if spec.skirt:   # saia: paineis finos ate o chao (esconde a base)
            sk = _darker(tuple(spec.mattress_rgb), spec.skirt_shade)
            so, st, sbc = spec.skirt_overhang, spec.skirt_t, spec.skirt_back_cut
            parts.append(_p("saia_f", "manta", -so, -so, W + so, st, 0.0, btop, sk))
            parts.append(_p("saia_l", "manta", -so, -so, st, L - sbc, 0.0, btop, sk))
            parts.append(_p("saia_r", "manta", W - st, -so, W + so, L - sbc, 0.0, btop, sk))
    else:   # plinth (default historico) + rail no estrado (shadow line dupla)
        parts.append(_p("plinto", "estrado", rv, rv, W - rv, L - rv, 0.0, bz0, plinth))
        rail_h = min(spec.plinth_rail_max, (btop - bz0) * spec.plinth_rail_frac)
        parts.append(_p("rail", "estrado", 0.0, 0.0, W, L, bz0, bz0 + rail_h, rail_rgb))
        parts.append(_p("estrado", "estrado", 0.0, 0.0, W, L, bz0 + rail_h, btop, estr))

    # --- cabeceira: ASSINATURA por estilo (cycle002 — legivel a distancia) ---
    hbt = spec.headboard_t
    ov = spec.headboard_overhang
    hb_rgb = tuple(spec.headboard_rgb)
    hh = spec.headboard_h
    parts.append(_p("cabeceira", "cabeceira", -ov, L - hbt, W + ov, L, 0.0, hh, hb_rgb))
    if spec.headboard_style == "panel":
        # arquitetonica: LEDGE horizontal (prateleira fina proud) no topo
        lo = spec.ledge_over
        parts.append(_p("cabeceira_ledge", "cabeceira", -ov - lo, L - hbt - spec.ledge_depth,
                        W + ov + lo, L, hh, hh + spec.ledge_h, _darker(hb_rgb, spec.ledge_shade)))
    elif spec.headboard_style == "upholstered":
        # acolhedora: BOLSTER central proud (volume macio emoldurado)
        ins = spec.bolster_inset
        parts.append(_p("cabeceira_bolster", "cabeceira", ins, L - hbt - spec.bolster_proud,
                        W - ins, L - hbt, mtop + spec.bolster_above_mattress, hh - ins,
                        tuple(min(255, int(c * spec.bolster_tint)) for c in hb_rgb)))
    # contained/plain: painel unico flush (sem gesto extra)

    # --- colchao (linho), transbordando levemente o estrado ---
    me = spec.mattress_edge
    parts.append(_p("colchao", "colchao", me, me, W - me, L - me, btop, mtop, tuple(spec.mattress_rgb)))

    # --- travesseiros SEPARADOS na cabeceira (Y alto) ---
    pw, pd, ph, n = spec.pillow_w, spec.pillow_depth, spec.pillow_h, spec.n_pillows
    gap = spec.pillow_gap
    span = n * pw + (n - 1) * gap
    x0p = (W - span) / 2.0
    py0 = L - spec.pillow_back_gap - pd
    pil = tuple(spec.pillow_rgb)
    for i in range(n):
        sx = x0p + i * (pw + gap)
        parts.append(_p(f"travesseiro_{i + 1}", "travesseiro", sx, py0, sx + pw, py0 + pd,
                        mtop, mtop + ph, pil))

    # --- manta/edredom dobrado no PE (Y baixo) ---
    bsi, bfo = spec.blanket_side_inset, spec.blanket_foot_offset
    parts.append(_p("manta", "manta", bsi, bfo, W - bsi, bfo + spec.blanket_depth,
                    mtop, mtop + spec.blanket_h, tuple(spec.blanket_rgb)))

    meta = {"size": spec.size, "n_parts": len(parts), "bbox_m": spec.bbox_m(),
            "front_axis": "-Y (pe)", "kinds": sorted({p["kind"] for p in parts})}
    return parts, meta


if __name__ == "__main__":
    for sz in ("king", "queen", "casal", "solteiro"):
        parts, meta = build_bed(bed_spec(sz))
        print(f"{sz:10} {meta['n_parts']} pecas | kinds={meta['kinds']} | bbox={meta['bbox_m']}")
