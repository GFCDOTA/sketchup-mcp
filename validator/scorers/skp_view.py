"""Scorer for SKP-derived screenshots (skp_view, sidebyside_skp,
_skp_open_iso, _skp_top, _su_screenshot).

The PNG quality reflects the underlying .skp quality. We use the most
recent ``inspect_walls_report`` JSON whose meta.skp_path basename matches
``entry.source.skp.path`` and check:

* ``wall_overlaps_top20`` must be empty (no duplicated walls).
* ``default_faces_count`` must be 0 (every face has a material).
* ``totals.faces`` should be reasonable (10..2000) — sanity check.
* The PNG itself should not be entirely white / black.

Score:
  overlaps_score (0..1)   1 if no overlaps, else clamp(1 - overlaps/3, 0, 1)
  default_score   (0..1)   1 if 0 default faces, else clamp(1 - n/20, 0, 1)
  png_basic       (0..1)   PNG isn't blank
  weights:        0.4, 0.4, 0.2
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from .base import Issue, ScorerContext, ScorerResult


def score_skp_view(entry: dict, ctx: ScorerContext) -> ScorerResult:
    issues: list[Issue] = []
    metrics: dict = {}

    png_path = ctx.repo_root / entry["history_path"]
    if not png_path.exists():
        return ScorerResult(
            score=0.0,
            issues=[Issue("error", "png_missing", f"history png missing: {png_path}")],
            scorer="skp_view",
        )

    # ---- PNG sanity -------------------------------------------------------
    img = np.asarray(Image.open(png_path).convert("RGB"))
    h, w, _ = img.shape
    metrics["size"] = [w, h]

    nonwhite = ~((img[..., 0] >= 250) & (img[..., 1] >= 250) & (img[..., 2] >= 250))
    nonblack = ~((img[..., 0] <= 5) & (img[..., 1] <= 5) & (img[..., 2] <= 5))
    nonwhite_ratio = float(nonwhite.sum()) / (h * w)
    nonblack_ratio = float(nonblack.sum()) / (h * w)
    metrics["nonwhite_ratio"] = round(nonwhite_ratio, 4)

    # color diversity: bucket pixels into 8x8x8 RGB bins and count populated
    # bins. A SketchUp viewport with real geometry hits 30-200+ bins; an
    # empty VMware window or a uniform background hits 1-3.
    bins = (img[..., 0] // 32) * 64 + (img[..., 1] // 32) * 8 + (img[..., 2] // 32)
    counts = np.bincount(bins.ravel(), minlength=512)
    populated = int((counts >= max(50, (h * w) * 0.0005)).sum())
    metrics["color_bins"] = populated

    if nonwhite_ratio < 0.005:
        png_basic = 0.0
        issues.append(Issue("error", "render_blank_white",
                            f"PNG is essentially white (nonwhite={nonwhite_ratio:.1%})"))
    elif nonblack_ratio < 0.01:
        png_basic = 0.1
        issues.append(Issue("error", "render_blank_black", "PNG is essentially black"))
    elif populated <= 3:
        png_basic = 0.0
        issues.append(Issue(
            "error", "render_uniform",
            f"PNG has only {populated} populated 8-bit color bins — likely an empty viewport screenshot",
            {"populated_bins": populated},
        ))
    elif populated <= 8:
        png_basic = 0.4
        issues.append(Issue(
            "warn", "render_low_diversity",
            f"PNG has only {populated} populated color bins — model may be off-camera",
        ))
    else:
        png_basic = 1.0

    # ---- inspect report ---------------------------------------------------
    rep = ctx.inspect_report
    if not rep:
        issues.append(Issue("warn", "inspect_report_missing",
                            "no inspect_walls_report*.json found for source.skp"))
        # Cannot compute structural score; fall back to PNG-only.
        metrics["inspect_report"] = None
        return ScorerResult(
            score=0.4 * png_basic,
            issues=issues,
            notes="skp_view: PNG-only score (no inspect report)",
            metrics=metrics,
            scorer="skp_view",
        )

    metrics["inspect_report_source"] = rep.get("__source__", "?")
    metrics["inspect_match"] = rep.get("__match__", "?")

    overlaps = rep.get("wall_overlaps_top20") or []
    default_faces = int(rep.get("default_faces_count", 0))
    totals = rep.get("totals", {}) or {}
    metrics["wall_overlaps"] = len(overlaps)
    metrics["default_faces_count"] = default_faces
    metrics["totals"] = totals

    if overlaps:
        overlaps_score = max(0.0, 1.0 - len(overlaps) / 3.0)
        issues.append(Issue(
            "error", "wall_overlaps",
            f"{len(overlaps)} overlapping wall pair(s) in source .skp",
            {"sample": overlaps[:3]},
        ))
    else:
        overlaps_score = 1.0

    if default_faces:
        default_score = max(0.0, 1.0 - default_faces / 20.0)
        issues.append(Issue(
            "warn" if default_faces < 5 else "error",
            "default_material_faces",
            f"{default_faces} faces still on default material (expected 0)",
            {"sample": rep.get("default_faces_sample", [])[:3]},
        ))
    else:
        default_score = 1.0

    faces = int(totals.get("faces", 0))
    if faces == 0:
        issues.append(Issue("error", "no_faces", ".skp has zero faces"))
    elif faces < 10 or faces > 5000:
        issues.append(Issue("warn", "faces_count_unusual",
                            f"unusual face count: {faces}"))

    score = 0.4 * overlaps_score + 0.4 * default_score + 0.2 * png_basic
    metrics.update({
        "overlaps_score": round(overlaps_score, 3),
        "default_score":  round(default_score, 3),
        "png_basic":      round(png_basic, 3),
    })

    notes = (
        f"skp_view: overlaps={len(overlaps)} default_faces={default_faces} "
        f"png_basic={png_basic:.2f}"
    )
    return ScorerResult(score=score, issues=issues, notes=notes,
                        metrics=metrics, scorer="skp_view")
