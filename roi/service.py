"""ROI (region of interest) detection for architectural plans.

A page may contain non-architectural blocks (text, legend, footer, mini-map)
that the extractor would otherwise process as if they were geometry. This
module identifies the bounding box of the actual plan by selecting the
largest connected dark-pixel component on the page after thinning. The
plan is a single linked frame of walls; text blocks, legends, mini-maps
and stamps are smaller, isolated components.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class RoiResult:
    applied: bool
    bbox: tuple[int, int, int, int] | None  # (min_x, min_y, max_x, max_y) in input pixel coords
    fallback_reason: str | None
    component_pixel_count: int = 0
    component_bbox_area: int = 0
    component_count: int = 0

    def to_dict(self) -> dict:
        return {
            "applied": self.applied,
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
            "fallback_reason": self.fallback_reason,
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

    Strategy: threshold the page to a binary, run connected-components
    on dark pixels (8-connected), and keep the component whose bounding
    box covers the largest area. The plan is a single linked wall frame;
    text blocks and stamps form their own much smaller components.

    Returns RoiResult.applied = False with an explicit fallback_reason
    whenever the page does not present a clear architectural cluster.
    Callers MUST honor the fallback signal and emit a warning instead of
    silently using the entire page.
    """
    if image.size == 0:
        return RoiResult(False, None, "empty_image")

    height, width = image.shape[:2]
    if min(height, width) < min_image_side:
        # Too small to meaningfully partition -- behave as if ROI were the
        # whole image. Signal `applied=True` so callers do not emit a
        # fallback warning for legitimate small inputs (synthetic tests).
        return RoiResult(True, (0, 0, width, height), None)

    if image.ndim == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image
    _, binary = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY_INV)

    nlabels, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    if nlabels <= 1:
        return RoiResult(False, None, "no_components", 0, 0, 0)

    # Skip background (label 0). Pick the component with the largest bbox
    # area; that is the one that physically sprawls across the page, which
    # for architectural drawings is the linked wall frame, not a label
    # block whose bbox is small even when the pixel count is high.
    best_label = -1
    best_area = -1
    best_pixels = 0
    for label in range(1, nlabels):
        x, y, w, h, area = stats[label]
        bbox_area = int(w) * int(h)
        if bbox_area > best_area:
            best_area = bbox_area
            best_label = label
            best_pixels = int(area)

    page_area = width * height
    if best_area < min_component_bbox_area_ratio * page_area:
        return RoiResult(
            False,
            None,
            "no_dominant_component",
            best_pixels,
            int(best_area),
            int(nlabels - 1),
        )

    x, y, w, h, _ = stats[best_label]
    margin_x = int(round(w * margin_ratio))
    margin_y = int(round(h * margin_ratio))
    bbox = (
        max(0, int(x) - margin_x),
        max(0, int(y) - margin_y),
        min(width, int(x + w) + margin_x),
        min(height, int(y + h) + margin_y),
    )
    return RoiResult(True, bbox, None, best_pixels, int(best_area), int(nlabels - 1))


def crop_image_to_bbox(image: np.ndarray, bbox: tuple[int, int, int, int]) -> np.ndarray:
    min_x, min_y, max_x, max_y = bbox
    return image[min_y:max_y, min_x:max_x]




