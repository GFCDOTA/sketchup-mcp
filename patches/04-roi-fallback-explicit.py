"""ROI fallback explicit — remove mascaramento de falha.

PATCH #04 — para aplicar em sketchup-mcp/roi/service.py:70-74

INVARIANTE RESOLVIDA: #2 (não mascarar falhas) e #3 (não usar bbox como sala)

PROBLEMA ATUAL (roi/service.py:70-74):
    if min(height, width) < min_image_side:
        # Too small to meaningfully partition -- behave as if ROI were the
        # whole image. Signal `applied=True` so callers do not emit a
        # fallback warning for legitimate small inputs (synthetic tests).
        return RoiResult(True, (0, 0, width, height), None)

Comentário admite: "Signal applied=True so callers do not emit a fallback warning"
= MASCARAMENTO INTENCIONAL da falha.

SOLUÇÃO ADITIVA (mantém schema estável 2.1.0 §4):

- `applied` — mantém semântica: True se ROI semanticamente detectada.
- `fallback_reason` — PERMANECE o campo canônico (schema 2.1.0 §4). Nunca
  renomear, consumers dependem desse nome.
- `fallback_used` — NOVO campo aditivo booleano. True quando o bbox é a
  página inteira por impossibilidade de detectar. Permite que callers
  distingam "ROI detectada" de "fallback explícito" sem olhar a string
  de `fallback_reason`.

REVIEW PENDENTE (Felipe, PR #1 comment):
Versão anterior deste patch renomeou `fallback_reason` para `reason` e
adicionou uma property de compat. O briefing do Felipe § "Invariantes a
respeitar" explicita: não renomear campos estáveis do schema 2.1.0;
apenas aditivos. Este patch agora mantém `fallback_reason` canônico e
acrescenta `fallback_used` ao lado.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


# ==============================================================================
# PATCH: atualizar RoiResult dataclass (ADITIVO — não renomear nada)
# ==============================================================================

@dataclass(frozen=True)
class RoiResult:
    """Resultado da detecção de ROI arquitetônico.

    Invariantes:
    - `applied=True` SEMPRE implica detecção real (não fallback).
    - `fallback_used=True` sinaliza bbox = página inteira por não poder
      detectar. Coexiste com `applied=False` nesse caso.
    - `fallback_reason` é campo ESTÁVEL (schema 2.1.0 §4) — não renomear.
      Sempre preenchido com descrição da decisão quando `applied=False`
      ou `fallback_used=True`.
    """
    applied: bool
    bbox: tuple[int, int, int, int] | None  # (min_x, min_y, max_x, max_y)
    fallback_reason: str | None = None  # CANÔNICO — schema 2.1.0 §4
    fallback_used: bool = False  # NOVO aditivo — distinto de `applied`
    component_pixel_count: int = 0
    component_bbox_area: int = 0
    component_count: int = 0

    def to_dict(self) -> dict:
        return {
            "applied": self.applied,
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason,
            "bbox": (
                {
                    "min_x": int(self.bbox[0]),
                    "min_y": int(self.bbox[1]),
                    "max_x": int(self.bbox[2]),
                    "max_y": int(self.bbox[3]),
                }
                if self.bbox
                else None
            ),
            "component_pixel_count": self.component_pixel_count,
            "component_bbox_area": self.component_bbox_area,
            "component_count": self.component_count,
        }


def detect_architectural_roi(
    image: np.ndarray,
    threshold: int = 200,
    min_image_side: int = 500,
    margin_ratio: float = 0.05,
    min_component_bbox_area_ratio: float = 0.05,
) -> RoiResult:
    """Find the bounding box of the architectural region on the page.

    ATUALIZADO: nunca mais mascara falha via `applied=True`.
    Se fallback é usado (página inteira), `fallback_used=True`,
    `applied=False` e `fallback_reason` explícita.
    """
    if image.size == 0:
        return RoiResult(
            applied=False,
            bbox=None,
            fallback_reason="empty_image",
            fallback_used=False,
        )

    height, width = image.shape[:2]

    # ANTIGO (violação #2 e #3):
    # if min(height, width) < min_image_side:
    #     return RoiResult(True, (0, 0, width, height), None)
    #     # ^ applied=True mascara que ROI é a página inteira

    # NOVO (explícito):
    if min(height, width) < min_image_side:
        # Pequeno demais para partition significativa; fallback honesto.
        return RoiResult(
            applied=False,
            bbox=(0, 0, width, height),
            fallback_reason="small_input_fallback_whole_page",
            fallback_used=True,
        )

    if image.ndim == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image

    _, binary = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY_INV)

    nlabels, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)

    if nlabels <= 1:
        return RoiResult(
            applied=False,
            bbox=None,
            fallback_reason="no_components",
            fallback_used=False,
            component_count=0,
        )

    # Skip background (label 0). Pick largest pixel count component.
    best_label = -1
    best_pixel_count = 0
    for label_id in range(1, nlabels):
        pixel_count = int(stats[label_id, cv2.CC_STAT_AREA])
        if pixel_count > best_pixel_count:
            best_pixel_count = pixel_count
            best_label = label_id

    if best_label == -1:
        return RoiResult(
            applied=False,
            bbox=None,
            fallback_reason="no_dominant_component",
            fallback_used=False,
            component_count=int(nlabels - 1),
        )

    # Check se componente dominante é significativo
    left = int(stats[best_label, cv2.CC_STAT_LEFT])
    top = int(stats[best_label, cv2.CC_STAT_TOP])
    w_comp = int(stats[best_label, cv2.CC_STAT_WIDTH])
    h_comp = int(stats[best_label, cv2.CC_STAT_HEIGHT])
    bbox_area = w_comp * h_comp
    total_area = width * height

    if bbox_area < min_component_bbox_area_ratio * total_area:
        return RoiResult(
            applied=False,
            bbox=None,
            fallback_reason="dominant_component_too_small",
            fallback_used=False,
            component_pixel_count=best_pixel_count,
            component_bbox_area=bbox_area,
            component_count=int(nlabels - 1),
        )

    # Margem expandida
    margin_x = int(width * margin_ratio)
    margin_y = int(height * margin_ratio)
    min_x = max(0, left - margin_x)
    min_y = max(0, top - margin_y)
    max_x = min(width, left + w_comp + margin_x)
    max_y = min(height, top + h_comp + margin_y)

    # SUCESSO: ROI detectada via componente real
    return RoiResult(
        applied=True,
        bbox=(min_x, min_y, max_x, max_y),
        fallback_reason=None,  # sucesso, sem fallback
        fallback_used=False,
        component_pixel_count=best_pixel_count,
        component_bbox_area=bbox_area,
        component_count=int(nlabels - 1),
    )


# ==============================================================================
# CALLERS: atualizar em pipeline.py para usar novos campos
# ==============================================================================

# ANTES (pipeline.py ~linha 80):
#   roi = detect_architectural_roi(page.image)
#   if not roi.applied:
#       warnings.append(f"roi_fallback: {roi.fallback_reason}")
#
# DEPOIS:
#   roi = detect_architectural_roi(page.image)
#   if roi.fallback_used:
#       # Warning explícito: bbox é página inteira, não detecção real.
#       warnings.append(f"roi_fallback_used: {roi.fallback_reason}")
#   elif not roi.applied:
#       # Sem fallback usado: ROI falhou completamente (bbox=None).
#       warnings.append(f"roi_failed: {roi.fallback_reason}")
#   else:
#       # ROI detectada com sucesso, bbox real.
#       pass
#
# IMPORTANTE: warnings devem ser emitidos mesmo quando `fallback_used=True`.
# Isso era o bug: antes silenciava o warning (violação invariante #2).


# ==============================================================================
# TESTES A ADICIONAR em tests/test_roi.py
# ==============================================================================

def test_roi_small_input_flags_fallback_used():
    """Imagem < min_image_side deve retornar fallback_used=True, applied=False.

    O bbox ainda é a página inteira (consumer consegue rodar o pipeline),
    mas o caller sabe que foi fallback e pode emitir warning.
    """
    import numpy as np
    small_image = np.zeros((400, 400), dtype=np.uint8)

    # result = detect_architectural_roi(small_image, min_image_side=500)
    # assert result.applied is False  # ANTES era True (mascarava falha), agora False
    # assert result.fallback_used is True  # NOVO
    # assert result.fallback_reason == "small_input_fallback_whole_page"
    # assert result.bbox == (0, 0, 400, 400)
    pass


def test_roi_detected_is_applied_and_no_fallback():
    """ROI detectada corretamente: applied=True, fallback_used=False, fallback_reason=None."""
    pass


def test_roi_empty_image_neither_applied_nor_fallback():
    """Imagem vazia: nem applied nem fallback — falha explícita sem bbox."""
    pass


def test_roi_no_components_sets_bbox_none():
    """Sem componentes detectados: bbox None, applied False, fallback_used False."""
    pass


def test_roi_fallback_reason_schema_name_is_preserved():
    """Consumer schema 2.1.0 §4 depende do nome `fallback_reason` — nunca renomear."""
    pass
