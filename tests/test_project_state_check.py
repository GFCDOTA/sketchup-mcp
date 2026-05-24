"""Tests for scripts/project_state_check.py.

This is the regression test for the project state hygiene gate
(G-PROJECT-STATE in docs/GATES.md). The gate validates that the
canonical docs / fixtures / scripts listed in docs/PROJECT_STATE.md
all exist; this test validates the gate itself.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "project_state_check.py"


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )


def test_script_is_importable():
    """The script file exists and parses as Python."""
    spec = SCRIPT
    assert spec.is_file(), f"script missing at {spec}"
    # Importing through subprocess is cleaner than sys.path tricks.
    proc = _run(["--help"])
    assert proc.returncode == 0, proc.stderr
    assert "project_state_check" in (proc.stdout + proc.stderr).lower() or \
           "usage" in (proc.stdout + proc.stderr).lower()


def test_check_passes_on_current_repo():
    """The repo state should currently pass the gate (exit 0).

    If this test fails, the canonical docs / fixtures / scripts listed
    in the script's CANONICAL_* constants are missing or empty. Read the
    text output to see which.
    """
    proc = _run([])
    assert proc.returncode == 0, (
        f"project_state_check.py FAILED (exit {proc.returncode}).\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )


def test_json_output_is_valid():
    """--json produces a parseable JSON document with the expected shape."""
    proc = _run(["--json"])
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert set(payload.keys()) == {"ok", "summary", "checks"}
    assert payload["ok"] is True
    assert isinstance(payload["checks"], list)
    assert payload["checks"], "expected at least one check"
    for entry in payload["checks"]:
        assert set(entry.keys()) == {"id", "kind", "path", "status", "reason"}
        assert entry["status"] in {"PASS", "FAIL", "WARN"}


def test_strict_mode_promotes_warnings_to_failures(tmp_path: Path):
    """When --strict is on, any WARN becomes FAIL.

    The current repo MAY have soft warnings (e.g., test files that only
    live on a feature branch). --strict turns those into hard fails.
    This test does not assert that --strict fails — it asserts that IF
    there are warnings, --strict reports them as FAIL instead.
    """
    plain = _run(["--json"])
    plain_payload = json.loads(plain.stdout)
    strict = _run(["--strict", "--json"])
    strict_payload = json.loads(strict.stdout)

    plain_warn_paths = {
        c["path"] for c in plain_payload["checks"] if c["status"] == "WARN"
    }
    strict_warn_paths = {
        c["path"] for c in strict_payload["checks"] if c["status"] == "WARN"
    }
    strict_fail_paths = {
        c["path"] for c in strict_payload["checks"] if c["status"] == "FAIL"
    }

    # No WARN remains in strict mode.
    assert not strict_warn_paths, (
        f"--strict should not leave any WARN, found {strict_warn_paths}"
    )
    # Every plain WARN becomes FAIL under strict.
    assert plain_warn_paths.issubset(
        strict_fail_paths | {p for p in plain_warn_paths if p not in plain_warn_paths}
    ), f"plain WARN paths missing from strict FAILs: {plain_warn_paths - strict_fail_paths}"


def test_canonical_docs_carry_status_header():
    """Every doc the policy says MUST have a Status: header has one.

    Mirrors docs/REPO_HYGIENE.md §2.
    """
    required = [
        "docs/PROJECT_STATE.md",
        "docs/HANDOFF.md",
        "docs/REPO_HYGIENE.md",
        "docs/GATES.md",
        "docs/ANTI_FORGETTING.md",
    ]
    missing: list[str] = []
    for rel in required:
        p = REPO_ROOT / rel
        assert p.is_file(), f"canonical doc missing: {rel}"
        head = "".join(
            p.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)[:30]
        )
        if "Status:" not in head:
            missing.append(rel)
    assert not missing, (
        f"docs missing Status: header (see docs/REPO_HYGIENE.md §2): {missing}"
    )
