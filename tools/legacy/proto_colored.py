"""P9 - dual filter on an annotated floor-plan PNG.

RED -> walls full-height. BROWN -> peitoril (low parapet, ~1.10 m).
Saves a mask PNG + a wall-only PDF for the red channel and a JSON
manifest of bounding boxes for the brown channel so downstream
``Wall(kind=peitoril)`` records can be generated later.

Originally hardcoded ``C:/Users/felip_local/Documents/paredes.png``;
refactored 2026-05-08 to take a CLI input path so it can be
ruff-checked and reused across machines.

Example::

    python proto_colored.py --input paredes.png
    python proto_colored.py --input C:/path/to/painted.png --output-dir runs/proto

Outputs (in ``--output-dir``)::

    p9_red_mask.png        # raw red HSV mask
    p9_brown_mask.png      # raw brown HSV mask (red removed)
    p9_red.pdf             # 150 dpi PDF of the (inverted) red mask
    p9_peitoris.json       # bbox + area of each brown blob (>= --min-peitoril-area px)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


def main(args: argparse.Namespace) -> int:
    src = Path(args.input)
    if not src.exists():
        print(f"ERROR: input not found: {src}", file=sys.stderr)
        return 2

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    img = cv2.imread(str(src))
    if img is None:
        print(f"ERROR: cv2 failed to read: {src}", file=sys.stderr)
        return 2
    print(f"input: {img.shape}")
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    # red (2 ranges in HSV — wraps around 0/180)
    r1 = cv2.inRange(hsv, (0, 100, 80), (12, 255, 255))
    r2 = cv2.inRange(hsv, (170, 100, 80), (180, 255, 255))
    red = cv2.bitwise_or(r1, r2)
    red = cv2.morphologyEx(red, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8), iterations=2)
    print(f"red px: {(red > 0).sum():,}")

    # brown (~hue 10-25, sat high, mid value)
    brown = cv2.inRange(hsv, (8, 80, 40), (25, 255, 180))
    # remove overlap with red (intense red can hit the low-hue range)
    brown = cv2.bitwise_and(brown, cv2.bitwise_not(red))
    brown = cv2.morphologyEx(brown, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8), iterations=2)
    print(f"brown px: {(brown > 0).sum():,}")

    # save masks for debug
    cv2.imwrite(str(out / "p9_red_mask.png"), red)
    cv2.imwrite(str(out / "p9_brown_mask.png"), brown)

    # walls in PDF (red only)
    Image.fromarray(255 - red).convert("RGB").save(
        out / "p9_red.pdf", "PDF", resolution=150.0
    )

    # peitoris: emit JSON with bounding boxes for downstream consensus injection
    n, _lbl, st, _ctr = cv2.connectedComponentsWithStats(brown, 8)
    peitoris = []
    for i in range(1, n):
        x, y, w, h, area = st[i]
        if area < args.min_peitoril_area:
            continue
        peitoris.append({
            "peitoril_id": f"peitoril-{i}",
            "bbox": [int(x), int(y), int(x + w), int(y + h)],
            "area_px": int(area),
            "kind": "peitoril",
            "height_m": args.peitoril_height_m,
        })
    (out / "p9_peitoris.json").write_text(json.dumps(peitoris, indent=2))
    print(f"peitoris: {len(peitoris)}")
    print("done")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Dual-filter an annotated floor-plan PNG: red -> walls full-height, "
            "brown -> peitoril (low parapet). Emits red mask PNG/PDF + brown mask "
            "PNG + peitoris JSON manifest."
        ),
    )
    p.add_argument(
        "--input",
        required=True,
        help="Path to the annotated PNG (e.g. paredes.png).",
    )
    p.add_argument(
        "--output-dir",
        default="runs/proto",
        help="Directory to write p9_* artifacts into. Default: runs/proto",
    )
    p.add_argument(
        "--min-peitoril-area",
        type=int,
        default=200,
        help=(
            "Minimum brown blob area (px) to register as a peitoril. "
            "Default: 200"
        ),
    )
    p.add_argument(
        "--peitoril-height-m",
        type=float,
        default=1.10,
        help=(
            "Height (m) recorded in p9_peitoris.json for each blob. "
            "Default: 1.10 (per the floor-plan legend)."
        ),
    )
    return p


if __name__ == "__main__":
    sys.exit(main(build_parser().parse_args()))
