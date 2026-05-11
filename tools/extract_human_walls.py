"""Extract human-painted walls from a color-coded PNG annotation.

Same architectural shape as ``tools/extract_human_openings.py`` — auto-
calibrate image-px to PDF-pt via the consensus wall bbox, mask pixels
by target color, run cv2 connected components, derive geometry for
each blob, emit a machine-readable truth JSON.

Color contract (planta_74):
- BLUE     #0000ff  →  structural wall (axis-aligned)
- PURPLE   #8000ff  →  alternative — also accepted as wall (reviewer preference)

Each blob is converted to a wall with:
- orientation: derived from bbox aspect ratio
- start, end: along the long axis at the cross-axis midpoint
- thickness: pulled from ``consensus.wall_thickness_pts`` (no invention)
- geometry_origin: ``"human_annotation"``

Output schema: ``fixtures/planta_74/human_walls_truth.schema.json``.

Companion: ``tools/apply_human_walls.py``,
``tools/render_human_walls_annotation_base.py``.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

# Default color → kind mapping. Wall paints in BLUE; PURPLE accepted as
# alternative so the reviewer can use either depending on PDF contrast.
DEFAULT_WALL_COLORS: dict[str, dict[str, Any]] = {
    "blue":   {"rgb": [0, 0, 255]},
    "purple": {"rgb": [128, 0, 255]},
}
DEFAULT_COLOR_TOLERANCE = 35
MIN_BLOB_AREA_PX = 60


@dataclass
class ExtractedWall:
    id: str
    color: str
    bbox_px: list[float]
    bbox_pts: list[float]
    orientation: str       # 'h' or 'v'
    start: list[float]     # PDF pts
    end: list[float]       # PDF pts
    thickness: float       # PDF pts (from consensus)
    geometry_origin: str = "human_annotation"


def _build_color_mask(img_rgb: np.ndarray,
                       target_rgb: tuple[int, int, int],
                       tol: int) -> np.ndarray:
    diff = np.abs(img_rgb.astype(np.int16)
                   - np.array(target_rgb, dtype=np.int16))
    mask = np.all(diff <= tol, axis=-1).astype(np.uint8) * 255
    return mask


def _auto_calibrate(img_rgb: np.ndarray,
                     walls: list[dict],
                     wall_color: tuple[int, int, int] = (158, 158, 158),
                     wall_tol: int = 35) -> dict | None:
    """Mirror of extract_human_openings._auto_calibrate but tuned to
    the render_human_walls_annotation_base output (walls drawn at RGB
    (158, 158, 158) — Matplotlib gray ``#9e9e9e``). The base image is
    rendered programmatically so the wall color is deterministic.

    Returns affine transform image-px → PDF-pt.
    """
    if not walls:
        return None
    pdf_xs = [pt[0] for w in walls for pt in (w.get("start"), w.get("end")) if pt]
    pdf_ys = [pt[1] for w in walls for pt in (w.get("start"), w.get("end")) if pt]
    if not pdf_xs or not pdf_ys:
        return None
    pdf_x0, pdf_x1 = float(min(pdf_xs)), float(max(pdf_xs))
    pdf_y0, pdf_y1 = float(min(pdf_ys)), float(max(pdf_ys))

    diff = np.abs(img_rgb.astype(np.int16)
                   - np.array(wall_color, dtype=np.int16))
    mask = ((diff <= wall_tol).all(axis=-1)).astype(np.uint8) * 255
    if mask.sum() < 200:
        # Fall back to scanning the PDF source wall color (#4e4e4e)
        for fallback in [(78, 78, 78), (110, 110, 110), (130, 130, 130)]:
            diff = np.abs(img_rgb.astype(np.int16)
                           - np.array(fallback, dtype=np.int16))
            mask = ((diff <= wall_tol).all(axis=-1)).astype(np.uint8) * 255
            if mask.sum() >= 200:
                break
        else:
            return None

    # Dilate moderately to merge wall fragments within the planta
    # without bridging to legend/footer regions. Then pick the
    # TOP-MOST large component (the planta), excluding the title
    # strip. Legend/notes/footer have their own dense wall-colored
    # regions and would otherwise tie-break by area against the
    # planta when the legend has many gray swatches.
    kernel = np.ones((9, 9), np.uint8)
    dilated = cv2.dilate(mask, kernel, iterations=2)
    n_labels, _label_img, stats, _centroids = (
        cv2.connectedComponentsWithStats(dilated, connectivity=8)
    )
    img_h = img_rgb.shape[0]
    img_w = img_rgb.shape[1]
    # Keep components with min area + drop title strip
    candidates: list[tuple[int, int, int, int, int]] = []
    for i in range(1, n_labels):
        s = stats[i]
        x, y, w, h, a = s[:5]
        if a < 5000:
            continue
        # Drop title strip (narrow vertical, near top, wide horizontal)
        if y < img_h * 0.10 and h < img_h * 0.08:
            continue
        candidates.append((int(x), int(y), int(x + w), int(y + h), int(a)))
    if not candidates:
        return None
    # Prefer landscape components in the TOP HALF of the image —
    # plantas of residential floor plans are wider than tall and live
    # in the page header area; legend / notes / footer occupy the
    # bottom half.
    def _score(c: tuple[int, int, int, int, int]) -> float:
        x0, y0, x1, y1, a = c
        w = x1 - x0
        h = y1 - y0
        if w == 0 or h == 0:
            return -1e18
        aspect_bonus = 1.0 if w >= h else 0.5
        top_bias = max(0.0, 1.0 - y0 / max(img_h, 1)) ** 2  # closer to top wins
        return a * aspect_bonus * (0.4 + 0.6 * top_bias)
    candidates.sort(key=_score, reverse=True)
    img_x0, img_y0, img_x1, img_y1, _ = candidates[0]
    return {
        "img_x0": img_x0, "img_y0": img_y0,
        "img_x1": img_x1, "img_y1": img_y1,
        "pdf_x0": pdf_x0, "pdf_y0": pdf_y0,
        "pdf_x1": pdf_x1, "pdf_y1": pdf_y1,
        "scale_x_pt_per_px": float((pdf_x1 - pdf_x0) / max(img_x1 - img_x0, 1)),
        "scale_y_pt_per_px": float((pdf_y1 - pdf_y0) / max(img_y1 - img_y0, 1)),
    }


def _px_bbox_to_pts(bbox_px: tuple[float, float, float, float],
                     img_size: tuple[int, int],
                     calibration: dict
                     ) -> tuple[float, float, float, float]:
    """Pixel bbox → PDF point bbox using the calibration affine
    transform (Y is flipped: PIL y-down, PDF y-up)."""
    x0p, y0p, x1p, y1p = bbox_px
    img_x0 = calibration["img_x0"]
    img_x1 = calibration["img_x1"]
    img_y0 = calibration["img_y0"]
    img_y1 = calibration["img_y1"]
    pdf_x0 = calibration["pdf_x0"]
    pdf_x1 = calibration["pdf_x1"]
    pdf_y0 = calibration["pdf_y0"]
    pdf_y1 = calibration["pdf_y1"]
    sx = (pdf_x1 - pdf_x0) / max(img_x1 - img_x0, 1e-6)
    sy = (pdf_y1 - pdf_y0) / max(img_y1 - img_y0, 1e-6)
    l_pt = pdf_x0 + (x0p - img_x0) * sx
    r_pt = pdf_x0 + (x1p - img_x0) * sx
    t_pt = pdf_y1 - (y0p - img_y0) * sy
    b_pt = pdf_y1 - (y1p - img_y0) * sy
    return l_pt, b_pt, r_pt, t_pt


def extract(image_path: Path,
            consensus_path: Path,
            color_mapping: dict[str, dict[str, Any]] | None = None,
            tol: int = DEFAULT_COLOR_TOLERANCE,
            min_blob_area: int = MIN_BLOB_AREA_PX,
            ) -> dict[str, Any]:
    cmap = color_mapping or DEFAULT_WALL_COLORS

    img_bgr = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if img_bgr is None:
        raise FileNotFoundError(
            f"Could not read image: {image_path}. Paint walls on the "
            f"base image (fixtures/planta_74/human_walls_annotation_base.png) "
            f"and save the result here."
        )
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    h_px, w_px = img_rgb.shape[:2]

    consensus = json.loads(consensus_path.read_text())
    walls = consensus.get("walls", [])
    thickness = float(consensus.get("wall_thickness_pts", 5.4))

    calibration = _auto_calibrate(img_rgb, walls)
    if calibration is None:
        raise RuntimeError(
            "Auto-calibration failed — no wall-like pixels found in the "
            "annotation image. Ensure the base image was generated from "
            "render_human_walls_annotation_base.py."
        )
    print(f"[calibrate] image planta px: "
          f"x=[{calibration['img_x0']},{calibration['img_x1']}], "
          f"y=[{calibration['img_y0']},{calibration['img_y1']}]")
    print(f"[calibrate] scale {calibration['scale_x_pt_per_px']:.4f} x "
          f"{calibration['scale_y_pt_per_px']:.4f} pt/px")

    # Restrict the paint search to the planta region established by
    # auto-calibrate. Without this, blue text in the legend / footer
    # ("paint MISSING WALLS in this BLUE") gets classified as a wall.
    planta_x0 = calibration["img_x0"]
    planta_y0 = calibration["img_y0"]
    planta_x1 = calibration["img_x1"]
    planta_y1 = calibration["img_y1"]
    extracted: list[ExtractedWall] = []
    n_rejected_outside_planta = 0
    idx = 0
    for color_name, info in cmap.items():
        target = tuple(info["rgb"])
        mask = _build_color_mask(img_rgb, target, tol)
        if not mask.any():
            continue
        n_labels, _label_img, stats, _centroids = (
            cv2.connectedComponentsWithStats(mask, connectivity=8)
        )
        for lbl in range(1, n_labels):
            x_px, y_px, w_blob, h_blob, area = stats[lbl]
            if area < min_blob_area:
                continue
            # Reject blobs whose CENTER is outside the planta region
            cx_px = x_px + w_blob / 2
            cy_px = y_px + h_blob / 2
            if not (planta_x0 <= cx_px <= planta_x1
                    and planta_y0 <= cy_px <= planta_y1):
                n_rejected_outside_planta += 1
                continue
            bbox_px = (float(x_px), float(y_px),
                        float(x_px + w_blob), float(y_px + h_blob))
            x0_pt, y0_pt, x1_pt, y1_pt = _px_bbox_to_pts(
                bbox_px, (w_px, h_px), calibration
            )
            # Orientation: longer axis of bbox in PDF coords
            w_pt = x1_pt - x0_pt
            h_pt = y1_pt - y0_pt
            if w_pt >= h_pt:
                orient = "h"
                cy = (y0_pt + y1_pt) / 2.0
                start = [x0_pt, cy]
                end = [x1_pt, cy]
            else:
                orient = "v"
                cx = (x0_pt + x1_pt) / 2.0
                start = [cx, y0_pt]
                end = [cx, y1_pt]
            extracted.append(ExtractedWall(
                id=f"h_w{idx:03d}",
                color=color_name,
                bbox_px=[round(v, 2) for v in bbox_px],
                bbox_pts=[round(v, 3) for v in (x0_pt, y0_pt, x1_pt, y1_pt)],
                orientation=orient,
                start=[round(start[0], 3), round(start[1], 3)],
                end=[round(end[0], 3), round(end[1], 3)],
                thickness=round(thickness, 3),
            ))
            idx += 1

    truth = {
        "schema_version": "1.0",
        "source_image": str(image_path).replace("\\", "/"),
        "image_size_px": [w_px, h_px],
        "color_mapping": {
            cname: {"rgb": info["rgb"], "kind": "structural_wall"}
            for cname, info in cmap.items()
        },
        "calibration": calibration,
        "consensus_wall_thickness_pts": thickness,
        "walls": [asdict(w) for w in extracted],
    }

    print()
    print(f"[extract] image={image_path.name} ({w_px}x{h_px} px)")
    print(f"  walls extracted: {len(extracted)}")
    if n_rejected_outside_planta:
        print(f"  rejected (outside planta region): {n_rejected_outside_planta}")
    by_color: dict[str, int] = {}
    for w in extracted:
        by_color[w.color] = by_color.get(w.color, 0) + 1
    for c, n in sorted(by_color.items()):
        print(f"    {c}: {n}")
    print("  by orientation:")
    by_ori = {"h": 0, "v": 0}
    for w in extracted:
        by_ori[w.orientation] += 1
    print(f"    h: {by_ori['h']}")
    print(f"    v: {by_ori['v']}")
    return truth


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("image", type=Path)
    ap.add_argument("--consensus", type=Path, required=True,
                    help="consensus_human.json (provides wall_thickness_pts "
                         "+ existing walls for auto-calibrate).")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--color-tolerance", type=int,
                    default=DEFAULT_COLOR_TOLERANCE)
    ap.add_argument("--min-blob-area-px", type=int,
                    default=MIN_BLOB_AREA_PX)
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    truth = extract(
        args.image, args.consensus,
        tol=args.color_tolerance,
        min_blob_area=args.min_blob_area_px,
    )
    args.out.write_text(json.dumps(truth, indent=2))
    print(f"[ok] truth -> {args.out}")


if __name__ == "__main__":
    main()
