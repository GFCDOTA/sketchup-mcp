"""Peças de mobiliário reutilizadas entre sala e quarto.

A mesma cadeira atende mesa de jantar e estação de trabalho.
"""
from __future__ import annotations


def _chair_parts():
    """Cadeira de jantar ESTOFADA (frame metal preto + assento/encosto grafite =
    tecido do sofá). Metros, frente = -Y (encosto em +Y). place_sofa_boxes orienta."""
    from tools.rooms.shared.parts import part as _p
    w, d, sh, bh, lt = 0.45, 0.50, 0.45, 0.90, 0.028
    fabric, frame = (74, 72, 78), (26, 26, 29)
    parts = []
    for x0, y0 in ((0.02, 0.02), (w - 0.02 - lt, 0.02), (0.02, d - 0.02 - lt), (w - 0.02 - lt, d - 0.02 - lt)):
        parts.append(_p("leg", "foot", x0, y0, x0 + lt, y0 + lt, 0.0, sh - 0.05, frame))
    parts.append(_p("seat_frame", "frame", 0.02, 0.02, w - 0.02, d - 0.02, sh - 0.05, sh - 0.03, frame))
    parts.append(_p("seat", "seat", 0.015, 0.015, w - 0.015, d - 0.015, sh - 0.03, sh + 0.02, fabric))
    parts.append(_p("back_frame", "frame", 0.03, d - 0.045, w - 0.03, d - 0.02, sh, bh - 0.02, frame))
    parts.append(_p("back", "back", 0.02, d - 0.06, w - 0.02, d - 0.038, sh + 0.10, bh, fabric))
    return parts
