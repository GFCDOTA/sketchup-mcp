"""bed_builder.py — CAMA parametrica como PECAS semanticas separadas (espelha o
sofa_builder; regra Felipe: NAO bloco unico). A partir de um BedSpec gera: plinto
recuado + estrado (madeira) + colchao (linho) + N travesseiros (cabeceira) + manta
dobrada no pe — cada um com material por papel; as pecas macias ganham bevel no .rb.

Convencao igual ao sofa: X=largura (ao longo da cabeceira), Y=comprimento (PE=Y=0=
frente=-Y; CABECA=Y=L encosta no painel), Z=altura. Origem no canto (0,0,0). A
colocacao na planta reusa place_sofa_boxes (rotaciona -Y -> facing + translada)."""
from __future__ import annotations

from tools.furniture_anatomy_spec import BED_REQUIRED_PARTS, BedSpec, bed_spec  # noqa: F401
from tools.sofa_builder import PT_TO_IN, _darker, _p, parts_to_boxes  # noqa: F401
from tools.sofa_builder import place_sofa_boxes as place_bed_boxes      # noqa: F401  (generico)


def build_bed(spec: BedSpec):
    """Devolve (parts, meta). parts = pecas (caixas em m, com z0/z1)."""
    spec.validate()
    W, L = spec.width, spec.length
    bz0, btop, mtop = spec.base_z0, spec.base_top, spec.mattress_top
    estr = tuple(spec.estrado_rgb)
    plinth = _darker(estr, 0.7)
    parts = []

    # --- BASE por estilo de classe (cama cycle001): plinto recuado (reveal
    # parametrico) | pes aparentes (underbed aberto) | box flush + saia ---
    rv = spec.reveal
    rail_rgb = _darker(estr, 0.82)   # cycle002: rail/shadow line — base DESENHADA
    if spec.base_style == "legs":
        lh, sec = spec.leg_height, spec.leg_section
        for i, (fx, fy) in enumerate([(0.05, 0.05), (W - 0.05 - sec, 0.05),
                                      (0.05, L - 0.05 - sec), (W - 0.05 - sec, L - 0.05 - sec),
                                      (0.05, L / 2 - sec / 2), (W - 0.05 - sec, L / 2 - sec / 2)]):
            parts.append(_p(f"pe_{i + 1}", "estrado", fx, fy, fx + sec, fy + sec,
                            0.0, lh, plinth))
        # rail estrutural (longarina escura) sob o deck = frame desenhado
        rail_h = min(0.06, (btop - lh) * 0.45)
        parts.append(_p("rail", "estrado", 0.0, 0.0, W, L, lh, lh + rail_h, rail_rgb))
        parts.append(_p("estrado", "estrado", 0.0, 0.0, W, L, lh + rail_h, btop, estr))
    elif spec.base_style == "box":
        # box com SHADOW LINE: faixa inferior recuada (junta horizontal) — a
        # massa continua inequivoca mas a base le como desenhada, nao caixote
        sl = 0.06
        parts.append(_p("box_shadow", "estrado", 0.02, 0.02, W - 0.02, L - 0.02,
                        0.0, sl, _darker(estr, 0.55)))
        parts.append(_p("box_base", "estrado", 0.0, 0.0, W, L, sl, bz0, plinth))
        parts.append(_p("estrado", "estrado", 0.0, 0.0, W, L, bz0, btop, estr))
        if spec.skirt:   # saia: paineis finos ate o chao (esconde a base)
            sk = _darker(tuple(spec.mattress_rgb), 0.92)
            parts.append(_p("saia_f", "manta", -0.01, -0.01, W + 0.01, 0.02, 0.0, btop, sk))
            parts.append(_p("saia_l", "manta", -0.01, -0.01, 0.02, L - 0.05, 0.0, btop, sk))
            parts.append(_p("saia_r", "manta", W - 0.02, -0.01, W + 0.01, L - 0.05, 0.0, btop, sk))
    else:   # plinth (default historico) + rail no estrado (shadow line dupla)
        parts.append(_p("plinto", "estrado", rv, rv, W - rv, L - rv, 0.0, bz0, plinth))
        rail_h = min(0.05, (btop - bz0) * 0.4)
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
        parts.append(_p("cabeceira_ledge", "cabeceira", -ov - 0.02, L - hbt - 0.10,
                        W + ov + 0.02, L, hh, hh + 0.04, _darker(hb_rgb, 0.85)))
    elif spec.headboard_style == "upholstered":
        # acolhedora: BOLSTER central proud (volume macio emoldurado)
        ins = 0.07
        parts.append(_p("cabeceira_bolster", "cabeceira", ins, L - hbt - 0.05,
                        W - ins, L - hbt, mtop + 0.04, hh - ins,
                        tuple(min(255, int(c * 1.06)) for c in hb_rgb)))
    # contained/plain: painel unico flush (sem gesto extra)

    # --- colchao (linho), transbordando levemente o estrado ---
    parts.append(_p("colchao", "colchao", 0.02, 0.02, W - 0.02, L - 0.02, btop, mtop, tuple(spec.mattress_rgb)))

    # --- travesseiros SEPARADOS na cabeceira (Y alto) ---
    pw, pd, ph, n = spec.pillow_w, spec.pillow_depth, spec.pillow_h, spec.n_pillows
    gap = 0.08
    span = n * pw + (n - 1) * gap
    x0p = (W - span) / 2.0
    py0 = L - 0.06 - pd
    pil = tuple(spec.pillow_rgb)
    for i in range(n):
        sx = x0p + i * (pw + gap)
        parts.append(_p(f"travesseiro_{i + 1}", "travesseiro", sx, py0, sx + pw, py0 + pd,
                        mtop, mtop + ph, pil))

    # --- manta/edredom dobrado no PE (Y baixo) ---
    parts.append(_p("manta", "manta", 0.04, 0.10, W - 0.04, 0.10 + spec.blanket_depth,
                    mtop, mtop + spec.blanket_h, tuple(spec.blanket_rgb)))

    meta = {"size": spec.size, "n_parts": len(parts), "bbox_m": spec.bbox_m(),
            "front_axis": "-Y (pe)", "kinds": sorted({p["kind"] for p in parts})}
    return parts, meta


if __name__ == "__main__":
    for sz in ("king", "queen", "casal", "solteiro"):
        parts, meta = build_bed(bed_spec(sz))
        print(f"{sz:10} {meta['n_parts']} pecas | kinds={meta['kinds']} | bbox={meta['bbox_m']}")
