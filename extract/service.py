from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from ingest.service import IngestedDocument
from model.types import WallCandidate


@dataclass(frozen=True)
class ExtractConfig:
    threshold: int = 200
    min_wall_length: int = 15
    hough_threshold: int = 12
    hough_max_line_gap: int = 40
    orthogonal_tolerance_ratio: float = 3.0
    binary_opening_kernel_h: int = 0
    binary_opening_kernel_v: int = 0
    # Directional morphological opening on the binary mask before
    # HoughLinesP. Use a tall kernel (e.g. v=3, h=1) to erase THIN
    # HORIZONTAL strokes (wood-flooring hachura, dimension ticks)
    # without eroding the real walls' horizontal extent; use a wide
    # kernel (h=3, v=1) to erase thin vertical strokes. A square
    # kernel erodes both directions and tends to break partition-wall
    # endpoints at junctions; the directional form keeps the topology
    # graph connected. Both default 0 = disabled to keep SVG path and
    # existing tests byte-identical (CLAUDE.md SVG byte-identical
    # guarantee). Raster opts in via _extract_with_roi_from_raster.


# "Noisy-regime" override: when the clean-baseline Hough settings
# produce a high density of candidates per raster megapixel, the input
# is a detailed architectural plan with legend / hachura / text. We
# re-run with a lower Hough vote threshold and a stricter minimum
# segment length to recover thin walls without re-admitting the short
# hachura ticks.
#
# The gate was previously raw count (> 500). Density per megapixel
# replaces it so the decision is scale-invariant: two plans drawn at
# different raster scales but the same semantic complexity now trigger
# the same branch. Values calibrated against the four baseline runs;
# see the F1 commit for observed density numbers.
_NOISE_DENSITY_PER_MPX = 300.0
_NOISE_CONFIG = {
    "min_wall_length": 20,
    "hough_threshold": 10,
}


def extract_from_document(
    document: IngestedDocument, config: ExtractConfig | None = None
) -> list[WallCandidate]:
    active_config = config or ExtractConfig()
    candidates: list[WallCandidate] = []
    for page in document.pages:
        candidates.extend(
            extract_from_raster(page.image, page_index=page.index, config=active_config)
        )

    # Adaptive re-extraction for noise-heavy plans. The baseline config
    # still wins on clean inputs (p12_red.pdf etc.) because it avoids
    # the dedup complexity below; only when the candidate density per
    # megapixel of raster exceeds the noise threshold do we switch to
    # the aggressive recall settings.
    if config is None and _noise_regime_triggered(candidates, document):
        noisy_config = ExtractConfig(
            threshold=active_config.threshold,
            min_wall_length=_NOISE_CONFIG["min_wall_length"],
            hough_threshold=_NOISE_CONFIG["hough_threshold"],
            hough_max_line_gap=active_config.hough_max_line_gap,
            orthogonal_tolerance_ratio=active_config.orthogonal_tolerance_ratio,
        )
        noisy_candidates: list[WallCandidate] = []
        for page in document.pages:
            noisy_candidates.extend(
                extract_from_raster(page.image, page_index=page.index, config=noisy_config)
            )
        return noisy_candidates
    return candidates


def _noise_regime_triggered(
    candidates: list[WallCandidate], document: IngestedDocument
) -> bool:
    """Decide whether the noise-regime re-extraction path should run.

    Returns True when the candidate density across all pages exceeds
    ``_NOISE_DENSITY_PER_MPX`` candidates per megapixel of raster.
    """
    total_mpx = 0.0
    for page in document.pages:
        if page.image is None:
            continue
        h = page.image.shape[0]
        w = page.image.shape[1] if page.image.ndim >= 2 else 0
        total_mpx += (h * w) / 1_000_000.0
    if total_mpx <= 0:
        return False
    density = len(candidates) / total_mpx
    return density >= _NOISE_DENSITY_PER_MPX


def extract_from_raster(
    image: np.ndarray, page_index: int = 0, config: ExtractConfig | None = None
) -> list[WallCandidate]:
    active_config = config or ExtractConfig()
    gray = _to_grayscale(image)
    _, binary = cv2.threshold(gray, active_config.threshold, 255, cv2.THRESH_BINARY_INV)

    # Distance transform on the ORIGINAL (un-eroded) binary so that
    # ``_sample_local_thickness`` returns honest stroke widths. Opening
    # the binary for Hough detection (below) shrinks strokes by ~1 px
    # along the kernel axis, which would bias thickness low and break
    # ``classify._pair_merge`` (real wall pairs would no longer match
    # the median used for the merge tolerance).
    dist_source = binary
    kh = active_config.binary_opening_kernel_h
    kv = active_config.binary_opening_kernel_v
    if kh > 0 or kv > 0:
        # Directional opening: a tall (h=1, v>=3) kernel deletes thin
        # horizontal hachura without touching wall horizontal extent;
        # a wide (h>=3, v=1) kernel does the same for vertical hachura.
        # Real walls have non-trivial extent in BOTH directions and
        # survive either form intact.
        kernel = np.ones((max(1, kv), max(1, kh)), np.uint8)
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)

    if int(binary.sum()) == 0:
        return []

    lines = cv2.HoughLinesP(
        binary,
        rho=1,
        theta=np.pi / 180,
        threshold=active_config.hough_threshold,
        minLineLength=active_config.min_wall_length,
        maxLineGap=active_config.hough_max_line_gap,
    )
    if lines is None:
        return []

    dist = cv2.distanceTransform(dist_source, cv2.DIST_L2, 3)
    ratio = active_config.orthogonal_tolerance_ratio

    candidates: list[WallCandidate] = []
    for line in lines:
        x1, y1, x2, y2 = (int(v) for v in line[0])
        dx = abs(x2 - x1)
        dy = abs(y2 - y1)
        thickness = _sample_local_thickness(dist, x1, y1, x2, y2)
        if dx >= dy * ratio:
            xs = sorted((x1, x2))
            center_y = (y1 + y2) / 2.0
            candidates.append(
                WallCandidate(
                    page_index=page_index,
                    start=(float(xs[0]), center_y),
                    end=(float(xs[1]), center_y),
                    thickness=thickness,
                    source="hough_horizontal",
                    confidence=1.0,
                )
            )
        elif dy >= dx * ratio:
            ys = sorted((y1, y2))
            center_x = (x1 + x2) / 2.0
            candidates.append(
                WallCandidate(
                    page_index=page_index,
                    start=(center_x, float(ys[0])),
                    end=(center_x, float(ys[1])),
                    thickness=thickness,
                    source="hough_vertical",
                    confidence=1.0,
                )
            )
    return candidates


def _to_grayscale(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return image
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def _sample_local_thickness(
    dist: np.ndarray, x1: int, y1: int, x2: int, y2: int
) -> float:
    # Sample the distance transform at 25%, 50%, 75% along the line. Each
    # value is the distance from a foreground pixel to the nearest background,
    # so twice the median approximates the local stroke thickness. Samples
    # that fall on background (dist==0) are ignored so a slightly mis-aligned
    # Hough endpoint does not poison the estimate.
    height, width = dist.shape
    samples: list[float] = []
    for t in (0.25, 0.5, 0.75):
        x = int(round(x1 + t * (x2 - x1)))
        y = int(round(y1 + t * (y2 - y1)))
        if 0 <= x < width and 0 <= y < height:
            value = float(dist[y, x])
            if value > 0:
                samples.append(value)
    if not samples:
        return 1.0
    samples.sort()
    median = samples[len(samples) // 2]
    return max(1.0, 2.0 * median)
