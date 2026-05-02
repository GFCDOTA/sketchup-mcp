"""Shared types for scorers."""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


@dataclass
class Issue:
    severity: str            # "info" | "warn" | "error"
    code: str                # short stable identifier ("rooms_count_mismatch")
    message: str             # human-readable
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ScorerResult:
    score: float                          # 0.0 .. 1.0
    issues: list[Issue] = field(default_factory=list)
    notes: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    scorer: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": round(float(self.score), 4),
            "issues": [i.to_dict() for i in self.issues],
            "notes": self.notes,
            "metrics": self.metrics,
            "scorer": self.scorer,
        }


@dataclass
class ScorerContext:
    """Pre-loaded artifacts the scorers can share without each one
    re-reading the same files."""
    repo_root: Path
    entry: dict[str, Any]
    consensus: dict[str, Any] | None = None    # parsed consensus_model.json
    inspect_report: dict[str, Any] | None = None  # tools/inspect_walls_report output

    @classmethod
    def build(cls, repo_root: Path, entry: dict[str, Any]) -> "ScorerContext":
        consensus = _maybe_load_json(repo_root, entry.get("source", {}).get("consensus"))
        inspect = _find_inspect_report(repo_root, entry)
        return cls(repo_root=repo_root, entry=entry, consensus=consensus, inspect_report=inspect)


def _maybe_load_json(repo_root: Path, src: dict[str, Any] | None) -> dict[str, Any] | None:
    if not src or src.get("missing"):
        return None
    p = (repo_root / src["path"]) if not Path(src["path"]).is_absolute() else Path(src["path"])
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _find_inspect_report(repo_root: Path, entry: dict[str, Any]) -> dict[str, Any] | None:
    """Try to find an inspect_walls_report.rb output that matches this
    entry's source.skp by sha256. Falls back to most-recent
    ``runs/vector/inspect_report*.json`` if no exact match."""
    src = entry.get("source", {}).get("skp")
    if not src or src.get("missing"):
        return None

    # The inspect report doesn't embed the .skp sha256, so match by basename.
    # When multiple reports point at the same .skp basename, prefer the one
    # whose mtime is closest to (but >=) the entry's source.skp.mtime — that
    # captures "the inspection that ran AFTER this .skp was written". If no
    # report matches the basename, return None rather than falling back to
    # an unrelated report (the scorer will then emit an `inspect_missing`
    # issue, which is honest).
    target_name = Path(src["path"]).name
    matches: list[tuple[Path, dict, float]] = []
    for cand in (repo_root / "runs").rglob("inspect_report*.json"):
        try:
            data = json.loads(cand.read_text(encoding="utf-8"))
        except Exception:
            continue
        cand_skp = data.get("meta", {}).get("skp_path", "")
        if Path(cand_skp).name == target_name:
            matches.append((cand, data, cand.stat().st_mtime))
    if not matches:
        return None

    src_mtime = 0.0
    if src.get("mtime"):
        try:
            import datetime as _dt
            src_mtime = _dt.datetime.fromisoformat(src["mtime"]).timestamp()
        except Exception:
            pass

    if src_mtime:
        # report.mtime >= skp.mtime is canonical (inspector ran on this skp);
        # otherwise pick the report closest in time.
        after = [m for m in matches if m[2] >= src_mtime]
        pick = min(after, key=lambda m: m[2] - src_mtime) if after else \
               min(matches, key=lambda m: abs(m[2] - src_mtime))
    else:
        pick = max(matches, key=lambda m: m[2])

    cand, data, _ = pick
    data["__match__"] = "name+mtime"
    data["__source__"] = str(cand)
    return data
