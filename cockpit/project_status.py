"""Mission Control reader — pure-Python, no Streamlit, no side effects.

Slice 1 of the project-level cockpit aba. Aggregates state from the
filesystem + git + ``gh`` CLI into one composable surface that
``cockpit/app.py`` renders as the Mission Control tabs.

## Why a separate module

- Same Boundary discipline as ``cockpit/overrides.py`` and
  ``cockpit/history_view.py``: no streamlit imports, every function
  pure (or read-only), unit-testable on synthetic fixtures.
- Lets the smoke harness, CI, or a future FastAPI surface reuse the
  same readers without dragging in the UI shell.

## Surface (Slice 1)

- ``current_project_state()`` -> single dict snapshot with branch,
  commit, dirty status, PR list summary, last events
- ``read_events(limit, log_path?)`` -> last N events from
  ``.ai_bridge/events.jsonl``
- ``current_branch()`` / ``current_commit()`` / ``working_tree_clean()``
- ``open_pull_requests()`` -> list of dicts via ``gh pr list``
- ``recent_runs(limit)`` -> dict per run dir with metadata + key paths
- ``recent_artifacts(limit)`` -> recently mtime-touched PNG/SVG/SKP
  paths under ``runs/`` and ``docs/diagnostics/``
- ``gates_summary(run_dir)`` -> per-gate status dict from a smoke run
- ``blockers_from_todo()`` -> RED/YELLOW items parsed from
  ``.ai_bridge/TODO_NEXT.md``
- ``handoff_excerpt()`` -> first ~30 lines of HANDOFF.md

## Failure semantics

Every function returns a partial / empty result on error rather than
raising. The cockpit MUST keep rendering even if git is unreachable,
``gh`` is missing, or the events file is corrupt.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

# ---------------------------------------------------------------------------
# Repo-root resolution (mirrors tools/log_event.py for consistency)
# ---------------------------------------------------------------------------

EVENTS_LOG_REL = Path(".ai_bridge") / "events.jsonl"
HANDOFF_REL = Path(".ai_bridge") / "HANDOFF.md"
TODO_NEXT_REL = Path(".ai_bridge") / "TODO_NEXT.md"
CURRENT_STATE_REL = Path(".ai_bridge") / "CURRENT_STATE.md"


def _resolve_repo_root() -> Path:
    """Best-effort: look for .ai_bridge ascending from this file."""
    here = Path(__file__).resolve()
    for d in (here.parent.parent, *here.parents):
        if (d / ".ai_bridge").is_dir():
            return d
    return Path.cwd()


def repo_root(override: Path | None = None) -> Path:
    if override:
        return Path(override)
    return _resolve_repo_root()


# ---------------------------------------------------------------------------
# Git state
# ---------------------------------------------------------------------------

def _run_git(args: list[str], cwd: Path) -> str:
    """Run a git command. Returns stdout text or "" on failure."""
    try:
        out = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True,
            timeout=10, check=False,
        )
        return out.stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def current_branch(repo: Path | None = None) -> str:
    return _run_git(["rev-parse", "--abbrev-ref", "HEAD"],
                    repo_root(repo)) or "?"


def current_commit(repo: Path | None = None) -> str:
    return _run_git(["rev-parse", "HEAD"], repo_root(repo)) or ""


def current_commit_short(repo: Path | None = None) -> str:
    return current_commit(repo)[:8]


def working_tree_clean(repo: Path | None = None) -> bool:
    out = _run_git(["status", "--porcelain"], repo_root(repo))
    return out == ""


def commits_ahead_of_develop(repo: Path | None = None) -> int:
    out = _run_git(["rev-list", "--count", "develop..HEAD"],
                   repo_root(repo))
    try:
        return int(out)
    except ValueError:
        return 0


def develop_sha(repo: Path | None = None) -> str:
    return _run_git(["rev-parse", "develop"], repo_root(repo))[:12]


def recent_commits(repo: Path | None = None, limit: int = 5) -> list[dict]:
    """List of {sha, subject, author, ts} for the last N commits on HEAD."""
    fmt = "%H%x09%s%x09%an%x09%aI"
    out = _run_git(
        ["log", f"-n{limit}", f"--pretty=format:{fmt}"], repo_root(repo),
    )
    rows: list[dict] = []
    for ln in out.splitlines():
        parts = ln.split("\t")
        if len(parts) != 4:
            continue
        sha, subj, author, ts = parts
        rows.append({
            "sha": sha, "sha_short": sha[:8],
            "subject": subj, "author": author, "ts": ts,
        })
    return rows


# ---------------------------------------------------------------------------
# Events log
# ---------------------------------------------------------------------------

def read_events(
    limit: int = 50,
    log_path: Path | None = None,
    repo: Path | None = None,
) -> list[dict]:
    """Read the last `limit` events from `.ai_bridge/events.jsonl`.

    Returns oldest-first ordered list of dicts. Malformed lines are
    silently skipped. Empty/missing file -> empty list.
    """
    target = Path(log_path) if log_path else (
        repo_root(repo) / EVENTS_LOG_REL
    )
    if not target.exists():
        return []
    out: list[dict] = []
    try:
        with target.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return out[-limit:] if limit > 0 else out


# ---------------------------------------------------------------------------
# GitHub via gh CLI
# ---------------------------------------------------------------------------

GH_CLI_PATH_DEFAULT = Path(r"C:\Program Files\GitHub CLI\gh.exe")


def _gh_cmd() -> list[str] | None:
    """Resolve a usable gh executable. Returns None if absent."""
    if GH_CLI_PATH_DEFAULT.exists():
        return [str(GH_CLI_PATH_DEFAULT)]
    # Fall back to PATH.
    try:
        out = subprocess.run(
            ["gh", "--version"], capture_output=True, text=True,
            timeout=5, check=False,
        )
        if out.returncode == 0:
            return ["gh"]
    except Exception:  # noqa: BLE001
        pass
    return None


def _gh_run(args: list[str], cwd: Path, timeout: int = 15) -> str | None:
    cmd = _gh_cmd()
    if cmd is None:
        return None
    try:
        out = subprocess.run(
            [*cmd, *args], cwd=cwd, capture_output=True, text=True,
            timeout=timeout, check=False,
        )
        if out.returncode != 0:
            return None
        return out.stdout
    except Exception:  # noqa: BLE001
        return None


def open_pull_requests(repo: Path | None = None) -> list[dict]:
    """List open PRs via `gh pr list --json`. Empty list on failure."""
    raw = _gh_run(
        ["pr", "list", "--json",
         "number,title,headRefName,mergeStateStatus,statusCheckRollup,createdAt"],
        repo_root(repo),
    )
    if not raw:
        return []
    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        return []
    out: list[dict] = []
    for it in items:
        checks = it.get("statusCheckRollup") or []
        succ = sum(1 for c in checks if c.get("conclusion") == "SUCCESS")
        fail = sum(1 for c in checks if c.get("conclusion") == "FAILURE")
        run = sum(1 for c in checks
                  if (c.get("status") in ("IN_PROGRESS", "QUEUED"))
                  or c.get("conclusion") == "")
        out.append({
            "number": it.get("number"),
            "title": it.get("title") or "",
            "branch": it.get("headRefName") or "",
            "merge_state": it.get("mergeStateStatus") or "?",
            "checks_total": len(checks),
            "checks_success": succ,
            "checks_failure": fail,
            "checks_running": run,
            "created_at": it.get("createdAt") or "",
        })
    return out


def merged_pull_requests_today(repo: Path | None = None) -> list[dict]:
    """Recent merged PRs (last 5)."""
    raw = _gh_run(
        ["pr", "list", "--state", "merged", "--limit", "5", "--json",
         "number,title,headRefName,mergedAt,mergeCommit"],
        repo_root(repo),
    )
    if not raw:
        return []
    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return [{
        "number": it.get("number"),
        "title": it.get("title") or "",
        "branch": it.get("headRefName") or "",
        "merged_at": it.get("mergedAt") or "",
        "sha": (it.get("mergeCommit") or {}).get("oid") or "",
    } for it in items]


# ---------------------------------------------------------------------------
# Runs + artifacts
# ---------------------------------------------------------------------------

@dataclass
class RunRow:
    """Light per-run summary for the Mission Control table."""

    run_id: str
    run_dir: Path
    consensus_path: Path | None
    fidelity_score: float | None
    f0_verdict: str | None
    structural_blockers_count: int
    structural_warnings_count: int
    has_skp: bool
    mtime: float

    def as_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "run_dir": str(self.run_dir),
            "consensus_path": (
                str(self.consensus_path) if self.consensus_path else None
            ),
            "fidelity_score": self.fidelity_score,
            "f0_verdict": self.f0_verdict,
            "structural_blockers_count": self.structural_blockers_count,
            "structural_warnings_count": self.structural_warnings_count,
            "has_skp": self.has_skp,
            "mtime": self.mtime,
        }


def _safe_load_json(p: Path) -> dict | None:
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _scan_run_dir(run_dir: Path) -> RunRow:
    consensus_path: Path | None = None
    for name in ("consensus.json", "consensus_with_room_context.json",
                 "consensus_classified.json"):
        p = run_dir / name
        if p.exists():
            consensus_path = p
            break

    fid = _safe_load_json(run_dir / "fidelity_report.json")
    score: float | None = None
    if fid is not None:
        v = fid.get("global_fidelity")
        if isinstance(v, (int, float)):
            score = float(v)

    psr_paths = [
        run_dir / "_smoke_out" / "pre_skp_review_report.json",
        run_dir / "pre_skp_review_report.json",
    ]
    psr: dict | None = None
    for p in psr_paths:
        psr = _safe_load_json(p)
        if psr is not None:
            break
    f0_verdict = psr.get("verdict") if psr else None
    sb = psr.get("structural_blockers_count", 0) if psr else 0
    sw = psr.get("structural_warnings_count", 0) if psr else 0

    has_skp = any(
        (run_dir / sub / "model.skp").exists()
        for sub in ("", "_smoke_out")
    )
    try:
        mtime = run_dir.stat().st_mtime
    except OSError:
        mtime = 0.0
    return RunRow(
        run_id=run_dir.name, run_dir=run_dir,
        consensus_path=consensus_path,
        fidelity_score=score, f0_verdict=f0_verdict,
        structural_blockers_count=int(sb),
        structural_warnings_count=int(sw),
        has_skp=has_skp, mtime=mtime,
    )


def recent_runs(repo: Path | None = None, limit: int = 8) -> list[RunRow]:
    runs_dir = repo_root(repo) / "runs"
    if not runs_dir.is_dir():
        return []
    rows: list[RunRow] = []
    for sub in runs_dir.iterdir():
        if not sub.is_dir():
            continue
        if sub.name.startswith("."):
            continue
        rows.append(_scan_run_dir(sub))
    rows.sort(key=lambda r: r.mtime, reverse=True)
    return rows[:limit]


def recent_artifacts(
    repo: Path | None = None, limit: int = 12,
    extensions: tuple[str, ...] = (".png", ".svg", ".skp"),
) -> list[Path]:
    """Most recently mtime'd image/skp files under runs/ + docs/diagnostics/."""
    root = repo_root(repo)
    candidates: list[tuple[float, Path]] = []
    for base in (root / "runs", root / "docs" / "diagnostics"):
        if not base.is_dir():
            continue
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            if p.suffix.lower() not in extensions:
                continue
            try:
                candidates.append((p.stat().st_mtime, p))
            except OSError:
                continue
    candidates.sort(key=lambda t: t[0], reverse=True)
    return [p for _, p in candidates[:limit]]


# ---------------------------------------------------------------------------
# Gates summary (per-run smoke harness output)
# ---------------------------------------------------------------------------

def gates_summary(run_dir: Path | str) -> dict:
    """Read a smoke run's sketchup_smoke_report.json + return per-gate status.

    Output:
        {
          "found": bool,
          "verdict": "PASS"|"FAIL"|...,
          "gates": [{"name": "...", "status": "pass"|"fail"|"skip", "message": "..."}, ...],
        }
    """
    p = Path(run_dir) / "_smoke_out" / "sketchup_smoke_report.json"
    if not p.exists():
        # Some runs write the report at run-dir level
        p = Path(run_dir) / "sketchup_smoke_report.json"
    data = _safe_load_json(p)
    if data is None:
        return {"found": False, "verdict": None, "gates": []}
    gates = []
    for g in data.get("gates") or []:
        gates.append({
            "name": g.get("name") or "",
            "status": g.get("status") or "",
            "message": g.get("message") or "",
        })
    return {
        "found": True,
        "verdict": data.get("verdict"),
        "gates": gates,
    }


# ---------------------------------------------------------------------------
# Blockers from TODO_NEXT.md
# ---------------------------------------------------------------------------

_BLOCKER_HEADER_RE = re.compile(
    r"^##\s*([🔴🟡🟢]+)?\s*(P\d)\s*[—-]\s*(.+?)\s*$"
)


def blockers_from_todo(repo: Path | None = None) -> list[dict]:
    """Parse the TODO_NEXT.md headings of form `## 🔴 P0 — Title`.

    Returns rows with color (RED/YELLOW/GREEN), priority, title.
    Best-effort parser: skips lines that don't match the canonical
    pattern.
    """
    p = repo_root(repo) / TODO_NEXT_REL
    if not p.exists():
        return []
    color_map = {"🔴": "RED", "🟡": "YELLOW", "🟢": "GREEN"}
    rows: list[dict] = []
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return []
    for ln in text.splitlines():
        m = _BLOCKER_HEADER_RE.match(ln)
        if not m:
            continue
        emoji_cluster = m.group(1) or ""
        color = "?"
        for ch in emoji_cluster:
            if ch in color_map:
                color = color_map[ch]
                break
        rows.append({
            "color": color,
            "priority": m.group(2),
            "title": m.group(3),
        })
    return rows


# ---------------------------------------------------------------------------
# HANDOFF.md excerpt
# ---------------------------------------------------------------------------

def handoff_excerpt(
    repo: Path | None = None, max_lines: int = 30,
) -> str:
    """Return the first `max_lines` of HANDOFF.md, or empty string."""
    p = repo_root(repo) / HANDOFF_REL
    if not p.exists():
        return ""
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    return "\n".join(lines[:max_lines])


def current_state_excerpt(
    repo: Path | None = None, max_lines: int = 50,
) -> str:
    """First N lines of CURRENT_STATE.md."""
    p = repo_root(repo) / CURRENT_STATE_REL
    if not p.exists():
        return ""
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    return "\n".join(lines[:max_lines])


# ---------------------------------------------------------------------------
# Top-level snapshot
# ---------------------------------------------------------------------------

def current_project_state(repo: Path | None = None) -> dict:
    """One-shot snapshot for the Mission Control "Overview" tab.

    Aggregates branch/commit/PR/events into a single dict so the UI
    can render without 8 separate calls. Errors short-circuit each
    sub-key independently — partial data is rendered.
    """
    root = repo_root(repo)
    return {
        "captured_at": datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ",
        ),
        "branch": current_branch(root),
        "commit": current_commit_short(root),
        "develop": develop_sha(root),
        "clean": working_tree_clean(root),
        "ahead_of_develop": commits_ahead_of_develop(root),
        "open_prs": open_pull_requests(root),
        "merged_recent": merged_pull_requests_today(root),
        "recent_events": read_events(limit=10, repo=root),
        "recent_runs": [r.as_dict() for r in recent_runs(root, limit=5)],
        "recent_artifacts": [
            str(p.relative_to(root)) if p.is_relative_to(root) else str(p)
            for p in recent_artifacts(root, limit=8)
        ],
        "blockers": blockers_from_todo(root),
    }
