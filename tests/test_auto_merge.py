"""FP-060 MT-15 (#647): merge automatico PROTEGIDO. Desligado por padrao; cada recusa e cada espera tem teste; o GitHub e injetado."""
from __future__ import annotations

import pytest

from tools.orchestration import auto_merge as am
from tools.orchestration import execution_guards as guards
from tools.orchestration import lifecycle

HEAD, OLD = "a" * 40, "b" * 40
REPO = "o/r"
POLICY = {"reviewers": ["fmmodesto"], "executor_logins": ["fmodesto30"]}
CFG = guards.load_config()
ON = (True, "")


def pr(**kw):
    base = {"number": 7, "state": "open", "merged": False, "draft": False, "mergeable_state": "clean", "user": {"login": "fmodesto30"},
            "base": {"ref": "develop", "repo": {"full_name": REPO}}, "head": {"sha": HEAD, "repo": {"full_name": REPO}},
            "labels": [{"name": am.PR_LABEL}, {"name": CFG.label}], "body": "Refs #5\n"}
    return {**base, **kw}


def files(*names, add=3, rem=1):
    return [{"filename": n, "additions": add, "deletions": rem, "changes": add + rem, "patch": "@@", "status": "modified"} for n in (names or ("docs/x.md",))]


def runs(bad=None, missing=None):
    out = []
    for n in sorted(lifecycle.MANDATORY_CHECKS):
        if n == missing:
            continue
        out.append({"name": n, "status": "completed", "conclusion": "failure" if n == bad else "success"})
    return out


def approval(state="APPROVED", user="fmmodesto", commit=HEAD):
    return {"id": 11, "user": {"login": user}, "state": state, "commit_id": commit}


def issues(labels=(am.ISSUE_LABEL,), state="open"):
    return {5: {"number": 5, "state": state, "labels": [{"name": n} for n in labels]}}


def decide(**kw):
    args = {"pr": pr(), "files": files(), "runs": runs(), "reviews": [approval()], "issues": issues(), "policy": POLICY, "cfg": CFG, "is_enabled": ON}
    args.update(kw)
    return am.decide(args.pop("pr"), args.pop("files"), args.pop("runs"), args.pop("reviews"), args.pop("issues"), args.pop("policy"), args.pop("cfg"), **args)


# ----------------------------------------------------------------------------------------------------------------- caminho feliz
def test_all_gates_green_with_an_independent_approval_on_the_exact_head_merges():
    d = decide()
    assert d.code == "MERGE" and HEAD[:12] in d.reasons[0]


# ------------------------------------------------------------------------------------------------------------------- desligado
def test_it_is_disabled_by_default_and_by_the_kill_switch(tmp_path, monkeypatch):
    monkeypatch.setenv("EVENT_BRIDGE_STATE_PATH", str(tmp_path / "gov" / "bridge.json"))
    assert am.enabled({})[0] is False and "padrao" in am.enabled({})[1]
    assert am.enabled({am.ENABLE_ENV: "true"})[0] is False and am.enabled({am.ENABLE_ENV: "1"})[0] is True
    am.kill_switch().parent.mkdir(parents=True)
    am.kill_switch().write_text("x", encoding="utf-8")
    assert am.enabled({am.ENABLE_ENV: "1"})[0] is False                                              # o interruptor vence a variavel
    assert decide(is_enabled=am.enabled({am.ENABLE_ENV: "1"})).code == "DISABLED"


# ---------------------------------------------------------------------------------------- recusas: decisao que e humana
@pytest.mark.parametrize("name,kw,needle", [
    ("draft", {"pr": pr(draft=True)}, "rascunho"),
    ("closed", {"pr": pr(state="closed")}, "nao esta aberto"),
    ("merged", {"pr": pr(merged=True)}, "nao esta aberto"),
    ("base", {"pr": pr(base={"ref": "main", "repo": {"full_name": REPO}})}, "base"),
    ("fork", {"pr": pr(head={"sha": HEAD, "repo": {"full_name": "x/fork"}})}, "fork"),
    ("author", {"pr": pr(user={"login": "outro"})}, "nao e o executor"),
    ("no_pr_label", {"pr": pr(labels=[{"name": CFG.label}])}, am.PR_LABEL),
    ("no_executor_label", {"pr": pr(labels=[{"name": am.PR_LABEL}])}, CFG.label),
    ("human_label", {"pr": pr(labels=[{"name": am.PR_LABEL}, {"name": CFG.label}, {"name": "visual-review"}])}, "decisao humana"),
    ("security_label", {"pr": pr(labels=[{"name": am.PR_LABEL}, {"name": CFG.label}, {"name": "security"}])}, "decisao humana"),
    ("no_refs", {"pr": pr(body="sem referencia")}, "Refs"),
    ("issue_missing", {"issues": {}}, "inexistente"),
    ("issue_closed", {"issues": issues(state="closed")}, "inexistente ou fechada"),
    ("issue_without_key", {"issues": issues(labels=())}, am.ISSUE_LABEL),
    ("issue_human", {"issues": issues(labels=(am.ISSUE_LABEL, "aprovação-humana-pendente"))}, "decisao humana"),
    ("issue_blocked", {"issues": issues(labels=(am.ISSUE_LABEL, "blocked"))}, "decisao humana"),
    ("no_files", {"files": []}, "sem arquivos"),
    ("conflict", {"pr": pr(mergeable_state="dirty")}, "conflito"),
    ("ci_failed", {"runs": runs(bad=sorted(lifecycle.MANDATORY_CHECKS)[0])}, "reprovados"),
    ("changes_requested", {"reviews": [approval(state="CHANGES_REQUESTED")]}, "pede mudancas"),
])
def test_a_human_decision_or_a_hard_failure_refuses_the_merge(name, kw, needle):
    d = decide(**kw)
    assert d.code == "REFUSE" and any(needle in r for r in d.reasons), d


@pytest.mark.parametrize("path", [".github/workflows/ci.yml", "docs/governance/review_policy.json", "tools/orchestration/event_executor.py",
                                   "tools/validation/backlog_gate.py", "core/plan_frame.py", "tools/rooms/capability_catalog.v1.json"])
def test_a_diff_touching_a_critical_path_always_needs_a_human(path):
    d = decide(files=files("docs/x.md", path))
    assert d.code == "REFUSE" and any("path_critico" in r for r in d.reasons)


def test_the_diff_ceilings_binary_files_and_file_types_refuse():
    assert any("max_files" in r for r in decide(files=files(*[f"docs/f{i}.md" for i in range(CFG.max_files + 1)])).reasons)
    assert any("max_lines" in r for r in decide(files=files("docs/x.md", add=CFG.max_lines, rem=1)).reasons)
    binary = [{"filename": "docs/a.png", "additions": 0, "deletions": 0, "changes": 0, "status": "added"}]
    d = decide(files=binary)
    assert d.code == "REFUSE" and any("binario" in r for r in d.reasons) and any("tipo nao permitido" in r for r in d.reasons)
    assert any("tipo nao permitido" in r for r in decide(files=files("artifacts/x.skp")).reasons)


def test_a_rename_out_of_a_critical_path_still_counts_the_origin():
    renamed = [{"filename": "docs/ok.md", "previous_filename": ".github/workflows/ci.yml", "additions": 0, "deletions": 0, "changes": 0, "patch": "", "status": "renamed"}]
    assert any("path_critico" in r for r in decide(files=renamed).reasons)


def test_every_reason_is_reported_not_only_the_first():
    d = decide(pr=pr(draft=True, labels=[]), issues={})
    assert d.code == "REFUSE" and len(d.reasons) >= 4


# ----------------------------------------------------------------------------------------------------------------------- esperas
@pytest.mark.parametrize("name,kw,needle", [
    ("ci_pending", {"runs": runs(missing=sorted(lifecycle.MANDATORY_CHECKS)[0])}, "checks obrigatorios pending"),
    ("no_checks", {"runs": []}, "checks obrigatorios none"),
    ("no_review", {"reviews": []}, "sem aprovacao"),
    ("review_on_old_head", {"reviews": [approval(commit=OLD)]}, "sem aprovacao"),
    ("review_by_executor", {"reviews": [approval(user="fmodesto30")]}, "sem aprovacao"),
    ("review_by_stranger", {"reviews": [approval(user="intruso")]}, "sem aprovacao"),
    ("commented_only", {"reviews": [approval(state="COMMENTED")]}, "sem aprovacao"),
    ("behind", {"pr": pr(mergeable_state="behind")}, "mergeable_state"),
    ("blocked", {"pr": pr(mergeable_state="blocked")}, "mergeable_state"),
])
def test_missing_proof_waits_and_never_merges(name, kw, needle):
    d = decide(**kw)
    assert d.code == "WAIT" and any(needle in r for r in d.reasons), d


def test_an_approval_followed_by_a_change_request_on_the_same_head_does_not_merge():
    assert decide(reviews=[approval(), approval(state="CHANGES_REQUESTED")]).code == "REFUSE"
    assert decide(reviews=[approval(state="CHANGES_REQUESTED"), approval()]).code == "MERGE"           # o ultimo parecer do revisor vale


# ------------------------------------------------------------------------------------------------------------------------ ciclo
class Gh:
    def __init__(self, head=HEAD, fresh_head=None, boom=None, labelled=True, **overrides):
        self.head, self.fresh_head, self.boom, self.labelled, self.overrides, self.calls = head, fresh_head, boom, labelled, overrides, []
        self.pulls = 0

    def __call__(self, path):
        self.calls.append(path)
        if self.boom:
            raise self.boom
        if path.startswith(f"repos/{REPO}/pulls?state=open"):
            return [{"number": 7, "labels": [{"name": am.PR_LABEL}] if self.labelled else []}]
        if path == f"repos/{REPO}/pulls/7":
            self.pulls += 1
            sha = self.fresh_head if (self.fresh_head and self.pulls > 1) else self.head
            return pr(head={"sha": sha, "repo": {"full_name": REPO}}, **self.overrides)
        if path.startswith(f"repos/{REPO}/pulls/7/files"):
            return files()
        if path.startswith(f"repos/{REPO}/pulls/7/reviews"):
            return [approval(commit=self.head)]
        if "check-runs" in path:
            return {"total_count": len(lifecycle.MANDATORY_CHECKS), "check_runs": runs()}
        if path == f"repos/{REPO}/issues/5":
            return issues()[5]
        raise AssertionError(path)


class Runner:
    def __init__(self, rc=0, err=""):
        self.rc, self.err, self.calls = rc, err, []

    def __call__(self, argv, **kw):
        self.calls.append((argv, kw))
        return type("P", (), {"returncode": self.rc, "stdout": "", "stderr": self.err})()


def test_a_disabled_cycle_reads_nothing_and_merges_nothing():
    gh, runner = Gh(), Runner()
    out = am.cycle(gh, POLICY, REPO, apply=True, runner=runner, is_enabled=(False, "desligado"))
    assert out == {"enabled": False, "reason": "desligado", "prs": []} and gh.calls == [] and runner.calls == []


def test_the_plan_never_merges_even_when_the_decision_is_merge():
    gh, runner = Gh(), Runner()
    out = am.cycle(gh, POLICY, REPO, apply=False, runner=runner, is_enabled=ON)
    assert out["prs"][0]["code"] == "MERGE" and runner.calls == [] and "merged" not in out["prs"][0]


def test_apply_merges_with_match_head_commit_and_the_executor_environment(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "ghp_" + "x" * 30)
    gh, runner = Gh(), Runner()
    out = am.cycle(gh, POLICY, REPO, apply=True, runner=runner, is_enabled=ON)
    argv, kw = runner.calls[0]
    assert out["prs"][0]["merged"] is True and argv[:4] == ["gh", "pr", "merge", "7"]
    assert argv[argv.index("--match-head-commit") + 1] == HEAD and "--merge" in argv and "--admin" not in argv and "--auto" not in argv
    assert "GH_TOKEN" not in kw["env"]


def test_a_head_that_moves_between_the_decision_and_the_merge_is_not_merged():
    gh, runner = Gh(fresh_head=OLD), Runner()
    out = am.cycle(gh, POLICY, REPO, apply=True, runner=runner, is_enabled=ON)
    assert out["prs"][0]["code"] == "WAIT" and runner.calls == []


def test_a_refused_merge_from_github_is_reported_not_hidden():
    out = am.cycle(Gh(), POLICY, REPO, apply=True, runner=Runner(rc=1, err="not mergeable: protecao"), is_enabled=ON)
    assert out["prs"][0]["merged"] is False and "recusado" in out["prs"][0]["merge_message"]


def test_a_github_failure_is_an_error_row_and_never_a_merge():
    runner = Runner()
    out = am.cycle(Gh(boom=RuntimeError("502")), POLICY, REPO, apply=True, runner=runner, is_enabled=ON)
    assert out["prs"][0]["code"] == "ERROR" and "listagem" in out["prs"][0]["reasons"][0]
    assert runner.calls == []


def test_a_failure_while_gathering_the_facts_of_one_pr_is_an_error_row_and_never_a_merge():
    class Half(Gh):
        def __call__(self, path):
            if path.endswith("/files?per_page=100&page=1") or "/files" in path:
                raise RuntimeError("502 nos arquivos")
            return super().__call__(path)
    runner = Runner()
    out = am.cycle(Half(), POLICY, REPO, apply=True, runner=runner, is_enabled=ON)
    assert out["prs"][0]["code"] == "ERROR" and runner.calls == []


def test_only_prs_with_the_automerge_label_are_candidates():
    gh, runner = Gh(labelled=False), Runner()
    assert am.cycle(gh, POLICY, REPO, apply=True, runner=runner, is_enabled=ON)["prs"] == [] and runner.calls == []


def test_merge_refuses_a_head_that_is_not_a_full_sha():
    ok, msg = am.merge(7, "main", REPO, runner=Runner())
    assert ok is False and "invalido" in msg


def test_the_merge_command_has_no_admin_bypass_flags():
    import inspect
    src = inspect.getsource(am.merge)
    assert "--admin" not in src and "--auto" not in src and "--squash" not in src
