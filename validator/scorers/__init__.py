"""Per-kind scorer dispatch.

Each scorer is a callable ``f(entry, ctx) -> ScorerResult`` registered in
``REGISTRY``. ``pipeline.validate_entry`` chooses one based on the
manifest entry's ``kind`` field, with a longest-prefix match.

Resolution order for a kind ``axon_axon`` is:
  1. exact match: ``axon_axon``
  2. longest prefix match in REGISTRY (e.g. ``axon_`` matches ``axon_axon``)
  3. ``__default__``
"""
from __future__ import annotations

from .base import Issue, ScorerContext, ScorerResult
from .axon import score_axon
from .skp_view import score_skp_view
from .sidebyside import score_sidebyside
from .legacy import score_legacy

REGISTRY = {
    "axon_axon":         score_axon,
    "axon_top":          score_axon,
    "axon":              score_axon,
    "skp_view":          score_skp_view,
    "_skp_open_iso":     score_skp_view,
    "_skp_top":          score_skp_view,
    "_su_screenshot":    score_skp_view,
    "sidebyside_skp":    score_skp_view,
    "sidebyside":        score_sidebyside,
    "side_by_side":      score_sidebyside,
    "sidebyside_axon":   score_sidebyside,
    "triple_comparison": score_sidebyside,
    "__default__":       score_legacy,
}


def resolve(kind: str, original_path: str | None = None):
    """Pick a scorer for the entry.

    Order:
      1. exact ``kind`` match
      2. longest-prefix match on ``kind``
      3. if ``kind == 'legacy'`` and ``original_path`` is given, sniff the
         filename for a known suffix (axon_*, side_by_side, _skp_, etc.)
         so backfilled entries get the right scorer
      4. ``__default__``
    """
    if kind in REGISTRY:
        return REGISTRY[kind]
    candidates = [k for k in REGISTRY if k != "__default__" and kind.startswith(k)]
    if candidates:
        return REGISTRY[max(candidates, key=len)]

    if kind == "legacy" and original_path:
        from pathlib import Path
        stem = Path(original_path).stem.lower()
        for needle, picked in (
            ("_skp_", "skp_view"),
            ("_su_screenshot", "skp_view"),
            ("sidebyside_skp", "sidebyside_skp"),
            ("triple_comparison", "triple_comparison"),
            ("sidebyside_axon", "sidebyside_axon"),
            ("side_by_side", "side_by_side"),
            ("sidebyside", "sidebyside"),
            ("axon_top", "axon_top"),
            ("axon_3d", "axon_axon"),
            ("axon", "axon"),
        ):
            if needle in stem:
                return REGISTRY[picked]

    return REGISTRY["__default__"]


__all__ = [
    "Issue", "ScorerContext", "ScorerResult",
    "REGISTRY", "resolve",
]
