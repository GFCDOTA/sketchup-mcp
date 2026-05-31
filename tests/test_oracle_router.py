"""Gate framework §6.1 — multi-oracle routing (pure, no I/O)."""
from __future__ import annotations

from tools.oracle_router import is_independent, route


def test_technical_decision_routes_to_claude():
    assert route(question_type="technical A/B/C") == "claude"
    assert route() == "claude"


def test_objective_question_routes_to_deterministic():
    # ground truth wins over any oracle
    assert route(question_type="factual check: do walls match the PDF?") == "deterministic"
    assert route(question_type="verify opening_host") == "deterministic"


def test_risky_decision_routes_to_non_claude_for_independence():
    pick = route(risk="high", asker_family="claude")
    assert pick != "claude"
    assert is_independent(pick, "claude")


def test_explicit_independent_ask_routes_non_claude():
    pick = route(question_type="want an independent second opinion", asker_family="claude")
    assert pick in ("chatgpt", "local")
    assert is_independent(pick, "claude")


def test_independent_with_only_local_available():
    assert route(risk="high", asker_family="claude", available={"claude", "local"}) == "local"


def test_graceful_fallback_when_no_independent_available():
    # only claude available -> falls back to claude, and caller can see it is NOT independent
    pick = route(risk="high", asker_family="claude", available={"claude"})
    assert pick == "claude"
    assert is_independent(pick, "claude") is False


def test_deterministic_fallback_when_absent():
    # factual but no deterministic provider available -> falls back, never raises
    assert route(question_type="factual", available={"claude"}) == "claude"


def test_is_independent_semantics():
    assert is_independent("local", "claude") is True
    assert is_independent("chatgpt", "claude") is True
    assert is_independent("claude", "claude") is False
    assert is_independent("deterministic", "claude") is False   # not an llm
    assert is_independent("nope", "claude") is False
