"""Visual sanity-check for vector opening extraction.

Renders the source PDF in grayscale and overlays each detected opening
as a colored circle (center) + bbox + arrow towards the hinge corner.
Quickly tells you whether arcs were associated to the right walls.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image, ImageDraw, ImageFont


def render(pdf_path: Path, consensus_path: Path, out: Path,
           scale: float = 2.0, crop_to_region: bool = True) -> None:
    pdf = pdfium.PdfDocument(str(pdf_path))
    page = pdf[0]
    pw_pts, ph_pts = page.get_size()
    img = page.render(scale=scale).to_pil().convert("RGB")
    W, H = img.size
    consensus = json.loads(consensus_path.read_text(encoding="utf-8"))
    walls = consensus.get("walls", [])
    openings = consensus.get("openings", [])
    region = consensus.get("planta_region")
    crop_offset = (0, 0)

    if crop_to_region and region and len(region) == 4:
        margin = 20
        rx0, ry0, rx1, ry1 = region
        cx0 = max(0, int((rx0 - margin) * scale))
        cy0 = max(0, int((ph_pts - ry1 - margin) * scale))
        cx1 = min(W, int((rx1 + margin) * scale))
        cy1 = min(H, int((ph_pts - ry0 + margin) * scale))
        img = img.crop((cx0, cy0, cx1, cy1))
        W, H = img.size
        crop_offset = (cx0, cy0)

    draw = ImageDraw.Draw(img, "RGBA")
    try:
        font = ImageFont.truetype("arial.ttf", 14)
    except Exception:
        font = ImageFont.load_default()

    def to_px(pt_xy: tuple[float, float]) -> tuple[float, float]:
        # PDF y grows up; PIL y grows down; account for crop offset
        x_pt, y_pt = pt_xy
        return x_pt * scale - crop_offset[0], (ph_pts - y_pt) * scale - crop_offset[1]

    # walls in light blue
    for w in walls:
        x1, y1 = to_px(w["start"])
        x2, y2 = to_px(w["end"])
        draw.line([(x1, y1), (x2, y2)], fill=(80, 130, 220, 200),
                  width=max(2, int(w.get("thickness", 5) * scale * 0.3)))

    # openings: orange circle on the projected wall point + green dot on hinge
    palette = [
        (220, 38, 38), (234, 88, 12), (217, 119, 6), (180, 83, 9),
        (132, 204, 22), (16, 185, 129), (6, 182, 212), (37, 99, 235),
        (124, 58, 237), (192, 38, 211), (244, 63, 94), (251, 113, 133),
    ]
    for i, o in enumerate(openings):
        col = palette[i % len(palette)]
        cx_px, cy_px = to_px(o["center"])
        # bbox
        l, b, r, t = o["arc_bbox_pts"]
        x0, y0 = to_px((l, t))
        x1, y1 = to_px((r, b))
        draw.rectangle([x0, y0, x1, y1], outline=col + (220,), width=2)
        # opening center (large)
        rd = 8
        draw.ellipse([cx_px - rd, cy_px - rd, cx_px + rd, cy_px + rd],
                     outline=col + (255,), width=3)
        # hinge corner
        if "hinge_corner_pt" in o:
            hx, hy = to_px(o["hinge_corner_pt"])
            hd = 5
            draw.ellipse([hx - hd, hy - hd, hx + hd, hy + hd],
                         fill=(34, 197, 94, 255))
            draw.line([(hx, hy), (cx_px, cy_px)], fill=(34, 197, 94, 200), width=2)
        # label
        label = f"{o['id']} c={o['confidence']:.2f}"
        draw.text((cx_px + 10, cy_px - 10), label, fill=col + (255,), font=font)

    # legend
    draw.rectangle([0, 0, W, 30], fill=(255, 255, 255, 220))
    draw.text((6, 6),
              f"{pdf_path.name}  walls={len(walls)}  openings={len(openings)} "
              f"(orange circle = center on wall, green dot = hinge corner)",
              fill="black", font=font)

    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    print(f"[wrote] {out}  size={img.size}")

    if not os.environ.get("PNG_HISTORY_DISABLE"):
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from png_history import register
            register(out, kind="openings_overlay",
                     source={"consensus": consensus_path, "pdf": pdf_path},
                     generator="tools/render_openings_overlay.py",
                     params={"scale": scale, "openings": len(openings)})
        except Exception as e:
            print(f"[png_history skipped] {e}")


def _cli() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--consensus", type=Path,
                    default=Path("runs/vector/consensus_model.json"))
    ap.add_argument("--out", type=Path,
                    default=Path("runs/vector/openings_overlay.png"))
    ap.add_argument("--scale", type=float, default=2.5)
    args = ap.parse_args()
    render(args.pdf, args.consensus, args.out, args.scale)
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
