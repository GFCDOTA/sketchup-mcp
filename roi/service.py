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
    """Result of architectural ROI detection.

    Invariants:
    - `applied=True` SEMPRE implies a real component-based detection.
    - `fallback_used=True` signals that bbox was set to the whole page
      because real detection was impossible (e.g. small input). It coexists
      with `applied=False` and a populated `fallback_reason`.
    - `fallback_reason` is the canonical schema field (2.1.0 §4) — never
      rename. Always set when applied=False or fallback_used=True.
    """
    applied: bool
    bbox: tuple[int, int, int, int] | None  # (min_x, min_y, max_x, max_y) in input pixel coords
    fallback_reason: str | None
    component_pixel_count: int = 0
    component_bbox_area: int = 0
    component_count: int = 0
    fallback_used: bool = False  # additive: distinct from `applied`

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
            "fallback_used": self.fallback_used,
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
        # Too small to meaningfully partition. Honest fallback: bbox is the
        # whole image so the pipeline can still run, but applied=False and
        # fallback_used=True so callers can emit a warning instead of
        # silently masking the failure (CLAUDE.md invariants #2 and #3).
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
        return RoiResult(False, None, "no_components", 0, 0, 0)

    # Skip background (label 0). Pick the component with the largest
    # PIXEL count: real wall frames carry many ink pixels, while a thin
    # page border or page outline has a huge bbox but very few pixels.
    # Selecting by pixel count avoids collapsing onto borders/frames.
    best_label = -1
    best_pixels = -1
    best_bbox_area = 0
    for label in range(1, nlabels):
        x, y, w, h, area = stats[label]
        pixels = int(area)
        if pixels > best_pixels:
            best_pixels = pixels
            best_label = label
            best_bbox_area = int(w) * int(h)

    page_area = width * height
    if best_bbox_area < min_component_bbox_area_ratio * page_area:
        return RoiResult(
            False,
            None,
            "no_dominant_component",
            max(0, best_pixels),
            int(best_bbox_area),
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
    return RoiResult(True, bbox, None, best_pixels, int(best_bbox_area), int(nlabels - 1))


def crop_image_to_bbox(image: np.ndarray, bbox: tuple[int, int, int, int]) -> np.ndarray:
    min_x, min_y, max_x, max_y = bbox
    return image[min_y:max_y, min_x:max_x]




