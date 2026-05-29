"""LL-024 — auto GPT consult wiring tests.

These cover the trigger detector + the orchestrator-level helper that
calls the gate. They do NOT run the full SKP build (would need SU).

What we check:
- detect_gpt_consult_trigger returns the right canonical trigger for
  each canonical pipeline state
- _maybe_run_gpt_consult writes a question file under .ai_bridge/
- mode=off short-circuits (no question even when trigger fires)
- mode=required + bridge offline returns block-required signal
- mode=auto + no trigger does NOT call the gate
- planta_74 state (oracle PASS + known warnings) triggers exactly
  oracle_pass_but_known_warnings
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.ask_gpt_gate import CANONICAL_TRIGGERS
from tools.run_skp_visual_review import (
    _build_consult_state, _maybe_run_gpt_consult,
    detect_gpt_consult_trigger, question_for_trigger,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


# ---- trigger detection ----------------------------------------------


def test_no_trigger_returns_none():
    """All-PASS state with no known warnings: no consult."""
    state = {
        "oracle_verdict": "PASS",
        "deterministic_verdict": "PASS",
        "carried_known_warnings_verdict": "PASS",
        "final_verdict": "PASS",
        "known_warnings_carried": [],
        "oracle_status": "ok",
    }
    assert detect_gpt_consult_trigger(state) is None


def test_final_fail_triggers_final_fail_non_obvious_fix():
    state = {
        "oracle_verdict": "PASS",
        "final_verdict": "FAIL",
    }
    assert (
        detect_gpt_consult_trigger(state)
        == "final_fail_non_obvious_fix"
    )


def test_final_blocked_triggers_require_oracle_blocks_backend():
    state = {"final_verdict": "BLOCKED"}
    assert (
        detect_gpt_consult_trigger(state)
        == "require_oracle_blocks_backend"
    )


def test_oracle_status_unavailable_triggers_require_oracle_blocks_backend():
    state = {
        "oracle_status": "unavailable",
        "final_verdict": "WARN_documented",
    }
    assert (
        detect_gpt_consult_trigger(state)
        == "require_oracle_blocks_backend"
    )


def test_oracle_status_incompatible_triggers_require_oracle_blocks_backend():
    state = {"oracle_status": "incompatible", "final_verdict": "PASS"}
    assert (
        detect_gpt_consult_trigger(state)
        == "require_oracle_blocks_backend"
    )


def test_disagreement_triggers_oracle_neq_final():
    state = {
        "oracle_verdict": "WARN",
        "final_verdict": "PASS",
        "oracle_status": "ok",
    }
    assert (
        detect_gpt_consult_trigger(state)
        == "oracle_verdict_neq_final_verdict"
    )


def test_oracle_pass_with_known_warnings_triggers_known_warnings():
    """The planta_74 canonical case."""
    state = {
        "oracle_verdict": "PASS",
        "deterministic_verdict": "PASS",
        "carried_known_warnings_verdict": "WARN_documented",
        "final_verdict": "WARN_documented",
        "known_warnings_carried": [
            "room_fidelity: 8 cells vs 11 ambients",
            "wall_fidelity: sb007 ambiguous",
            "wall_fidelity: sb_sliver",
        ],
        "oracle_status": "ok",
    }
    assert (
        detect_gpt_consult_trigger(state)
        == "oracle_pass_but_known_warnings"
    )


def test_carried_warn_documented_alone_triggers_known_warnings():
    """Defensive: even if known_warnings_carried list isn't populated,
    the carried verdict alone is enough."""
    state = {
        "carried_known_warnings_verdict": "WARN_documented",
        "final_verdict": "WARN_documented",
    }
    assert (
        detect_gpt_consult_trigger(state)
        == "oracle_pass_but_known_warnings"
    )


def test_every_trigger_has_a_question():
    """Every trigger emitted by the detector must have a registered
    question in question_for_trigger."""
    sample_states = [
        {"final_verdict": "FAIL"},
        {"final_verdict": "BLOCKED"},
        {"oracle_status": "unavailable"},
        {"oracle_verdict": "WARN", "final_verdict": "PASS"},
        {
            "oracle_verdict": "PASS",
            "known_warnings_carried": ["x"],
            "carried_known_warnings_verdict": "WARN_documented",
            "final_verdict": "WARN_documented",
        },
    ]
    for s in sample_states:
        trig = detect_gpt_consult_trigger(s)
        assert trig in CANONICAL_TRIGGERS
        q = question_for_trigger(trig)
        assert isinstance(q, str)
        assert len(q) > 30


# ---- _maybe_run_gpt_consult wiring ---------------------------------


def _planta_74_attempts() -> list[dict]:
    return [{
        "attempt": "canonical", "verdict": "WARN_documented",
        "oracle_verdict": "PASS",
        "deterministic_verdict": "PASS",
        "carried_known_warnings_verdict": "WARN_documented",
        "known_warnings_carried": [
            "room_fidelity: open-plan",
            "wall_fidelity: sb007",
            "wall_fidelity: sb_sliver",
        ],
        "findings": [], "axes": {},
        "input_summary": {},
    }]


def test_mode_off_does_not_call_gate_even_with_trigger(tmp_path: Path):
    attempts = _planta_74_attempts()
    block_required = _maybe_run_gpt_consult(
        "off", attempts, "planta_74", tmp_path / "final",
        oracle_status="ok", oracle_status_detail="ok",
        require_oracle_block=False,
    )
    record = attempts[-1]["gpt_consult"]
    assert record["mode"] == "off"
    assert record["triggered"] is False
    assert record["status"] == "not_applicable"
    assert block_required is False
    # No question file written under .ai_bridge/
    qdir = REPO_ROOT / ".ai_bridge" / "questions"
    if qdir.exists():
        before = set(qdir.iterdir())
    else:
        before = set()
    # Call again to confirm idempotent off
    _maybe_run_gpt_consult(
        "off", attempts, "planta_74", tmp_path / "final",
        oracle_status="ok", oracle_status_detail="ok",
        require_oracle_block=False,
    )
    if qdir.exists():
        after = set(qdir.iterdir())
        assert after == before


def test_mode_auto_writes_question_for_planta_74_case(tmp_path: Path, monkeypatch):
    """Forces bridge offline by using a closed port; default mode writes
    SKIPPED_OFFLINE without blocking."""
    # Redirect .ai_bridge to a tmp dir so we do not pollute the repo
    fake_repo = tmp_path / "repo"
    fake_repo.mkdir()
    (fake_repo / ".ai_bridge" / "questions").mkdir(parents=True)
    (fake_repo / ".ai_bridge" / "responses").mkdir(parents=True)
    monkeypatch.setattr(
        "tools.run_skp_visual_review.REPO_ROOT", fake_repo,
    )

    attempts = _planta_74_attempts()
    block_required = _maybe_run_gpt_consult(
        "auto", attempts, "planta_74", tmp_path / "final",
        oracle_status="ok", oracle_status_detail="ok",
        require_oracle_block=False,
    )
    record = attempts[-1]["gpt_consult"]
    assert record["triggered"] is True
    assert record["trigger"] == "oracle_pass_but_known_warnings"
    assert record["status"] == "SKIPPED_OFFLINE"
    assert record["question_path"] is not None
    assert block_required is False

    qdir = fake_repo / ".ai_bridge" / "questions"
    files = list(qdir.iterdir())
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8")
    assert "oracle_pass_but_known_warnings" in content


def test_mode_required_offline_returns_block_required(tmp_path: Path, monkeypatch):
    fake_repo = tmp_path / "repo"
    fake_repo.mkdir()
    monkeypatch.setattr(
        "tools.run_skp_visual_review.REPO_ROOT", fake_repo,
    )
    attempts = _planta_74_attempts()
    block_required = _maybe_run_gpt_consult(
        "required", attempts, "planta_74", tmp_path / "final",
        oracle_status="ok", oracle_status_detail="ok",
        require_oracle_block=False,
    )
    record = attempts[-1]["gpt_consult"]
    assert record["mode"] == "required"
    assert record["triggered"] is True
    # Bridge offline -> SKIPPED_OFFLINE, but mode=required bubbles up
    assert record["status"] == "SKIPPED_OFFLINE"
    assert block_required is True


def test_mode_auto_no_trigger_no_call(tmp_path: Path):
    attempts = [{
        "attempt": "canonical", "verdict": "PASS",
        "oracle_verdict": "PASS",
        "deterministic_verdict": "PASS",
        "carried_known_warnings_verdict": "PASS",
        "known_warnings_carried": [],
        "findings": [], "axes": {},
    }]
    block_required = _maybe_run_gpt_consult(
        "auto", attempts, "quadrado", tmp_path / "final",
        oracle_status="ok", oracle_status_detail="ok",
        require_oracle_block=False,
    )
    record = attempts[-1]["gpt_consult"]
    assert record["triggered"] is False
    assert record["status"] == "not_applicable"
    assert block_required is False


# ---- state builder --------------------------------------------------


def test_build_consult_state_handles_empty_attempts():
    assert _build_consult_state([], None) == {}


def test_build_consult_state_pulls_from_last_attempt():
    attempts = [{
        "verdict": "WARN_documented",
        "oracle_verdict": "PASS",
        "deterministic_verdict": "PASS",
        "carried_known_warnings_verdict": "WARN_documented",
        "known_warnings_carried": ["foo"],
    }]
    state = _build_consult_state(attempts, "ok")
    assert state["final_verdict"] == "WARN_documented"
    assert state["oracle_verdict"] == "PASS"
    assert state["known_warnings_carried"] == ["foo"]
    assert state["oracle_status"] == "ok"
