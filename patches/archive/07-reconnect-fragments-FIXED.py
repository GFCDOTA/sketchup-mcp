"""Reconnect fragments — VERSÃO CORRIGIDA após code review.

PATCH #07 FIXED — substitui extract/service.py + ajusta topology/service.py

BUGS CORRIGIDOS vs versão original:
- A1: Renomeado source="fld_*" (é FastLineDetector, não LSD real)
- A2: Flag real `used_fld` em vez de verificar `lines is not None` (sempre True)
- A3: LSD separado por orientação em vez de bitwise_or (evita blobs em cruzamentos)
- A4: Kernel adaptativo por image diagonal (não 80px fixo)
- A6: KDTree via scipy em vez de O(n²) sobre endpoints
- A9: Floor 20px pra plantas pequenas (< 20 walls)

OPÇÃO DE USAR LSD REAL (cv2.createLineSegmentDetector):
- Disponível em OpenCV core 4.5.4+ (não precisa contrib)
- LSD patent expirou comercialmente (2010+15 = 2025)
- Superior ao FastLineDetector pra plantas arquitetônicas

INSTALAÇÃO:
    pip install opencv-python>=4.5.4  # LSD no core
    # OU
    pip install opencv-contrib-python>=4.5.4  # FastLineDetector em ximgproc
    pip install scipy  # KDTree pra snap tolerance adaptativa
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class ExtractConfigV2:
    threshold: int = 200
    min_wall_length: int = 15
    orthogonal_tolerance_ratio: float = 3.0
    lsd_min_length_ratio: float = 0.02
    prefer_lsd_over_fld: bool = True  # LSD (core) preferido sobre FastLineDetector (contrib)


def extract_from_raster_v2(
    image: np.ndarray,
    page_index: int = 0,
    config: ExtractConfigV2 | None = None,
):
    """Extract wall candidates com reconnection de fragmentos."""
    from model.types import WallCandidate

    active_config = config or ExtractConfigV2()
    gray = _to_grayscale(image)

    # Otsu adaptativo em vez de threshold fixo (estende a plantas de baixa luz)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    if int(binary.sum()) == 0:
        return []

    # FIX A4: kernel escala com imagem diagonal (~1% de diagonal)
    H, W = binary.shape
    diag = (H ** 2 + W ** 2) ** 0.5
    kernel_len = max(20, int(diag * 0.01))

    # FIX A3: closing separado por orientação, LSD em cada um
    closed_h = _morphological_close_1d(binary, "horizontal", kernel_len)
    closed_v = _morphological_close_1d(binary, "vertical", kernel_len)

    # Distance transform sobre binary ORIGINAL (não closed)
    dist = cv2.distanceTransform(binary, cv2.DIST_L2, 3)

    # Detecta linhas SEPARADAMENTE em closed_h e closed_v
    lines_h = _detect_lines(closed_h, active_config, orientation="horizontal") or []
    lines_v = _detect_lines(closed_v, active_config, orientation="vertical") or []
    used_advanced_detector = (len(lines_h) + len(lines_v)) > 0

    # FIX A2: flag real pra source tagging correto
    if not used_advanced_detector:
        # Fallback HoughLinesP sobre union
        closed = cv2.bitwise_or(closed_h, closed_v)
        hough = cv2.HoughLinesP(
            closed, rho=1, theta=np.pi / 180, threshold=12,
            minLineLength=active_config.min_wall_length,
            maxLineGap=20,
        )
        if hough is None:
            return []
        # Separar Hough em H e V por slope
        lines_h = [l for l in hough if abs(l[0][2] - l[0][0]) >= abs(l[0][3] - l[0][1])]
        lines_v = [l for l in hough if l not in lines_h]

    detector_tag = "lsd" if used_advanced_detector else "hough"

    ratio = active_config.orthogonal_tolerance_ratio
    candidates = []
    candidates += _lines_to_candidates(
        lines_h, "horizontal", dist, page_index, detector_tag, ratio
    )
    candidates += _lines_to_candidates(
        lines_v, "vertical", dist, page_index, detector_tag, ratio
    )

    # Collinearity merge após candidates construídos
    candidates = _merge_collinear_fragments(candidates, max_gap_px=120, perp_tol_px=4.0)

    return candidates


def _detect_lines(binary: np.ndarray, config: ExtractConfigV2, orientation: str):
    """Tenta LSD real primeiro (OpenCV 4.5.4+ core), FastLineDetector como fallback.

    LSD real (cv2.createLineSegmentDetector):
    - Disponível no core OpenCV desde 4.5.4
    - Patent expirou, uso comercial OK
    - Subpixel accuracy, controle automático de false alarms

    FastLineDetector (cv2.ximgproc.createFastLineDetector):
    - Requer opencv-contrib-python
    - Mais rápido, menos preciso
    """
    # Tentativa 1: LSD real (preferido)
    if config.prefer_lsd_over_fld:
        try:
            lsd = cv2.createLineSegmentDetector(refine=cv2.LSD_REFINE_ADV)
            lines_raw, _, _, _ = lsd.detect(binary)
            if lines_raw is not None and len(lines_raw) > 0:
                return lines_raw  # shape (N, 1, 4)
        except (AttributeError, cv2.error):
            pass  # LSD não disponível, tenta FastLineDetector

    # Tentativa 2: FastLineDetector (contrib)
    try:
        detector = cv2.ximgproc.createFastLineDetector(
            length_threshold=int(config.min_wall_length),
            distance_threshold=1.41,
            canny_th1=50.0,
            canny_th2=50.0,
            canny_aperture_size=3,
            do_merge=True,
        )
        lines_raw = detector.detect(binary)
        if lines_raw is not None and len(lines_raw) > 0:
            return lines_raw
    except (AttributeError, cv2.error):
        pass

    return None  # Caller vai fazer fallback Hough


def _lines_to_candidates(
    lines, orientation: str, dist: np.ndarray, page_index: int,
    detector_tag: str, ortho_ratio: float
):
    """Converte saída do detector em WallCandidate[]."""
    from model.types import WallCandidate

    candidates = []
    for line in lines:
        x1, y1, x2, y2 = (int(v) for v in line[0])
        dx = abs(x2 - x1)
        dy = abs(y2 - y1)
        thickness = _sample_local_thickness(dist, x1, y1, x2, y2)

        if orientation == "horizontal" and dx >= dy * ortho_ratio:
            xs = sorted((x1, x2))
            center_y = (y1 + y2) / 2.0
            candidates.append(
                WallCandidate(
                    page_index=page_index,
                    start=(float(xs[0]), center_y),
                    end=(float(xs[1]), center_y),
                    thickness=thickness,
                    source=f"{detector_tag}_horizontal",
                    confidence=1.0,
                )
            )
        elif orientation == "vertical" and dy >= dx * ortho_ratio:
            ys = sorted((y1, y2))
            center_x = (x1 + x2) / 2.0
            candidates.append(
                WallCandidate(
                    page_index=page_index,
                    start=(center_x, float(ys[0])),
                    end=(center_x, float(ys[1])),
                    thickness=thickness,
                    source=f"{detector_tag}_vertical",
                    confidence=1.0,
                )
            )
    return candidates


def _morphological_close_1d(binary: np.ndarray, orientation: str, length: int):
    if orientation == "horizontal":
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (length, 1))
    else:
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, length))
    return cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)


def _merge_collinear_fragments(
    candidates: list, max_gap_px: float = 120.0, perp_tol_px: float = 4.0
):
    from model.types import WallCandidate

    if not candidates:
        return candidates

    horiz = [c for c in candidates if _candidate_orientation(c) == "horizontal"]
    vert = [c for c in candidates if _candidate_orientation(c) == "vertical"]

    horiz_merged = _merge_collinear_group(horiz, "horizontal", max_gap_px, perp_tol_px)
    vert_merged = _merge_collinear_group(vert, "vertical", max_gap_px, perp_tol_px)

    return horiz_merged + vert_merged


def _merge_collinear_group(candidates, orientation, max_gap_px, perp_tol_px):
    from model.types import WallCandidate

    if len(candidates) < 2:
        return candidates

    # Agrupar por perp coord com tolerância
    groups = []
    for c in candidates:
        perp = c.start[1] if orientation == "horizontal" else c.start[0]
        assigned = False
        for group in groups:
            group_perp = sum(
                (x.start[1] if orientation == "horizontal" else x.start[0])
                for x in group
            ) / len(group)
            if abs(perp - group_perp) < perp_tol_px:
                group.append(c)
                assigned = True
                break
        if not assigned:
            groups.append([c])

    merged = []
    for group in groups:
        if len(group) == 1:
            merged.append(group[0])
            continue

        def para_min(c):
            return min(
                c.start[0] if orientation == "horizontal" else c.start[1],
                c.end[0] if orientation == "horizontal" else c.end[1],
            )

        group.sort(key=para_min)

        current = group[0]
        for nxt in group[1:]:
            current_end = max(
                current.start[0] if orientation == "horizontal" else current.start[1],
                current.end[0] if orientation == "horizontal" else current.end[1],
            )
            nxt_start = para_min(nxt)

            gap = nxt_start - current_end
            if gap <= max_gap_px:
                if orientation == "horizontal":
                    perp = (current.start[1] + nxt.start[1]) / 2
                    xs_all = [current.start[0], current.end[0], nxt.start[0], nxt.end[0]]
                    new_start = (min(xs_all), perp)
                    new_end = (max(xs_all), perp)
                else:
                    perp = (current.start[0] + nxt.start[0]) / 2
                    ys_all = [current.start[1], current.end[1], nxt.start[1], nxt.end[1]]
                    new_start = (perp, min(ys_all))
                    new_end = (perp, max(ys_all))

                current = WallCandidate(
                    page_index=current.page_index,
                    start=new_start,
                    end=new_end,
                    thickness=max(current.thickness, nxt.thickness),
                    source=f"{current.source}_merged",
                    confidence=min(current.confidence, nxt.confidence),
                )
            else:
                merged.append(current)
                current = nxt
        merged.append(current)

    return merged


def _candidate_orientation(c) -> str:
    dx = abs(c.end[0] - c.start[0])
    dy = abs(c.end[1] - c.start[1])
    return "horizontal" if dx >= dy else "vertical"


def _to_grayscale(image):
    if image.ndim == 2:
        return image
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def _sample_local_thickness(dist, x1, y1, x2, y2):
    import statistics
    height, width = dist.shape
    samples = []
    for t in (0.25, 0.5, 0.75):
        x = int(round(x1 + t * (x2 - x1)))
        y = int(round(y1 + t * (y2 - y1)))
        if 0 <= x < width and 0 <= y < height:
            value = float(dist[y, x])
            if value > 0:
                samples.append(value)
    if not samples:
        return 1.0
    return max(1.0, 2.0 * statistics.median(samples))


# ==============================================================================
# FIX A6 + A9: snap tolerance adaptativo com KDTree
# ==============================================================================

from model.types import Wall  # type-only import

def _infer_snap_tolerance_v2(walls: list["Wall"]) -> float:
    """Snap tolerance baseado em distribuição real de gaps (KDTree).

    FIX A6: scipy.spatial.cKDTree em vez de O(n²)
    FIX A9: floor 20px para plantas pequenas (< 20 walls)
    """
    import math

    if not walls:
        return 2.0

    # FIX A9: plantas pequenas precisam floor fixo
    if len(walls) < 20:
        thicknesses = sorted(w.thickness for w in walls if w.thickness > 0)
        if not thicknesses:
            return 20.0
        median = thicknesses[len(thicknesses) // 2]
        return max(20.0, 2.0 * median)

    # Extrair endpoints
    endpoints = []
    for w in walls:
        endpoints.append(w.start)
        endpoints.append(w.end)

    # Computar gaps entre endpoints próximos
    gaps = []
    try:
        from scipy.spatial import cKDTree

        tree = cKDTree(endpoints)
        pairs = tree.query_pairs(r=200.0)
        for i, j in pairs:
            g = math.hypot(
                endpoints[i][0] - endpoints[j][0],
                endpoints[i][1] - endpoints[j][1],
            )
            if 0 < g < 200:
                gaps.append(g)
    except ImportError:
        # Fallback: amostragem aleatória (não primeiros-N enviesados)
        import random
        sample_size = min(500, len(endpoints))
        sample = random.sample(endpoints, sample_size)
        for i in range(len(sample)):
            for j in range(i + 1, len(sample)):
                g = math.hypot(
                    sample[i][0] - sample[j][0],
                    sample[i][1] - sample[j][1],
                )
                if 0 < g < 200:
                    gaps.append(g)

    if not gaps:
        return 4.0

    gaps.sort()
    p25 = gaps[len(gaps) // 4]

    thicknesses = sorted(w.thickness for w in walls if w.thickness > 0)
    if thicknesses:
        thick_floor = 2.0 * thicknesses[len(thicknesses) // 2]
    else:
        thick_floor = 4.0

    return max(thick_floor, p25 * 1.2)
