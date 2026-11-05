"""FP-059/F2 (#601): revisor Codex — read-only, parecer JSON validado, HEAD verificado, publicacao so com identidade independente, falha fechada."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tools.orchestration import codex_reviewer as cr

SHA = "a" * 40
POLICY = {"reviewers": ["fmmodesto"], "executor_logins": ["fmodesto30"]}
REPO = "o/r"
FINDING = {"severity": "HIGH", "file": "x.py", "line": 3, "reason": "bug", "required_change": "corrigir"}


def verdict(**kw):
    base = {"pr": 7, "head_sha": SHA, "verdict": "REQUEST_CHANGES", "findings": [FINDING], "tests_reviewed": [], "confidence": "HIGH"}
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
    def __init__(self, head=SHA, state="open", login="fmodesto30", moved=None):
        self.head, self.state, self.login, self.moved, self.calls = head, state, login, moved, 0

    def __call__(self, path):
        if path == "user":
            return {"login": self.login}
        if path == f"repos/{REPO}/pulls/7":
            self.calls += 1
            head = self.moved if (self.moved and self.calls > 1) else self.head
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
