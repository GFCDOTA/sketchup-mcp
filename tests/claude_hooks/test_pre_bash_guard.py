"""Smoke tests for `.claude/hooks/pre_bash_guard.py`.

Tests the rule engine without actually invoking Claude Code's hook
machinery — we just import `evaluate()` and check verdict per command.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK_PATH = REPO_ROOT / ".claude" / "hooks" / "pre_bash_guard.py"


def _load_hook_module():
    """Load .claude/hooks/pre_bash_guard.py as a module."""
    spec = importlib.util.spec_from_file_location("pre_bash_guard", HOOK_PATH)
    mod = importlib.util.module_from_spec(spec)
    # Register in sys.modules so @dataclass can introspect it
    sys.modules["pre_bash_guard"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def hook():
    return _load_hook_module()


# ---------------------------------------------------------------------------
# Commands that MUST be blocked
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("command", [
    "git push origin main",
    "git push -u origin main",
    "git push   origin   main",
    "git push origin main:main",
])
def test_blocks_direct_push_to_main(hook, command):
    reason = hook.evaluate(command, branch="some-feature-branch")
    assert reason is not None, f"should block: {command!r}"
    assert "main" in reason.lower() or "develop" in reason.lower()


@pytest.mark.parametrize("command,branch", [
    ("git push --force origin main", "feature/x"),
    ("git push --force origin develop", "feature/x"),
    ("git push -f origin main", "feature/x"),
    ("git push -f origin develop", "feature/x"),
])
def test_blocks_force_push_to_protected(hook, command, branch):
    reason = hook.evaluate(command, branch=branch)
    assert reason is not None, f"should block: {command!r}"


@pytest.mark.parametrize("branch", ["main", "develop", "master"])
def test_blocks_commit_on_protected_branch(hook, branch):
    reason = hook.evaluate('git commit -m "fix something"', branch=branch)
    assert reason is not None, f"should block commit on {branch}"


@pytest.mark.parametrize("command", [
    "rm -rf runs",
    "rm -rf runs/",
    "rm -rf docs",
    "rm -rf patches/",
    "rm -rf vendor/",
])
def test_blocks_rm_protected_dirs(hook, command):
    reason = hook.evaluate(command, branch="feature/x")
    assert reason is not None, f"should block: {command!r}"


@pytest.mark.parametrize("command", [
    "Remove-Item -Recurse runs",
    "Remove-Item -Recurse patches",
    "remove-item -recurse docs",
])
def test_blocks_powershell_rm_protected(hook, command):
    reason = hook.evaluate(command, branch="feature/x")
    assert reason is not None, f"should block: {command!r}"


@pytest.mark.parametrize("command", [
    "ruff check . --fix",
    "ruff --fix .",
    "ruff format",
    "ruff format .",
])
def test_blocks_ruff_repo_wide_autofix(hook, command):
    reason = hook.evaluate(command, branch="feature/x")
    assert reason is not None, f"should block: {command!r}"


def test_blocks_no_verify_commit(hook):
    reason = hook.evaluate('git commit --no-verify -m "x"', branch="feature/x")
    assert reason is not None


def test_blocks_no_verify_push(hook):
    reason = hook.evaluate("git push --no-verify", branch="feature/x")
    assert reason is not None


def test_blocks_archive_patches_delete(hook):
    reason = hook.evaluate("rm patches/archive/07-reconnect-fragments-FIXED.py",
                           branch="feature/x")
    assert reason is not None


# ---------------------------------------------------------------------------
# Commands that MUST be allowed
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("command,branch", [
    ("git status", "feature/x"),
    ("git status -s", "feature/x"),
    ("git pull origin develop", "feature/x"),
    ("git push origin feature/foo", "feature/foo"),
    ("git push -u origin chore/repo-cleanup", "chore/repo-cleanup"),
    ("git checkout -b feature/new", "develop"),
    ("git commit -m 'x'", "feature/x"),  # not on main/develop, allowed
    ("pytest -q", "feature/x"),
    ("pytest -q --tb=short", "feature/x"),
    ("python -m ruff check .", "feature/x"),  # check only, no --fix
    ("ruff check . --statistics", "feature/x"),
    ("ruff check . --output-format=concise", "feature/x"),
    ("rm -rf /tmp/foo", "feature/x"),  # /tmp not protected
    ("rm -rf runs.bak", "feature/x"),  # not "runs" exactly
    ("ls runs/", "feature/x"),
    ("git log --oneline -5", "feature/x"),
])
def test_allows_safe_commands(hook, command, branch):
    reason = hook.evaluate(command, branch=branch)
    assert reason is None, f"should allow but blocked with: {reason!r} — {command!r}"


def test_allows_empty_command(hook):
    assert hook.evaluate("", branch="feature/x") is None
