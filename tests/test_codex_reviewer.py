"""FP-059/F2 (#601): revisor Codex — read-only, parecer JSON validado, HEAD verificado, publicacao so com identidade independente, falha fechada."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from tools.orchestration import codex_reviewer as cr

SHA = "a" * 40
POLICY = {"reviewers": ["fmmodesto"], "executor_logins": ["fmodesto30"]}
REPO = "o/r"
FINDING = {"severity": "HIGH", "file": "x.py", "line": 3, "reason": "bug", "required_change": "corrigir"}


X_TEXT = "def soma(a, b):\n    return a - b  # bug\n"
X_SHA = hashlib.sha256(X_TEXT.encode("utf-8")).hexdigest()
PKG = {"base": "b" * 40, "sha": SHA, "files": {"x.py": {"sha256": X_SHA, "text": X_TEXT}}}
REVIEWED = [{"path": "x.py", "sha256": X_SHA, "code_excerpt": "return a - b  # bug"}]
GREEN = {"source": "coordinator_test_runner", "isolation": "env_allowlist_only", "tests_passed": True, "selected": ["tests/test_x.py"],
         "uncovered": [], "summary": "1 passed"}
REAL = {"review_package": cr.review_package, "run_coordinator_tests": cr.run_coordinator_tests, "check_untouched": cr.check_untouched}  # antes do autouse


def verdict(**kw):
    base = {"pr": 7, "head_sha": SHA, "verdict": "REQUEST_CHANGES", "findings": [FINDING], "tests_reviewed": [], "confidence": "HIGH",
            "files_reviewed": REVIEWED}
    return json.dumps({**base, **kw})


# ------------------------------------------------------------------------------------------------ validacao do parecer
def test_a_well_formed_request_changes_is_accepted():
    assert cr.validate_verdict(verdict(), 7, SHA)["verdict"] == "REQUEST_CHANGES"


def test_approve_needs_zero_findings_tests_reviewed_and_non_low_confidence():
    ok = verdict(verdict="APPROVE", findings=[], tests_reviewed=["tests/test_x.py"])
    assert cr.validate_verdict(ok, 7, SHA)["verdict"] == "APPROVE"
    for bad in (verdict(verdict="APPROVE", findings=[FINDING], tests_reviewed=["t"]), verdict(verdict="APPROVE", findings=[], tests_reviewed=[]),
                verdict(verdict="APPROVE", findings=[], tests_reviewed=["t"], confidence="LOW")):
        with pytest.raises(cr.ReviewError, match="APPROVE sem evidencia"):
            cr.validate_verdict(bad, 7, SHA)


@pytest.mark.parametrize("text", ["nao e json", "[]", "{}", json.dumps({"pr": 7}), "", verdict(pr=8), verdict(head_sha="b" * 40),
                                  verdict(verdict="LGTM"), verdict(confidence="MAX"), verdict(findings=[]), verdict(findings=["x"]),
                                  verdict(findings=[{**FINDING, "line": "3"}]), verdict(findings=[{**FINDING, "reason": " "}]),
                                  verdict(findings=[{**FINDING, "severity": "MEH"}]), verdict(findings=[{**FINDING, "extra": 1}]),
                                  verdict(tests_reviewed="t"), verdict(pr=True)])
def test_invalid_or_mismatched_verdicts_are_refused_never_approved(text):
    with pytest.raises(cr.ReviewError):
        cr.validate_verdict(text, 7, SHA)


def test_schema_requires_every_field_and_forbids_extras_for_codex_structured_output():
    assert cr.REVIEW_SCHEMA["additionalProperties"] is False
    assert set(cr.REVIEW_SCHEMA["required"]) == set(cr.REVIEW_SCHEMA["properties"])
    item = cr.REVIEW_SCHEMA["properties"]["findings"]["items"]
    assert item["additionalProperties"] is False and set(item["required"]) == set(item["properties"])


# ---------------------------------------------------------------------------------------------------- comando read-only
def test_command_is_read_only_ephemeral_with_schema_output_and_prompt_by_stdin():
    argv = cr.build_command("codex", Path("wt"), Path("s.json"), Path("o.json"))
    assert argv[:2] == ["codex", "exec"] and argv[argv.index("--sandbox") + 1] == "read-only" and argv[-1] == "-"
    assert "--ephemeral" in argv and "--output-schema" in argv and "--output-last-message" in argv
    assert "workspace-write" not in argv and "danger-full-access" not in argv and "--dangerously-bypass-approvals-and-sandbox" not in argv


def test_prompt_pins_the_exact_head_and_forbids_edits():
    p = cr.PROMPT.format(repo=REPO, pr=7, sha=SHA, base="b" * 40)
    assert SHA in p and "nao edite" in p and "APENAS com o JSON" in p and "NEEDS_HUMAN" in p


# ------------------------------------------------------------------------------------------------------ fluxo (mocks)
class FakeGh:
    def __init__(self, head=SHA, state="open", login="fmodesto30", moved=None, moved_after=1):
        self.head, self.state, self.login, self.moved, self.calls, self.moved_after = head, state, login, moved, 0, moved_after

    def __call__(self, path):
        if path == "user":
            return {"login": self.login}
        if path == f"repos/{REPO}/pulls/7":
            self.calls += 1
            head = self.moved if (self.moved and self.calls > self.moved_after) else self.head
            return {"state": self.state, "head": {"sha": head, "repo": {"full_name": REPO}}, "base": {"sha": "b" * 40}}
        raise AssertionError(path)


class Run:
    def __init__(self, text=None, rc=0, err="", out="", timed_out=False):
        self.text, self.rc, self.err, self.out, self.timed_out, self.calls = text, rc, err, out, timed_out, []

    def __call__(self, argv, cwd, prompt):
        self.calls.append((argv, cwd, prompt))
        if self.text is not None:
            Path(argv[argv.index("--output-last-message") + 1]).write_text(self.text, encoding="utf-8")
        return self.rc, self.out, self.err, self.timed_out


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("EVENT_BRIDGE_STATE_PATH", str(tmp_path / "gov" / "bridge.json"))
    monkeypatch.setenv("BRIDGE_WORKTREE_ROOT", str(tmp_path / "wt"))
    monkeypatch.delenv("CODEX_REVIEWER_GH_TOKEN", raising=False)
    monkeypatch.setattr(cr, "review_worktree", lambda pr, sha, root, run=None: tmp_path / "wt" / f"codex-pr{pr}")
    (tmp_path / "wt" / "codex-pr7").mkdir(parents=True)
    monkeypatch.setattr(cr, "review_package", lambda wt, base, sha: PKG)
    monkeypatch.setattr(cr, "run_coordinator_tests", lambda wt, files: dict(GREEN))
    monkeypatch.setattr(cr, "check_untouched", lambda wt, sha, stage: None)


def rec(tmp_path):
    return json.loads((tmp_path / "gov" / "codex" / "last_review.json").read_text(encoding="utf-8"))


def review(tmp_path, gh=None, run=None, **kw):
    return cr.review_pr(7, gh or FakeGh(), POLICY, REPO, runner=run or Run(verdict()), codex_bin="codex", tmp=tmp_path / "out", **kw)


def test_review_without_publishing_records_the_verdict_for_the_bar(tmp_path):
    res = review(tmp_path)
    assert res["action"] == "DONE" and res["verdict"]["verdict"] == "REQUEST_CHANGES" and not res["published"]
    r = rec(tmp_path)
    assert r["status"] == "done" and r["pr"] == 7 and r["sha"] == SHA and r["verdict"] == "REQUEST_CHANGES" and r["findings"] == 1


def test_runner_receives_the_read_only_command_in_the_separate_worktree_with_the_pinned_prompt(tmp_path):
    run = Run(verdict())
    review(tmp_path, run=run)
    argv, cwd, prompt = run.calls[0]
    assert argv[argv.index("--sandbox") + 1] == "read-only" and cwd.name == "codex-pr7" and SHA in prompt


def test_stale_head_during_the_review_discards_the_verdict(tmp_path):
    res = review(tmp_path, gh=FakeGh(moved="c" * 40))
    assert res["action"] == "STALE" and rec(tmp_path)["status"] == "failed" and "STALE" in rec(tmp_path)["error"]


@pytest.mark.parametrize("run,needle", [
    (Run(text=None, rc=1, err="Not logged in, please login"), "auth/limite"),
    (Run(text=None, rc=1, err="usage limit reached"), "auth/limite"),
    (Run(text=None, rc=2, err="boom"), "codigo 2"),
    (Run(text=None, timed_out=True), "timeout"),
    (Run(text=None), "nao gerou o parecer"),
    (Run(text="isto nao e json"), "nao e JSON"),
    (Run(text=verdict(head_sha="d" * 40)), "difere do HEAD"),
    (Run(text=verdict(verdict="APPROVE", findings=[], tests_reviewed=[])), "APPROVE sem evidencia"),
])
def test_every_failure_mode_is_review_blocked_and_never_an_approval(tmp_path, run, needle):
    res = review(tmp_path, run=run)
    assert res["action"] == "REVIEW_BLOCKED" and needle in res["reason"] and "verdict" not in res
    assert rec(tmp_path)["status"] == "failed"


def test_closed_pr_and_wrong_identity_do_not_run_codex(tmp_path):
    run = Run(verdict())
    assert review(tmp_path, gh=FakeGh(state="closed"), run=run)["action"] == "SKIPPED" and run.calls == []
    assert review(tmp_path, gh=FakeGh(login="outro"), run=run)["action"] == "FAILED" and run.calls == []


# ------------------------------------------------------------------------------------------- publicacao independente
def test_without_an_independent_identity_the_review_is_blocked_and_nothing_is_published(tmp_path):
    published = []
    res = review(tmp_path, do_publish=True, publisher=lambda *a: published.append(a))
    assert res["action"] == "REVIEW_BLOCKED" and "CODEX_REVIEWER_GH_TOKEN ausente" in res["reason"] and not published
    r = rec(tmp_path)
    assert r["status"] == "done" and r["blocked"] and not r["published"]                      # o parecer fica salvo


@pytest.mark.parametrize("login,needle", [(None, "invalido"), ("fmodesto30", "do executor"), ("qualquer", "nao esta em review_policy")])
def test_publisher_identity_must_be_a_listed_reviewer_and_not_the_executor(monkeypatch, login, needle):
    monkeypatch.setenv("CODEX_REVIEWER_GH_TOKEN", "tok")
    token, why = cr.publisher_identity(POLICY, lambda t: login)
    assert token is None and needle in why


def test_independent_identity_publishes_exactly_the_validated_verdict(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_REVIEWER_GH_TOKEN", "﻿tok")
    published = []
    res = review(tmp_path, do_publish=True, gh_user=lambda t: "fmmodesto", publisher=lambda v, token, repo: published.append((v["verdict"], token, repo)) or "https://x/r/1")
    assert res["action"] == "DONE" and res["published"] == "https://x/r/1" and published == [("REQUEST_CHANGES", "tok", REPO)]
    assert rec(tmp_path)["published"] == "https://x/r/1"


def test_needs_human_is_never_published_as_a_review(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_REVIEWER_GH_TOKEN", "tok")
    published = []
    run = Run(verdict(verdict="NEEDS_HUMAN", findings=[], confidence="LOW"))
    res = review(tmp_path, run=run, do_publish=True, gh_user=lambda t: "fmmodesto", publisher=lambda *a: published.append(a))
    assert res["action"] == "REVIEW_BLOCKED" and "NEEDS_HUMAN" in res["reason"] and not published


def test_the_executor_token_is_never_inherited_by_the_codex_child(monkeypatch):
    seen = {}

    def fake_run(argv, **kw):
        seen["env"] = kw["env"]
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
    monkeypatch.setenv("GH_TOKEN", "x")
    monkeypatch.setenv("GITHUB_TOKEN", "y")
    monkeypatch.setenv("CODEX_REVIEWER_GH_TOKEN", "z")
    monkeypatch.setattr(cr.subprocess, "run", fake_run)
    cr.run_codex(["codex"], Path("."), "p")
    assert not ({"GH_TOKEN", "GITHUB_TOKEN", "CODEX_REVIEWER_GH_TOKEN"} & set(seen["env"]))


def test_review_worktree_is_separate_and_a_dirty_one_blocks(tmp_path, monkeypatch):
    monkeypatch.undo()
    monkeypatch.setenv("BRIDGE_WORKTREE_ROOT", str(tmp_path / "wt2"))
    calls = []

    def run(args, cwd):
        calls.append(args)
        return 0, ""
    wt = cr.review_worktree(7, SHA, tmp_path, run=run)
    assert wt.name == "codex-pr7" and "bridge-pr" not in str(wt) and calls[0][:3] == ["worktree", "add", "--detach"]
    wt.mkdir(parents=True)
    with pytest.raises(cr.ReviewError, match="suja"):
        cr.review_worktree(7, SHA, tmp_path, run=lambda a, c: (0, " M x.py"))


def test_module_has_no_write_capable_codex_flags():
    src = Path(cr.__file__).read_text(encoding="utf-8")
    assert "danger-full-access" not in src and "dangerously-bypass" not in src and '"workspace-write"' not in src


# ------------------------------------------------------------------- FP-060 D-060-02 / D-060-03: prova de inspecao e teste confiavel
def test_schema_requires_files_reviewed_with_hash_and_verbatim_excerpt():
    assert "files_reviewed" in cr.REVIEW_SCHEMA["required"]
    item = cr.REVIEW_SCHEMA["properties"]["files_reviewed"]["items"]
    assert item["additionalProperties"] is False and set(item["required"]) == {"path", "sha256", "code_excerpt"}


def test_a_review_that_cites_real_bytes_of_the_reviewed_head_is_accepted():
    v = cr.validate_verdict(verdict(), 7, SHA)
    cr.verify_inspection(v, PKG)                                                     # nao levanta


@pytest.mark.parametrize("reviewed,needle", [
    ([], "sem prova de inspecao"),
    ([{**REVIEWED[0], "sha256": "0" * 64}], "sha256"),
    ([{**REVIEWED[0], "path": "y.py"}], "fora do diff"),
    ([{**REVIEWED[0], "code_excerpt": "return a + b"}], "nao e trecho literal"),
    ([{**REVIEWED[0], "code_excerpt": "a"}], "nao e trecho literal"),
])
def test_a_review_without_verifiable_inspection_is_blocked(reviewed, needle):
    v = cr.validate_verdict(verdict(files_reviewed=reviewed), 7, SHA)
    with pytest.raises(cr.ReviewError, match=needle):
        cr.verify_inspection(v, PKG)


@pytest.mark.parametrize("bad", ["x", [1], [{"path": "x.py"}], [{**REVIEWED[0], "extra": 1}], [{**REVIEWED[0], "sha256": 5}]])
def test_malformed_files_reviewed_is_refused(bad):
    with pytest.raises(cr.ReviewError, match="files_reviewed"):
        cr.validate_verdict(verdict(files_reviewed=bad), 7, SHA)


def test_needs_human_may_declare_it_could_not_inspect():
    cr.verify_inspection(cr.validate_verdict(verdict(verdict="NEEDS_HUMAN", findings=[], files_reviewed=[]), 7, SHA), PKG)


def test_a_finding_on_a_file_that_was_not_inspected_is_blocked():
    v = cr.validate_verdict(verdict(findings=[{**FINDING, "file": "z.py"}]), 7, SHA)
    with pytest.raises(cr.ReviewError, match="nao inspecionado"):
        cr.verify_inspection(v, PKG)


def test_excerpt_matches_across_crlf_checkouts():
    pkg = {**PKG, "files": {"x.py": {"sha256": X_SHA, "text": X_TEXT.replace("\n", "\r\n")}}}
    cr.verify_inspection(cr.validate_verdict(verdict(), 7, SHA), pkg)


@pytest.mark.parametrize("evidence", [{"tests_passed": False, "summary": "1 failed"}, {"tests_passed": None, "summary": "nenhum teste"}])
def test_approve_requires_green_tests_from_the_trusted_runner_not_from_the_model(tmp_path, monkeypatch, evidence):
    monkeypatch.setattr(cr, "run_coordinator_tests", lambda wt, files: {"source": "coordinator_test_runner", "selected": [], **evidence})
    run = Run(verdict(verdict="APPROVE", findings=[], tests_reviewed=["tests/test_x.py"]))
    res = review(tmp_path, run=run)
    assert res["action"] == "REVIEW_BLOCKED" and "testes do coordenador nao verdes" in res["reason"]


def test_request_changes_is_still_valid_when_trusted_tests_are_red(tmp_path, monkeypatch):
    monkeypatch.setattr(cr, "run_coordinator_tests", lambda wt, files: {"source": "coordinator_test_runner", "selected": [], "tests_passed": False,
                                                                   "summary": "1 failed"})
    assert review(tmp_path)["action"] == "DONE"


def test_the_trusted_test_result_and_the_file_contents_go_into_the_prompt(tmp_path):
    run = Run(verdict())
    review(tmp_path, run=run)
    prompt = run.calls[0][2]
    assert X_SHA in prompt and "return a - b  # bug" in prompt and "1 passed" in prompt and "coordinator_test_runner" in prompt


def test_approve_with_green_trusted_tests_and_real_inspection_is_done(tmp_path):
    res = review(tmp_path, run=Run(verdict(verdict="APPROVE", findings=[], tests_reviewed=["tests/test_x.py"])))
    assert res["action"] == "DONE" and res["verdict"]["verdict"] == "APPROVE"
    assert rec(tmp_path)["tests_passed"] is True and rec(tmp_path)["files_reviewed"] == ["x.py"] and rec(tmp_path)["isolation"] == "env_allowlist_only"


def test_codex_touching_the_worktree_invalidates_the_review(tmp_path, monkeypatch):
    def untouched(wt, sha, stage):
        if stage == "after_codex":
            raise cr.ReviewError("Codex alterou a worktree do revisor")
    monkeypatch.setattr(cr, "check_untouched", untouched)
    res = review(tmp_path, run=Run(verdict()))
    assert res["action"] == "REVIEW_BLOCKED" and "alterou a worktree" in res["reason"]


def test_check_untouched_blocks_on_dirty_tree_or_moved_head():
    check = REAL["check_untouched"]
    with pytest.raises(cr.ReviewError, match="alterou a worktree"):
        check(Path("."), SHA, "after_codex", run=lambda a, c: (0, " M x.py") if a[0] == "status" else (0, SHA))
    with pytest.raises(cr.ReviewError, match="HEAD"):
        check(Path("."), SHA, "after_codex", run=lambda a, c: (0, "") if a[0] == "status" else (0, "c" * 40))
    check(Path("."), SHA, "after_codex", run=lambda a, c: (0, "") if a[0] == "status" else (0, SHA))


def test_trusted_runner_without_changed_tests_gives_no_evidence_and_never_runs_pytest(monkeypatch):
    monkeypatch.setattr(cr.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("nao deveria rodar")))
    ev = REAL["run_coordinator_tests"](Path("."), ["tools/orchestration/x.py"])
    assert ev["tests_passed"] is None and ev["selected"] == [] and ev["source"] == "coordinator_test_runner"


def test_trusted_runner_reports_the_real_exit_code_of_the_selected_tests(tmp_path, monkeypatch):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text("", encoding="utf-8")
    seen = {}

    def fake_run(argv, **kw):
        seen["argv"], seen["env"] = argv, kw["env"]
        return type("R", (), {"returncode": 1, "stdout": "1 failed", "stderr": ""})()
    monkeypatch.setenv("GH_TOKEN", "x")
    monkeypatch.setattr(cr.subprocess, "run", fake_run)
    ev = REAL["run_coordinator_tests"](tmp_path, ["tests/test_x.py", "tools/y.py"], python="py")
    assert ev["tests_passed"] is False and ev["selected"] == ["tests/test_x.py"] and "1 failed" in ev["summary"] and ev["uncovered"] == ["tools/y.py"]
    assert seen["argv"][:3] == ["py", "-m", "pytest"] and "no:cacheprovider" in seen["argv"] and "GH_TOKEN" not in seen["env"]


def test_review_package_hashes_the_blob_at_the_head_and_skips_deleted_files():
    blobs = {"x.py": X_TEXT.encode("utf-8"), "gone.py": None}
    pkg = REAL["review_package"](Path("."), "b" * 40, SHA, run=lambda a, c: (0, "x.py\ngone.py"), blob=lambda wt, sha, p: blobs[p])
    assert pkg["files"] == {"x.py": {"sha256": X_SHA, "text": X_TEXT}}


# ------------------------------------------------- review 2026-11-05: isolamento declarado, cobertura, TOCTOU na publicacao
def test_child_env_is_an_allowlist_with_gh_and_git_credentials_cut():
    base = {"PATH": "p", "USERPROFILE": "u", "CODEX_HOME": "c", "GH_TOKEN": "x", "AWS_SECRET_ACCESS_KEY": "a", "OPENAI_API_KEY": "o",
            "SSH_AUTH_SOCK": "s", "QUALQUER": "q", "CODEX_REVIEWER_GH_TOKEN": "z"}
    env = cr._child_env(base)
    assert {"PATH", "USERPROFILE", "CODEX_HOME"} <= set(env)
    assert not ({"GH_TOKEN", "AWS_SECRET_ACCESS_KEY", "OPENAI_API_KEY", "SSH_AUTH_SOCK", "QUALQUER", "CODEX_REVIEWER_GH_TOKEN"} & set(env))
    assert Path(env["GH_CONFIG_DIR"]).is_dir() and env["GIT_CONFIG_NOSYSTEM"] == "1" and Path(env["GIT_CONFIG_GLOBAL"]).read_text() == ""


def test_the_runner_never_claims_to_be_trusted_and_declares_its_isolation():
    src = Path(cr.__file__).read_text(encoding="utf-8")
    assert "trusted_test_runner" not in src and cr.RUNNER_SOURCE == "coordinator_test_runner" and cr.ISOLATION == "env_allowlist_only"


def test_select_tests_maps_changed_modules_to_their_tests_and_reports_uncovered_code(tmp_path):
    (tmp_path / "tests" / "orch").mkdir(parents=True)
    for name in ("tests/test_alpha.py", "tests/orch/test_alpha_extra.py", "tests/test_changed.py"):
        (tmp_path / name).write_text("", encoding="utf-8")
    sel, unc = cr.select_tests(tmp_path, ["tools/a/alpha.py", "tools/b/beta.py", "tests/test_changed.py", "ops/run.ps1", "docs/x.md",
                                          "docs/specs/fp042_inventory.v1.json"])
    assert sel == ["tests/orch/test_alpha_extra.py", "tests/test_alpha.py", "tests/test_changed.py"]
    assert unc == ["ops/run.ps1", "tools/b/beta.py"]


@pytest.mark.parametrize("evidence,v_kw,needle", [
    ({"uncovered": ["tools/b.py"]}, {}, "sem teste correspondente"),
    ({}, {"tests_reviewed": ["tests/test_outro.py"]}, "fora dos testes executados"),
    ({}, {"tests_reviewed": []}, "tests_reviewed vazio"),
])
def test_approve_without_coverage_or_with_tests_not_actually_run_is_blocked(tmp_path, monkeypatch, evidence, v_kw, needle):
    monkeypatch.setattr(cr, "run_coordinator_tests", lambda wt, files: {**GREEN, **evidence})
    kw = {"verdict": "APPROVE", "findings": [], "tests_reviewed": ["tests/test_x.py"], **v_kw}
    if not kw["tests_reviewed"]:
        res = review(tmp_path, run=Run(verdict(**kw)))                              # validate_verdict ja barra APPROVE sem tests_reviewed
        assert res["action"] == "REVIEW_BLOCKED"
        return
    res = review(tmp_path, run=Run(verdict(**kw)))
    assert res["action"] == "REVIEW_BLOCKED" and needle in res["reason"]


def test_approve_must_inspect_every_code_file_of_the_diff(tmp_path, monkeypatch):
    y = "def y():\n    return 42\n"
    pkg = {**PKG, "files": {**PKG["files"], "y.py": {"sha256": hashlib.sha256(y.encode()).hexdigest(), "text": y}}}
    monkeypatch.setattr(cr, "review_package", lambda wt, base, sha: pkg)
    res = review(tmp_path, run=Run(verdict(verdict="APPROVE", findings=[], tests_reviewed=["tests/test_x.py"])))
    assert res["action"] == "REVIEW_BLOCKED" and "nao inspecionado: y.py" in res["reason"]


def test_a_valid_approve_is_recorded_but_never_auto_published_without_an_os_sandbox(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_REVIEWER_GH_TOKEN", "tok")
    published = []
    res = review(tmp_path, run=Run(verdict(verdict="APPROVE", findings=[], tests_reviewed=["tests/test_x.py"])), do_publish=True,
                 gh_user=lambda t: "fmmodesto", publisher=lambda *a: published.append(a))
    assert res["action"] == "REVIEW_BLOCKED" and "sandbox de SO" in res["reason"] and not published
    assert rec(tmp_path)["verdict"] == "APPROVE" and rec(tmp_path)["blocked"]


def test_head_moving_between_validation_and_publish_aborts_the_post(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_REVIEWER_GH_TOKEN", "tok")
    published = []
    gh = FakeGh(moved="c" * 40, moved_after=2)                                   # 1 = inicio, 2 = checagem pos-Codex, 3 = antes do POST
    res = review(tmp_path, gh=gh, do_publish=True, gh_user=lambda t: "fmmodesto", publisher=lambda *a: published.append(a) or "u")
    assert res["action"] == "STALE" and "antes de publicar" in res["reason"] and not published


def test_head_moving_right_after_publish_is_reconciled_and_reported(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_REVIEWER_GH_TOKEN", "tok")
    gh = FakeGh(moved="c" * 40, moved_after=3)                                   # 4 = reconciliacao depois do POST
    res = review(tmp_path, gh=gh, do_publish=True, gh_user=lambda t: "fmmodesto", publisher=lambda *a: "https://x/r/2")
    assert res["action"] == "DONE" and res["published"] == "https://x/r/2" and res["head_moved_after_publish"] == "c" * 40
    assert rec(tmp_path)["head_moved_after_publish"] == "c" * 40
