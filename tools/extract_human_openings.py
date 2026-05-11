"""Extract human-annotated openings from a color-coded PNG.

Reads an annotated planta render where the human painted color blobs
over each opening, then emits a machine-readable
``human_openings_truth.json`` per the schema in
``fixtures/planta_74/human_openings_truth.schema.json``.

Color → kind mapping (defaults, override via CLI):
- GREEN   (#00ff00)  →  interior_door
- MAGENTA (#ff00ff)  →  window
- ORANGE  (#ffa500)  →  glazed_balcony

For each color, connected components are found via cv2 (8-connectivity).
Each component yields one opening with bbox, center, orientation, and
the nearest wall_id from ``consensus.walls`` (if a consensus is provided).

The image-to-PDF coordinate transform uses the PDF page size:
``scale = image_size_px / pdf_page_size_pts``.
Coordinates are flipped on Y (PIL Y-down → PDF Y-up).

The output is NOT applied to the consensus here; that step is done by
``tools/apply_human_openings.py`` so this script stays a pure observer
of the annotation image.

Companion docs:
- ``fixtures/planta_74/README.md``
- ``fixtures/planta_74/human_openings_truth.schema.json``
- ``docs/learning/human_openings_truth_protocol.md``
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

# Default color → opening kind mapping
DEFAULT_COLOR_MAPPING: dict[str, dict[str, Any]] = {
    "green":   {"rgb": [0, 255, 0],    "kind": "interior_door"},
    "magenta": {"rgb": [255, 0, 255],  "kind": "window"},
    "orange":  {"rgb": [255, 165, 0],  "kind": "glazed_balcony"},
}

# Default required counts per planta_74 user spec (2026-05-11)
DEFAULT_REQUIRED_COUNTS: dict[str, int] = {
    "interior_door": 7,
    "window": 4,
    "glazed_balcony": 1,
}

# Tolerance per RGB channel when matching pixels to a target color.
# 25 catches both pure colors and slight anti-aliasing while rejecting
# unrelated pixels (e.g. red of wall outlines vs pure red).
DEFAULT_COLOR_TOLERANCE = 25

# Minimum connected-component area (in pixels) to count as a valid
# opening blob. Below this is treated as paint noise.
MIN_BLOB_AREA_PX = 30


@dataclass
class ExtractedOpening:
    id: str
    kind: str
    color: str
    bbox_px: list[float]
    bbox_pts: list[float]
    center_pts: list[float]
    orientation: str
    wall_id: str | None
    wall_dist_pts: float | None
    opening_width_pts: float
    required: bool = True


def _build_color_mask(img_rgb: np.ndarray,
                       target_rgb: tuple[int, int, int],
                       tol: int) -> np.ndarray:
    """Return a binary mask of pixels matching ``target_rgb`` within
    ``tol`` per channel. RGB order (not BGR)."""
    diff = np.abs(img_rgb.astype(np.int16) - np.array(target_rgb,
                                                       dtype=np.int16))
    mask = np.all(diff <= tol, axis=-1).astype(np.uint8) * 255
    return mask


def _px_bbox_to_pts(bbox_px: tuple[float, float, float, float],
                     img_size: tuple[int, int],
                     pdf_size: tuple[float, float]
                     ) -> tuple[float, float, float, float]:
    """Convert pixel bbox (PIL coords, y-down) to PDF point bbox
    (y-up).
    bbox_px order: (x0_px, y0_px, x1_px, y1_px).
    Returns (l_pt, b_pt, r_pt, t_pt) in PDF pts.
    """
    iw, ih = img_size
    pw, ph = pdf_size
    sx = pw / iw
    sy = ph / ih
    x0p, y0p, x1p, y1p = bbox_px
    l_pt = x0p * sx
    r_pt = x1p * sx
    # Flip Y: pixel y=0 is image top; PDF y=0 is page bottom.
    t_pt = ph - y0p * sy
    b_pt = ph - y1p * sy
    return l_pt, b_pt, r_pt, t_pt


def _nearest_wall(center_pts: tuple[float, float],
                   orientation: str,
                   walls: list[dict]) -> tuple[str | None, float]:
    """Return (wall_id, distance_pts) of the wall whose CENTERLINE is
    closest to ``center_pts``, optionally filtered to walls of matching
    orientation. Returns (None, inf) if walls is empty."""
    if not walls:
        return None, float("inf")
    cx, cy = center_pts
    best_id: str | None = None
    best_d = float("inf")
    for w in walls:
        # Only consider walls of matching orientation when one is given;
        # an interior_door in a horizontal opening should belong to a
        # horizontal wall.
        if orientation and w.get("orientation") and \
                w["orientation"] != orientation:
            continue
        s = w.get("start")
        e = w.get("end")
        if not s or not e:
            continue
        # Distance from point to wall centerline segment.
        sx, sy = float(s[0]), float(s[1])
        ex, ey = float(e[0]), float(e[1])
        dx, dy = ex - sx, ey - sy
        seg_len_sq = dx * dx + dy * dy
        if seg_len_sq < 1e-6:
            d_sq = (cx - sx) ** 2 + (cy - sy) ** 2
        else:
            # Project point onto segment, clamp t to [0, 1]
            t = max(0.0, min(1.0, ((cx - sx) * dx + (cy - sy) * dy) / seg_len_sq))
            px = sx + t * dx
            py = sy + t * dy
            d_sq = (cx - px) ** 2 + (cy - py) ** 2
        d = float(np.sqrt(d_sq))
        if d < best_d:
            best_d = d
            best_id = w.get("id")
    return best_id, best_d


def extract(image_path: Path,
            consensus_path: Path | None,
            pdf_page_size: tuple[float, float],
            color_mapping: dict[str, dict[str, Any]] | None = None,
            required_counts: dict[str, int] | None = None,
            tol: int = DEFAULT_COLOR_TOLERANCE,
            min_blob_area: int = MIN_BLOB_AREA_PX,
            explicit_constraints: list[dict] | None = None
            ) -> dict[str, Any]:
    """Run the full pipeline on a single annotated image."""
    cmap = color_mapping or DEFAULT_COLOR_MAPPING
    req = required_counts or DEFAULT_REQUIRED_COUNTS

    img_bgr = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if img_bgr is None:
        raise FileNotFoundError(
            f"Could not read image: {image_path}. Drop the human "
            f"annotation PNG here and rerun."
        )
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    h_px, w_px = img_rgb.shape[:2]

    walls: list[dict] = []
    if consensus_path is not None and consensus_path.exists():
        consensus = json.loads(consensus_path.read_text())
        walls = consensus.get("walls", [])

    openings: list[ExtractedOpening] = []
    op_idx = 0
    for color_name, info in cmap.items():
        target = tuple(info["rgb"])
        kind = info["kind"]
        mask = _build_color_mask(img_rgb, target, tol)
        if not mask.any():
            continue
        n_labels, label_img, stats, centroids = (
            cv2.connectedComponentsWithStats(mask, connectivity=8)
        )
        # label 0 is background; iterate 1..n_labels-1
        for lbl in range(1, n_labels):
            x_px, y_px, w_blob, h_blob, area = stats[lbl]
            if area < min_blob_area:
                continue
            bbox_px = (float(x_px), float(y_px),
                        float(x_px + w_blob), float(y_px + h_blob))
            x0_pt, y0_pt, x1_pt, y1_pt = _px_bbox_to_pts(
                bbox_px, (w_px, h_px), pdf_page_size
            )
            cx_pt = (x0_pt + x1_pt) / 2.0
            cy_pt = (y0_pt + y1_pt) / 2.0
            # Orientation: longer axis of bbox decides.
            orientation = "h" if (x1_pt - x0_pt) >= (y1_pt - y0_pt) else "v"
            # Opening width in pts: longer-axis length of bbox.
            opening_width_pts = float(max(x1_pt - x0_pt, y1_pt - y0_pt))
            wall_id, dist = _nearest_wall((cx_pt, cy_pt), orientation, walls)
            openings.append(ExtractedOpening(
                id=f"h_o{op_idx:03d}",
                kind=kind,
                color=color_name,
                bbox_px=[round(v, 2) for v in bbox_px],
                bbox_pts=[round(v, 3) for v in (x0_pt, y0_pt, x1_pt, y1_pt)],
                center_pts=[round(cx_pt, 3), round(cy_pt, 3)],
                orientation=orientation,
                wall_id=wall_id,
                wall_dist_pts=(round(dist, 3) if dist != float("inf") else None),
                opening_width_pts=round(opening_width_pts, 3),
            ))
            op_idx += 1

    truth = {
        "schema_version": "1.0",
        "source_image": str(image_path).replace("\\", "/"),
        "image_size_px": [w_px, h_px],
        "pdf_page_size_pts": list(pdf_page_size),
        "color_mapping": {
            cname: {"rgb": info["rgb"], "kind": info["kind"]}
            for cname, info in cmap.items()
        },
        "required_counts": req,
        "openings": [asdict(o) for o in openings],
    }
    if explicit_constraints:
        truth["explicit_constraints"] = explicit_constraints

    # Summary print
    by_kind: dict[str, int] = {}
    for o in openings:
        by_kind[o.kind] = by_kind.get(o.kind, 0) + 1
    print(f"[extract] image={image_path.name} "
          f"({w_px}x{h_px}px -> PDF {pdf_page_size[0]:.0f}x{pdf_page_size[1]:.0f}pt)")
    print(f"  walls in consensus: {len(walls)}")
    print(f"  openings extracted: {len(openings)}")
    for kind, count in sorted(by_kind.items()):
        required = req.get(kind, 0)
        status = "OK" if count >= required else "MISSING"
        print(f"    {kind:18}: {count} (required={required}) [{status}]")

    return truth


def _planta_74_explicit_constraints() -> list[dict]:
    """Return the per-room explicit constraints the user pinned for planta_74.
    Search regions are in PDF points (y-up). Coordinates derived from the
    locked baseline (planta_region ~ [39, 395, 564, 708]) plus per-room
    bboxes inferred from the room polygons + label positions."""
    return [
        {
            "name": "BANHO_02_west_door",
            "description": "BANHO 02 must have an interior_door on its WEST (left) vertical wall, opening inward.",
            "kind": "interior_door",
            "policy": "require_present",
            "search_region_pts": [325, 510, 345, 590],
        },
        {
            "name": "SALA_ESTAR_TERRACO_SOCIAL_balcony",
            "description": "There must be a glazed_balcony between SALA DE ESTAR and TERRAÇO SOCIAL.",
            "kind": "glazed_balcony",
            "policy": "require_present",
            "search_region_pts": [100, 440, 280, 470],
        },
        {
            "name": "SUITE_02_south_window",
            "description": "SUITE 02 south opening is MAGENTA (window), NOT orange.",
            "kind": "window",
            "policy": "require_present",
            "search_region_pts": [255, 395, 380, 415],
        },
        {
            "name": "NO_SUITE_01_BANHO_01_internal_window",
            "description": "There must NOT be any window between SUITE 01 and BANHO 01.",
            "kind": "window",
            "policy": "require_absent",
            "search_region_pts": [475, 540, 510, 605],
        },
    ]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("image", type=Path,
                    help="Path to the annotated PNG.")
    ap.add_argument("--consensus", type=Path, default=None,
                    help="Optional consensus_model.json — when provided, "
                         "each opening is matched to its nearest wall.")
    ap.add_argument("--out", type=Path, required=True,
                    help="Output truth JSON path.")
    ap.add_argument("--pdf-width-pts", type=float, default=595.0)
    ap.add_argument("--pdf-height-pts", type=float, default=842.0)
    ap.add_argument("--color-tolerance", type=int,
                    default=DEFAULT_COLOR_TOLERANCE)
    ap.add_argument("--min-blob-area-px", type=int,
                    default=MIN_BLOB_AREA_PX)
    ap.add_argument("--no-explicit-constraints", action="store_true",
                    help="Skip the planta_74 explicit positional constraints.")
    args = ap.parse_args()

    constraints = (None if args.no_explicit_constraints
                   else _planta_74_explicit_constraints())
    truth = extract(
        args.image,
        args.consensus,
        (args.pdf_width_pts, args.pdf_height_pts),
        tol=args.color_tolerance,
        min_blob_area=args.min_blob_area_px,
        explicit_constraints=constraints,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(truth, indent=2))
    print(f"[ok] truth -> {args.out}")


if __name__ == "__main__":
    main()
