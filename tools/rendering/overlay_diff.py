#!/usr/bin/env python3
"""FP-030 deterministic overlay/diff — consensus wall-presence detector (slice B).

Motivation: the `ollama_vision` oracle confidently PASSes a planta_74 render with
a clearly-erased exterior wall (see PR #209 / negative_dogfood). We need a
DETERMINISTIC check that flags a missing wall. Approach (chosen with GPT peer
review, trigger a_b_c_decision_with_tradeoff): project each consensus wall
segment into the SKP top-render pixel frame, sample a buffered corridor around
the expected wall, and require a minimum dark-pixel coverage.

This module is the calibration-INDEPENDENT, unit-tested core:
  - Affine          : axis-aligned consensus(pdf-points) -> pixel transform
  - wall_segment_coverage / detect_missing_walls : the detection logic

The real `planta_74` Affine (a, b, c, d) must be CALIBRATED — the SKP top render
is ortho-top + zoom_extents over the FULL model bounds (build_plan_shell_skp.rb
setup_top_camera; up=(0,1,0) => pixel-Y is flipped), so the transform is affine
but its coefficients depend on the pt->m scale and SU's zoom_extents fit. That
calibration (empirical, via known correspondences) is wired separately; this
core is verified on synthetic masks so the detection contract is locked first.
No SketchUp build, no geometry mutation.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Affine:
    """Axis-aligned consensus(pdf-points) -> pixel transform.

    px = a * x + b ; py = c * y + d. For the ortho-top render with up=(0,1,0),
    `c` is negative (world +Y is up, pixel +Y is down).
    """
    a: float
    b: float
    c: float
    d: float

    def project(self, x: float, y: float) -> tuple[float, float]:
        return (self.a * x + self.b, self.c * y + self.d)


def dark_mask(rgb: np.ndarray, brightness_thresh: int = 120) -> np.ndarray:
    """Boolean mask of 'wall-ish' (dark) pixels. rgb is HxWx3 uint8/int."""
    return rgb.astype(int).sum(axis=2) / 3.0 < brightness_thresh


def wall_segment_coverage(
    mask: np.ndarray,
    affine: Affine,
    start: tuple[float, float],
    end: tuple[float, float],
    radius: int = 6,
    n_samples: int = 24,
) -> float:
    """Fraction of IN-FRAME sampled points along the segment that have a dark
    pixel within `radius` in `mask`. Tolerates openings (a door/window gap drops
    coverage only over its span). Samples that project outside the image are not
    counted (a wall clipped by the render frame is handled by
    `wall_inframe_fraction`, not penalised here)."""
    h, w = mask.shape
    (x0, y0), (x1, y1) = start, end
    hits = 0
    in_frame = 0
    for i in range(n_samples + 1):
        t = i / n_samples
        px, py = affine.project(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)
        px, py = int(round(px)), int(round(py))
        if px < 0 or py < 0 or px >= w or py >= h:
            continue
        in_frame += 1
        y_lo, y_hi = max(0, py - radius), min(h, py + radius + 1)
        x_lo, x_hi = max(0, px - radius), min(w, px + radius + 1)
        if mask[y_lo:y_hi, x_lo:x_hi].any():
            hits += 1
    return hits / in_frame if in_frame else 0.0


def wall_inframe_fraction(
    affine: Affine,
    start: tuple[float, float],
    end: tuple[float, float],
    shape: tuple[int, int],
    n_samples: int = 24,
) -> float:
    """Fraction of sampled points along the segment that land inside the image.
    < ~0.5 means the wall is largely clipped by the render frame, so its
    coverage cannot be judged (NOT evidence of a missing wall)."""
    h, w = shape
    (x0, y0), (x1, y1) = start, end
    inside = 0
    for i in range(n_samples + 1):
        t = i / n_samples
        px, py = affine.project(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)
        if 0 <= px < w and 0 <= py < h:
            inside += 1
    return inside / (n_samples + 1)


def detect_missing_walls(
    mask: np.ndarray,
    affine: Affine,
    walls: list[dict],
    coverage_threshold: float = 0.6,
    radius: int = 6,
    n_samples: int = 24,
    min_inframe: float = 0.5,
) -> list[dict]:
    """Flag consensus wall segments that are substantially IN-FRAME yet whose
    dark-pixel coverage is below `coverage_threshold` (i.e. the wall is largely
    absent from the render). Walls clipped by the render frame
    (`in_frame < min_inframe`) are skipped — they cannot be judged and are NOT
    reported as missing."""
    findings: list[dict] = []
    for wseg in walls:
        start = tuple(wseg["start"])
        end = tuple(wseg["end"])
        inframe = wall_inframe_fraction(
            affine, start, end, mask.shape, n_samples=n_samples,
        )
        if inframe < min_inframe:
            continue  # clipped by the render frame -> unverifiable, not missing
        cov = wall_segment_coverage(
            mask, affine, start, end, radius=radius, n_samples=n_samples,
        )
        if cov < coverage_threshold:
            mx = (start[0] + end[0]) / 2
            my = (start[1] + end[1]) / 2
            ppx, ppy = affine.project(mx, my)
            findings.append({
                "type": "missing_wall_continuation",
                "wall_id": wseg.get("id"),
                "coverage": round(cov, 3),
                "threshold": coverage_threshold,
                "pixel_midpoint": [int(round(ppx)), int(round(ppy))],
                "evidence": (
                    f"wall {wseg.get('id')} coverage={cov:.2f} < "
                    f"{coverage_threshold}: largely absent from the render"
                ),
            })
    return findings


# ---- real-render calibration + gate (FP-031, #2) -------------------
#
# The detection core above is calibration-independent (unit-tested on synthetic
# masks). To run it on the ACTUAL SKP top render we need the pdf-points -> pixel
# Affine. The top render is ortho-top, so the projection is a centered uniform
# scale; its only unknowns (the post-zoom_extents cam.height + cam.target) are
# emitted EXACTLY by the builder into a `<png>.proj.json` sidecar (via SU's own
# view, FP-031). `affine_from_sidecar` turns that into a zero-error Affine — no
# pixel calibration, no guessing. `calibrate_affine` (coloured-floor bbox) is a
# best-effort FALLBACK for renders built before the sidecar existed.


def affine_from_sidecar(proj: dict) -> Affine:
    """Exact pdf-points -> pixel Affine from the builder's top-view projection
    sidecar. Ortho-top => uniform square scale `s = img_h / cam_height_in`
    (px per inch), with `cam_target` landing on the image centre.
    """
    s = proj["img_h"] / proj["cam_height_in"]      # px per world-inch (square)
    pt = proj["pt_to_in"]                          # inch per pdf-point
    tx, ty = proj["cam_target_in"]
    cx, cy = proj["img_w"] / 2.0, proj["img_h"] / 2.0
    # px = cx + s*(x_pt*pt - tx) ; py = cy - s*(y_pt*pt - ty)  (y flipped)
    return Affine(a=s * pt, b=cx - s * tx, c=-s * pt, d=cy + s * ty)


def chroma_mask(rgb: np.ndarray, thresh: int = 18) -> np.ndarray:
    """Coloured (room-floor) pixels: chroma = max-min channel > thresh.
    Background grey and dark walls are achromatic, so this isolates floors."""
    a = rgb.astype(int)
    return (a.max(axis=2) - a.min(axis=2)) > thresh


def bbox_of(mask: np.ndarray) -> tuple[int, int, int, int] | None:
    """(min_x, min_y, max_x, max_y) of True pixels, or None if empty."""
    ys, xs = np.where(mask)
    if xs.size == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def calibrate_affine(
    rgb: np.ndarray, rooms: list[dict], chroma_thresh: int = 18,
) -> Affine:
    """Affine (consensus pdf-points -> render pixels) from the floor extent:
    coloured-pixel bbox <-> consensus room-polygon bbox. Robust to wall erasure.
    """
    fbb = bbox_of(chroma_mask(rgb, chroma_thresh))
    if fbb is None:
        raise ValueError("calibrate_affine: no coloured floor pixels found")
    pminx, pminy, pmaxx, pmaxy = fbb
    xs = [p[0] for r in rooms for p in (r.get("polygon_pts") or [])]
    ys = [p[1] for r in rooms for p in (r.get("polygon_pts") or [])]
    if not xs:
        raise ValueError("calibrate_affine: no room polygon points")
    wminx, wmaxx, wminy, wmaxy = min(xs), max(xs), min(ys), max(ys)
    if wmaxx == wminx or wmaxy == wminy:
        raise ValueError("calibrate_affine: degenerate room bbox")
    a = (pmaxx - pminx) / (wmaxx - wminx)
    b = pminx - a * wminx
    c = (pminy - pmaxy) / (wmaxy - wminy)  # y flipped (world +Y up, pixel +Y down)
    d = pmaxy - c * wminy
    return Affine(a=a, b=b, c=c, d=d)


def run_gate(
    render_path,
    consensus_path,
    coverage_threshold: float = 0.6,
    radius: int = 8,
    chroma_thresh: int = 18,
    brightness_thresh: int = 160,  # catches dark walls (~78) AND parapets (~135)
    min_inframe: float = 0.5,
) -> dict:
    """End-to-end deterministic wall-presence gate on a real SKP top render.

    Prefers the builder's exact `<png>.proj.json` projection sidecar; falls back
    to coloured-floor calibration if absent. Returns {affine, calibration,
    n_walls, findings, verdict}. verdict='FAIL' iff any IN-FRAME consensus wall
    segment is largely absent from the render.
    """
    import json
    import os
    from pathlib import Path

    from PIL import Image

    rgb = np.asarray(Image.open(render_path).convert("RGB"))
    con = json.loads(Path(consensus_path).read_text("utf-8"))
    proj_path = str(render_path) + ".proj.json"
    if os.path.exists(proj_path):
        proj = json.loads(Path(proj_path).read_text("utf-8"))
        affine = affine_from_sidecar(proj)
        calibration = "sidecar_exact"
    else:
        affine = calibrate_affine(rgb, con.get("rooms", []), chroma_thresh)
        calibration = "floor_chroma_fallback"
    mask = dark_mask(rgb, brightness_thresh)
    findings = detect_missing_walls(
        mask, affine, con.get("walls", []),
        coverage_threshold=coverage_threshold, radius=radius,
        min_inframe=min_inframe,
    )
    return {
        "affine": affine,
        "calibration": calibration,
        "n_walls": len(con.get("walls", [])),
        "findings": findings,
        "verdict": "PASS" if not findings else "FAIL",
    }


if __name__ == "__main__":
    import argparse
    import json

    ap = argparse.ArgumentParser(description="deterministic wall-presence gate")
    ap.add_argument("--render", required=True, help="SKP top render PNG")
    ap.add_argument("--consensus", required=True, help="consensus_model.json")
    ap.add_argument("--coverage", type=float, default=0.6)
    ap.add_argument("--radius", type=int, default=8)
    a = ap.parse_args()
    res = run_gate(a.render, a.consensus,
                   coverage_threshold=a.coverage, radius=a.radius)
    print(f"verdict={res['verdict']} walls={res['n_walls']} "
          f"calibration={res['calibration']} flagged={len(res['findings'])}")
    for f in res["findings"]:
        print(f"  {f['wall_id']}: cov={f['coverage']} @ {f['pixel_midpoint']}")
    raise SystemExit(0 if res["verdict"] == "PASS" else 1)
