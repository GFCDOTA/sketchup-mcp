"""Unit tests for tools/su_runner_safety.py.

Enforces the SU runner mode protocol per CLAUDE.md §18.6, LL-015,
FP-019. Safe default is `interactive` (no termination) so any
concurrent human SU session is protected.
"""
from __future__ import annotations

import pytest

from tools.su_runner_safety import (
    MODES,
    HEADLESS_MODES,
    INTERACTIVE_MODES,
    ATTACH_MODES,
    parse_mode,
    should_terminate,
    is_attach,
)


class TestParseMode:
    """`parse_mode` resolves the runtime mode from CLI/env/default."""

    def test_default_is_interactive(self):
        """No --mode, no --no-terminate, no RUN_MODE → interactive.

        Safe-default contract: protect human session by default.
        """
        assert parse_mode(argv=[], env={}) == "interactive"

    def test_no_terminate_flag_forces_interactive(self):
        assert parse_mode(argv=["--no-terminate"], env={}) == "interactive"

    def test_no_terminate_overrides_mode_flag(self):
        """--no-terminate wins even if --mode headless is given."""
        result = parse_mode(
            argv=["--mode", "headless", "--no-terminate"], env={}
        )
        assert result == "interactive"

    def test_mode_cli_takes_precedence_over_env(self):
        assert parse_mode(
            argv=["--mode", "headless"], env={"RUN_MODE": "interactive"}
        ) == "headless"

    @pytest.mark.parametrize("mode", list(MODES))
    def test_each_mode_resolves(self, mode: str):
        assert parse_mode(argv=["--mode", mode], env={}) == mode

    @pytest.mark.parametrize("mode", list(MODES))
    def test_each_mode_via_env(self, mode: str):
        assert parse_mode(argv=[], env={"RUN_MODE": mode}) == mode

    def test_unknown_mode_falls_back_to_default(self, capsys):
        result = parse_mode(argv=["--mode", "garbage"], env={})
        assert result == "interactive"
        err = capsys.readouterr().err
        assert "garbage" in err
        assert "interactive" in err

    def test_unknown_env_mode_falls_back_to_default(self, capsys):
        result = parse_mode(argv=[], env={"RUN_MODE": "garbage"})
        assert result == "interactive"
        err = capsys.readouterr().err
        assert "garbage" in err

    def test_default_argument_overrides_safe_default(self):
        """Caller can override the fallback for niche cases."""
        result = parse_mode(argv=[], env={}, default="headless")
        assert result == "headless"


class TestShouldTerminate:
    """`should_terminate` answers: may we kill the child SU process?"""

    @pytest.mark.parametrize("mode", sorted(HEADLESS_MODES))
    def test_headless_modes_may_terminate(self, mode: str):
        assert should_terminate(mode) is True

    @pytest.mark.parametrize("mode", sorted(INTERACTIVE_MODES))
    def test_interactive_modes_must_not_terminate(self, mode: str):
        assert should_terminate(mode) is False

    @pytest.mark.parametrize("mode", sorted(ATTACH_MODES))
    def test_attach_modes_must_not_terminate(self, mode: str):
        assert should_terminate(mode) is False

    def test_unknown_mode_does_not_terminate(self):
        """Defensive: an unrecognized mode must NOT terminate."""
        assert should_terminate("not-a-real-mode") is False


class TestIsAttach:
    @pytest.mark.parametrize("mode", sorted(ATTACH_MODES))
    def test_attach_modes_are_attach(self, mode: str):
        assert is_attach(mode) is True

    @pytest.mark.parametrize(
        "mode", sorted(HEADLESS_MODES | INTERACTIVE_MODES)
    )
    def test_non_attach_modes_are_not_attach(self, mode: str):
        assert is_attach(mode) is False


class TestProtocolInvariants:
    """Cross-mode invariants codified by the protocol."""

    def test_mode_sets_are_disjoint(self):
        assert HEADLESS_MODES.isdisjoint(INTERACTIVE_MODES)
        assert HEADLESS_MODES.isdisjoint(ATTACH_MODES)
        assert INTERACTIVE_MODES.isdisjoint(ATTACH_MODES)

    def test_all_mode_aliases_covered(self):
        union = HEADLESS_MODES | INTERACTIVE_MODES | ATTACH_MODES
        assert union == set(MODES)

    def test_safe_default_is_non_destructive(self):
        """The safe default MUST be a mode that does not terminate."""
        default_mode = parse_mode(argv=[], env={})
        assert should_terminate(default_mode) is False
