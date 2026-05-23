"""Tests for the runner-mode integration in
tools.build_plan_shell_skp.

These tests target the mode-resolution helpers + signature surface
of `run()`. They do NOT spawn SketchUp (the actual launch path is
exercised manually per `docs/adr/ADR-003-plan-shell-exporter.md`).

Per CLAUDE.md §18, LL-015, FP-023 — safe default is `interactive`;
`headless` is opt-in via CI env or explicit `--mode`/`RUN_MODE`.
"""
from __future__ import annotations

import inspect
from pathlib import Path

from tools import build_plan_shell_skp as bps

# ----------------------------------------------------------------
# _default_runner_mode: CI-aware safe default
# ----------------------------------------------------------------


class TestDefaultRunnerMode:
    """`_default_runner_mode` picks `headless` only when CI env set."""

    def test_no_env_returns_interactive(self, monkeypatch):
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        assert bps._default_runner_mode() == "interactive"

    def test_ci_true_returns_headless(self, monkeypatch):
        monkeypatch.setenv("CI", "true")
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        assert bps._default_runner_mode() == "headless"

    def test_ci_uppercase_true_also_headless(self, monkeypatch):
        monkeypatch.setenv("CI", "True")
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        assert bps._default_runner_mode() == "headless"

    def test_github_actions_true_returns_headless(self, monkeypatch):
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        assert bps._default_runner_mode() == "headless"

    def test_both_ci_envs_returns_headless(self, monkeypatch):
        monkeypatch.setenv("CI", "true")
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        assert bps._default_runner_mode() == "headless"

    def test_ci_false_returns_interactive(self, monkeypatch):
        monkeypatch.setenv("CI", "false")
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        assert bps._default_runner_mode() == "interactive"

    def test_ci_empty_string_returns_interactive(self, monkeypatch):
        monkeypatch.setenv("CI", "")
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        assert bps._default_runner_mode() == "interactive"


# ----------------------------------------------------------------
# run() signature: accepts a `mode` parameter
# ----------------------------------------------------------------


class TestRunSignature:
    """`run()` exposes `mode` parameter without breaking call sites."""

    def test_run_accepts_mode_parameter(self):
        sig = inspect.signature(bps.run)
        assert "mode" in sig.parameters
        # Must be optional (default None) so existing callers don't break
        assert sig.parameters["mode"].default is None

    def test_run_mode_param_is_keyword_only_compatible(self):
        sig = inspect.signature(bps.run)
        param = sig.parameters["mode"]
        assert param.kind in (
            inspect.Parameter.KEYWORD_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )


# ----------------------------------------------------------------
# Module-level wiring: imports the safety helper
# ----------------------------------------------------------------


def test_module_imports_su_runner_safety():
    """Sanity: the migration actually imported the helper."""
    src = Path(bps.__file__).read_text(encoding="utf-8")
    assert "from tools.su_runner_safety import" in src
    assert "parse_mode" in src
    assert "should_terminate" in src
    assert "log_mode" in src
