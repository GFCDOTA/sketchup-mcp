"""FP-030 — Side-by-side composer contract tests.

Uses the existing canonical PDF and a reuse of the canonical renders
in `artifacts/planta_74/`. Generates output into a tmp dir.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tools.compose_side_by_side import (
    DEFAULT_PDF_CROP, compose, compose_to_file, crop_pdf_to_floorplan,
    fit_to_height, render_pdf_page,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
PDF = REPO_ROOT / "planta_74.pdf"
TOP = REPO_ROOT / "artifacts" / "planta_74" / "planta_74_top.png"
ISO = REPO_ROOT / "artifacts" / "planta_74" / "planta_74_iso.png"


def test_render_pdf_page_returns_pil_image():
    pytest.importorskip("PIL")
    img = render_pdf_page(PDF)
    assert img.mode in {"RGB", "RGBA"}
    assert img.width > 100 and img.height > 100


def test_crop_pdf_to_floorplan_shrinks_image():
    img = render_pdf_page(PDF)
    crop = crop_pdf_to_floorplan(img, crop_box_fractional=DEFAULT_PDF_CROP)
    assert crop.width < img.width
    assert crop.height < img.height
    assert crop.width > 50 and crop.height > 50


def test_fit_to_height_preserves_aspect_ratio():
    from PIL import Image
    img = Image.new("RGB", (400, 200), "white")
    out = fit_to_height(img, 600)
    assert out.height == 600
    # Original ratio 400/200 = 2.0, so new width should be 1200
    assert out.width == 1200


def test_compose_produces_canvas_with_title_band():
    from PIL import Image
    a = Image.new("RGB", (100, 200), (255, 0, 0))
    b = Image.new("RGB", (150, 200), (0, 255, 0))
    c = Image.new("RGB", (200, 200), (0, 0, 255))
    canvas = compose(a, b, c, target_height=600, gap=20, title_band=60)
    # 3 panels at 600px, ratios preserved:
    #   a: 100/200 * 600 = 300
    #   b: 150/200 * 600 = 450
    #   c: 200/200 * 600 = 600
    # Total width = 300 + 20 + 450 + 20 + 600 = 1390
    assert canvas.width == 1390
    assert canvas.height == 660


@pytest.mark.skipif(
    not (TOP.exists() and ISO.exists()),
    reason="canonical artifacts/planta_74/ renders not present",
)
def test_compose_to_file_generates_output(tmp_path: Path):
    out = tmp_path / "side_by_side.png"
    result = compose_to_file(
        pdf_path=PDF, top_path=TOP, iso_path=ISO, out_path=out,
    )
    assert result == out
    assert out.exists()
    assert out.stat().st_size > 10_000  # at least 10 KB


def test_compose_to_file_raises_on_missing_pdf(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        compose_to_file(
            pdf_path=tmp_path / "nope.pdf",
            top_path=TOP, iso_path=ISO,
            out_path=tmp_path / "out.png",
        )


def test_compose_to_file_raises_on_missing_top(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        compose_to_file(
            pdf_path=PDF,
            top_path=tmp_path / "nope_top.png",
            iso_path=ISO,
            out_path=tmp_path / "out.png",
        )


def test_compose_to_file_raises_on_missing_iso(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        compose_to_file(
            pdf_path=PDF, top_path=TOP,
            iso_path=tmp_path / "nope_iso.png",
            out_path=tmp_path / "out.png",
        )
