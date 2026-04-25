"""Peitoril/mureta automatic detector.

Substitui o JSON manual `pNN_peitoris.json` por extracao programatica via
filtro de cor MARROM (HSV) + filtros morfologicos (aspecto + tamanho).

Veja `service.detect_peitoris`.
"""
from peitoris.service import (
    DEFAULT_HEIGHT_M,
    PeitorilDetectionConfig,
    detect_peitoris,
    detect_peitoris_from_path,
)

__all__ = [
    "DEFAULT_HEIGHT_M",
    "PeitorilDetectionConfig",
    "detect_peitoris",
    "detect_peitoris_from_path",
]
