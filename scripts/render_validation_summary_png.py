"""Render consolidated validation summary PNG — F1 scores across all plans.

Shows 5 plans (planta_74m2 + 4 synthetics) with walls + openings rendered
for each, plus F1/P/R badges. Meant as the headline artifact for the
VALIDATION-F1-REPORT.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

# Reuse helpers from existing renderer
sys.path.insert(0, str(Path(__file__).parent))
from render_openings_conclusion_png import load_font, load_font_mono, plan_bounds
from score_openings import load_detections, load_gt, match_openings


PLANS = [
    ("planta_74m2", "runs/validation_p74/observed_model.json",
     "tests/fixtures/svg/planta_74m2_openings_gt.yaml", "alpha GT (pipeline-derived)"),
    ("studio", "runs/synth_studio/observed_model.json",
     "tests/fixtures/svg/synthetic/studio_openings_gt.yaml", "synthetic — 3 rooms"),
    ("2br", "runs/synth_2br/observed_model.json",
     "tests/fixtures/svg/synthetic/2br_openings_gt.yaml", "synthetic — 2 bedrooms"),
    ("3br", "runs/synth_3br/observed_model.json",
     "tests/fixtures/svg/synthetic/3br_openings_gt.yaml", "synthetic — 3 bedrooms"),
    ("lshape", "runs/synth_lshape/observed_model.json",
     "tests/fixtures/svg/synthetic/lshape_openings_gt.yaml", "synthetic — L-shape"),
]


def draw_plan_panel(
    base: Image.Image,
    plan_name: str,
    model_path: str,
    gt_path: str,
    subtitle: str,
    panel_box: tuple[int, int, int, int],
    font_title,
    font_sub,
    font_big,
    font_mono,
) -> None:
    x0, y0, x1, y1 = panel_box
    w = x1 - x0
    h = y1 - y0

    draw = ImageDraw.Draw(base)
    draw.rectangle(panel_box, fill=(22, 27, 34), outline=(48, 54, 61), width=2)

    header_h = 82
    draw.rectangle([x0, y0, x1, y0 + header_h], fill=(31, 36, 44))

    # Title
    draw.text((x0 + 16, y0 + 10), plan_name, font=font_title, fill=(230, 237, 243))
    draw.text((x0 + 16, y0 + 36), subtitle, font=font_sub, fill=(139, 148, 158))

    # Run score
    thickness, gt_openings = load_gt(Path(gt_path))
    dets, _walls = load_detections(Path(model_path))
    result = match_openings(gt_openings, dets, thickness=thickness)
    tp = len(result.tp_pairs)
    fp = len(result.fp)
    fn = len(result.fn)
    precision = result.precision
    recall = result.recall
    f1 = result.f1

    # F1 big number
    f1_text = f"{f1:.3f}"
    bbox = draw.textbbox((0, 0), f1_text, font=font_big)
    tw = bbox[2] - bbox[0]
    f1_color = (63, 185, 80) if f1 >= 0.90 else ((210, 153, 34) if f1 >= 0.75 else (248, 81, 73))
    draw.text((x1 - tw - 20, y0 + 6), f1_text, font=font_big, fill=f1_color)
    draw.text((x1 - 85, y0 + 52), "F1 score", font=font_sub, fill=(139, 148, 158))

    # P/R/TP/FP/FN line
    metrics = f"P={precision:.2f}  R={recall:.2f}  TP={tp}  FP={fp}  FN={fn}"
    draw.text((x0 + 16, y0 + 58), metrics, font=font_mono, fill=(139, 148, 158))

    # Plan area
    m = json.loads(Path(model_path).read_text(encoding="utf-8"))
    walls = m["walls"]
    openings = m["openings"]
    if not walls:
        draw.text((x0 + w // 2 - 60, y0 + h // 2), "(no walls)", font=font_sub, fill=(139, 148, 158))
        return

    pax0, pay0 = x0 + 12, y0 + header_h + 8
    pax1, pay1 = x1 - 12, y1 - 12
    minx, miny, maxx, maxy = plan_bounds(walls)
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

    # Walls light gray
    for wall in walls:
        p0 = P(*wall["start"])
        p1 = P(*wall["end"])
        draw.line([p0, p1], fill=(168, 168, 168), width=1)

    # TPs as green filled
    matched_det_ids = {pair[1].opening_id for pair in result.tp_pairs}
    matched_gt_ids = {pair[0].gt_id for pair in result.tp_pairs}

    # Match detections to render
    for o in openings:
        cx, cy = o["center"]
        rr = max(4, int((o["width"] / 2) * scale))
        ox, oy = P(cx, cy)
        if o["opening_id"] in matched_det_ids:
            color = (63, 185, 80)  # green TP
        else:
            color = (248, 81, 73)  # red FP
        draw.ellipse([ox - rr, oy - rr, ox + rr, oy + rr], fill=color, outline=color)

    # FN as orange ring at GT position
    for gt_op in gt_openings:
        if gt_op.gt_id in matched_gt_ids:
            continue
        cx, cy = gt_op.center
        rr = max(4, int((gt_op.width / 2) * scale))
        ox, oy = P(cx, cy)
        draw.ellipse([ox - rr, oy - rr, ox + rr, oy + rr], outline=(210, 153, 34), width=3)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    cols, rows = 3, 2
    panel_w = 640
    panel_h = 470
    gap = 16
    header_h = 120

    total_w = cols * panel_w + (cols + 1) * gap
    total_h = header_h + rows * panel_h + (rows + 1) * gap

    img = Image.new("RGB", (total_w, total_h), (14, 17, 22))
    draw = ImageDraw.Draw(img)

    font_hero = load_font(36)
    font_title = load_font(22)
    font_sub = load_font_mono(14)
    font_mono = load_font_mono(13)
    font_big = load_font(50)

    draw.text((gap * 2, 24), "Openings validation — F1 across 5 plans", font=font_hero, fill=(230, 237, 243))
    draw.text(
        (gap * 2, 74),
        "5/5 plans F1 >= 0.90 target (green).  Synthetics carry generalization signal; planta_74m2 alpha GT is self-consistent.",
        font=font_sub,
        fill=(139, 148, 158),
    )

    for idx, (name, model_path, gt_path, subtitle) in enumerate(PLANS):
        col = idx % cols
        row = idx // cols
        ox = gap + col * (panel_w + gap)
        oy = header_h + gap + row * (panel_h + gap)
        draw_plan_panel(img, name, model_path, gt_path, subtitle,
                       (ox, oy, ox + panel_w, oy + panel_h),
                       font_title, font_sub, font_big, font_mono)

    # Legend area in the unused 6th slot
    idx = 5
    col = idx % cols
    row = idx // cols
    ox = gap + col * (panel_w + gap)
    oy = header_h + gap + row * (panel_h + gap)
    draw.rectangle([ox, oy, ox + panel_w, oy + panel_h], fill=(22, 27, 34), outline=(48, 54, 61), width=2)
    draw.text((ox + 20, oy + 20), "Legend", font=font_title, fill=(230, 237, 243))
    items = [
        ("walls", (168, 168, 168), "line"),
        ("TP (matched detection)", (63, 185, 80), "fill"),
        ("FP (false positive)", (248, 81, 73), "fill"),
        ("FN (missed GT)", (210, 153, 34), "ring"),
    ]
    for i, (label, color, shape) in enumerate(items):
        y = oy + 60 + i * 36
        if shape == "line":
            draw.line([(ox + 24, y + 8), (ox + 80, y + 8)], fill=color, width=2)
        elif shape == "fill":
            draw.ellipse([ox + 40, y, ox + 56, y + 16], fill=color)
        else:
            draw.ellipse([ox + 40, y, ox + 56, y + 16], outline=color, width=3)
        draw.text((ox + 100, y), label, font=font_sub, fill=(230, 237, 243))
    draw.text((ox + 20, oy + 220), "Thresholds", font=font_title, fill=(230, 237, 243))
    details = [
        ("center_tol = 2 x thickness (12.5 px on SVG)", 260),
        ("width_ratio must fall in [0.5, 2.0]", 286),
        ("F1 >= 0.90 = green", 312),
        ("F1 in [0.75, 0.90) = amber", 338),
        ("F1 < 0.75 = red", 364),
    ]
    for text, dy in details:
        draw.text((ox + 24, oy + dy), text, font=font_sub, fill=(139, 148, 158))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    img.save(args.out, "PNG", optimize=True)
    print(f"wrote {args.out} ({total_w}x{total_h})")


if __name__ == "__main__":
    main()
