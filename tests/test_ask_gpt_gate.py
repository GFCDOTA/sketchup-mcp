"""LL-024 — GPT Auto-Consult Gate contract tests.

Cover:
- GateInput validation (unknown trigger rejected, empty question rejected)
- build_prompt includes all 4 expected sections
- probe_bridge returns honest False when port closed
- run_gate writes question file when offline
- --require-consult + offline returns BLOCKED_BRIDGE_OFFLINE
- default + offline returns SKIPPED_OFFLINE (exit 0)
- canonical trigger list shape

No real network calls. Tests run against a guaranteed-closed local port.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.ask_gpt_gate import (
    BRIDGE_URL, CANONICAL_TRIGGERS, GateInput, GateResult,
    build_prompt, probe_bridge, run_gate,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


# ---- canonical trigger list ------------------------------------------


def test_canonical_triggers_count():
    assert len(CANONICAL_TRIGGERS) == 9


def test_canonical_triggers_include_pr206_case():
    assert "oracle_pass_but_known_warnings" in CANONICAL_TRIGGERS


def test_canonical_triggers_include_user_request():
    assert "user_requested_consult" in CANONICAL_TRIGGERS


# ---- GateInput validation -------------------------------------------


def test_gate_input_rejects_unknown_trigger():
    g = GateInput(trigger="bogus", question="hi", context={})
    with pytest.raises(ValueError):
        g.validate()


def test_gate_input_rejects_empty_question():
    g = GateInput(
        trigger="user_requested_consult", question="   ", context={},
    )
    with pytest.raises(ValueError):
        g.validate()


def test_gate_input_accepts_valid():
    g = GateInput(
        trigger="user_requested_consult",
        question="should we merge?",
        context={"some": "ctx"},
    )
    g.validate()  # should not raise


# ---- prompt builder --------------------------------------------------


def test_build_prompt_includes_all_sections():
    g = GateInput(
        trigger="oracle_pass_but_known_warnings",
        question="Should PR #206 merge?",
        context={"final_verdict": "WARN_documented"},
        repo_state={"branch": "develop", "pr": 206},
    )
    prompt = build_prompt(g)
    assert "## Trigger" in prompt
    assert "## Repo state" in prompt
    assert "## Context" in prompt
    assert "## Question" in prompt
    assert "## Answer format" in prompt
    # And the dynamic values
    assert "oracle_pass_but_known_warnings" in prompt
    assert "Should PR #206 merge?" in prompt
    assert "WARN_documented" in prompt


def test_build_prompt_without_repo_state():
    g = GateInput(
        trigger="user_requested_consult",
        question="X?",
        context={},
    )
    prompt = build_prompt(g)
    assert "## Repo state" not in prompt
    assert "## Context" in prompt


# ---- bridge probe ----------------------------------------------------


def test_probe_bridge_returns_false_when_closed_port():
    """The probe must not raise even when the port is closed."""
    available, detail = probe_bridge(url="http://127.0.0.1:1")
    assert available is False
    assert "unreachable" in detail.lower() or "127.0.0.1:1" in detail


# ---- run_gate offline behaviour -------------------------------------


def test_run_gate_default_offline_returns_SKIPPED_OFFLINE(tmp_path: Path):
    g = GateInput(
        trigger="user_requested_consult",
        question="X?",
        context={},
    )
    result = run_gate(
        g,
        questions_dir=tmp_path / "q",
        responses_dir=tmp_path / "r",
        require_consult=False,
        url="http://127.0.0.1:1",
    )
    assert result.status == "SKIPPED_OFFLINE"
    assert result.question_path is not None
    assert result.question_path.exists()
    assert result.response_path is None
    # Question file references trigger and is non-empty
    content = result.question_path.read_text(encoding="utf-8")
    assert "user_requested_consult" in content
    assert "X?" in content
    assert "OFFLINE" in content


def test_run_gate_require_consult_offline_returns_BLOCKED(tmp_path: Path):
    g = GateInput(
        trigger="oracle_pass_but_known_warnings",
        question="merge?",
        context={"oracle_verdict": "PASS", "final_verdict": "WARN_documented"},
    )
    result = run_gate(
        g,
        questions_dir=tmp_path / "q",
        responses_dir=tmp_path / "r",
        require_consult=True,
        url="http://127.0.0.1:1",
    )
    assert result.status == "BLOCKED_BRIDGE_OFFLINE"
    assert result.question_path is not None
    assert result.question_path.exists()


def test_run_gate_invalid_trigger_returns_invalid_no_files(tmp_path: Path):
    g = GateInput(trigger="not_a_real_trigger", question="?", context={})
    result = run_gate(
        g,
        questions_dir=tmp_path / "q",
        responses_dir=tmp_path / "r",
        require_consult=False,
        url="http://127.0.0.1:1",
    )
    assert result.status == "invalid"
    assert result.question_path is None
    # No artefacts written for invalid input
    assert not (tmp_path / "q").exists() or not list((tmp_path / "q").iterdir())


# ---- run_gate online parsing (§6.4 wired) ---------------------------


def test_run_gate_online_parses_verdict(tmp_path: Path, monkeypatch):
    """§6.4 wired: when the bridge responds, run_gate parses the verdict so
    the asker can act on it programmatically — not just re-read prose."""
    import tools.ask_gpt_gate as gate
    raw = (
        "- Verdict: NO-GO\n"
        "- Confidence: high\n"
        "- Reasoning: the change mutates a canonical fixture.\n"
        "- Assumptions:\n"
        "  - the smoke suite pins this fixture\n"
        "- Risks:\n"
        "  - silent regression\n"
        "- Suggested next action: revert and branch\n"
    )
    monkeypatch.setattr(
        gate, "probe_bridge", lambda url=gate.BRIDGE_URL: (True, "ok"))
    monkeypatch.setattr(
        gate, "call_bridge", lambda prompt, url=gate.BRIDGE_URL: raw)
    g = GateInput(
        trigger="user_requested_consult", question="merge?", context={})
    result = run_gate(
        g, questions_dir=tmp_path / "q", responses_dir=tmp_path / "r")
    assert result.status == "ok"
    assert result.verdict == "NO-GO"
    assert result.confidence == "high"
    assert result.assumptions and any(
        "smoke suite" in a for a in result.assumptions)
    assert result.raw_response == raw
    body = result.response_path.read_text(encoding="utf-8")
    assert "Parsed verdict" in body
    assert "NO-GO" in body


# ---- repo structure --------------------------------------------------


def test_ai_bridge_questions_dir_documented():
    """The .ai_bridge/questions/ and responses/ dirs are expected to
    exist when the tool is dogfooded. Their presence in develop is
    evidence of the gate being used."""
    # Soft check — directories may not exist yet on a fresh clone
    # but the LL-024 spec documents them.
    spec = REPO_ROOT / "docs" / "specs" / "LL-024_gpt_auto_consult_gate.md"
    assert spec.exists()
    text = spec.read_text(encoding="utf-8")
    assert ".ai_bridge/questions/" in text
    assert ".ai_bridge/responses/" in text
