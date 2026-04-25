"""Tests for the optional preprocessing layer (preprocess/)."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from preprocess import (
    AVAILABLE_COLORS,
    apply_preprocessing,
    detect_dominant_color,
    extract_color_dominant_mask,
    preprocess_warning_for,
    skeletonize_mask,
)
from model.pipeline import run_raster_pipeline


# ---------------------------------------------------------------------------
# Synthetic fixtures
# ---------------------------------------------------------------------------


def _white_canvas(w: int = 240, h: int = 240) -> np.ndarray:
    return np.full((h, w, 3), 255, dtype=np.uint8)


def red_rectangle_on_white() -> np.ndarray:
    """Solid red rectangle outline on a white background. The rectangle is
    drawn in BGR (OpenCV native), so the red channel sits at index 2.
    """
    canvas = _white_canvas()
    cv2.rectangle(canvas, (40, 40), (200, 200), color=(0, 0, 255), thickness=8)
    return canvas


def black_rectangle_on_white() -> np.ndarray:
    canvas = _white_canvas()
    cv2.rectangle(canvas, (40, 40), (200, 200), color=(0, 0, 0), thickness=8)
    return canvas


def red_walls_with_grey_clutter() -> np.ndarray:
    """Red walls plus thin grey dimension lines and small text-like dots —
    the case the proto pipeline was designed for: keep red, drop the rest.
    """
    canvas = _white_canvas(320, 320)
    cv2.rectangle(canvas, (40, 40), (280, 280), color=(0, 0, 255), thickness=8)
    cv2.line(canvas, (40, 20), (280, 20), color=(120, 120, 120), thickness=1)
    cv2.line(canvas, (20, 40), (20, 280), color=(120, 120, 120), thickness=1)
    for x in (60, 90, 120, 150):
        cv2.circle(canvas, (x, 300), 1, color=(80, 80, 80), thickness=-1)
    return canvas


# ---------------------------------------------------------------------------
# color_mask
# ---------------------------------------------------------------------------


def test_extract_red_mask_returns_binary_mask() -> None:
    img = red_rectangle_on_white()
    mask = extract_color_dominant_mask(img, color_hint="red")

    assert mask.shape == img.shape[:2]
    assert mask.dtype == np.uint8
    assert set(np.unique(mask).tolist()).issubset({0, 255})
    # The rectangle outline is non-trivial pixel mass.
    assert (mask > 0).sum() > 1500


def test_extract_red_mask_ignores_white_background() -> None:
    img = red_rectangle_on_white()
    mask = extract_color_dominant_mask(img, color_hint="red")
    # Center of the canvas is white background -> must be 0.
    assert mask[120, 120] == 0
    # A pixel known to fall on the red outline -> must be 255.
    assert mask[40, 120] == 255


def test_extract_black_mask_picks_walls() -> None:
    img = black_rectangle_on_white()
    mask = extract_color_dominant_mask(img, color_hint="black")
    assert (mask > 0).sum() > 1500
    assert mask[120, 120] == 0  # white interior
    assert mask[40, 120] == 255  # black outline


def test_detect_dominant_color_picks_red_when_present() -> None:
    img = red_walls_with_grey_clutter()
    assert detect_dominant_color(img) == "red"


def test_detect_dominant_color_falls_back_to_black_on_grey_only() -> None:
    img = black_rectangle_on_white()
    # No chromatic mass -> defaults to black preset.
    assert detect_dominant_color(img) == "black"


def test_extract_with_auto_uses_dominant_color() -> None:
    img = red_walls_with_grey_clutter()
    auto_mask = extract_color_dominant_mask(img, color_hint="auto")
    red_mask = extract_color_dominant_mask(img, color_hint="red")
    assert np.array_equal(auto_mask, red_mask)


def test_unknown_color_hint_raises() -> None:
    img = red_rectangle_on_white()
    with pytest.raises(ValueError):
        extract_color_dominant_mask(img, color_hint="chartreuse")


def test_available_colors_contains_required_presets() -> None:
    for required in ("auto", "red", "black", "grey31"):
        assert required in AVAILABLE_COLORS


# ---------------------------------------------------------------------------
# skeleton
# ---------------------------------------------------------------------------


def test_skeletonize_reduces_pixel_mass() -> None:
    mask = extract_color_dominant_mask(red_rectangle_on_white(), color_hint="red")
    skel = skeletonize_mask(mask, redilate=0)
    assert (skel > 0).sum() < (mask > 0).sum()


# ---------------------------------------------------------------------------
# apply_preprocessing
# ---------------------------------------------------------------------------


def test_apply_preprocessing_none_is_identity() -> None:
    img = red_rectangle_on_white()
    out = apply_preprocessing(img, None)
    assert out is img  # no copy made


def test_apply_preprocessing_color_mask_returns_inverted_3ch() -> None:
    img = red_rectangle_on_white()
    out = apply_preprocessing(img, {"mode": "color_mask", "color": "red"})
    assert out.shape == img.shape
    assert out.dtype == np.uint8
    # Walls become near-black, background near-white.
    assert int(out[120, 120, 0]) >= 250  # background stays white
    assert int(out[40, 120, 0]) <= 5     # red wall becomes black


def test_apply_preprocessing_unknown_mode_raises() -> None:
    img = red_rectangle_on_white()
    with pytest.raises(ValueError):
        apply_preprocessing(img, {"mode": "magic"})


# ---------------------------------------------------------------------------
# Warning tag registry
# ---------------------------------------------------------------------------


def test_preprocess_warning_tag_for_color_mask() -> None:
    assert preprocess_warning_for("color_mask") == "preprocess_color_mask_applied"


def test_preprocess_warning_tag_unknown_mode_raises() -> None:
    with pytest.raises(ValueError):
        preprocess_warning_for("nope")


# ---------------------------------------------------------------------------
# Pipeline integration
# ---------------------------------------------------------------------------


def test_pipeline_emits_warning_when_preprocess_applied(tmp_path: Path) -> None:
    img = red_walls_with_grey_clutter()
    result = run_raster_pipeline(
        img,
        output_dir=tmp_path / "with_preprocess",
        preprocess={"mode": "color_mask", "color": "red"},
    )
    assert "preprocess_color_mask_applied" in result.observed_model["warnings"]


def test_pipeline_does_not_emit_preprocess_warning_when_disabled(tmp_path: Path) -> None:
    img = black_rectangle_on_white()
    result = run_raster_pipeline(img, output_dir=tmp_path / "no_preprocess")
    assert "preprocess_color_mask_applied" not in result.observed_model["warnings"]
