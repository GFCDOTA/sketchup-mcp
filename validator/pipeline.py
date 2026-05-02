"""End-to-end validation pipeline.

``validate_entry(entry, repo_root)`` picks a scorer, runs it, optionally
asks a vision LLM for qualitative critique, and returns the validation
dict ready to be passed to ``tools.png_history.apply_validation``.
"""
from __future__ import annotations

import datetime as _dt
import os
from pathlib import Path
from typing import Any

from .scorers import REGISTRY, ScorerContext, resolve
from .vision import maybe_vision_critique


def validate_entry(entry: dict, repo_root: Path,
                   *, vision: bool = False) -> dict[str, Any]:
    ctx = ScorerContext.build(repo_root, entry)
    scorer = resolve(entry.get("kind", "__default__"),
                     original_path=entry.get("original_path"))
    result = scorer(entry, ctx).to_dict()

    if vision:
        critique = maybe_vision_critique(entry, ctx)
        if critique is not None:
            result["vision"] = critique

    result["validated_at"] = _dt.datetime.now(tz=_dt.timezone.utc).isoformat()
    return result


def validate_pending(repo_root: Path, *, vision: bool = False,
                     limit: int | None = None,
                     force: bool = False) -> list[dict[str, Any]]:
    """Validate every entry where ``validation is None``. Returns a list
    of ``{id, validation}`` dicts (also persisted to manifest).

    ``force=True`` re-runs the scorer on already-validated entries too.
    """
    from tools.png_history import apply_validation, list_entries

    out = []
    if force:
        pending = list_entries()
    else:
        pending = [e for e in list_entries() if e.get("validation") is None]
    if limit is not None:
        pending = pending[:limit]
    for entry in pending:
        try:
            v = validate_entry(entry, repo_root, vision=vision)
        except Exception as exc:  # never let one bad entry kill the batch
            v = {
                "score": 0.0,
                "issues": [{
                    "severity": "error",
                    "code": "scorer_crash",
                    "message": f"{type(exc).__name__}: {exc}",
                    "detail": {},
                }],
                "notes": "scorer raised",
                "scorer": "exception",
                "validated_at": _dt.datetime.now(tz=_dt.timezone.utc).isoformat(),
            }
        ok = apply_validation(entry["id"], v)
        out.append({"id": entry["id"], "ok": ok, "validation": v})
    return out
