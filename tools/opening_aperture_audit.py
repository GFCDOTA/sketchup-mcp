#!/usr/bin/env python3
"""Deterministic opening-aperture presence on the SKP top render (BANHO-2 class).

The existing gates check walls present (overlay_diff) and opening<->host-wall
DATA consistency (opening_host_audit). NEITHER checks that an opening actually
RENDERED as an aperture. The BANHO-2 bug slipped through exactly there: the
aperture pushpull stopped short -> a blind pocket (geometry cutout, but no
through-hole/glass), which reads as solid wall in top view. Felipe's eye caught
it; no deterministic gate did.

This detector closes that gap by a SELF-CALIBRATING comparison: for each opening,
sample a transect across the host-wall thickness at the opening centre, and the
same transect at adjacent SOLID stretches of the same wall. A real aperture is
much LESS solid than its own wall (gap/glass); a blind pocket is just as solid.
Comparing to the wall's own solidity cancels the background overshoot of the
transect and is robust to the render palette (no absolute threshold on tone).

Calibration-independent core (mirrors overlay_diff): the affine + ratios are
PASSED IN, and synthetic tests lock the contract. Real-plant wiring (sidecar
affine + a calibrated flag_ratio that separates a thin glass line from a blind
pocket on the actual planta_74 render) is a separate, oracle-reviewed step.
"""
from __future__ import annotations

import numpy as np

from tools.overlay_diff import Affine, dark_mask


def host_wall(consensus: dict, opening: dict) -> dict | None:
    wid = opening.get("wall_id") or opening.get("host_wall_id")
    for w in consensus.get("walls", []):
        if w.get("id") == wid:
            return w
    return None


def wall_orientation(wall: dict) -> str:
    (x0, y0), (x1, y1) = wall["start"], wall["end"]
    return "h" if abs(x1 - x0) >= abs(y1 - y0) else "v"


def _dark_fraction_transect(
    mask: np.ndarray, affine: Affine, cx: float, cy: float, ori: str,
    half: float, n_samples: int,
) -> tuple[float, int]:
    """(dark fraction, in-frame sample count) along a transect of half-length
    `half` across the wall thickness (perpendicular to the wall) at (cx, cy)."""
    h, w = mask.shape
    seen = dark = 0
    for i in range(n_samples + 1):
        t = (i / n_samples - 0.5) * 2.0 * half  # -half .. +half across thickness
        wx, wy = (cx, cy + t) if ori == "h" else (cx + t, cy)
        px, py = affine.project(wx, wy)
        px, py = int(round(px)), int(round(py))
        if 0 <= px < w and 0 <= py < h:
            seen += 1
            if mask[py, px]:
                dark += 1
    return (dark / seen if seen else 0.0), seen


def wall_solidity_ratio(
    mask: np.ndarray,
    affine: Affine,
    opening: dict,
    wall: dict,
    thickness_pts: float,
    *,
    margin: float = 1.4,
    n_samples: int = 16,
) -> float | None:
    """opening_dark_frac / reference_solid_dark_frac. ~1.0 = the opening is as
    solid as its own wall (blind pocket); ~0.0 = a real gap. Reference = the
    MOST-solid of several adjacent transects on the same wall (so one reference
    landing on another opening doesn't fool it). None = inconclusive (opening
    off-frame, or no solid reference found -> wall too short/thin)."""
    cx, cy = opening["center"]
    half = thickness_pts * margin / 2.0
    ori = wall_orientation(wall)
    width = float(opening.get("opening_width_pts") or thickness_pts * 2.0)
    op_frac, op_seen = _dark_fraction_transect(
        mask, affine, cx, cy, ori, half, n_samples)
    if not op_seen:
        return None
    step = max(width, thickness_pts)
    refs: list[float] = []
    for k in (1.5, 2.5, -1.5, -2.5):
        off = k * step
        rx, ry = (cx + off, cy) if ori == "h" else (cx, cy + off)
        frac, seen = _dark_fraction_transect(
            mask, affine, rx, ry, ori, half, n_samples)
        if seen:
            refs.append(frac)
    if not refs:
        return None
    ref_frac = max(refs)
    if ref_frac <= 0.0:
        return None  # no solid wall to compare against -> inconclusive
    return op_frac / ref_frac


def detect_blind_pockets(
    consensus: dict,
    rgb: np.ndarray,
    affine: Affine,
    *,
    brightness_thresh: int = 120,
    flag_ratio: float = 0.6,
    thickness_default: float = 5.4,
) -> dict:
    """Flag openings that did NOT render as an aperture (blind pocket). An
    opening whose solidity is >= flag_ratio of its own wall's solidity reads as
    solid -> FLAG. Returns {overall, n_openings, n_fail, n_inconclusive,
    findings, flag_ratio}."""
    mask = dark_mask(rgb, brightness_thresh)
    findings: list[dict] = []
    n_inconclusive = 0
    openings = consensus.get("openings", [])
    for op in openings:
        wall = host_wall(consensus, op)
        if wall is None:
            findings.append({"id": op.get("id"), "ratio": None,
                             "reason": "no_host_wall"})
            continue
        thick = float(wall.get("thickness")
                      or consensus.get("wall_thickness_pts")
                      or thickness_default)
        ratio = wall_solidity_ratio(mask, affine, op, wall, thick)
        if ratio is None:
            n_inconclusive += 1
            continue
        if ratio >= flag_ratio:
            findings.append({"id": op.get("id"), "ratio": round(ratio, 3),
                             "reason": "blind_pocket_no_aperture"})
    return {
        "overall": "PASS" if not findings else "FAIL",
        "n_openings": len(openings),
        "n_fail": len(findings),
        "n_inconclusive": n_inconclusive,
        "findings": findings,
        "flag_ratio": flag_ratio,
    }
