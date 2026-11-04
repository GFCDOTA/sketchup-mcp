"""FP-057/P8 (#589): a ENTREGA e do executor, nao do LLM — autorizacao revalidada (TOCTOU), staging explicito, guards, selecao segura de testes
e push so para a branch do PR (git real com remoto bare)."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from tools.orchestration import event_executor as ex
from tools.orchestration import execution_guards as g
from tools.orchestration import executor_delivery as dl

ITEM = {"event_id": "review:777:5:abc", "pr": 5, "issue": 589}
CFG = g.load_config()
OK = lambda py, wt, files, tests=None: (True, "")  # noqa: E731
BAD = lambda py, wt, files, tests=None: (False, "pytest rc=1")  # noqa: E731
AUTH = lambda: (True, "ok")  # noqa: E731


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
    (wt / "tools").mkdir()
    (wt / "tools" / "mod.py").write_text("X = 1\n", encoding="utf-8")
    sh(wt, "add", "-A")
    sh(wt, "commit", "-qm", "base")
    sh(wt, "push", "-q", "origin", "HEAD:refs/heads/feat/x")
    return wt, remote, sh(wt, "rev-parse", "HEAD")


def run(wt, base, **kw):
    kw.setdefault("check", OK)
    kw.setdefault("revalidate", AUTH)
    return dl.deliver(wt, "feat/x", base, "py", ITEM, cfg=CFG, **kw)


def edit_test(wt, text="assert 1 == 1"):
    (wt / "tests" / "test_a.py").write_text(f"def test_a():\n    {text}\n", encoding="utf-8")


def untouched(remote, base):
    return sh(remote, "rev-parse", "feat/x") == base


# ------------------------------------------------------------------------------------------------------ caminho feliz
def test_pending_edit_is_committed_and_pushed_only_to_the_pr_branch(repo):
    wt, remote, base = repo
    edit_test(wt)
    action, msg = run(wt, base)
    assert action == "PUSHED", msg
    assert sh(remote, "rev-parse", "feat/x") == sh(wt, "rev-parse", "HEAD") != base
    assert "Refs #589" in sh(wt, "log", "-1", "--format=%s")


def test_no_change_is_a_noop_and_pushes_nothing(repo):
    wt, remote, base = repo
    assert run(wt, base)[0] == "NOOP" and untouched(remote, base)


def test_a_local_commit_made_by_the_llm_is_verified_and_pushed_too(repo):
    wt, remote, base = repo
    edit_test(wt, "assert 2 == 2")
    sh(wt, "commit", "-aqm", "fix: llm")
    assert run(wt, base)[0] == "PUSHED" and sh(remote, "rev-parse", "feat/x") == sh(wt, "rev-parse", "HEAD")


# ------------------------------------------------------------------------- TOCTOU / autorizacao revalidada (bloqueio 1)
def test_stale_authorization_before_staging_blocks_everything_and_stages_nothing(repo):
    wt, remote, base = repo
    edit_test(wt)
    action, msg = run(wt, base, revalidate=lambda: (False, "HEAD mudou"))
    assert action == "STALE" and "HEAD mudou" in msg and untouched(remote, base) and sh(wt, "diff", "--cached", "--name-only") == ""


def test_authorization_lost_while_checks_were_running_blocks_the_push(repo):
    wt, remote, base = repo
    edit_test(wt)
    calls = []

    def revalidate():
        calls.append(1)
        return (len(calls) < 2), "review obsoleto"                              # 1a ok, 2a (imediatamente antes do push) falha

    action, msg = run(wt, base, revalidate=revalidate)
    assert action == "STALE" and len(calls) == 2 and "imediatamente antes do push" in msg and untouched(remote, base)


def test_remote_head_that_advanced_blocks_even_if_authorization_still_looks_valid(repo, tmp_path):
    wt, remote, base = repo
    other = tmp_path / "other"
    sh(tmp_path, "clone", "-q", "-b", "feat/x", str(remote), str(other))
    for k, v in (("user.email", "o@o"), ("user.name", "o")):
        sh(other, "config", k, v)
    (other / "tests" / "test_a.py").write_text("def test_a():\n    assert 'concorrente'\n", encoding="utf-8")
    sh(other, "commit", "-aqm", "outro agente")
    sh(other, "push", "-q", "origin", "HEAD:refs/heads/feat/x")
    edit_test(wt)
    action, msg = run(wt, base)
    assert action == "STALE" and "HEAD remoto" in msg and sh(remote, "log", "-1", "--format=%s", "feat/x") == "outro agente"


def test_remote_advancing_during_validation_is_caught_by_the_second_barrier(repo, tmp_path):
    wt, remote, base = repo
    edit_test(wt)
    other = tmp_path / "other"
    sh(tmp_path, "clone", "-q", "-b", "feat/x", str(remote), str(other))
    for k, v in (("user.email", "o@o"), ("user.name", "o")):
        sh(other, "config", k, v)

    def slow_check(py, w, files, tests=None):
        (other / "tests" / "test_a.py").write_text("def test_a():\n    assert 'meio da validacao'\n", encoding="utf-8")
        sh(other, "commit", "-aqm", "durante os checks")
        sh(other, "push", "-q", "origin", "HEAD:refs/heads/feat/x")
        return True, ""

    action, msg = run(wt, base, check=slow_check)
    assert action == "STALE" and "durante a validacao" in msg and sh(remote, "log", "-1", "--format=%s", "feat/x") == "durante os checks"


def test_missing_revalidation_is_fail_closed(repo):
    wt, remote, base = repo
    edit_test(wt)
    assert dl.deliver(wt, "feat/x", base, "py", ITEM, check=OK, cfg=CFG)[0] == "STALE" and untouched(remote, base)


def test_unexpected_branch_with_no_remote_ref_is_stale(repo):
    wt, remote, base = repo
    edit_test(wt)
    assert dl.deliver(wt, "feat/inexistente", base, "py", ITEM, check=OK, cfg=CFG, revalidate=AUTH)[0] == "STALE"


def test_push_refused_by_the_remote_is_an_error_and_a_retry_does_not_duplicate(repo):
    wt, remote, base = repo
    hook = remote / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    os.chmod(hook, 0o755)
    edit_test(wt)
    action, msg = run(wt, base)
    assert action == "ERROR" and "recusado" in msg and untouched(remote, base)
    hook.unlink()
    assert run(wt, base)[0] == "PUSHED"                                         # retry: publica UMA vez
    assert len(sh(wt, "rev-list", f"{base}..HEAD").splitlines()) == 1
    assert run(wt, base)[0] == "STALE"                                          # 3a vez: o remoto ja avancou, nada e republicado


# ------------------------------------------------------- staging explicito / arquivos nao autorizados (bloqueio 2)
def test_unrelated_untracked_files_are_never_swept_into_the_commit(repo):
    wt, remote, base = repo
    edit_test(wt)
    (wt / ".env").write_text("TOKEN=segredo\n", encoding="utf-8")
    action, msg = run(wt, base)
    assert action == "BLOCKED_GUARDS" and ".env" in msg and untouched(remote, base)
    assert sh(wt, "diff", "--cached", "--name-only") == ""                       # nada ficou no indice


@pytest.mark.parametrize("name", ["tools/ferramenta.exe", "dados.skp", "img.png", "tests/conftest.py", "tests/fixtures/x.json"])
def test_unauthorized_types_and_test_helpers_are_refused_before_staging(repo, name):
    wt, remote, base = repo
    (wt / name).parent.mkdir(parents=True, exist_ok=True)
    (wt / name).write_bytes(b"x")
    action, msg = run(wt, base)
    assert action == "BLOCKED_GUARDS" and name.split("/")[-1] in msg and untouched(remote, base)


@pytest.mark.skipif(os.name == "nt", reason="symlink exige privilegio no Windows")
def test_symlink_is_refused(repo):
    wt, remote, base = repo
    os.symlink("/etc/passwd", wt / "tests" / "test_link.py")
    action, msg = run(wt, base)
    assert action == "BLOCKED_GUARDS" and "symlink" in msg and untouched(remote, base)


def test_symlink_mode_in_a_commit_made_by_the_llm_is_refused_by_the_raw_diff(repo):
    wt, remote, base = repo
    blob = sh(wt, "hash-object", "-w", "--stdin") if False else subprocess.run(
        ["git", "hash-object", "-w", "--stdin"], cwd=wt, input="alvo\n", capture_output=True, text=True, check=True).stdout.strip()
    sh(wt, "update-index", "--add", "--cacheinfo", f"120000,{blob},tests/test_link.py")
    sh(wt, "commit", "-qm", "fix: symlink do llm")
    sh(wt, "checkout", "--", "tests/test_link.py")                              # materializa como numa worktree real
    action, msg = run(wt, base)
    assert action == "BLOCKED_GUARDS" and "120000" in msg and untouched(remote, base)


def test_critical_path_blocks_before_any_commit_or_push(repo):
    wt, remote, base = repo
    (wt / "tools" / "validation").mkdir()
    (wt / "tools" / "validation" / "x.py").write_text("x = 1\n", encoding="utf-8")
    action, msg = run(wt, base)
    assert action == "BLOCKED_GUARDS" and "critico" in msg and untouched(remote, base) and sh(wt, "rev-parse", "HEAD") == base


def test_diff_over_the_ceiling_blocks_and_unstages(repo):
    wt, remote, base = repo
    (wt / "docs").mkdir()
    (wt / "docs" / "big.md").write_text("l\n" * 400, encoding="utf-8")
    assert run(wt, base)[0] == "BLOCKED_GUARDS" and untouched(remote, base) and sh(wt, "diff", "--cached", "--name-only") == ""


def test_delivery_source_never_uses_git_add_dash_A():
    src = Path(dl.__file__).read_text(encoding="utf-8")
    assert '"add", "-A"' not in src and "add -A" not in src and '"-A"' not in src


# ------------------------------------------------------------------------ selecao segura de testes (bloqueio 3)
def test_production_code_without_a_matching_test_is_blocked_not_published(repo):
    wt, remote, base = repo
    (wt / "tools" / "mod.py").write_text("X = 2\n", encoding="utf-8")
    action, msg = run(wt, base)
    assert action == "BLOCKED_GUARDS" and "sem teste correspondente" in msg and untouched(remote, base)


def test_production_code_with_a_matching_test_runs_that_test_and_is_published(repo):
    wt, remote, base = repo
    (wt / "tests" / "test_mod.py").write_text("def test_mod():\n    assert True\n", encoding="utf-8")
    sh(wt, "add", "-A")
    sh(wt, "commit", "-qm", "test: mod")
    sh(wt, "push", "-q", "origin", "HEAD:refs/heads/feat/x")
    base2 = sh(wt, "rev-parse", "HEAD")
    (wt / "tools" / "mod.py").write_text("X = 2\n", encoding="utf-8")
    seen = {}

    def check(py, w, files, tests=None):
        seen["tests"], seen["files"] = tests, files
        return True, ""
    assert run(wt, base2, check=check)[0] == "PUSHED" and seen["tests"] == ["tests/test_mod.py"] and seen["files"] == ["tools/mod.py"]


def test_select_tests_contract(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_foo.py").write_text("", encoding="utf-8")
    (tmp_path / "tests" / "test_foo_extra.py").write_text("", encoding="utf-8")
    assert dl.select_tests(["docs/a.md"], tmp_path) == ([], "")
    assert dl.select_tests(["tools/foo.py"], tmp_path)[0] == ["tests/test_foo.py", "tests/test_foo_extra.py"]
    assert dl.select_tests(["tests/test_x.py"], tmp_path)[0] == ["tests/test_x.py"]
    assert dl.select_tests(["tests/conftest.py"], tmp_path)[0] is None
    assert dl.select_tests(["tests/helpers.py"], tmp_path)[0] is None
    assert dl.select_tests(["tools/bar.py"], tmp_path)[0] is None
    assert dl.select_tests(["config.json"], tmp_path)[0] is None


def test_failing_checks_block_the_push(repo):
    wt, remote, base = repo
    edit_test(wt, "assert False")
    action, msg = run(wt, base, check=BAD)
    assert action == "FAILED_CHECKS" and "pytest" in msg and untouched(remote, base)


def test_run_checks_runs_ruff_and_pytest_for_the_selected_files_with_the_real_venv(repo):
    wt, _remote, _base = repo
    assert ex.run_checks(ex.venv_python(), wt, ["tests/test_a.py"], ["tests/test_a.py"])[0]
    edit_test(wt, "assert False")
    assert not ex.run_checks(ex.venv_python(), wt, ["tests/test_a.py"], ["tests/test_a.py"])[0]


def test_prompt_tells_the_model_a_denied_command_does_not_block_the_allowed_ones():
    assert "tente-os" in ex.PROMPT and "o executor valida" in ex.PROMPT
