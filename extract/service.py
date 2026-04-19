from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from ingest.service import IngestedDocument
from model.types import WallCandidate


@dataclass(frozen=True)
class ExtractConfig:
    threshold: int = 200
    min_wall_length: int = 24
    line_kernel_ratio: float = 0.04


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

    height, width = binary.shape
    horizontal_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT, (max(3, int(width * active_config.line_kernel_ratio)), 1)
    )
    vertical_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT, (1, max(3, int(height * active_config.line_kernel_ratio)))
    )

    horizontal = cv2.morphologyEx(binary, cv2.MORPH_OPEN, horizontal_kernel)
    vertical = cv2.morphologyEx(binary, cv2.MORPH_OPEN, vertical_kernel)

    candidates = []
    candidates.extend(
        _contours_to_candidates(horizontal, page_index=page_index, orientation="horizontal", config=active_config)
    )
    candidates.extend(
        _contours_to_candidates(vertical, page_index=page_index, orientation="vertical", config=active_config)
    )
    return candidates


def _to_grayscale(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return image
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def _contours_to_candidates(
    mask: np.ndarray,
    page_index: int,
    orientation: str,
    config: ExtractConfig,
) -> list[WallCandidate]:
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    results: list[WallCandidate] = []

    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if orientation == "horizontal":
            if w < config.min_wall_length:
                continue
            center_y = y + (h / 2.0)
            results.append(
                WallCandidate(
                    page_index=page_index,
                    start=(float(x), float(center_y)),
                    end=(float(x + w), float(center_y)),
                    thickness=float(max(1, h)),
                    source="raster_horizontal",
                    confidence=1.0,
                )
            )
        else:
            if h < config.min_wall_length:
                continue
            center_x = x + (w / 2.0)
            results.append(
                WallCandidate(
                    page_index=page_index,
                    start=(float(center_x), float(y)),
                    end=(float(center_x), float(y + h)),
                    thickness=float(max(1, w)),
                    source="raster_vertical",
                    confidence=1.0,
                )
            )

    return results
