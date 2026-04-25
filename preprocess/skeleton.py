"""Optional morphological skeletonization for binary wall masks.

Promoted from proto_skel / proto_colored_skel. The skeleton collapses each
wall band to a 1px centerline, which fuses near-parallel bands separated by
a small drift — useful when the source uses double-line rendering for
walls. The output is re-dilated by a small amount so the downstream Hough
transform retains enough votes.
"""

from __future__ import annotations

import numpy as np

try:
    import cv2
except ImportError as _cv2_exc:  # pragma: no cover
    cv2 = None
    _CV2_IMPORT_ERROR = _cv2_exc
else:
    _CV2_IMPORT_ERROR = None

try:
    from skimage.morphology import skeletonize as _skeletonize
except ImportError as _sk_exc:  # pragma: no cover
    _skeletonize = None
    _SK_IMPORT_ERROR = _sk_exc
else:
    _SK_IMPORT_ERROR = None


def skeletonize_mask(mask: np.ndarray, redilate: int = 1) -> np.ndarray:
    """Skeletonize a binary mask and re-thicken slightly.

    Parameters
    ----------
    mask : np.ndarray
        ``(H, W)`` uint8 mask {0, 255}. Non-binary input is binarized
        with ``mask > 0``.
    redilate : int
        Iterations of 3x3 dilation applied AFTER skeletonization. ``0``
        keeps the strict 1px skeleton, ``1`` (default) gives ~3px lines.

    Returns
    -------
    np.ndarray
        Same shape, uint8 {0, 255}.
    """
    if cv2 is None:
        raise RuntimeError("OpenCV (cv2) required for preprocess.skeleton") from _CV2_IMPORT_ERROR
    if _skeletonize is None:
        raise RuntimeError(
            "scikit-image required for preprocess.skeleton"
        ) from _SK_IMPORT_ERROR

    skel = _skeletonize(mask > 0).astype(np.uint8) * 255
    if redilate > 0:
        skel = cv2.dilate(skel, np.ones((3, 3), np.uint8), iterations=redilate)
    return skel
