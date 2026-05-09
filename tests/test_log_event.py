"""Tests for tools.log_event — Mission Control event writer."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.log_event import SCHEMA_VERSION, log_event


def _read_lines(p: Path) -> list[dict]:
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def test_log_event_appends_a_line(tmp_path):
    log = tmp_path / "events.jsonl"
    rec = log_event("task_started", log_path=log, title="Hello")
    assert log.exists()
    rows = _read_lines(log)
    assert len(rows) == 1
    assert rows[0]["type"] == "task_started"
    assert rows[0]["title"] == "Hello"
    assert rows[0]["actor"] == "claude"
    assert rows[0]["schema_version"] == SCHEMA_VERSION
    assert "ts" in rec


def test_log_event_multiple_events_appended(tmp_path):
    log = tmp_path / "events.jsonl"
    log_event("task_started", log_path=log, title="A")
    log_event("task_finished", log_path=log, title="A", status="ok")
    rows = _read_lines(log)
    assert len(rows) == 2
    assert rows[0]["type"] == "task_started"
    assert rows[1]["type"] == "task_finished"
    assert rows[1]["status"] == "ok"


def test_log_event_creates_parent_dir(tmp_path):
    log = tmp_path / "missing" / "events.jsonl"
    log_event("x", log_path=log)
    assert log.exists()
    assert log.parent.is_dir()


def test_log_event_actor_override(tmp_path):
    log = tmp_path / "events.jsonl"
    log_event("pr_opened", log_path=log, actor="human:fmodesto30", number=99)
    rows = _read_lines(log)
    assert rows[0]["actor"] == "human:fmodesto30"
    assert rows[0]["number"] == 99


def test_log_event_coerces_unserialisable_to_str(tmp_path):
    log = tmp_path / "events.jsonl"
    class Weird:
        pass
    log_event("oddball", log_path=log, target=Weird(), path=Path("/tmp/x"))
    rows = _read_lines(log)
    assert isinstance(rows[0]["target"], str)
    # Path coerces to its string form
    assert "x" in rows[0]["path"]


def test_log_event_handles_unicode(tmp_path):
    log = tmp_path / "events.jsonl"
    log_event("decision", log_path=log, title="ADR-002 — adicionado")
    rows = _read_lines(log)
    assert "—" in rows[0]["title"]


def test_log_event_returns_record_even_on_disk_error(tmp_path, monkeypatch):
    """If disk write fails, returns the dict + prints stderr (no raise)."""
    log = tmp_path / "events.jsonl"
    # Force open() to error
    real_open = Path.open
    calls = {"n": 0}
    def boom(self, *args, **kwargs):
        if str(self) == str(log):
            calls["n"] += 1
            raise OSError("disk full (test)")
        return real_open(self, *args, **kwargs)
    monkeypatch.setattr(Path, "open", boom)
    rec = log_event("oops", log_path=log, title="dies silently")
    # Returns the record even though file wasn't written
    assert rec["type"] == "oops"
    assert rec["title"] == "dies silently"


def test_log_event_writes_compact_json(tmp_path):
    """Records should be on a single line each (no inner newlines)."""
    log = tmp_path / "events.jsonl"
    log_event("nested", log_path=log,
              detail={"a": 1, "b": [2, 3], "c": "hello"})
    raw = log.read_text(encoding="utf-8")
    lines = [ln for ln in raw.splitlines() if ln.strip()]
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["detail"] == {"a": 1, "b": [2, 3], "c": "hello"}
