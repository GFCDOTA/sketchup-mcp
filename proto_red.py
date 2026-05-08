"""P8 - extract only RED pixels from a user-annotated PNG, emit mask + PDF.

Originally hardcoded ``C:/Users/felip_local/Documents/paredes.png``;
refactored 2026-05-08 to take a CLI input path so it can be
ruff-checked and reused across machines.

Example::

    python proto_red.py --input paredes.png
    python proto_red.py --input C:/path/to/painted.png --output-dir runs/proto

Outputs (in ``--output-dir``)::

    p8_red_mask.png        # raw red HSV mask
    p8_red.pdf             # 150 dpi PDF of the (inverted) red mask
    p8_red_skel_mask.png   # 1-px skeletonised + dilated red mask
    p8_red_skel.pdf        # 150 dpi PDF of the skeleton
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from skimage.morphology import skeletonize


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

    # 1) red filter: R high, G/B low. Use HSV for robustness.
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    # red wraps around 0/180 in HSV, so two ranges
    m1 = cv2.inRange(hsv, (0, 100, 80), (12, 255, 255))
    m2 = cv2.inRange(hsv, (170, 100, 80), (180, 255, 255))
    red = cv2.bitwise_or(m1, m2)

    # 2) close to reconnect small fragments
    red = cv2.morphologyEx(red, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8), iterations=2)
    print(f"red px: {(red > 0).sum():,}")

    # 3) raw variant (thick lines) -> PDF
    cv2.imwrite(str(out / "p8_red_mask.png"), red)
    Image.fromarray(255 - red).convert("RGB").save(out / "p8_red.pdf", "PDF", resolution=150.0)

    # 4) skeletonised variant (1px centerline) -> PDF
    skel = skeletonize(red > 0).astype(np.uint8) * 255
    skel = cv2.dilate(skel, np.ones((3, 3), np.uint8), iterations=2)
    cv2.imwrite(str(out / "p8_red_skel_mask.png"), skel)
    Image.fromarray(255 - skel).convert("RGB").save(
        out / "p8_red_skel.pdf", "PDF", resolution=150.0
    )
    print("done")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Extract red pixels from an annotated floor-plan PNG; "
            "emit raw mask + skeletonised mask as PNG and PDF (150 dpi)."
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
        help="Directory to write p8_red_*.{png,pdf} into. Default: runs/proto",
    )
    return p


if __name__ == "__main__":
    sys.exit(main(build_parser().parse_args()))
