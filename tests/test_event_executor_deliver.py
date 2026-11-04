"""FP-057/P8 (#589): a ENTREGA e do executor, nao do LLM — guards, ruff/pytest, commit e push so para a branch do PR (git real)."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tools.orchestration import event_executor as ex
from tools.orchestration import execution_guards as g

ITEM = {"event_id": "review:777:5:abc", "pr": 5, "issue": 589}
OK = lambda py, wt, files: (True, "")  # noqa: E731
BAD = lambda py, wt, files: (False, "pytest rc=1")  # noqa: E731


def sh(cwd: Path, *a: str) -> str:
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, check=True, encoding="utf-8").stdout.strip()


@pytest.fixture()
def repo(tmp_path):
    remote = tmp_path / "remote.git"
    sh(tmp_path, "init", "-q", "--bare", str(remote))
    wt = tmp_path / "wt"
    sh(tmp_path, "clone", "-q", str(remote), str(wt))
    for k, v in (("user.email", "t@t"), ("user.name", "t")):
        sh(wt, "config", k, v)
    (wt / "tests").mkdir()
    (wt / "tests" / "test_a.py").write_text("def test_a():\n    assert True\n", encoding="utf-8")
    sh(wt, "add", "-A")
    sh(wt, "commit", "-qm", "base")
    sh(wt, "push", "-q", "origin", "HEAD:feat/x")
    return wt, remote, sh(wt, "rev-parse", "HEAD")


def test_pending_edit_is_committed_and_pushed_by_the_executor_only_to_the_pr_branch(repo):
    wt, remote, base = repo
    (wt / "tests" / "test_a.py").write_text("def test_a():\n    assert 1 == 1\n", encoding="utf-8")
    action, msg = ex.deliver(wt, "feat/x", base, "py", ITEM, check=OK, cfg=g.load_config())
    assert action == "PUSHED", msg
    assert sh(remote, "rev-parse", "feat/x") == sh(wt, "rev-parse", "HEAD") != base
    assert "Refs #589" in sh(wt, "log", "-1", "--format=%s")


def test_no_change_is_a_noop_and_pushes_nothing(repo):
    wt, remote, base = repo
    assert ex.deliver(wt, "feat/x", base, "py", ITEM, check=OK, cfg=g.load_config())[0] == "NOOP"
    assert sh(remote, "rev-parse", "feat/x") == base


def test_critical_path_blocks_before_any_commit_or_push(repo):
    wt, remote, base = repo
    (wt / ".github" / "workflows").mkdir(parents=True)
    (wt / ".github" / "workflows" / "ci.yml").write_text("x: 1\n", encoding="utf-8")
    action, msg = ex.deliver(wt, "feat/x", base, "py", ITEM, check=OK, cfg=g.load_config())
    assert action == "BLOCKED_GUARDS" and "path_critico" in msg
    assert sh(wt, "rev-parse", "HEAD") == base and sh(remote, "rev-parse", "feat/x") == base


def test_diff_over_the_ceiling_blocks(repo):
    wt, remote, base = repo
    (wt / "tests" / "big.txt").write_text("l\n" * 400, encoding="utf-8")
    assert ex.deliver(wt, "feat/x", base, "py", ITEM, check=OK, cfg=g.load_config())[0] == "BLOCKED_GUARDS"
    assert sh(remote, "rev-parse", "feat/x") == base


def test_failing_checks_block_the_push(repo):
    wt, remote, base = repo
    (wt / "tests" / "test_a.py").write_text("def test_a():\n    assert False\n", encoding="utf-8")
    action, msg = ex.deliver(wt, "feat/x", base, "py", ITEM, check=BAD, cfg=g.load_config())
    assert action == "FAILED_CHECKS" and "pytest" in msg and sh(remote, "rev-parse", "feat/x") == base


def test_a_local_commit_made_by_the_llm_is_verified_and_pushed_too(repo):
    wt, remote, base = repo
    (wt / "tests" / "test_a.py").write_text("def test_a():\n    assert 2 == 2\n", encoding="utf-8")
    sh(wt, "commit", "-aqm", "fix: llm")
    assert ex.deliver(wt, "feat/x", base, "py", ITEM, check=OK, cfg=g.load_config())[0] == "PUSHED"
    assert sh(remote, "rev-parse", "feat/x") == sh(wt, "rev-parse", "HEAD")


def test_run_checks_runs_ruff_and_pytest_for_touched_files_with_the_real_venv(repo):
    wt, _remote, _base = repo
    ok, why = ex.run_checks(ex.venv_python(), wt, ["tests/test_a.py"])
    assert ok, why
    (wt / "tests" / "test_a.py").write_text("def test_a():\n    assert False\n", encoding="utf-8")
    assert not ex.run_checks(ex.venv_python(), wt, ["tests/test_a.py"])[0]


def test_prompt_tells_the_model_a_denied_command_does_not_block_the_allowed_ones():
    assert "tente-os" in ex.PROMPT and "o executor valida" in ex.PROMPT
