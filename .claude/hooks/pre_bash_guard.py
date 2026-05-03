"""PreToolUse hook for the Bash tool — block destructive or
policy-violating commands before they execute.

Reads JSON from stdin (the tool input + context provided by Claude
Code), writes JSON to stdout to allow/deny the call.

Output schema:
- exit code 0 + empty stdout → allow
- exit code 0 + JSON {"hook_specific_output": {"hookEventName":
  "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason":
  "..."}} → block with explanation
- non-zero exit → fail closed (treated as block by Claude Code)

This file is the "electric fence" referenced in CLAUDE.md §9.
Update the rule lists carefully — broaden them, don't relax them.

Manual test:
    echo '{"tool_input": {"command": "git push origin main"}}' \
        | python .claude/hooks/pre_bash_guard.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import Iterable


@dataclass
class Rule:
    """A single guard rule. If `pattern` matches the command, block
    with `reason`. `applies_to_branch` (optional callable) further
    constrains when the rule fires (e.g. only when on main/develop)."""
    pattern: re.Pattern[str]
    reason: str
    applies_to_branch: object = None  # callable(branch) -> bool, or None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _current_branch() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return "unknown"


def _on_protected_branch(branch: str) -> bool:
    return branch in {"main", "develop", "master"}


# ---------------------------------------------------------------------------
# Rule list (update with care; broaden, don't relax)
# ---------------------------------------------------------------------------

RULES: list[Rule] = [
    # --- Direct push to main ---
    Rule(
        pattern=re.compile(r"\bgit\s+push\b[^|;&]*\b(origin|upstream)?\s*\bmain\b"),
        reason=(
            "Blocked: direct push to main is forbidden by CLAUDE.md §0. "
            "Open a PR from develop to main instead."
        ),
    ),
    Rule(
        pattern=re.compile(r"\bgit\s+push\b[^|;&]*\bmain:main\b"),
        reason=(
            "Blocked: direct push to main is forbidden by CLAUDE.md §0. "
            "Open a PR from develop to main instead."
        ),
    ),

    # --- Force push to main or develop ---
    Rule(
        pattern=re.compile(
            r"\bgit\s+push\b[^|;&]*--force\b[^|;&]*\b(origin|upstream)?\s*\b(main|develop|master)\b"
        ),
        reason=(
            "Blocked: force-pushing main/develop is forbidden by CLAUDE.md §0. "
            "If history rewrite is truly needed, get explicit user authorization."
        ),
    ),
    Rule(
        pattern=re.compile(
            r"\bgit\s+push\b[^|;&]*-f\b[^|;&]*\b(origin|upstream)?\s*\b(main|develop|master)\b"
        ),
        reason="Blocked: force-pushing main/develop is forbidden (CLAUDE.md §0).",
    ),

    # --- Direct commit while on main/develop ---
    Rule(
        pattern=re.compile(r"\bgit\s+commit\b"),
        reason=(
            "Blocked: direct commit on main/develop is forbidden by CLAUDE.md §0. "
            "Switch to a feature/fix/chore branch first: "
            "`git checkout -b <prefix>/<slug>`."
        ),
        applies_to_branch=_on_protected_branch,
    ),

    # --- Destructive removal of historical artifact dirs ---
    Rule(
        # Require delimiter after the dir name (slash, space, quote, end)
        # so `rm -rf runs.bak` doesn't false-positive on `runs`.
        pattern=re.compile(
            r"\brm\s+-[rRf]+[^|;&]*\b(?:runs|patches|docs|vendor)(?=/|\s|$|['\"])"
        ),
        reason=(
            "Blocked: deleting runs/, patches/, docs/, or vendor/ requires "
            "explicit user approval (CLAUDE.md §1 hard rule #1). "
            "Use `git rm` on specific files within a PR instead."
        ),
    ),
    Rule(
        pattern=re.compile(
            r"\bRemove-Item\b[^|;&]*-Recurse[^|;&]*\b(?:runs|patches|docs|vendor)(?=/|\s|$|['\"])",
            re.IGNORECASE,
        ),
        reason=(
            "Blocked: deleting runs/, patches/, docs/, or vendor/ requires "
            "explicit user approval (CLAUDE.md §1 hard rule #1)."
        ),
    ),

    # --- Repo-wide ruff fix / format (banned per CLAUDE.md §1 rules 7-8) ---
    Rule(
        pattern=re.compile(r"\bruff\s+(check\s+)?[^|;&]*--fix\b[^|;&]*(\s\.|\s\*|$)"),
        reason=(
            "Blocked: `ruff --fix` over the whole repo is forbidden by "
            "CLAUDE.md §1 rule #7. Cleanup is done in dedicated, scoped PRs."
        ),
    ),
    Rule(
        pattern=re.compile(r"\bruff\s+format\b"),
        reason=(
            "Blocked: `ruff format` is forbidden by CLAUDE.md §1 rule #8. "
            "No mass autoformat."
        ),
    ),

    # --- Don't push --no-verify ---
    Rule(
        pattern=re.compile(r"\bgit\s+(commit|push)\b[^|;&]*--no-verify\b"),
        reason=(
            "Blocked: --no-verify is forbidden without explicit authorization "
            "(CLAUDE.md §0). Hooks exist for a reason; investigate the failure."
        ),
    ),

    # --- Don't tamper with patches/archive ---
    Rule(
        pattern=re.compile(r"\b(rm|mv)\s+[^|;&]*\bpatches/archive/"),
        reason=(
            "Blocked: patches/archive/ contains HIGH-risk patches under "
            "review embargo (CLAUDE.md §11). No deletes or moves without "
            "an explicit, signed-off PR plan."
        ),
    ),
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def evaluate(command: str, branch: str) -> str | None:
    """Return reason to deny, or None to allow."""
    if not command:
        return None
    for rule in RULES:
        if rule.applies_to_branch is not None and not rule.applies_to_branch(branch):
            continue
        if rule.pattern.search(command):
            return rule.reason
    return None


def emit_deny(reason: str) -> None:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
    json.dump(payload, sys.stdout)
    sys.stdout.write("\n")


def main(argv: list[str] | None = None) -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        return 0  # nothing to evaluate, allow

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        # Don't fail Claude Code over malformed input; allow but log.
        sys.stderr.write(f"[pre_bash_guard] could not parse stdin: {raw[:200]}\n")
        return 0

    tool_input = payload.get("tool_input") or {}
    command = tool_input.get("command", "")
    branch = _current_branch()

    reason = evaluate(command, branch)
    if reason:
        emit_deny(reason)
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
