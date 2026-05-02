"""Scorer for axon_axon, axon_top, axon_*.

Heuristics
----------
1. PNG must exist and have a sensible non-white drawing area.
2. ``consensus.rooms`` should be present and >= 6 (planta_74 baseline).
3. Drawing fill: fraction of non-white pixels inside the *tight* drawing
   bbox. A healthy axon fills 25%..85% of its bbox. <5% means the render
   is essentially blank, >95% means the bbox is white background bleeding
   in.
4. Image-wide coverage: total non-white fraction of the canvas should be
   between 5% and 70%; outside that range the render is likely broken.

The previous version assumed walls are pure-black (<60 RGB), which is
false — render_axon paints walls brown (~RGB 140). Using a tight bbox +
non-white density avoids that mistake.

Score = 0.45 * rooms_score + 0.35 * fill_score + 0.20 * coverage_score.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from .base import Issue, ScorerContext, ScorerResult

# render_axon paints on a cream background ~RGB(245,243,238). A strict
# 248 threshold would mark the background as non-white and saturate the
# coverage metric. 230 catches anything visibly drawn (walls, room
# polygons, labels) while ignoring eggshell-cream background.
WHITE_TIGHT = 220     # bbox detection (stricter)
WHITE_LOOSE = 230     # non-white density inside bbox

FILL_OK_LO = 0.20     # >= 20% non-white inside bbox => good
FILL_OK_HI = 0.85     # <= 85% non-white inside bbox => good (else background bleed)
FILL_FAIL_LO = 0.05
FILL_FAIL_HI = 0.97

COV_OK_LO = 0.05      # canvas-wide non-white range
COV_OK_HI = 0.70


def _nonwhite_mask(img: np.ndarray, threshold: int) -> np.ndarray:
    return ~((img[..., 0] >= threshold)
             & (img[..., 1] >= threshold)
             & (img[..., 2] >= threshold))


def _tight_bbox(img: np.ndarray, threshold: int) -> tuple[int, int, int, int] | None:
    mask = _nonwhite_mask(img, threshold)
    if not mask.any():
        return None
    ys, xs = np.where(mask)
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def score_axon(entry: dict, ctx: ScorerContext) -> ScorerResult:
    issues: list[Issue] = []
    metrics: dict = {}

    png_path = ctx.repo_root / entry["history_path"]
    if not png_path.exists():
        return ScorerResult(
            score=0.0,
            issues=[Issue("error", "png_missing", f"history png missing: {png_path}")],
            scorer="axon",
        )

    img = np.asarray(Image.open(png_path).convert("RGB"))
    h, w, _ = img.shape
    metrics["size"] = [w, h]

    # ---- canvas-wide coverage --------------------------------------------
    canvas_nw = _nonwhite_mask(img, WHITE_LOOSE)
    coverage = float(canvas_nw.sum()) / (h * w)
    metrics["coverage"] = round(coverage, 4)

    if coverage < 0.005:
        return ScorerResult(
            score=0.0,
            issues=[Issue("error", "render_blank_white", "axon PNG has no drawing")],
            metrics=metrics,
            scorer="axon",
        )

    if coverage < COV_OK_LO:
        coverage_score = coverage / COV_OK_LO
        issues.append(Issue("warn", "low_coverage",
                            f"non-white coverage = {coverage:.1%} (expected 5-70%)"))
    elif coverage > COV_OK_HI:
        coverage_score = max(0.0, 1.0 - (coverage - COV_OK_HI) / 0.25)
        issues.append(Issue("warn", "high_coverage",
                            f"non-white coverage = {coverage:.1%} (expected 5-70%)"))
    else:
        coverage_score = 1.0

    # ---- tight bbox + fill density ---------------------------------------
    bbox = _tight_bbox(img, WHITE_TIGHT)
    if bbox is None:
        fill = 0.0
        metrics["bbox"] = None
    else:
        x0, y0, x1, y1 = bbox
        bbox_area = (x1 - x0) * (y1 - y0)
        bbox_nw = _nonwhite_mask(img[y0:y1, x0:x1], WHITE_LOOSE).sum()
        fill = float(bbox_nw) / max(bbox_area, 1)
        metrics["bbox"] = [x0, y0, x1, y1]
        metrics["bbox_area_frac"] = round(bbox_area / (h * w), 4)
    metrics["fill_inside_bbox"] = round(fill, 4)

    if fill < FILL_FAIL_LO or fill > FILL_FAIL_HI:
        fill_score = 0.0
        issues.append(Issue("error", "fill_out_of_range",
                            f"bbox fill = {fill:.1%} outside [{FILL_FAIL_LO:.0%},{FILL_FAIL_HI:.0%}]"))
    elif FILL_OK_LO <= fill <= FILL_OK_HI:
        fill_score = 1.0
    elif fill < FILL_OK_LO:
        fill_score = (fill - FILL_FAIL_LO) / (FILL_OK_LO - FILL_FAIL_LO)
        issues.append(Issue("warn", "fill_low",
                            f"bbox fill = {fill:.1%} (target {FILL_OK_LO:.0%}-{FILL_OK_HI:.0%})"))
    else:  # FILL_OK_HI < fill < FILL_FAIL_HI
        fill_score = 1.0 - (fill - FILL_OK_HI) / (FILL_FAIL_HI - FILL_OK_HI)
        issues.append(Issue("warn", "fill_high",
                            f"bbox fill = {fill:.1%} (target {FILL_OK_LO:.0%}-{FILL_OK_HI:.0%})"))

    # ---- consensus rooms -------------------------------------------------
    rooms = (ctx.consensus or {}).get("rooms", []) if ctx.consensus else []
    metrics["consensus_rooms"] = len(rooms)
    if not ctx.consensus:
        rooms_score = 0.0
        issues.append(Issue("warn", "consensus_missing",
                            "no consensus_model.json available for cross-check"))
    elif not rooms:
        rooms_score = 0.0
        issues.append(Issue("error", "no_rooms",
                            "consensus has 0 rooms — render cannot represent any space"))
    elif len(rooms) < 6:
        rooms_score = len(rooms) / 6
        issues.append(Issue("warn", "few_rooms",
                            f"only {len(rooms)} rooms (expected >= 6 for planta_74)"))
    else:
        rooms_score = 1.0

    score = 0.45 * rooms_score + 0.35 * fill_score + 0.20 * coverage_score
    metrics.update({
        "rooms_score":    round(rooms_score, 3),
        "fill_score":     round(fill_score, 3),
        "coverage_score": round(coverage_score, 3),
    })

    notes = (
        f"axon: rooms={rooms_score:.2f} "
        f"fill={fill_score:.2f}({fill:.1%}) coverage={coverage_score:.2f}({coverage:.1%})"
    )
    return ScorerResult(score=score, issues=issues, notes=notes,
                        metrics=metrics, scorer="axon")
