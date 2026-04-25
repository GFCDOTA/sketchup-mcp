"""Generic color-dominant mask extraction.

Promoted to production from the proto_red / proto_colored prototypes
(runs/proto/p1..p12). The function is palette-aware: callers either name
the color they want to retain ("red", "black", "grey31", ...) or pass
``color_hint="auto"`` to let the function pick the dominant non-background
chromatic cluster.

Design invariants:
 - Pure function: no disk I/O, no logging, no warnings here.
 - Color presets describe *families*, never specific PDFs.
 - The output is a single-channel uint8 mask {0, 255} where 255 = "kept".
"""

from __future__ import annotations

from typing import Iterable

import numpy as np

try:
    import cv2
except ImportError as _cv2_exc:  # pragma: no cover - cv2 is a hard dep
    cv2 = None
    _CV2_IMPORT_ERROR = _cv2_exc
else:
    _CV2_IMPORT_ERROR = None


# (lower_hsv, upper_hsv) ranges. For colors that wrap around H=0/180 we
# accept a list of ranges and OR them.
_HSV_PRESETS: dict[str, list[tuple[tuple[int, int, int], tuple[int, int, int]]]] = {
    "red": [
        ((0, 100, 80), (12, 255, 255)),
        ((170, 100, 80), (180, 255, 255)),
    ],
    "brown": [((8, 80, 40), (25, 255, 180))],
    "orange": [((10, 120, 120), (25, 255, 255))],
    "yellow": [((25, 100, 120), (40, 255, 255))],
    "green": [((40, 80, 60), (85, 255, 255))],
    "cyan": [((85, 80, 80), (100, 255, 255))],
    "blue": [((100, 100, 60), (135, 255, 255))],
    "magenta": [((140, 80, 80), (170, 255, 255))],
    # Achromatic presets are checked against grayscale, not HSV hue.
    "black": [],
    "grey31": [],   # ~31% luma; corresponds to RGB ~(80,80,80)
    "grey50": [],
    "white": [],
}

AVAILABLE_COLORS = tuple(_HSV_PRESETS.keys()) + ("auto",)


def _ensure_cv2() -> None:
    if cv2 is None:
        raise RuntimeError(
            "OpenCV (cv2) is required for preprocess.color_mask"
        ) from _CV2_IMPORT_ERROR


def _ensure_bgr(image: np.ndarray) -> np.ndarray:
    """Caller may pass either RGB or BGR. We treat input as BGR (the pipeline
    convention coming out of OpenCV imread). When the array came from
    pypdfium2 (`render(...).to_numpy()`), it is RGBA->RGB; the channel order
    in HSV mapping is symmetric for the achromatic case and matters for the
    chromatic case. Callers wanting strict RGB should convert first.
    """
    if image.ndim != 3 or image.shape[2] not in (3, 4):
        raise ValueError(
            f"extract_color_dominant_mask expects an HxWx3 image, got shape {image.shape}"
        )
    if image.shape[2] == 4:
        image = image[:, :, :3]
    if image.dtype != np.uint8:
        image = image.astype(np.uint8)
    return image


def _achromatic_mask(image_bgr: np.ndarray, color: str) -> np.ndarray:
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    if color == "black":
        _, mask = cv2.threshold(gray, 60, 255, cv2.THRESH_BINARY_INV)
    elif color == "grey31":
        mask = cv2.inRange(gray, 60, 110)
    elif color == "grey50":
        mask = cv2.inRange(gray, 110, 160)
    elif color == "white":
        _, mask = cv2.threshold(gray, 220, 255, cv2.THRESH_BINARY)
    else:  # pragma: no cover - guarded by caller
        raise ValueError(f"Unknown achromatic preset: {color!r}")
    return mask


def _hsv_mask(
    image_bgr: np.ndarray,
    ranges: Iterable[tuple[tuple[int, int, int], tuple[int, int, int]]],
) -> np.ndarray:
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    out = None
    for lo, hi in ranges:
        m = cv2.inRange(hsv, lo, hi)
        out = m if out is None else cv2.bitwise_or(out, m)
    return out if out is not None else np.zeros(image_bgr.shape[:2], dtype=np.uint8)


def detect_dominant_color(image: np.ndarray) -> str:
    """Return the preset name that captures the largest *chromatic* mass
    in ``image``, falling back to ``'black'`` when the page is essentially
    grayscale (printer output, scanned blueprints, ...).

    The decision is based purely on pixel counts among the named presets
    — there is no codified knowledge of any specific PDF.
    """
    _ensure_cv2()
    bgr = _ensure_bgr(image)
    best_name = "black"
    best_count = 0

    chromatic_presets = [n for n, r in _HSV_PRESETS.items() if r]
    for name in chromatic_presets:
        m = _hsv_mask(bgr, _HSV_PRESETS[name])
        c = int((m > 0).sum())
        if c > best_count:
            best_count = c
            best_name = name

    # Heuristic: require at least 0.5% of the page to be that color, else
    # the page is essentially achromatic.
    total = bgr.shape[0] * bgr.shape[1]
    if best_count < int(0.005 * total):
        return "black"
    return best_name


def extract_color_dominant_mask(
    image: np.ndarray,
    color_hint: str = "auto",
    close_iters: int = 2,
) -> np.ndarray:
    """Return a single-channel uint8 mask {0, 255} of the requested color.

    Parameters
    ----------
    image : np.ndarray
        HxWx3 (or HxWx4) uint8 image.
    color_hint : str
        One of :data:`AVAILABLE_COLORS`. ``"auto"`` chooses via
        :func:`detect_dominant_color`.
    close_iters : int
        Number of MORPH_CLOSE iterations applied with a 3x3 kernel.
        Bridges 1-2px gaps that printing artifacts introduce.

    Returns
    -------
    np.ndarray
        ``(H, W)`` uint8 mask. ``255`` = wall pixel, ``0`` = background.
    """
    _ensure_cv2()
    bgr = _ensure_bgr(image)

    color = color_hint
    if color == "auto":
        color = detect_dominant_color(bgr)

    if color not in _HSV_PRESETS:
        raise ValueError(
            f"Unknown color hint {color_hint!r}. "
            f"Available: {sorted(AVAILABLE_COLORS)!r}"
        )

    if _HSV_PRESETS[color]:
        mask = _hsv_mask(bgr, _HSV_PRESETS[color])
    else:
        mask = _achromatic_mask(bgr, color)

    if close_iters > 0:
        mask = cv2.morphologyEx(
            mask,
            cv2.MORPH_CLOSE,
            np.ones((3, 3), np.uint8),
            iterations=close_iters,
        )
    return mask
