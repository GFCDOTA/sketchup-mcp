"""Render the openings refinement conclusion as a single PNG.

4 panels in a 2x2 grid: baseline, post-A, post-A+B, post-A+B+C+D (final).
Walls in light gray, openings as filled circles color-coded by stage.
Numbers and delta chips on top of each panel.

Usage:
    python scripts/render_openings_conclusion_png.py \\
        --out runs/openings_conclusion.png
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


STAGES = [
    {"path": "runs/openings_refine_baseline/observed_model.json", "title": "Baseline",
     "sub": "detect_openings bruto", "color": (214, 96, 77), "delta": None},
    {"path": "runs/openings_refine_v1_a/observed_model.json", "title": "Filtro A",
     "sub": "prune orphan", "color": (224, 130, 20), "delta": -28},
    {"path": "runs/openings_refine_v1_b/observed_model.json", "title": "Filtro A+B",
     "sub": "+ size floor 3.5xt", "color": (253, 184, 99), "delta": -3},
    {"path": "runs/openings_refine_final/observed_model.json", "title": "Final A+B+C+D",
     "sub": "+ dedup 1.5xt + roomless", "color": (27, 120, 55), "delta": -13},
]


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in (
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def load_font_mono(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in (
        "C:/Windows/Fonts/consola.ttf",
        "C:/Windows/Fonts/cour.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    ):
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def plan_bounds(walls: list[dict]) -> tuple[float, float, float, float]:
    xs, ys = [], []
    for w in walls:
        xs.extend([w["start"][0], w["end"][0]])
        ys.extend([w["start"][1], w["end"][1]])
    return min(xs), min(ys), max(xs), max(ys)


def draw_panel(
    base: Image.Image,
    stage: dict,
    panel_box: tuple[int, int, int, int],
    font_title: ImageFont.ImageFont,
    font_sub: ImageFont.ImageFont,
    font_mono: ImageFont.ImageFont,
    font_big: ImageFont.ImageFont,
) -> None:
    x0, y0, x1, y1 = panel_box
    w = x1 - x0
    h = y1 - y0

    draw = ImageDraw.Draw(base)
    # Panel background
    draw.rectangle(panel_box, fill=(22, 27, 34), outline=(48, 54, 61), width=2)

    # Header strip
    header_h = 72
    draw.rectangle([x0, y0, x1, y0 + header_h], fill=(31, 36, 44))

    # Title + subtitle
    draw.text((x0 + 16, y0 + 10), stage["title"], font=font_title, fill=(230, 237, 243))
    draw.text((x0 + 16, y0 + 38), stage["sub"], font=font_sub, fill=(139, 148, 158))

    # Count badge on the right
    model = json.loads(Path(stage["path"]).read_text(encoding="utf-8"))
    count = len(model["openings"])
    r, g, b = stage["color"]
    badge_text = str(count)
    bbox = draw.textbbox((0, 0), badge_text, font=font_big)
    bw = bbox[2] - bbox[0]
    draw.text((x1 - bw - 20, y0 + 8), badge_text, font=font_big, fill=(r, g, b))
    draw.text((x1 - 90, y0 + 48), "openings", font=font_sub, fill=(139, 148, 158))

    # Delta chip
    if stage["delta"] is not None:
        delta_text = f"{stage['delta']:+d}"
        chip_font = font_sub
        dbox = draw.textbbox((0, 0), delta_text, font=chip_font)
        dw = dbox[2] - dbox[0] + 16
        dh = dbox[3] - dbox[1] + 8
        chip_x = x1 - bw - 20 - dw - 10
        chip_y = y0 + 18
        chip_color = (63, 185, 80) if stage["delta"] < 0 else (248, 81, 73)
        draw.rounded_rectangle(
            [chip_x, chip_y, chip_x + dw, chip_y + dh], radius=8, fill=(22, 27, 34), outline=chip_color
        )
        draw.text((chip_x + 8, chip_y + 2), delta_text, font=chip_font, fill=chip_color)

    # Plan area (below header)
    pax0, pay0 = x0 + 12, y0 + header_h + 8
    pax1, pay1 = x1 - 12, y1 - 12
    minx, miny, maxx, maxy = plan_bounds(model["walls"])
    pad = 30
    plan_w = (maxx - minx) + 2 * pad
    plan_h = (maxy - miny) + 2 * pad
    scale = min((pax1 - pax0) / plan_w, (pay1 - pay0) / plan_h)
    draw_w = plan_w * scale
    draw_h = plan_h * scale
    tx = pax0 + ((pax1 - pax0) - draw_w) / 2
    ty = pay0 + ((pay1 - pay0) - draw_h) / 2

    def P(x: float, y: float) -> tuple[int, int]:
        return (int(tx + (x - minx + pad) * scale), int(ty + (y - miny + pad) * scale))

    # Walls in light gray
    for wall in model["walls"]:
        p0 = P(*wall["start"])
        p1 = P(*wall["end"])
        draw.line([p0, p1], fill=(168, 168, 168), width=1)

    # Openings as filled circles
    for o in model["openings"]:
        cx, cy = o["center"]
        rr = max(3, int((o["width"] / 2) * scale))
        ox, oy = P(cx, cy)
        draw.ellipse([ox - rr, oy - rr, ox + rr, oy + rr], fill=(r, g, b, 200), outline=(r, g, b))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    # Total canvas
    panel_w = 900
    panel_h = 560
    gap = 20
    header_total_h = 120

    canvas_w = panel_w * 2 + gap * 3
    canvas_h = panel_h * 2 + gap * 3 + header_total_h

    img = Image.new("RGB", (canvas_w, canvas_h), (14, 17, 22))
    draw = ImageDraw.Draw(img)

    font_hero = load_font(36)
    font_title = load_font(22)
    font_sub = load_font_mono(15)
    font_mono = load_font_mono(14)
    font_big = load_font(52)

    # Top header
    draw.text(
        (gap * 2, 24),
        "openings refinement — planta_74m2.svg",
        font=font_hero,
        fill=(230, 237, 243),
    )
    draw.text(
        (gap * 2, 74),
        "68 -> 24 openings (-65%) · walls / rooms / junctions inalterados · raster byte-identical",
        font=font_sub,
        fill=(139, 148, 158),
    )

    # 2x2 grid
    for idx, stage in enumerate(STAGES):
        col = idx % 2
        row = idx // 2
        ox = gap + col * (panel_w + gap)
        oy = header_total_h + gap + row * (panel_h + gap)
        draw_panel(img, stage, (ox, oy, ox + panel_w, oy + panel_h),
                   font_title, font_sub, font_mono, font_big)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    img.save(args.out, "PNG", optimize=True)
    print(f"wrote {args.out} ({canvas_w}x{canvas_h})")


if __name__ == "__main__":
    main()
