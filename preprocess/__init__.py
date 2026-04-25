"""Optional image preprocessing stage for the extract pipeline.

Preprocessing is OFF by default. When enabled it transforms a rasterized page
image (RGB/BGR numpy array) into a cleaner binary representation that the
geometry extractor consumes more reliably.

Invariant: any preprocessing application MUST surface a warning string
(`preprocess_color_mask_applied`, etc.) so the observed_model never hides the
fact that the input was altered before extraction.

The preprocessing layer is intentionally generic — it must not encode
heuristics tied to a specific PDF, only to a *family* of source palettes
(walls drawn in solid red, solid black, grey31, etc.).
"""

from __future__ import annotations

from typing import Any

import numpy as np

from preprocess.color_mask import (
    AVAILABLE_COLORS,
    detect_dominant_color,
    extract_color_dominant_mask,
)
from preprocess.skeleton import skeletonize_mask

__all__ = [
    "AVAILABLE_COLORS",
    "apply_preprocessing",
    "detect_dominant_color",
    "extract_color_dominant_mask",
    "skeletonize_mask",
    "preprocess_warning_for",
]


# Warning tags the pipeline may emit so callers can grep a single registry.
PREPROCESS_WARNING_TAGS = {
    "color_mask": "preprocess_color_mask_applied",
    "skeleton": "preprocess_skeleton_applied",
}


def preprocess_warning_for(mode: str) -> str:
    """Return the warning tag associated with a given preprocessing mode."""
    try:
        return PREPROCESS_WARNING_TAGS[mode]
    except KeyError as exc:
        raise ValueError(f"Unknown preprocess mode: {mode!r}") from exc


def apply_preprocessing(image: np.ndarray, config: dict[str, Any] | None) -> np.ndarray:
    """Apply optional preprocessing to a single page image.

    Parameters
    ----------
    image : np.ndarray
        Input image (H, W, 3) in BGR or RGB order, uint8.
    config : dict | None
        ``None`` -> no-op, returns ``image`` unchanged.
        ``{"mode": "color_mask", "color": "auto"|"red"|"black"|"grey31"|...}``
            applies :func:`extract_color_dominant_mask` and returns an
            RGB image where wall pixels are black on white background
            (the convention the rest of the pipeline expects).
        ``{"mode": "color_mask", ..., "skeleton": True}`` additionally
            collapses the mask to a 1px centerline (re-thickened to ~3px).

    Returns
    -------
    np.ndarray
        The processed image. Same dtype/shape conventions as the input
        (H, W, 3) uint8.

    Notes
    -----
    The function is pure — it never touches disk, never writes warnings.
    The pipeline layer is responsible for surfacing the warning tag via
    :func:`preprocess_warning_for`.
    """
    if config is None:
        return image

    mode = config.get("mode")
    if mode is None:
        return image

    if mode != "color_mask":
        raise ValueError(
            f"Unsupported preprocess mode: {mode!r}. "
            f"Supported: {sorted(PREPROCESS_WARNING_TAGS)!r}"
        )

    color_hint = config.get("color", "auto")
    mask = extract_color_dominant_mask(image, color_hint=color_hint)

    if config.get("skeleton"):
        mask = skeletonize_mask(mask, redilate=int(config.get("skeleton_redilate", 1)))

    # Convention: pipeline expects walls dark on light background (BGR/RGB 3-ch).
    inverted = 255 - mask
    rgb = np.stack([inverted, inverted, inverted], axis=-1).astype(np.uint8)
    return rgb
