"""Validação sem efeitos colaterais dos kinds permitidos em ambientes molhados.

Mantém exatamente as regras do guard legado do orquestrador.
"""
from __future__ import annotations

WET_KINDS = frozenset({
    "gabinete", "bancada_banho", "cuba", "espelho",
    "vaso", "box_vidro", "box",
})


def unexpected_wet_room_kinds(boxes) -> list[str]:
    """Retorna kinds estranhos, ordenados e sem duplicação; sem mutar boxes."""
    return sorted({
        str(box.get("kind"))
        for box in (boxes or [])
        if str(box.get("kind")) not in WET_KINDS
        and not str(box.get("kind")).startswith("kb_")
    })
