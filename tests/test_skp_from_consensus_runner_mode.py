"""Tests for the runner-mode integration in tools.skp_from_consensus.

These tests target the mode-resolution helpers + signature surface
of `run()`. They do NOT spawn SketchUp (the actual launch path is
exercised manually per
`docs/validation/sketchup_smoke_workflow.md`). The skip-cache path
of `run()` is exercised here to confirm that mode resolution is
not invoked on the cached short-circuit.

Per CLAUDE.md §18, LL-015, FP-023 — the safe default is
`interactive` (no terminate); `headless` is opt-in via CI env or
explicit `--mode`/`RUN_MODE`.
"""
from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from tools import skp_from_consensus as sfc

# ----------------------------------------------------------------
# _default_runner_mode: CI-aware safe default
# ----------------------------------------------------------------

class TestDefaultRunnerMode:
    """`_default_runner_mode` picks `headless` only when CI env set."""

    def test_no_env_returns_interactive(self, monkeypatch):
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        assert sfc._default_runner_mode() == "interactive"

    def test_ci_true_returns_headless(self, monkeypatch):
        monkeypatch.setenv("CI", "true")
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        assert sfc._default_runner_mode() == "headless"

    def test_ci_uppercase_true_also_headless(self, monkeypatch):
        # Some CI runners use uppercase. We lower() to compare.
        monkeypatch.setenv("CI", "True")
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        assert sfc._default_runner_mode() == "headless"

    def test_github_actions_true_returns_headless(self, monkeypatch):
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        assert sfc._default_runner_mode() == "headless"

    def test_both_ci_envs_returns_headless(self, monkeypatch):
        monkeypatch.setenv("CI", "true")
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        assert sfc._default_runner_mode() == "headless"

    def test_ci_false_returns_interactive(self, monkeypatch):
        # Some workflows set CI=false explicitly.
        monkeypatch.setenv("CI", "false")
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        assert sfc._default_runner_mode() == "interactive"

    def test_ci_empty_string_returns_interactive(self, monkeypatch):
        monkeypatch.setenv("CI", "")
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        assert sfc._default_runner_mode() == "interactive"


# ----------------------------------------------------------------
# run() signature: accepts a `mode` parameter
# ----------------------------------------------------------------

class TestRunSignature:
    """`run()` exposes `mode` parameter without breaking call sites."""

    def test_run_accepts_mode_parameter(self):
        sig = inspect.signature(sfc.run)
        assert "mode" in sig.parameters
        # Must be optional (default None) so existing callers don't break
        assert sig.parameters["mode"].default is None

    def test_run_mode_param_is_keyword_only_compatible(self):
        # Confirm `mode=` works (i.e. it's not POSITIONAL_ONLY)
        sig = inspect.signature(sfc.run)
        param = sig.parameters["mode"]
        assert param.kind in (
            inspect.Parameter.KEYWORD_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )


# ----------------------------------------------------------------
# Skip path: mode is irrelevant when cache hits
# ----------------------------------------------------------------

@pytest.fixture()
def fake_consensus(tmp_path: Path) -> Path:
    p = tmp_path / "consensus_model.json"
    p.write_text(json.dumps({"walls": [], "rooms": [], "openings": []}))
    return p


class TestRunSkipPathIgnoresMode:
    """The cache-hit short-circuit returns BEFORE mode is resolved."""

    def test_skip_works_with_default_mode(self, tmp_path, fake_consensus):
        skp = tmp_path / "model.skp"
        skp.write_bytes(b"placeholder")
        # Prime the sidecar so should_skip() returns True.
        sfc.write_metadata(
            skp,
            consensus_sha256=sfc._file_sha256(fake_consensus),
            sketchup_exe=Path("C:/fake/SU.exe"),
            command=["fake", "SU.exe"],
        )
        # No mode passed → run() must NOT spawn SU; returns skipped=True
        result = sfc.run(
            fake_consensus.resolve(),
            skp.resolve(),
            sketchup_exe=Path("C:/fake/SU.exe"),
        )
        assert result["skipped"] is True
        assert result["ok"] is True

    def test_skip_works_with_explicit_attach_mode(
        self, tmp_path, fake_consensus
    ):
        skp = tmp_path / "model.skp"
        skp.write_bytes(b"placeholder")
        sfc.write_metadata(
            skp,
            consensus_sha256=sfc._file_sha256(fake_consensus),
            sketchup_exe=Path("C:/fake/SU.exe"),
            command=["fake", "SU.exe"],
        )
        # attach mode would prohibit Popen — but skip happens first.
        result = sfc.run(
            fake_consensus.resolve(),
            skp.resolve(),
            sketchup_exe=Path("C:/fake/SU.exe"),
            mode="attach",
        )
        assert result["skipped"] is True
        assert result["ok"] is True


# ----------------------------------------------------------------
# Module-level wiring: imports the safety helper
# ----------------------------------------------------------------

def test_module_imports_su_runner_safety():
    """Sanity: the migration actually imported the helper."""
    src = Path(sfc.__file__).read_text(encoding="utf-8")
    assert "from tools.su_runner_safety import" in src
    assert "parse_mode" in src
    assert "should_terminate" in src
    assert "log_mode" in src
