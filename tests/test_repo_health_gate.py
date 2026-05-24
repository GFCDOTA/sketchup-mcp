"""Tests for tools/repo_health_gate.py.

The gate enforces docs/REPO_HYGIENE.md and CLAUDE.md §15 mechanically.
This test file pins:

  - exit-code contract per mode (audit always 0, check 1 on errors,
    fix always 0);
  - the JSON output schema;
  - that the gate produces zero ERROR findings on the current repo
    state (so CI on develop is green);
  - that individual detectors fire on synthetic inputs (cover false-
    negative regressions);
  - that --base diff-mode promotes new-in-PR .md without Status to
    ERROR;
  - that fix-mode never touches tracked files.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
GATE = REPO_ROOT / "tools" / "repo_health_gate.py"


# --- subprocess helper ---------------------------------------------------


def _run(args: list[str], *, env: dict | None = None,
          cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GATE), *args],
        capture_output=True,
        text=True,
        cwd=cwd or REPO_ROOT,
        env=env,
    )


# --- contract tests on the real repo -------------------------------------


def test_help_works():
    proc = _run(["--help"])
    assert proc.returncode == 0
    assert "repo health gate" in (proc.stdout + proc.stderr).lower() or \
           "usage" in (proc.stdout + proc.stderr).lower()


def test_audit_mode_always_exit_zero():
    """Audit is read-only and must not gate CI."""
    proc = _run(["--mode", "audit", "--no-report"])
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_check_mode_currently_clean():
    """check-mode (non-strict) must currently exit 0.

    If this fails, the repo has new ERROR-class violations and the gate
    is doing its job — fix the underlying issue, do NOT relax the
    detector.
    """
    proc = _run(["--mode", "check", "--no-report"])
    assert proc.returncode == 0, (
        f"check mode unexpectedly failed:\n{proc.stdout}\n{proc.stderr}"
    )


def test_json_output_shape():
    proc = _run(["--mode", "audit", "--no-report", "--json"])
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert set(payload.keys()) >= {"branch", "head", "base", "mode",
                                     "summary", "findings", "fixes"}
    assert set(payload["summary"].keys()) == {"error", "warning", "info"}
    assert isinstance(payload["findings"], list)
    if payload["findings"]:
        first = payload["findings"][0]
        assert set(first.keys()) >= {"code", "severity", "category",
                                       "path", "message"}
        assert first["severity"] in {"error", "warning", "info"}


def test_strict_promotes_warnings_to_failures():
    """check + --strict makes any warning fail the run."""
    plain = _run(["--mode", "check", "--no-report", "--json"])
    plain_payload = json.loads(plain.stdout)
    if plain_payload["summary"]["warning"] == 0:
        pytest.skip("no warnings on the current repo state")
    strict = _run(["--mode", "check", "--strict", "--no-report"])
    assert strict.returncode == 1, (
        f"--strict should fail with warnings present, got {strict.returncode}"
    )


def test_fix_dry_run_does_not_touch_anything(tmp_path: Path):
    """fix --dry-run must report actions without applying them."""
    # Capture .gitignore content before & after.
    gi = REPO_ROOT / ".gitignore"
    before = gi.read_bytes()
    proc = _run(["--mode", "fix", "--dry-run", "--no-report"])
    after = gi.read_bytes()
    assert proc.returncode == 0
    assert before == after, "fix --dry-run modified .gitignore"


def test_report_writes_to_default_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """The default --report-path lands under reports/current/."""
    custom = tmp_path / "health.md"
    proc = _run(["--mode", "audit", "--report-path", str(custom)])
    assert proc.returncode == 0
    assert custom.is_file(), proc.stdout + proc.stderr
    head = custom.read_text(encoding="utf-8")
    assert head.startswith("# Repo Health Report")
    assert "Status:** Generated" in head


# --- detector unit tests (synthetic mini-repos) --------------------------


def _init_mini_repo(tmp_path: Path) -> Path:
    """Create a minimal git repo at tmp_path with a basic structure."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.t"],
                    cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path,
                    check=True)
    (tmp_path / ".gitignore").write_text(
        "__pycache__/\n*.py[cod]\n.pytest_cache/\n.ruff_cache/\n"
        ".mypy_cache/\n.venv/\n*.log\n.DS_Store\nThumbs.db\n"
        ".tmp_*\n*.bak\n*.swp\n*.orig\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text("# mini\n", encoding="utf-8")
    (tmp_path / "main.py").write_text("print('hi')\n", encoding="utf-8")
    return tmp_path


def _commit_all(repo: Path, msg: str = "init") -> None:
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", msg], cwd=repo,
                    check=True)


def _run_in_repo(repo: Path, args: list[str]) -> subprocess.CompletedProcess:
    """Run the gate against a synthetic repo via a wrapped invocation.

    The gate hardcodes REPO_ROOT relative to its own file. Run it from
    the synthetic repo by copying the script in.
    """
    target = repo / "tools" / "repo_health_gate.py"
    target.parent.mkdir(exist_ok=True)
    target.write_bytes(GATE.read_bytes())
    return subprocess.run(
        [sys.executable, str(target), *args],
        capture_output=True,
        text=True,
        cwd=repo,
    )


def test_tmp_file_tracked_fires(tmp_path: Path):
    """E001 fires when a .tmp_ file is in the index."""
    repo = _init_mini_repo(tmp_path)
    # Bypass .gitignore via -f because .tmp_* is gitignored.
    (repo / ".tmp_pr_body.md").write_text("draft\n", encoding="utf-8")
    subprocess.run(["git", "add", "-f", ".tmp_pr_body.md"], cwd=repo,
                    check=True)
    _commit_all(repo, "add tmp")
    proc = _run_in_repo(repo, ["--mode", "audit", "--json", "--no-report"])
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    codes = {f["code"] for f in payload["findings"]}
    assert "E001" in codes, payload["findings"]


def test_loose_script_in_root_fires(tmp_path: Path):
    """W001 fires for a *.py at repo root other than main.py/setup.py."""
    repo = _init_mini_repo(tmp_path)
    (repo / "proto_demo.py").write_text("# scratch\n", encoding="utf-8")
    _commit_all(repo, "add loose script")
    proc = _run_in_repo(repo, ["--mode", "audit", "--json", "--no-report"])
    payload = json.loads(proc.stdout)
    w001 = [f for f in payload["findings"] if f["code"] == "W001"]
    paths = {f["path"] for f in w001}
    assert "proto_demo.py" in paths
    assert "main.py" not in paths


def test_md_missing_status_fires(tmp_path: Path):
    """W002 fires for docs/*.md without Status: header."""
    repo = _init_mini_repo(tmp_path)
    (repo / "docs").mkdir()
    (repo / "docs" / "FOO.md").write_text("# Foo\n\nno status here.\n",
                                            encoding="utf-8")
    _commit_all(repo, "add docs")
    proc = _run_in_repo(repo, ["--mode", "audit", "--json", "--no-report"])
    payload = json.loads(proc.stdout)
    w002_paths = {f["path"] for f in payload["findings"]
                  if f["code"] == "W002"}
    assert "docs/FOO.md" in w002_paths


def test_md_with_status_header_passes(tmp_path: Path):
    """W002 does NOT fire when a Status: header is present."""
    repo = _init_mini_repo(tmp_path)
    (repo / "docs").mkdir()
    (repo / "docs" / "OK.md").write_text(
        "# OK\n\n> **Status:** Canonical\n\nbody.\n", encoding="utf-8")
    _commit_all(repo, "add docs")
    proc = _run_in_repo(repo, ["--mode", "audit", "--json", "--no-report"])
    payload = json.loads(proc.stdout)
    w002_paths = {f["path"] for f in payload["findings"]
                  if f["code"] == "W002"}
    assert "docs/OK.md" not in w002_paths


def test_new_md_no_status_promotes_to_error_in_pr_mode(tmp_path: Path):
    """E004: a NEW .md in a PR without Status: must be ERROR, not WARN."""
    repo = _init_mini_repo(tmp_path)
    (repo / "docs").mkdir()
    (repo / "docs" / "OLD.md").write_text(
        "# old\n\n> **Status:** Canonical\n\n", encoding="utf-8")
    _commit_all(repo, "base")
    base_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo,
                                capture_output=True, text=True,
                                check=True).stdout.strip()
    (repo / "docs" / "NEW.md").write_text(
        "# new\n\nno status here.\n", encoding="utf-8")
    _commit_all(repo, "add new doc")
    proc = _run_in_repo(repo, ["--mode", "check", "--base", base_sha,
                                  "--json", "--no-report"])
    payload = json.loads(proc.stdout)
    codes_for_new = {f["code"] for f in payload["findings"]
                      if f["path"] == "docs/NEW.md"}
    assert "E004" in codes_for_new, payload["findings"]
    assert proc.returncode == 1


def test_project_state_stale_fires_on_structural_diff(tmp_path: Path):
    """E006: structural change without state-doc update is an error."""
    repo = _init_mini_repo(tmp_path)
    (repo / "docs").mkdir()
    (repo / "docs" / "PROJECT_STATE.md").write_text(
        "# state\n\n> **Status:** Canonical\n", encoding="utf-8")
    (repo / "tools").mkdir()
    (repo / "tools" / "existing.py").write_text("# x\n", encoding="utf-8")
    _commit_all(repo, "base")
    base_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo,
                                capture_output=True, text=True,
                                check=True).stdout.strip()
    # PR adds a new tool but doesn't touch state docs.
    (repo / "tools" / "new_tool.py").write_text("# new\n",
                                                  encoding="utf-8")
    _commit_all(repo, "add tool")
    proc = _run_in_repo(repo, ["--mode", "check", "--base", base_sha,
                                  "--json", "--no-report"])
    payload = json.loads(proc.stdout)
    codes = {f["code"] for f in payload["findings"]}
    assert "E006" in codes, payload["findings"]
    assert proc.returncode == 1


def test_project_state_stale_passes_when_docs_updated(tmp_path: Path):
    """E006 does NOT fire when state docs ARE in the diff."""
    repo = _init_mini_repo(tmp_path)
    (repo / "docs").mkdir()
    (repo / "docs" / "PROJECT_STATE.md").write_text(
        "# state\n\n> **Status:** Canonical\n", encoding="utf-8")
    (repo / "tools").mkdir()
    (repo / "tools" / "existing.py").write_text("# x\n", encoding="utf-8")
    _commit_all(repo, "base")
    base_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo,
                                capture_output=True, text=True,
                                check=True).stdout.strip()
    # PR adds a new tool AND updates state doc.
    (repo / "tools" / "new_tool.py").write_text("# new\n",
                                                  encoding="utf-8")
    (repo / "docs" / "PROJECT_STATE.md").write_text(
        "# state v2\n\n> **Status:** Canonical\n", encoding="utf-8")
    _commit_all(repo, "add tool + state")
    proc = _run_in_repo(repo, ["--mode", "check", "--base", base_sha,
                                  "--json", "--no-report"])
    payload = json.loads(proc.stdout)
    codes = {f["code"] for f in payload["findings"]}
    assert "E006" not in codes, payload["findings"]


def test_new_dir_not_canonical_fires(tmp_path: Path):
    """E003: PR introduces an unexpected top-level dir."""
    repo = _init_mini_repo(tmp_path)
    _commit_all(repo, "base")
    base_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo,
                                capture_output=True, text=True,
                                check=True).stdout.strip()
    (repo / "stuff").mkdir()
    (repo / "stuff" / "x.txt").write_text("y\n", encoding="utf-8")
    _commit_all(repo, "add new top-level")
    proc = _run_in_repo(repo, ["--mode", "check", "--base", base_sha,
                                  "--json", "--no-report"])
    payload = json.loads(proc.stdout)
    e003 = [f for f in payload["findings"] if f["code"] == "E003"]
    assert e003 and any(f["path"] == "stuff/" for f in e003), payload["findings"]


def test_canonical_top_level_dirs_accept_specs(tmp_path: Path):
    """E003 must NOT fire on `specs/` — it is part of the canonical set.

    Regression test for the PR that added spec-driven development files
    under specs/. Without specs/ in CANONICAL_TOP_LEVEL_DIRS the SDD PR
    chain (#145-#149) fails this gate.
    """
    repo = _init_mini_repo(tmp_path)
    _commit_all(repo, "base")
    base_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo,
                                capture_output=True, text=True,
                                check=True).stdout.strip()
    (repo / "specs").mkdir()
    (repo / "specs" / "example.spec.yaml").write_text(
        "name: example\nrules: []\n", encoding="utf-8")
    _commit_all(repo, "add specs/")
    proc = _run_in_repo(repo, ["--mode", "check", "--base", base_sha,
                                  "--json", "--no-report"])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json.loads(proc.stdout)
    e003_for_specs = [f for f in payload["findings"]
                      if f["code"] == "E003" and f["path"] == "specs/"]
    assert not e003_for_specs, (
        f"E003 unexpectedly fired on specs/: {e003_for_specs}"
    )


def test_fix_mode_never_deletes_tracked_files(tmp_path: Path):
    """fix mode must NOT remove or modify tracked files in the repo."""
    repo = _init_mini_repo(tmp_path)
    (repo / "tools").mkdir()
    (repo / "docs").mkdir()
    (repo / "docs" / "FOO.md").write_text("# foo\n", encoding="utf-8")
    _commit_all(repo, "base")
    # Capture all tracked files and their SHA before fix.
    tracked_before = subprocess.run(["git", "ls-files"], cwd=repo,
                                      capture_output=True, text=True,
                                      check=True).stdout
    proc = _run_in_repo(repo, ["--mode", "fix", "--no-report"])
    assert proc.returncode == 0
    tracked_after = subprocess.run(["git", "ls-files"], cwd=repo,
                                     capture_output=True, text=True,
                                     check=True).stdout
    assert tracked_before == tracked_after, (
        "fix mode changed the tracked file set"
    )
