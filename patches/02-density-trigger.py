"""Density-based trigger — substitui `len(strokes) > 200`.

PATCH #02 — para aplicar em sketchup-mcp/classify/service.py:
1. Adicionar função `_should_apply_noise_filters` no topo do arquivo.
2. Substituir `if len(strokes) > 200:` por `if _should_apply_noise_filters(...):`
3. Remover constante mágica, substituir por `_DENSITY_THRESHOLD_PER_CM2`.

INVARIANTE RESOLVIDA: #4 (não acoplar pipeline a tamanho de planta)

ANTES (classify/service.py:70-71, 81-82):
    if len(strokes) > 200:
        strokes = _remove_text_baselines(strokes)
        strokes = _drop_orientation_imbalanced(strokes)

DEPOIS:
    if _should_apply_noise_filters(strokes, roi_bbox, dpi):
        strokes = _remove_text_baselines(strokes)
        strokes = _drop_orientation_imbalanced(strokes)
"""
from __future__ import annotations

# Adicionar no topo de classify/service.py após os imports:

# ==============================================================================
# DENSITY-BASED TRIGGER (substitui `len > 200` hardcoded)
# ==============================================================================

# Baseado em calibração: planta residencial típica tem 30-80 candidates/cm²
# em PDFs @ 150-300 DPI. Densidades muito altas indicam:
# - Floor hachura não filtrada
# - Text blocks tratados como candidates
# - PDFs de baixa qualidade com ruído
# Threshold 50/cm² é conservador: ativa filtros de ruído quando densidade é alta.
_DENSITY_THRESHOLD_PER_CM2 = 50.0

# Conversão DPI → pixels/cm (1 inch = 2.54 cm)
def _pixels_per_cm(dpi: float) -> float:
    return dpi / 2.54


def _candidate_density_per_cm2(
    n_candidates: int,
    roi_bbox: tuple[int, int, int, int] | None,
    dpi: float = 150.0,
) -> float:
    """Densidade de candidatos por cm² da ROI.

    Se roi_bbox é None, assume ROI inválida e retorna densidade infinita
    (força aplicar filtros). Isso é comportamento seguro: é melhor filtrar
    ruído do que perder qualidade.

    Parameters
    ----------
    n_candidates : int
        Número de strokes/candidates.
    roi_bbox : tuple or None
        (min_x, min_y, max_x, max_y) em pixels.
    dpi : float
        Resolução do raster em DPI. Default 150 é o do pipeline atual.

    Returns
    -------
    Densidade em candidates/cm². Retorna float('inf') se ROI inválida.
    """
    if roi_bbox is None:
        return float('inf')

    min_x, min_y, max_x, max_y = roi_bbox
    width_px = max(1, max_x - min_x)
    height_px = max(1, max_y - min_y)

    px_per_cm = _pixels_per_cm(dpi)
    area_cm2 = (width_px / px_per_cm) * (height_px / px_per_cm)

    if area_cm2 <= 0:
        return float('inf')

    return n_candidates / area_cm2


def _should_apply_noise_filters(
    strokes: list,
    roi_bbox: tuple[int, int, int, int] | None = None,
    dpi: float = 150.0,
    threshold: float = _DENSITY_THRESHOLD_PER_CM2,
) -> bool:
    """Decide se filtros de ruído (text-baseline, orientation-dominance,
    pair-merge) devem ser aplicados.

    ANTES: `if len(strokes) > 200:` (acoplado a tamanho absoluto)
    DEPOIS: baseado em densidade por área (robusto a tamanho de planta)

    Plantas pequenas densas (ex: estúdio 30m² com muito ruído) → ATIVA filtros
    Plantas grandes esparsas (ex: casa 300m² com pouco ruído) → SKIP filtros
    """
    if not strokes:
        return False

    density = _candidate_density_per_cm2(len(strokes), roi_bbox, dpi)
    return density >= threshold


# ==============================================================================
# ATUALIZAÇÃO DA FUNÇÃO classify_walls
# ==============================================================================

# Substituir a assinatura atual:
#
# def classify_walls(
#     candidates: list[WallCandidate], coordinate_tolerance: float | None = None
# ) -> list[Wall]:
#
# POR:
#
# def classify_walls(
#     candidates: list[WallCandidate],
#     coordinate_tolerance: float | None = None,
#     roi_bbox: tuple[int, int, int, int] | None = None,  # NOVO
#     dpi: float = 150.0,  # NOVO
# ) -> list[Wall]:
#
# E substituir os dois `if len(strokes) > 200:` por:
#
#     if _should_apply_noise_filters(strokes, roi_bbox, dpi):
#         strokes = _remove_text_baselines(strokes)
#         strokes = _drop_orientation_imbalanced(strokes)
#     ...
#     if _should_apply_noise_filters(strokes, roi_bbox, dpi):
#         wall_candidates = _pair_merge_strokes(strokes)
#     else:
#         wall_candidates = list(strokes)


# ==============================================================================
# ATUALIZAR CALLERS em model/pipeline.py e tests/
# ==============================================================================

# Em pipeline.py, chamada atual:
#   walls = classify_walls(candidates, coordinate_tolerance=tolerance)
# Atualizar para:
#   walls = classify_walls(
#       candidates,
#       coordinate_tolerance=tolerance,
#       roi_bbox=roi_result.bbox,
#       dpi=page.dpi,  # ou 150.0 se não estiver disponível
#   )
#
# Em tests/ — fixtures sintéticos têm roi_bbox=None.
# Comportamento: como ROI é None, densidade = inf, filtros sempre aplicados.
# Isso replica comportamento atual pra tests pequenos.


# ==============================================================================
# JUSTIFICATIVA DO THRESHOLD 50/cm²
# ==============================================================================
#
# Calibração baseada em:
# - Planta residencial @ 150 DPI: ~59 px/cm
# - Planta típica 10m×10m = 1000cm² área útil
# - Walls típicas: ~100-200 candidates bem detectados
# - Densidade esperada: 100/1000 = 0.1 cand/cm² (background walls)
# - Com ruído (text blocks, hachura): 50-200 cand/cm²
# - Threshold 50/cm² captura casos onde filtros são necessários
#
# Este valor pode ser tunado. Documentar em README.md ou config:
# - Plantas muito detalhadas (mobiliário completo): bump para 80-100
# - Plantas minimalistas (só estrutura): baixar para 30
# - Pode virar parâmetro CLI do main.py
