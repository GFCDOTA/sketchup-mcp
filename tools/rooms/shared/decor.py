"""Conversão genérica de decoração paramétrica para boxes orientados.

Usada inicialmente na sala, mas independente da categoria do cômodo.
"""
from __future__ import annotations


def place_decor_boxes(kind, center_in, facing, z_lift=0.0, module=None, **overrides):
    """Adapter de DECOR: build_decor(kind) (parts em metros, frente -Y) -> boxes
    orientados pra 'facing' em center_in (inches), REUSANDO place_sofa_boxes (rotacao
    provada). z_lift (m) sobe a peca (quadro na parede). module = grupo editavel no .skp."""
    from tools.rooms.shared.decor_builders import build_decor
    from tools.rooms.shared.parts import place_parts as place_sofa_boxes
    parts, _ = build_decor(kind, **overrides)
    if z_lift:
        for p in parts:
            p["z0"] += z_lift
            p["z1"] += z_lift
    bx = place_sofa_boxes(parts, center_in, facing)
    for b in bx:
        b["module"] = module or kind
    return bx
