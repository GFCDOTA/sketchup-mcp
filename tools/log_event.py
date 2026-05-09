"""Append-only event log writer for the Mission Control surface.

Writes JSON-Lines events to ``.ai_bridge/events.jsonl``. Pure-Python,
zero non-stdlib dependencies, atomic per-line writes via ``open(... 'a')``
+ trailing newline (POSIX & Windows guarantee single-line atomicity for
small writes < PIPE_BUF).

## Rationale

The Mission Control cockpit aba consumes this file via
``cockpit.project_status.read_events`` to render the live timeline.
Without an event stream, "what is Claude doing right now?" is
unanswerable from the UI. With it, every meaningful action (task
started, gate result, artifact created, PR opened) becomes a
notification line.

## Event shape

Each line is one JSON object with at minimum ``ts`` (ISO-8601 UTC) and
``type`` (snake_case). Other fields are free-form per event type.

Conventional types:

- ``task_started`` — ``{title, branch?, commit?, status?}``
- ``task_finished`` — ``{title, status, duration_s?}``
- ``pr_opened`` — ``{number, title, branch}``
- ``pr_merged`` — ``{number, title, sha}``
- ``gate_result`` — ``{gate, status, reason?, report?}``
- ``artifact_created`` — ``{path, kind, run_id?}``
- ``decision_recorded`` — ``{title, ref?}``
- ``blocked`` — ``{reason, blocker_kind?}``

Producers SHOULD use ``log_event(type, **fields)`` rather than writing
raw JSON to keep schema discoverability via grep + the test suite.

## Boundary

This module ONLY appends to ``.ai_bridge/events.jsonl``. It does NOT:

- read events back (that's ``cockpit.project_status.read_events``)
- mutate any other file
- import streamlit / FastAPI / external services

It is safe to import from anywhere — including subprocess hooks,
smoke harness gates, and tools/* CLI scripts.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EVENTS_LOG_REL = Path(".ai_bridge") / "events.jsonl"
SCHEMA_VERSION = "events_v1"


def repo_root() -> Path:
    """Best-effort repo-root resolution.

    Looks for ``.ai_bridge/`` ascending from this file's dir, then
    cwd. Falls back to cwd if nothing matches; downstream callers can
    pass ``log_path`` explicitly when needed.
    """
    here = Path(__file__).resolve()
    for d in (here.parent.parent, *here.parents):
        if (d / ".ai_bridge").is_dir():
            return d
    return Path.cwd()


def default_log_path() -> Path:
    return repo_root() / EVENTS_LOG_REL


# ---------------------------------------------------------------------------
# Time helper
# ---------------------------------------------------------------------------

def _utc_iso() -> str:
    """ISO-8601 UTC timestamp, second precision."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def log_event(
    event_type: str,
    *,
    log_path: Path | None = None,
    actor: str = "claude",
    **fields: Any,
) -> dict:
    """Append an event to the log. Returns the written record.

    Defensive: failures (disk full, permission, weird encoding) are
    caught and printed to stderr — log_event MUST NEVER crash the
    caller. Mission Control showing stale data is preferable to a
    pipeline gate that fails because the log file was unwritable.

    Parameters
    ----------
    event_type : str
        Snake_case event identifier. See module docstring for the
        conventional set; arbitrary types are permitted.
    log_path : Path | None
        Override the default path (mainly for tests).
    actor : str
        Who emitted the event. Defaults to ``"claude"``. Other valid
        actors: ``"human:fmodesto30"``, ``"agent:<name>"``, ``"smoke"``,
        ``"ci"``.
    **fields
        Arbitrary additional payload merged into the record. Must be
        JSON-serialisable; anything else is coerced to ``str``.
    """
    record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "ts": _utc_iso(),
        "type": event_type,
        "actor": actor,
    }
    for k, v in fields.items():
        record[k] = _safe_value(v)

    target = Path(log_path) if log_path else default_log_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        # Append with explicit utf-8 encoding to avoid Windows cp1252.
        with target.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception as e:  # noqa: BLE001 — never propagate
        print(
            f"[log_event] failed to write {target}: "
            f"{type(e).__name__}: {e}",
            file=sys.stderr,
        )
    return record


def _safe_value(v: Any) -> Any:
    """Coerce non-serialisable values into JSON-friendly forms."""
    try:
        json.dumps(v)
        return v
    except (TypeError, ValueError):
        if isinstance(v, Path):
            return str(v)
        if isinstance(v, (set, frozenset)):
            return sorted(_safe_value(x) for x in v)
        return repr(v)


# ---------------------------------------------------------------------------
# CLI — emit ad-hoc events from shell
# ---------------------------------------------------------------------------

def _main(argv: list[str] | None = None) -> int:
    """Tiny CLI:

        python -m tools.log_event <type> [key=value ...]

    Examples:
        python -m tools.log_event task_started title="FP-014 visual gate"
        python -m tools.log_event pr_opened number=106 title="..." branch=...
    """
    import argparse
    p = argparse.ArgumentParser(
        description="Append an event to .ai_bridge/events.jsonl",
    )
    p.add_argument("event_type")
    p.add_argument("fields", nargs="*",
                   help="key=value pairs (value parsed as JSON if possible)")
    p.add_argument("--actor", default="claude")
    p.add_argument("--log-path", type=Path, default=None)
    args = p.parse_args(argv)
    parsed: dict[str, Any] = {}
    for kv in args.fields:
        if "=" not in kv:
            print(f"skip {kv!r}: no '=' separator", file=sys.stderr)
            continue
        k, v = kv.split("=", 1)
        # Avoid clashing with reserved kwargs of log_event.
        if k in ("actor", "log_path", "event_type"):
            print(f"skip {kv!r}: reserved key (use --{k.replace('_','-')})",
                  file=sys.stderr)
            continue
        try:
            parsed[k] = json.loads(v)
        except json.JSONDecodeError:
            parsed[k] = v
    record = log_event(args.event_type, log_path=args.log_path,
                       actor=args.actor, **parsed)
    print(json.dumps(record, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
