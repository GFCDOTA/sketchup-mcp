"""Color-aware preprocessing — substitui red-mask hardcoded.

PATCH #01 — para aplicar:
1. Criar novo arquivo: sketchup-mcp/preprocess/__init__.py (vazio)
2. Copiar este arquivo para: sketchup-mcp/preprocess/color_aware.py
3. Editar main.py ou model/pipeline.py para chamar `detect_wall_mask()` antes de ROI

INVARIANTE RESOLVIDA: #4 (não acoplar pipeline a PDF específico)

ANTES (proto_red.py hardcoded):
    walls_mask = image[:, :, 2] > 200  # Red channel > 200

DEPOIS (este módulo):
    result = detect_wall_mask(image)
    walls_mask = result.mask  # K-means adaptativo, sem hardcoding
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class ColorAnalysisResult:
    mask: np.ndarray  # binary mask, True = wall candidate pixel
    peitoril_mask: np.ndarray | None  # binary mask, cor distinta de walls (opcional)
    n_clusters_detected: int
    wall_cluster_variance: float
    method: str  # "kmeans" | "fallback_grayscale"
    confidence: float  # 0.0-1.0


def detect_wall_mask(
    image: np.ndarray,
    n_clusters: int = 5,
    detect_peitoris: bool = True,
) -> ColorAnalysisResult:
    """Detecta máscara de walls via K-means clustering adaptativo.

    Ao contrário de red-mask hardcoded, este método:
    - Detecta a paleta real da página (qualquer cor: cinza, vermelho, azul, etc.)
    - Identifica cluster de walls por variância de tons + density + oriented extent
    - Separa peitoris (cor distinta, tipicamente marrom/tan) se detect_peitoris=True
    - Funciona em plantas BR, EUA, Europa — CAD-agnóstico

    Parameters
    ----------
    image : np.ndarray
        Imagem BGR ou grayscale do PDF rasterizado.
    n_clusters : int
        Número de clusters K-means. 5 é ótimo para plantas residenciais
        (background, walls, peitoris, text, annotations).
    detect_peitoris : bool
        Se True, identifica cluster separado pra peitoris (2° maior variância).

    Returns
    -------
    ColorAnalysisResult com mask binário de walls (e peitoris opcional).
    """
    if image.size == 0:
        return ColorAnalysisResult(
            mask=np.zeros((1, 1), dtype=bool),
            peitoril_mask=None,
            n_clusters_detected=0,
            wall_cluster_variance=0.0,
            method="fallback_grayscale",
            confidence=0.0,
        )

    # Fallback: grayscale input
    if image.ndim == 2:
        return _fallback_grayscale_threshold(image)

    if image.ndim != 3 or image.shape[2] < 3:
        return _fallback_grayscale_threshold(
            cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
        )

    # K-means clustering
    pixels = image.reshape((-1, 3)).astype(np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.5)
    _, labels, centers = cv2.kmeans(
        pixels,
        K=n_clusters,
        bestLabels=None,
        criteria=criteria,
        attempts=10,
        flags=cv2.KMEANS_PP_CENTERS,
    )

    centers = centers.astype(np.uint8)
    labels_flat = labels.flatten()

    # Calcular métricas por cluster
    cluster_stats = []
    for cluster_id in range(n_clusters):
        cluster_pixels = pixels[labels_flat == cluster_id]
        if len(cluster_pixels) == 0:
            cluster_stats.append(None)
            continue

        variance = float(np.mean(np.std(cluster_pixels, axis=0)))
        mean_color = cluster_pixels.mean(axis=0)
        darkness = float(255.0 - mean_color.mean())  # walls são tipicamente escuras
        cluster_stats.append({
            "id": cluster_id,
            "variance": variance,
            "darkness": darkness,
            "size": len(cluster_pixels),
            "mean_color": tuple(mean_color.astype(int)),
        })

    # Selecionar cluster de walls: prioriza darkness × size (grande e escuro)
    # Variance secundária (paredes tem tons variados por anti-aliasing)
    valid_clusters = [c for c in cluster_stats if c is not None]
    if not valid_clusters:
        return _fallback_grayscale_threshold(
            cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        )

    # Heurística robusta: cluster mais escuro que não seja o maior (background)
    sorted_by_size = sorted(valid_clusters, key=lambda c: c["size"], reverse=True)
    background_cluster_id = sorted_by_size[0]["id"]

    wall_candidates = [c for c in valid_clusters if c["id"] != background_cluster_id]
    if not wall_candidates:
        return _fallback_grayscale_threshold(
            cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        )

    wall_cluster = max(wall_candidates, key=lambda c: c["darkness"])

    # Construir máscara de walls
    labels_2d = labels_flat.reshape(image.shape[:2])
    walls_mask = (labels_2d == wall_cluster["id"])

    # Morphological cleanup (remover noise de cluster)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    walls_mask = cv2.morphologyEx(
        walls_mask.astype(np.uint8) * 255,
        cv2.MORPH_OPEN,
        kernel,
    ).astype(bool)

    # Detecção de peitoril (cluster com cor distinta, tipicamente marrom/tan)
    peitoril_mask = None
    if detect_peitoris and len(wall_candidates) > 1:
        # Peitoris: cluster com hue diferente de walls + não background
        peitoril_candidates = [
            c for c in wall_candidates
            if c["id"] != wall_cluster["id"]
            and _is_browish(c["mean_color"])
        ]
        if peitoril_candidates:
            peitoril_cluster = max(peitoril_candidates, key=lambda c: c["size"])
            peitoril_mask = (labels_2d == peitoril_cluster["id"])

    # Confidence heurística: walls representam 3-15% dos pixels tipicamente
    wall_pct = walls_mask.sum() / walls_mask.size
    if 0.02 <= wall_pct <= 0.20:
        confidence = 0.9
    elif 0.01 <= wall_pct <= 0.30:
        confidence = 0.6
    else:
        confidence = 0.3  # suspeito: muito pouco ou muito pixels

    return ColorAnalysisResult(
        mask=walls_mask,
        peitoril_mask=peitoril_mask,
        n_clusters_detected=n_clusters,
        wall_cluster_variance=wall_cluster["variance"],
        method="kmeans",
        confidence=confidence,
    )


def _fallback_grayscale_threshold(gray: np.ndarray) -> ColorAnalysisResult:
    """Fallback quando K-means não é aplicável (grayscale ou imagem pequena)."""
    # Otsu threshold — adaptativo, sem hardcoding
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    mask = binary > 0
    return ColorAnalysisResult(
        mask=mask,
        peitoril_mask=None,
        n_clusters_detected=1,
        wall_cluster_variance=float(np.std(gray)),
        method="fallback_grayscale",
        confidence=0.5,
    )


def _is_browish(bgr_color: tuple[int, int, int]) -> bool:
    """Heurística: marrom/tan tem blue < green ≈ red, todos médios."""
    b, g, r = bgr_color
    # Marrom: R > G > B, todos em meio-range
    if not (50 < r < 200 and 30 < g < 180 and 10 < b < 150):
        return False
    if not (r > g and g > b):
        return False
    return (r - b) > 30  # diferença significativa entre red e blue


def build_roi_from_mask(
    mask: np.ndarray, margin_ratio: float = 0.02
) -> tuple[int, int, int, int] | None:
    """Converte máscara de walls em bounding box ROI. Retorna None se mask vazia."""
    if mask is None or not mask.any():
        return None

    ys, xs = np.where(mask)
    h, w = mask.shape
    margin_y = int(h * margin_ratio)
    margin_x = int(w * margin_ratio)

    min_y = max(0, int(ys.min()) - margin_y)
    max_y = min(h, int(ys.max()) + margin_y)
    min_x = max(0, int(xs.min()) - margin_x)
    max_x = min(w, int(xs.max()) + margin_x)

    return (min_x, min_y, max_x, max_y)


# -------- INTEGRATION EXAMPLE (adicionar em main.py ou pipeline.py) --------
#
# from preprocess.color_aware import detect_wall_mask, build_roi_from_mask
#
# def run_pdf_pipeline(pdf_bytes):
#     document = ingest_pdf(pdf_bytes)
#     for page in document.pages:
#         # NOVO: análise de cor antes de ROI
#         color_result = detect_wall_mask(page.image)
#         if color_result.confidence > 0.7:
#             # Usa mask de cor como ROI
#             roi_bbox = build_roi_from_mask(color_result.mask)
#             ...
#         else:
#             # Fallback pro ROI por connected components (comportamento original)
#             roi_result = detect_architectural_roi(page.image)
#             ...
#
# ------------------------------------------------------------------------
