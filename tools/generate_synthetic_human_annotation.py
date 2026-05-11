"""Generate a synthetic human-openings annotation image for testing.

Produces a PNG that mimics what the human would paint on top of a
planta render: solid GREEN / MAGENTA / ORANGE rectangles at PDF
coordinates picked to mirror the planta_74 user spec (2026-05-11):
- 7 green = interior doors
- 4 magenta = windows
- 1 orange = glazed_balcony

This is a TEST FIXTURE for the human-openings pipeline. It is NOT a
substitute for a real reviewer-painted image; it exists so the
extract → apply → gate pipeline can run end-to-end before any real
annotation drops.

Coordinates were picked from:
- The planta_74 room centroids in the locked baseline
- The user's positional constraints (BANHO 02 west door,
  SALA ESTAR↔TERRACO SOCIAL balcony, SUITE 02 south window)

When the real image arrives at
``fixtures/planta_74/human_openings_annotation.png``, the same
extract → apply → gate pipeline runs unchanged.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

# 12 synthetic blob positions for planta_74 (PDF pts, y-up). Chosen
# to mirror the user-mandated counts; positions are approximate but
# inside the planta_region [39, 395, 564, 708].
#
# (center_x_pt, center_y_pt, width_pt, height_pt, color_name)
SYNTHETIC_BLOBS: list[tuple[float, float, float, float, str]] = [
    # 7 interior doors (green)
    (335, 550, 8, 22, "green"),   # BANHO 02 west door (per user constraint)
    (470, 605, 8, 22, "green"),   # SUITE 01 → BANHO 01
    (320, 595, 22, 8, "green"),   # SUITE 01 entrance
    (260, 595, 8, 22, "green"),   # SUITE 02 entrance (south of LAVABO)
    (295, 625, 8, 22, "green"),   # LAVABO door
    (90,  555, 22, 8,  "green"),  # A.S. door (from COZINHA)
    (175, 620, 22, 8,  "green"),  # SALA DE JANTAR / COZINHA passage
    # 4 windows (magenta)
    (320, 410, 35, 8,  "magenta"),  # SUITE 02 south window (per user)
    (395, 685, 35, 8,  "magenta"),  # SALA DE JANTAR street window
    (50,  580, 8,  35, "magenta"),  # A.S. side window
    (548, 580, 8,  35, "magenta"),  # BANHO 01 east window
    # 1 glazed_balcony (orange)
    (155, 460, 80, 8,  "orange"),   # SALA DE ESTAR ↔ TERRACO SOCIAL
]

COLOR_RGB: dict[str, tuple[int, int, int]] = {
    "green":   (0, 255, 0),
    "magenta": (255, 0, 255),
    "orange":  (255, 165, 0),
}


def generate(out_path: Path,
             pdf_width: float = 595.0,
             pdf_height: float = 842.0,
             scale: float = 2.0,
             base_image: Path | None = None) -> None:
    """Write a synthetic annotation PNG.

    ``scale`` controls pixel-per-pt density. Default 2 → 1190×1684
    pixels for a planta_74 page, matching ``render_axon`` output.
    If ``base_image`` is provided, blobs are painted on top of it
    (useful for human-style annotations on the actual planta render).
    Otherwise the canvas is plain white.
    """
    img_w = int(pdf_width * scale)
    img_h = int(pdf_height * scale)

    if base_image and base_image.exists():
        img = Image.open(base_image).convert("RGB")
        img_w, img_h = img.size
    else:
        img = Image.new("RGB", (img_w, img_h), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Scale factor PDF→image with the current canvas size
    sx = img_w / pdf_width
    sy = img_h / pdf_height

    for cx_pt, cy_pt, w_pt, h_pt, color in SYNTHETIC_BLOBS:
        rgb = COLOR_RGB[color]
        x0_pt = cx_pt - w_pt / 2
        x1_pt = cx_pt + w_pt / 2
        y0_pt = cy_pt - h_pt / 2
        y1_pt = cy_pt + h_pt / 2
        # PDF y-up → PIL y-down
        l_px = x0_pt * sx
        r_px = x1_pt * sx
        t_px = img_h - y1_pt * sy
        b_px = img_h - y0_pt * sy
        draw.rectangle((l_px, t_px, r_px, b_px), fill=rgb)

    img.save(out_path, "PNG")
    print(f"[ok] synthetic annotation -> {out_path} "
          f"({img_w}x{img_h}px, {len(SYNTHETIC_BLOBS)} blobs)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--pdf-width-pts", type=float, default=595.0)
    ap.add_argument("--pdf-height-pts", type=float, default=842.0)
    ap.add_argument("--scale", type=float, default=2.0)
    ap.add_argument("--base-image", type=Path, default=None,
                    help="Optional base image to paint on top of "
                         "(typically a planta render PNG).")
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    generate(args.out, args.pdf_width_pts, args.pdf_height_pts,
              args.scale, args.base_image)


if __name__ == "__main__":
    main()


# ----- silence unused-import lint (numpy reserved for future variants) -----
_ = np
