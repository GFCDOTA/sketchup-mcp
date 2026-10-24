"""FP-055 P1: identidade de runtime — checkout velho, sujo ou processo desatualizado bloqueia o perfil inteligente."""
from __future__ import annotations

import subprocess

import pytest

from tools.sketchup import runtime_identity as ri


def _git(repo, *a):
    subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path):
    """origin (bare) + clone com 2 commits no develop remoto; o clone fica 1 atras."""
    origin, work = tmp_path / "origin.git", tmp_path / "work"
    subprocess.run(["git", "init", "--bare", "-b", "develop", str(origin)], check=True, capture_output=True)
    subprocess.run(["git", "clone", str(origin), str(work)], check=True, capture_output=True)
    _git(work, "config", "user.email", "t@t")
    _git(work, "config", "user.name", "t")
    _git(work, "checkout", "-b", "develop")
    for rel in ri.BRIDGE_FILES:
        (work / rel).parent.mkdir(parents=True, exist_ok=True)
        (work / rel).write_text("# rb\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "a")
    _git(work, "push", "-u", "origin", "develop")
    return work


def _ident(repo):
    code = ri.code_identity(repo)
    return {"code": code, "process": {"start_head": code["head"], "stale": False}, "bridge": ri.bridge_identity(repo)}


def test_synced_clean_checkout_is_ok(repo):
    assert ri.check("INTELLIGENT_BUILD", _ident(repo))["status"] == "OK"


def test_checkout_behind_origin_blocks_intelligent_but_legacy_only_records(repo):
    _git(repo, "commit", "--allow-empty", "-m", "b")
    _git(repo, "push")
    _git(repo, "reset", "-q", "--hard", "HEAD~1")                # clone de teste volta 1 commit (tmp_path, descartavel)
    ident = _ident(repo)
    assert ident["code"]["behind"] == 1
    r = ri.check("INTELLIGENT_BUILD", ident)
    assert r["status"] == "BLOCKED" and any("atras 1" in x for x in r["reasons"])
    assert ri.check("LEGACY_DIAGNOSTIC", ident)["status"] == "RECORDED"
    assert ri.check("INTELLIGENT_BUILD", ident, allow_dev=True)["status"] == "DEV_OVERRIDE"


def test_dirty_checkout_blocks(repo):
    (repo / "x.txt").write_text("sujo")
    r = ri.check("INTELLIGENT_DRY_RUN", _ident(repo))
    assert r["status"] == "BLOCKED" and any("sujo" in x for x in r["reasons"])


def test_process_loaded_older_code_than_disk_blocks(repo):
    ident = _ident(repo)
    ident["process"] = {"start_head": "0" * 40, "stale": True}      # servidor iniciado antes de um pull
    r = ri.check("INTELLIGENT_BUILD", ident)
    assert r["status"] == "BLOCKED" and any("reiniciar o servidor" in x for x in r["reasons"])


def test_expected_commit_mismatch_and_missing_bridge_block(repo):
    ident = _ident(repo)
    assert ri.check("INTELLIGENT_BUILD", ident, expected_commit="f" * 40)["status"] == "BLOCKED"
    (repo / ri.BRIDGE_FILES[0]).unlink()
    assert any("Ruby" in x for x in ri.check("INTELLIGENT_BUILD", _ident(repo))["reasons"])


def test_unknown_git_fails_closed(tmp_path):
    code = ri.code_identity(tmp_path)                                # nao e repo git
    ident = {"code": code, "process": {"start_head": ri.UNKNOWN, "stale": True}, "bridge": ri.bridge_identity(tmp_path)}
    assert ri.check("INTELLIGENT_BUILD", ident)["status"] == "BLOCKED"
    assert ri.check("NOPE", ident)["status"] == "BLOCKED"
