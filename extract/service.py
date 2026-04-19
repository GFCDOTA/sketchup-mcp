from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from ingest.service import IngestedDocument
from model.types import WallCandidate


@dataclass(frozen=True)
class ExtractConfig:
    threshold: int = 200
    min_wall_length: int = 20
    hough_threshold: int = 30
    hough_max_line_gap: int = 10
    orthogonal_tolerance_ratio: float = 3.0


def extract_from_document(
    document: IngestedDocument, config: ExtractConfig | None = None
) -> list[WallCandidate]:
    active_config = config or ExtractConfig()
    candidates: list[WallCandidate] = []
    for page in document.pages:
        candidates.extend(
            extract_from_raster(page.image, page_index=page.index, config=active_config)
        )
    return candidates


def extract_from_raster(
    image: np.ndarray, page_index: int = 0, config: ExtractConfig | None = None
) -> list[WallCandidate]:
    active_config = config or ExtractConfig()
    gray = _to_grayscale(image)
    _, binary = cv2.threshold(gray, active_config.threshold, 255, cv2.THRESH_BINARY_INV)

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

    thickness_estimate = _estimate_stroke_thickness(binary)
    ratio = active_config.orthogonal_tolerance_ratio

    candidates: list[WallCandidate] = []
    for line in lines:
        x1, y1, x2, y2 = (int(v) for v in line[0])
        dx = abs(x2 - x1)
        dy = abs(y2 - y1)
        if dx >= dy * ratio:
            xs = sorted((x1, x2))
            center_y = (y1 + y2) / 2.0
            candidates.append(
                WallCandidate(
                    page_index=page_index,
                    start=(float(xs[0]), center_y),
                    end=(float(xs[1]), center_y),
                    thickness=thickness_estimate,
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
                    thickness=thickness_estimate,
                    source="hough_vertical",
                    confidence=1.0,
                )
            )
    return candidates


def _to_grayscale(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return image
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def _estimate_stroke_thickness(binary: np.ndarray) -> float:
    # distance transform peak is half the stroke width; double it to get thickness estimate
    dist = cv2.distanceTransform(binary, cv2.DIST_L2, 3)
    peak = float(dist.max()) if dist.size else 0.0
    return max(1.0, 2.0 * peak)
