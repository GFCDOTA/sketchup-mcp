#!/usr/bin/env python3
"""FP-030 — Side-by-side composite (PDF | SKP top | SKP iso).

Standalone composer that replaces the ad-hoc PIL inline used in PR #200.

Usage:
    python -m tools.compose_side_by_side \\
        --pdf fixtures/planta_74/planta_74.pdf \\
        --top runs/planta_74/model_top.png \\
        --iso runs/planta_74/model_iso.png \\
        --out artifacts/review/planta_74/<run>/final/side_by_side_pdf_vs_skp.png

Behaviour:
- Renders page 1 of the PDF via pypdfium2 at 2.0x scale
- Auto-crops the white margins on the right (legend/notes) by cropping
  to the top-left 78% width × 48% height of the PDF page
- Normalises top + iso renders to the same height as the PDF crop (600 px)
- Composes horizontally with 20px gaps and discrete titles
- Exits 1 with a clear message if any input file is missing
- Does NOT distort aspect ratio (uses Image.LANCZOS resize preserving
  width-to-height ratio)

Tests: `tests/test_side_by_side_composer.py`.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
import pypdfium2 as pdfium

DEFAULT_TARGET_HEIGHT = 600
DEFAULT_GAP_PX = 20
DEFAULT_TITLE_BAND_PX = 60
DEFAULT_PDF_SCALE = 2.0
# Crop box of the PDF page, in fractions of (width, height), to skip the
# header banner and the legend/notes column on the right. Tuned for the
# planta_74 PDF layout but small enough that other landscape/portrait
# floor plans still show their main drawing area.
DEFAULT_PDF_CROP = (0.05, 0.07, 0.78, 0.55)


def render_pdf_page(pdf_path: Path, page_idx: int = 0,
                    scale: float = DEFAULT_PDF_SCALE) -> Image.Image:
    """Render a PDF page to a PIL image."""
    doc = pdfium.PdfDocument(str(pdf_path))
    if page_idx >= len(doc):
        raise ValueError(
            f"PDF has {len(doc)} pages; cannot render page {page_idx}"
        )
    return doc[page_idx].render(scale=scale).to_pil()


def crop_pdf_to_floorplan(
    pdf_img: Image.Image,
    crop_box_fractional: tuple[float, float, float, float] = DEFAULT_PDF_CROP,
) -> Image.Image:
    """Crop the rendered PDF page to the floor plan region.

    crop_box_fractional = (left, top, right, bottom) as fractions of
    the image size. Defaults are tuned for the planta_74 layout."""
    w, h = pdf_img.size
    l, t, r, b = crop_box_fractional
    return pdf_img.crop((int(w * l), int(h * t), int(w * r), int(h * b)))


def fit_to_height(img: Image.Image, target_h: int) -> Image.Image:
    """Resize preserving aspect ratio to the target height."""
    if img.height == target_h:
        return img
    ratio = target_h / img.height
    new_w = max(1, int(img.width * ratio))
    return img.resize((new_w, target_h), Image.LANCZOS)


def _load_font(size: int) -> ImageFont.ImageFont:
    """Load a system font with graceful fallback."""
    for name in ("arial.ttf", "DejaVuSans.ttf", "FreeSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def compose(
    pdf_crop: Image.Image,
    top_img: Image.Image,
    iso_img: Image.Image,
    *,
    target_height: int = DEFAULT_TARGET_HEIGHT,
    gap: int = DEFAULT_GAP_PX,
    title_band: int = DEFAULT_TITLE_BAND_PX,
    titles: tuple[str, str, str] = (
        "PDF (page 1, cropped)", "SKP top", "SKP iso"
    ),
    background_rgb: tuple[int, int, int] = (245, 245, 245),
    title_rgb: tuple[int, int, int] = (20, 20, 20),
) -> Image.Image:
    """Compose the 3-panel side-by-side. Returns the canvas image."""
    pdf_fit = fit_to_height(pdf_crop, target_height)
    top_fit = fit_to_height(top_img, target_height)
    iso_fit = fit_to_height(iso_img, target_height)

    total_w = pdf_fit.width + top_fit.width + iso_fit.width + gap * 2
    total_h = target_height + title_band
    canvas = Image.new("RGB", (total_w, total_h), background_rgb)

    canvas.paste(pdf_fit, (0, title_band))
    canvas.paste(top_fit, (pdf_fit.width + gap, title_band))
    canvas.paste(
        iso_fit, (pdf_fit.width + gap + top_fit.width + gap, title_band)
    )

    draw = ImageDraw.Draw(canvas)
    font = _load_font(max(14, title_band // 3))
    x_positions = [
        10,
        pdf_fit.width + gap + 10,
        pdf_fit.width + gap + top_fit.width + gap + 10,
    ]
    y_title = max(8, (title_band - font.size) // 2)
    for x, title in zip(x_positions, titles):
        draw.text((x, y_title), title, fill=title_rgb, font=font)

    return canvas


def compose_to_file(
    *,
    pdf_path: Path,
    top_path: Path,
    iso_path: Path,
    out_path: Path,
    target_height: int = DEFAULT_TARGET_HEIGHT,
) -> Path:
    """Full pipeline: validate inputs, render, compose, save. Returns
    the output path."""
    missing: list[Path] = []
    for label, p in [("--pdf", pdf_path), ("--top", top_path), ("--iso", iso_path)]:
        if not p.exists():
            missing.append(p)
    if missing:
        for p in missing:
            print(
                f"[compose_side_by_side] missing input: {p}",
                file=sys.stderr,
            )
        raise FileNotFoundError(
            "one or more inputs missing; see stderr"
        )

    pdf_full = render_pdf_page(pdf_path)
    pdf_crop = crop_pdf_to_floorplan(pdf_full)
    top_img = Image.open(top_path)
    iso_img = Image.open(iso_path)

    canvas = compose(pdf_crop, top_img, iso_img, target_height=target_height)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path, optimize=True)
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compose PDF | SKP top | SKP iso side-by-side panel.",
    )
    parser.add_argument("--pdf", type=Path, required=True,
                        help="Source PDF (page 1 will be rendered + cropped)")
    parser.add_argument("--top", type=Path, required=True,
                        help="SKP top render PNG")
    parser.add_argument("--iso", type=Path, required=True,
                        help="SKP iso render PNG")
    parser.add_argument("--out", type=Path, required=True,
                        help="Output composite PNG path")
    parser.add_argument("--target-height", type=int,
                        default=DEFAULT_TARGET_HEIGHT,
                        help="Per-panel height in pixels (default: 600)")
    args = parser.parse_args()

    try:
        out = compose_to_file(
            pdf_path=args.pdf,
            top_path=args.top,
            iso_path=args.iso,
            out_path=args.out,
            target_height=args.target_height,
        )
    except FileNotFoundError:
        return 1
    except Exception as exc:
        print(f"[compose_side_by_side] error: {exc!r}", file=sys.stderr)
        return 2

    sz = out.stat().st_size // 1024
    print(f"[compose_side_by_side] wrote {out} ({sz} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
