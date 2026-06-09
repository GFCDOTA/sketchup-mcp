"""nightstand_builder.py — CRIADO-MUDO parametrico como PECAS separadas (espelha bed/
wardrobe builder; regra Felipe: NAO bloco unico). De um NightstandSpec gera: 4 pes +
corpo + tampo (transborda) + gaveta (frente) + knob — material por papel.

Convencao: X=largura, Y=profundidade (FRENTE=Y=0=-Y, gaveta vira p/ fora), Z=altura.
Coloca via place_sofa_boxes (generico)."""
from __future__ import annotations

from tools.furniture_anatomy_spec import NIGHTSTAND_REQUIRED_PARTS, NightstandSpec, nightstand_spec  # noqa: F401,E501
from tools.sofa_builder import PT_TO_IN, _p, parts_to_boxes  # noqa: F401
from tools.sofa_builder import place_sofa_boxes as place_nightstand_boxes  # noqa: F401


def build_nightstand(spec: NightstandSpec):
    spec.validate()
    W, D, H = spec.width, spec.depth, spec.height
    fh, tt, dt = spec.foot_h, spec.top_t, spec.drawer_t
    body = tuple(spec.body_rgb)
    top = tuple(spec.top_rgb)
    drawer = tuple(spec.drawer_rgb)
    foot = tuple(spec.foot_rgb)
    knob = tuple(spec.knob_rgb)
    fs = 0.05
    parts = []

    # --- 4 pes ---
    for i, (fx, fy) in enumerate([(0.02, 0.02), (W - 0.02 - fs, 0.02),
                                  (0.02, D - 0.02 - fs), (W - 0.02 - fs, D - 0.02 - fs)]):
        parts.append(_p(f"pe_{i + 1}", "pe", fx, fy, fx + fs, fy + fs, 0.0, fh, foot))

    # --- corpo (recuado) + tampo (transborda) ---
    parts.append(_p("corpo", "corpo", 0.02, 0.02, W - 0.02, D - 0.02, fh, H - tt, body))
    parts.append(_p("tampo", "tampo", 0.0, 0.0, W, D, H - tt, H, top))

    # --- gaveta na FRENTE (Y[0,dt]) + knob ---
    gz0, gz1 = fh + 0.04, H - tt - 0.03
    parts.append(_p("gaveta", "gaveta", 0.05, 0.0, W - 0.05, dt, gz0, gz1, drawer))
    kz = (gz0 + gz1) / 2
    parts.append(_p("knob", "puxador", W / 2 - 0.03, 0.0, W / 2 + 0.03, dt + 0.04, kz - 0.015, kz + 0.015, knob))

    meta = {"n_parts": len(parts), "bbox_m": spec.bbox_m(), "front_axis": "-Y",
            "kinds": sorted({p["kind"] for p in parts})}
    return parts, meta


if __name__ == "__main__":
    parts, meta = build_nightstand(nightstand_spec())
    print(f"criado {meta['n_parts']} pecas | kinds={meta['kinds']} | bbox={meta['bbox_m']}")
