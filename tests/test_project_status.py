"""Tests for cockpit.project_status — Mission Control reader."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from cockpit.project_status import (
    blockers_from_todo,
    current_project_state,
    current_state_excerpt,
    gates_summary,
    handoff_excerpt,
    read_events,
    recent_artifacts,
    recent_runs,
)
from tools.log_event import log_event


# ---------------------------------------------------------------------------
# read_events
# ---------------------------------------------------------------------------


def test_read_events_empty_file_when_missing(tmp_path):
    log = tmp_path / "events.jsonl"
    assert read_events(log_path=log) == []


def test_read_events_returns_oldest_first_under_limit(tmp_path):
    log = tmp_path / "events.jsonl"
    log_event("e1", log_path=log)
    log_event("e2", log_path=log)
    log_event("e3", log_path=log)
    rows = read_events(limit=10, log_path=log)
    assert [r["type"] for r in rows] == ["e1", "e2", "e3"]


def test_read_events_truncates_to_limit_keeping_latest(tmp_path):
    log = tmp_path / "events.jsonl"
    for i in range(5):
        log_event(f"e{i}", log_path=log)
    rows = read_events(limit=2, log_path=log)
    assert [r["type"] for r in rows] == ["e3", "e4"]


def test_read_events_skips_malformed_lines(tmp_path):
    log = tmp_path / "events.jsonl"
    log.write_text(
        '{"type": "ok"}\nthis is not json\n{"type": "alsook"}\n',
        encoding="utf-8",
    )
    rows = read_events(log_path=log)
    assert [r["type"] for r in rows] == ["ok", "alsook"]


# ---------------------------------------------------------------------------
# blockers_from_todo
# ---------------------------------------------------------------------------


def test_blockers_from_todo_parses_header_pattern(tmp_path):
    todo = tmp_path / ".ai_bridge" / "TODO_NEXT.md"
    todo.parent.mkdir(parents=True)
    todo.write_text(
        "## 🔴 P0 — Real multi-PDF corpus\n\n"
        "## 🟡 P1 — ADR-002 room polygon override\n\n"
        "## 🟢 P2 — promote inspect-strict\n\n"
        "## not a blocker — random heading\n",
        encoding="utf-8",
    )
    rows = blockers_from_todo(repo=tmp_path)
    assert len(rows) == 3
    assert rows[0] == {"color": "RED", "priority": "P0",
                       "title": "Real multi-PDF corpus"}
    assert rows[1]["color"] == "YELLOW"
    assert rows[2]["color"] == "GREEN"


def test_blockers_from_todo_missing_returns_empty(tmp_path):
    assert blockers_from_todo(repo=tmp_path) == []


# ---------------------------------------------------------------------------
# handoff_excerpt
# ---------------------------------------------------------------------------


def test_handoff_excerpt_returns_first_n_lines(tmp_path):
    p = tmp_path / ".ai_bridge" / "HANDOFF.md"
    p.parent.mkdir(parents=True)
    p.write_text("\n".join(f"line {i}" for i in range(50)),
                 encoding="utf-8")
    excerpt = handoff_excerpt(repo=tmp_path, max_lines=10)
    assert excerpt.count("\n") == 9
    assert excerpt.startswith("line 0")


def test_handoff_excerpt_missing_returns_empty(tmp_path):
    assert handoff_excerpt(repo=tmp_path) == ""


# ---------------------------------------------------------------------------
# recent_runs
# ---------------------------------------------------------------------------


def _mk_run(parent: Path, name: str, *, with_consensus=False,
            with_fidelity=None, with_psr_verdict=None,
            structural_blockers=0, with_skp=False) -> Path:
    run = parent / "runs" / name
    run.mkdir(parents=True, exist_ok=True)
    if with_consensus:
        (run / "consensus.json").write_text(
            json.dumps({"walls": [], "rooms": [], "openings": []}),
            encoding="utf-8",
        )
    if with_fidelity is not None:
        (run / "fidelity_report.json").write_text(
            json.dumps({"global_fidelity": with_fidelity}),
            encoding="utf-8",
        )
    if with_psr_verdict is not None:
        out = run / "_smoke_out"
        out.mkdir(parents=True)
        (out / "pre_skp_review_report.json").write_text(
            json.dumps({
                "verdict": with_psr_verdict,
                "structural_blockers_count": structural_blockers,
                "structural_warnings_count": 0,
            }),
            encoding="utf-8",
        )
    if with_skp:
        out = run / "_smoke_out"
        out.mkdir(parents=True, exist_ok=True)
        (out / "model.skp").write_bytes(b"FAKESKP")
    return run


def test_recent_runs_returns_runs_with_metadata(tmp_path):
    _mk_run(tmp_path, "alpha", with_consensus=True,
            with_fidelity=0.92, with_psr_verdict="PASS")
    _mk_run(tmp_path, "beta", with_consensus=True,
            with_fidelity=0.69, with_psr_verdict="FAIL",
            structural_blockers=12, with_skp=True)
    rows = recent_runs(repo=tmp_path, limit=5)
    by_id = {r.run_id: r for r in rows}
    assert "alpha" in by_id and "beta" in by_id
    a = by_id["alpha"]
    assert a.fidelity_score == 0.92
    assert a.f0_verdict == "PASS"
    assert a.has_skp is False
    b = by_id["beta"]
    assert b.fidelity_score == 0.69
    assert b.f0_verdict == "FAIL"
    assert b.structural_blockers_count == 12
    assert b.has_skp is True


def test_recent_runs_skips_dotted_dirs(tmp_path):
    _mk_run(tmp_path, "_test_thing")
    _mk_run(tmp_path, ".hidden")
    rows = recent_runs(repo=tmp_path)
    ids = {r.run_id for r in rows}
    assert ".hidden" not in ids
    assert "_test_thing" in ids


def test_recent_runs_empty_when_no_runs_dir(tmp_path):
    assert recent_runs(repo=tmp_path) == []


# ---------------------------------------------------------------------------
# recent_artifacts
# ---------------------------------------------------------------------------


def test_recent_artifacts_finds_pngs_under_runs_and_diagnostics(tmp_path):
    (tmp_path / "runs" / "x").mkdir(parents=True)
    (tmp_path / "runs" / "x" / "preview.png").write_bytes(b"PNG")
    (tmp_path / "docs" / "diagnostics").mkdir(parents=True)
    (tmp_path / "docs" / "diagnostics" / "shot.svg").write_text(
        "<svg/>", encoding="utf-8",
    )
    (tmp_path / "docs" / "diagnostics" / "ignore.md").write_text(
        "ignored", encoding="utf-8",
    )
    arts = recent_artifacts(repo=tmp_path, limit=10)
    names = {a.name for a in arts}
    assert "preview.png" in names
    assert "shot.svg" in names
    assert "ignore.md" not in names


def test_recent_artifacts_orders_by_mtime_newest_first(tmp_path):
    base = tmp_path / "runs"
    base.mkdir()
    p1 = base / "old.png"; p1.write_bytes(b"OLD")
    p2 = base / "new.png"; p2.write_bytes(b"NEW")
    import os, time
    # Force older mtime on p1
    os.utime(p1, (time.time() - 1000, time.time() - 1000))
    arts = recent_artifacts(repo=tmp_path, limit=10)
    assert arts[0].name == "new.png"
    assert arts[1].name == "old.png"


# ---------------------------------------------------------------------------
# gates_summary
# ---------------------------------------------------------------------------


def test_gates_summary_reads_smoke_report(tmp_path):
    run = tmp_path / "run0"
    out = run / "_smoke_out"; out.mkdir(parents=True)
    (out / "sketchup_smoke_report.json").write_text(json.dumps({
        "verdict": "FAIL",
        "gates": [
            {"name": "A. Preparation", "status": "pass", "message": "ok"},
            {"name": "F0. Pre-SKP review", "status": "fail",
             "message": "12 structural_blocker(s)"},
        ],
    }), encoding="utf-8")
    s = gates_summary(run)
    assert s["found"] is True
    assert s["verdict"] == "FAIL"
    assert len(s["gates"]) == 2
    assert s["gates"][1]["status"] == "fail"


def test_gates_summary_missing_report_returns_unfound(tmp_path):
    s = gates_summary(tmp_path / "nonexistent")
    assert s == {"found": False, "verdict": None, "gates": []}


# ---------------------------------------------------------------------------
# current_project_state — top-level snapshot
# ---------------------------------------------------------------------------


def test_current_project_state_does_not_crash_on_empty_repo(tmp_path):
    """Even with no .ai_bridge/, no runs/, no git → returns dict shape."""
    state = current_project_state(repo=tmp_path)
    assert "captured_at" in state
    assert "branch" in state
    assert state["recent_events"] == []
    assert state["recent_runs"] == []
    assert state["blockers"] == []
