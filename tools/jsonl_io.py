"""Shared JSONL + queue-key helpers for the FP-033 correction queues.

Single source for the idioms that the queue WRITER (`tools/correction_loop`)
and the queue CONSUMER (`tools/vision_queue_consumer`) must keep in lockstep:

- tolerant JSONL read (skip blank/garbage lines, keep dict rows only) — the
  queues are append-only logs shared across processes, a torn line must never
  poison a drain;
- append-only JSONL write (queues are NEVER rewritten in place);
- ``queue_key``: THE dedup identity of a queued finding. Writer and consumer
  compare signatures of the SAME queue file, so a second implementation of
  this key is duplication-that-will-diverge (it already had: ``room=None``
  produced different keys on each side before this module existed).

Pure stdlib, no project imports — safe for both `tools/` and
`tools/claude_bridge/` callers.
"""
from __future__ import annotations

import json
from pathlib import Path


def read_jsonl(path: Path) -> list[dict]:
    """Tolerant read: missing file -> [], blank/garbage/non-dict lines skipped."""
    path = Path(path)
    if not path.is_file():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def append_jsonl(path: Path, rows: list[dict]) -> None:
    """Append rows to a JSONL log (queues are append-only, never rewritten)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def queue_key(finding: dict) -> tuple:
    """Dedup identity of a queued correction finding: (type, room, evidence[:80]).

    None-safe on both `room` and `evidence` (a finding may carry ``"room": None``
    explicitly — `.get(key, "")` would NOT default in that case).
    """
    return (finding.get("type"), finding.get("room") or "",
            (finding.get("evidence") or "")[:80])
