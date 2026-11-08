"""store_factory.py — EventStore singleton and bridge/executor integration.

Wiring layer between the existing event_bridge / event_executor (JSON-file
queue) and the new durable EventStore (SQLite).  SPEC §6.3 migration: shadow
mode — the bridge dual-writes to both JSON and SQLite; the executor prefers
SQLite claims and falls back to JSON.  Rollback = disable SQLite reads.

Path: ``runs/governance/event_store.db`` (overridable via
``EVENT_STORE_DB_PATH``).  The db lives outside worktrees so it survives
worktree cleanup.
"""
from __future__ import annotations

import os
from pathlib import Path

from tools.orchestration.event_store import EventStore

_STORE: EventStore | None = None


def store_path() -> Path:
    env = os.environ.get("EVENT_STORE_DB_PATH")
    if env:
        return Path(env)
    from tools.orchestration import event_bridge as eb
    return eb.bridge_path().with_name("event_store.db")


def get_store(path: Path | str | None = None, **kw) -> EventStore:
    """Singleton per process.  Thread-safe because EventStore uses per-call
    connections with WAL + IMMEDIATE transactions."""
    global _STORE
    if _STORE is not None and (path is None or str(path) == _STORE.path):
        return _STORE
    p = Path(path) if path else store_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    _STORE = EventStore(p, **kw)
    return _STORE


def reset_store() -> None:
    """Test helper: drop the cached singleton."""
    global _STORE
    _STORE = None


def bridge_event_type(event: dict) -> str | None:
    """Map a bridge event to an EventStore event_type.

    Returns None for events the EventStore doesn't consume yet."""
    if event.get("kind") == "review" and event.get("state") == "CHANGES_REQUESTED":
        return "CORRECTION_REQUESTED"
    return None


def bridge_to_store_args(event: dict, pr_facts: dict) -> dict | None:
    """Build ``EventStore.publish()`` kwargs from a bridge event + PR facts.

    Returns None if the event type is not mapped.  The idempotency key matches
    the bridge's ``task_key`` so duplicate detection spans both systems."""
    et = bridge_event_type(event)
    if et is None:
        return None
    head_sha = pr_facts.get("head_sha", "")
    job_id = f"pr:{event.get('pr', '')}"
    idem = f"{event['event_id']}:{event.get('pr')}:{head_sha}"
    return dict(
        event_type=et,
        idempotency_key=idem,
        job_id=job_id,
        payload={
            "pr": event.get("pr"),
            "issue": sorted(pr_facts.get("refs", []))[0] if pr_facts.get("refs") else None,
            "head_sha": head_sha,
            "review_id": event.get("event_id", "").replace("review:", ""),
            "author": event.get("author"),
            "url": event.get("url"),
        },
        correlation_id=f"bridge:{event['event_id']}",
        producer="event_bridge",
    )
