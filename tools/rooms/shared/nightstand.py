"""nightstand_builder.py — CRIADO-MUDO parametrico como PECAS separadas (espelha bed/
wardrobe builder; regra Felipe: NAO bloco unico). De um NightstandSpec gera: 4 pes +
corpo + tampo (transborda) + gaveta (frente) + knob — material por papel.

Convencao: X=largura, Y=profundidade (FRENTE=Y=0=-Y, gaveta vira p/ fora), Z=altura.
Coloca via place_sofa_boxes (generico)."""
from __future__ import annotations

from tools.rooms.shared.anatomy import NIGHTSTAND_REQUIRED_PARTS, NightstandSpec, nightstand_spec  # noqa: F401,E501
from tools.rooms.shared.parts import PT_TO_IN, parts_to_boxes  # noqa: F401
from tools.rooms.shared.parts import part as _p
from tools.rooms.shared.parts import place_parts as place_nightstand_boxes  # noqa: F401


def build_nightstand(spec: NightstandSpec):
    spec.validate()
    W, D, H = spec.width, spec.depth, spec.height
    fh, tt, dt = spec.foot_h, spec.top_t, spec.drawer_t
    body = tuple(spec.body_rgb)
    top = tuple(spec.top_rgb)
    drawer = tuple(spec.drawer_rgb)
    foot = tuple(spec.foot_rgb)
    knob = tuple(spec.knob_rgb)
    fs, ei = spec.foot_size, spec.edge_inset
    parts = []

    # --- 4 pes ---
    for i, (fx, fy) in enumerate([(ei, ei), (W - ei - fs, ei),
                                  (ei, D - ei - fs), (W - ei - fs, D - ei - fs)]):
        parts.append(_p(f"pe_{i + 1}", "pe", fx, fy, fx + fs, fy + fs, 0.0, fh, foot))

    # --- corpo (recuado) + tampo (transborda) ---
    parts.append(_p("corpo", "corpo", ei, ei, W - ei, D - ei, fh, H - tt, body))
    parts.append(_p("tampo", "tampo", 0.0, 0.0, W, D, H - tt, H, top))

    # --- gaveta na FRENTE (Y[0,dt]) + knob ---
    gz0, gz1 = fh + spec.drawer_bottom_gap, H - tt - spec.drawer_top_gap
    parts.append(_p("gaveta", "gaveta", spec.drawer_side_inset, 0.0, W - spec.drawer_side_inset, dt, gz0, gz1, drawer))
    kz = (gz0 + gz1) / 2
    parts.append(_p("knob", "puxador", W / 2 - spec.knob_half_w, 0.0, W / 2 + spec.knob_half_w, dt + spec.knob_proud,
                 kz - spec.knob_half_h, kz + spec.knob_half_h, knob))

    meta = {"n_parts": len(parts), "bbox_m": spec.bbox_m(), "front_axis": "-Y",
            "kinds": sorted({p["kind"] for p in parts})}
    return parts, meta


if __name__ == "__main__":
    parts, meta = build_nightstand(nightstand_spec())
    print(f"criado {meta['n_parts']} pecas | kinds={meta['kinds']} | bbox={meta['bbox_m']}")
