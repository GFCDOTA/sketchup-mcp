"""Fallback scorer for kinds without a dedicated heuristic.

Just sanity-checks the PNG: file exists, sha256 matches what the manifest
claimed at registration time, image isn't blank, file size is plausible.

Useful for `kind=legacy` backfill entries where we don't know what the
PNG was supposed to show.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
from PIL import Image

from .base import Issue, ScorerContext, ScorerResult


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def score_legacy(entry: dict, ctx: ScorerContext) -> ScorerResult:
    issues: list[Issue] = []
    metrics: dict = {}

    png_path = ctx.repo_root / entry["history_path"]
    if not png_path.exists():
        return ScorerResult(
            score=0.0,
            issues=[Issue("error", "png_missing", f"history png missing: {png_path}")],
            scorer="legacy",
        )

    actual_sha = _sha256(png_path)
    metrics["sha256_actual"] = actual_sha
    if entry.get("sha256") and actual_sha != entry["sha256"]:
        issues.append(Issue(
            "error", "sha256_mismatch",
            "history PNG hash differs from manifest",
            {"manifest": entry["sha256"], "actual": actual_sha},
        ))

    img = np.asarray(Image.open(png_path).convert("RGB"))
    h, w, _ = img.shape
    metrics["size"] = [w, h]

    nonwhite = ~((img[..., 0] >= 245) & (img[..., 1] >= 245) & (img[..., 2] >= 245))
    nonwhite_ratio = float(nonwhite.sum()) / (h * w)
    metrics["nonwhite_ratio"] = round(nonwhite_ratio, 4)

    if nonwhite_ratio < 0.005:
        score = 0.0
        issues.append(Issue("error", "render_blank", "PNG is essentially blank"))
    elif nonwhite_ratio < 0.02:
        score = 0.3
        issues.append(Issue("warn", "render_low_density",
                            f"low non-white ratio {nonwhite_ratio:.1%}"))
    else:
        score = 0.7  # legacy can't earn higher than 0.7 without a real heuristic

    notes = f"legacy fallback: nonwhite={nonwhite_ratio:.1%}"
    return ScorerResult(score=score, issues=issues, notes=notes,
                        metrics=metrics, scorer="legacy")
