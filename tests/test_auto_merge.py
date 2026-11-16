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
            "labels": [], "body": "Refs #5\n"}
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


def strong(head=HEAD, pr_number=7, repo=REPO, verdict="APPROVE"):
    return f"Codex CLI (revisor independente) — HEAD {head} — confianca HIGH\n<!-- fp060-outbox-key:review:{repo}#{pr_number}:{head}:{verdict} -->"


STRONG = strong()


def approval(state="APPROVED", user="fmmodesto", commit=HEAD, body="ok"):
    return {"id": 11, "user": {"login": user}, "state": state, "commit_id": commit, "body": body}


def issues(labels=(), state="open"):
    return {5: {"number": 5, "state": state, "labels": [{"name": n} for n in labels]}}


def decide(**kw):
    args = {"pr": pr(), "files": files(), "runs": runs(), "reviews": [approval()], "issues": issues(), "policy": POLICY, "cfg": CFG, "is_enabled": ON}
    args.update(kw)
    return am.decide(args.pop("pr"), args.pop("files"), args.pop("runs"), args.pop("reviews"), args.pop("issues"), args.pop("policy"), args.pop("cfg"), **args)


# ----------------------------------------------------------------------------------------------------------------- caminho feliz
def test_all_gates_green_with_an_independent_approval_on_the_exact_head_merges_without_any_manual_label():
    d = decide()
    assert d.code == "MERGE" and HEAD[:12] in d.reasons[0]
    assert decide(pr=pr(labels=[]), issues=issues(labels=())).code == "MERGE"                    # nenhuma label manual de autorizacao


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
    ("human_label", {"pr": pr(labels=[{"name": "visual-review"}])}, "decisao humana"),
    ("security_label", {"pr": pr(labels=[{"name": "security"}])}, "decisao humana"),
    ("governance_label", {"pr": pr(labels=[{"name": "governance"}])}, "decisao humana"),
    ("no_refs", {"pr": pr(body="sem referencia")}, "Refs"),
    ("issue_missing", {"issues": {}}, "inexistente"),
    ("issue_closed", {"issues": issues(state="closed")}, "inexistente ou fechada"),
    ("issue_human", {"issues": issues(labels=("aprovação-humana-pendente",))}, "decisao humana"),
    ("issue_blocked", {"issues": issues(labels=("blocked",))}, "decisao humana"),
    ("no_files", {"files": []}, "sem arquivos"),
    ("conflict", {"pr": pr(mergeable_state="dirty")}, "conflito"),
    ("ci_failed", {"runs": runs(bad=sorted(lifecycle.MANDATORY_CHECKS)[0])}, "reprovados"),
    ("changes_requested", {"reviews": [approval(state="CHANGES_REQUESTED")]}, "pede mudancas"),
])
def test_a_human_decision_or_a_hard_failure_refuses_the_merge(name, kw, needle):
    d = decide(**kw)
    assert d.code == "REFUSE" and any(needle in r for r in d.reasons), d


AUTONOMOUS = [{"name": CFG.label}]
CRITICAL = ["tools/orchestration/event_executor.py", "tools/validation/backlog_gate.py", "core/plan_frame.py", "tools/rooms/capability_catalog.v1.json"]


@pytest.mark.parametrize("path", [".github/workflows/ci.yml", "docs/governance/review_policy.json", ".claude/CLAUDE.md", "docs/adr/0001.md"])
@pytest.mark.parametrize("labels", [[], AUTONOMOUS])
def test_governance_paths_always_need_a_human_even_with_a_strong_approval(path, labels):
    d = decide(pr=pr(labels=labels), files=files("docs/x.md", path), reviews=[approval(body=STRONG)], issues=issues(labels=(am.GPT_LABEL,)))
    assert d.code == "REFUSE" and any("governanca" in r for r in d.reasons)


@pytest.mark.parametrize("path", CRITICAL)
def test_an_autonomous_executor_pr_never_merges_on_a_critical_path(path):
    d = decide(pr=pr(labels=AUTONOMOUS), files=files("docs/x.md", path), reviews=[approval(body=STRONG)], issues=issues(labels=(am.GPT_LABEL,)))
    assert d.code == "REFUSE" and any("path_critico" in r for r in d.reasons)


@pytest.mark.parametrize("path", CRITICAL)
def test_a_technical_pr_on_a_critical_path_needs_the_reinforced_review(path):
    ok = decide(files=files("docs/x.md", path), reviews=[approval(body=STRONG)], issues=issues(labels=(am.GPT_LABEL,)))
    assert ok.code == "MERGE"
    plain_review = decide(files=files(path), reviews=[approval(body="ok")], issues=issues(labels=(am.GPT_LABEL,)))
    assert plain_review.code == "WAIT" and any("reforcada" in r for r in plain_review.reasons)
    only_high = decide(files=files(path), reviews=[approval(body="confianca HIGH sem marcador")], issues=issues(labels=(am.GPT_LABEL,)))
    assert only_high.code == "WAIT"
    no_label = decide(files=files(path), reviews=[approval(body=STRONG)], issues=issues(labels=()))
    assert no_label.code == "WAIT" and any(am.GPT_LABEL in r for r in no_label.reasons)


def test_the_diff_ceilings_bind_the_autonomous_pr_but_not_a_technical_one():
    many = files(*[f"docs/f{i}.md" for i in range(CFG.max_files + 1)])
    assert any("max_files" in r for r in decide(pr=pr(labels=AUTONOMOUS), files=many).reasons)
    assert any("max_lines" in r for r in decide(pr=pr(labels=AUTONOMOUS), files=files("docs/x.md", add=CFG.max_lines, rem=1)).reasons)
    assert decide(files=many).code == "MERGE" and decide(files=files("docs/x.md", add=5000, rem=1)).code == "MERGE"


def test_binary_files_and_file_types_refuse_for_every_pr():
    binary = [{"filename": "docs/a.png", "additions": 0, "deletions": 0, "changes": 0, "status": "added"}]
    d = decide(files=binary)
    assert d.code == "REFUSE" and any("binario" in r for r in d.reasons) and any("tipo nao permitido" in r for r in d.reasons)
    assert any("tipo nao permitido" in r for r in decide(files=files("artifacts/x.skp")).reasons)
    assert any("tipo nao permitido" in r for r in decide(pr=pr(labels=AUTONOMOUS), files=files("artifacts/x.skp")).reasons)


def test_a_rename_out_of_a_governance_path_still_counts_the_origin():
    renamed = [{"filename": "docs/ok.md", "previous_filename": ".github/workflows/ci.yml", "additions": 0, "deletions": 0, "changes": 0, "patch": "", "status": "renamed"}]
    assert any("governanca" in r for r in decide(files=renamed).reasons)


def test_every_reason_is_reported_not_only_the_first():
    d = decide(pr=pr(draft=True, user={"login": "outro"}, labels=[{"name": "security"}]), issues={})
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
    def __init__(self, head=HEAD, fresh_head=None, boom=None, labelled=True, draft=False, **overrides):
        self.head, self.fresh_head, self.boom, self.labelled, self.overrides, self.calls = head, fresh_head, boom, labelled, overrides, []
        self.draft = draft
        self.pulls = 0

    def __call__(self, path):
        self.calls.append(path)
        if self.boom:
            raise self.boom
        if path.startswith(f"repos/{REPO}/pulls?state=open"):
            return [{"number": 7, "draft": self.draft, "user": {"login": "fmodesto30" if self.labelled else "outro"}, "labels": []}]
        if path == f"repos/{REPO}/pulls/7":
            self.pulls += 1
            sha = self.fresh_head if (self.fresh_head and self.pulls > 1) else self.head
            return pr(head={"sha": sha, "repo": {"full_name": REPO}}, **self.overrides)
        if path.startswith(f"repos/{REPO}/pulls/7/files"):
            return files()
        if path.startswith(f"repos/{REPO}/pulls/7/reviews"):
            return [approval(commit=self.head, body=strong(self.head))]
        if "check-runs" in path:
            return {"total_count": len(lifecycle.MANDATORY_CHECKS), "check_runs": runs()}
        if path == f"repos/{REPO}/issues/5":
            return issues(labels=(am.GPT_LABEL,))[5]
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


def test_only_open_non_draft_prs_of_the_executor_are_candidates():
    for gh in (Gh(labelled=False), Gh(draft=True)):
        runner = Runner()
        assert am.cycle(gh, POLICY, REPO, apply=True, runner=runner, is_enabled=ON)["prs"] == [] and runner.calls == []


def test_merge_refuses_a_head_that_is_not_a_full_sha():
    ok, msg = am.merge(7, "main", REPO, runner=Runner())
    assert ok is False and "invalido" in msg


def test_the_merge_command_has_no_admin_bypass_flags():
    import inspect
    src = inspect.getsource(am.merge)
    assert "--admin" not in src and "--auto" not in src and "--squash" not in src


# --------------------------------------------- revisao independente do #648 (Codex): marcador, TOCTOU, caminhos, paginacao
@pytest.mark.parametrize("name,body", [
    ("other_pr", strong(pr_number=8)), ("other_head", strong(head="c" * 40)), ("other_repo", strong(repo="x/y")),
    ("other_verdict", strong(verdict="REQUEST_CHANGES")), ("only_text", "confianca HIGH fp060-outbox-key:review: copiado"),
    ("no_confidence", f"<!-- fp060-outbox-key:review:{REPO}#7:{HEAD}:APPROVE -->"),
    ("marker_without_comment_syntax", f"confianca HIGH fp060-outbox-key:review:{REPO}#7:{HEAD}:APPROVE")])
def test_the_reinforced_marker_must_bind_repo_pr_head_and_verdict_exactly(name, body):
    d = decide(files=files(CRITICAL[0]), reviews=[approval(body=body)], issues=issues(labels=(am.GPT_LABEL,)))
    assert d.code == "WAIT" and any("reforcada" in r for r in d.reasons), (name, d)


def test_the_reinforced_review_must_be_on_the_exact_head_too():
    stale = approval(commit="c" * 40, body=strong())                                           # marcador certo, review em outro commit
    assert am.reinforced(stale, REPO, 7, HEAD) is False and am.reinforced(approval(body=strong()), REPO, 7, HEAD) is True


@pytest.mark.parametrize("path", ["Docs/governance/review_policy.json", "DOCS/GOVERNANCE/x.json", "docs\\governance\\x.json", "./docs/governance/x.json",
                                   ".GitHub/workflows/ci.yml", "docs/governance./x.json", ".Claude/CLAUDE.md", "docs/ADR/0001.md"])
def test_governance_prefixes_are_compared_after_the_same_normalization_as_the_executor_guards(path):
    d = decide(files=files("docs/x.md", path), reviews=[approval(body=strong())], issues=issues(labels=(am.GPT_LABEL,)))
    assert d.code == "REFUSE" and any("governanca" in r for r in d.reasons), (path, d)


@pytest.mark.parametrize("path", ["../x.py", "/etc/x.py", "C:/x.py"])
def test_an_unsafe_path_is_refused_not_normalized_away(path):
    d = decide(files=files(path))
    assert d.code == "REFUSE" and any("caminho invalido" in r for r in d.reasons)


class MovingGh(Gh):
    """Os fatos mudam DEPOIS da primeira decisao, com o HEAD constante."""
    def __init__(self, change, **kw):
        super().__init__(**kw)
        self.change, self.reads = change, 0

    def __call__(self, path):
        if path == f"repos/{REPO}/pulls/7":
            self.reads += 1
            if self.reads > 1 and self.change == "base":
                self.overrides = {**self.overrides, "base": {"ref": "release", "repo": {"full_name": REPO}}}
            if self.reads > 1 and self.change == "label":
                self.overrides = {**self.overrides, "labels": [{"name": "security"}]}
        if path == f"repos/{REPO}/issues/5" and self.reads > 1 and self.change == "issue":
            return issues(labels=(am.GPT_LABEL, "aprovação-humana-pendente"))[5]
        if path == f"repos/{REPO}/issues/5" and self.reads > 1 and self.change == "closed":
            return issues(state="closed")[5]
        return super().__call__(path)


@pytest.mark.parametrize("change", ["base", "label", "issue", "closed"])
def test_every_fact_is_decided_again_right_before_the_merge_not_only_the_head(change):
    gh, runner = MovingGh(change), Runner()
    out = am.cycle(gh, POLICY, REPO, apply=True, runner=runner, is_enabled=ON)
    assert out["prs"][0]["code"] == "WAIT" and "mudaram" in out["prs"][0]["reasons"][0] and runner.calls == []


def test_an_unchanged_world_still_merges_after_the_second_decision():
    runner = Runner()
    assert am.cycle(MovingGh("nada"), POLICY, REPO, apply=True, runner=runner, is_enabled=ON)["prs"][0]["merged"] is True and len(runner.calls) == 1


def test_complete_check_runs_refuses_a_partial_answer():
    def partial(path):
        return {"total_count": 9, "check_runs": runs()[:3]}
    with pytest.raises(RuntimeError, match="incompletos"):
        am.complete_check_runs(partial, REPO, HEAD)
    with pytest.raises(RuntimeError, match="malformada"):
        am.complete_check_runs(lambda p: {"check_runs": "x"}, REPO, HEAD)
    assert len(am.complete_check_runs(lambda p: {"total_count": 9, "check_runs": runs()}, REPO, HEAD)) == 9


def test_complete_list_refuses_a_non_list_answer():
    for bad in ({"a": 1}, None, ["texto"], "x"):
        with pytest.raises(RuntimeError):
            am.complete_list(lambda p, b=bad: b, "repos/o/r/pulls/7/files?per_page=100")


class Proc:
    def __init__(self, rc=0, out="", err=""):
        self.returncode, self.stdout, self.stderr = rc, out, err


def test_the_production_client_merges_every_page_of_lists_and_check_runs():
    import json as _json
    seen = []

    def runner(argv, **kw):
        seen.append(argv)
        return Proc(0, _json.dumps([[{"n": 1}, {"n": 2}], [{"n": 3}]]))
    assert am.slurp_client("repos/o/r/pulls/7/files?per_page=100", runner=runner, gh_bin="gh") == [{"n": 1}, {"n": 2}, {"n": 3}]
    assert "--slurp" in seen[0] and "--paginate" in seen[0]

    def cr(argv, **kw):
        return Proc(0, _json.dumps([{"total_count": 3, "check_runs": [{"name": "a"}, {"name": "b"}]}, {"total_count": 3, "check_runs": [{"name": "c"}]}]))
    merged = am.slurp_client("repos/o/r/commits/x/check-runs?per_page=100", runner=cr, gh_bin="gh")
    assert merged["total_count"] == 3 and [r["name"] for r in merged["check_runs"]] == ["a", "b", "c"]
    assert am.slurp_client("repos/o/r/pulls/7", runner=lambda a, **k: Proc(0, _json.dumps([{"number": 7}])), gh_bin="gh") == {"number": 7}


@pytest.mark.parametrize("proc", [Proc(1, "", "boom"), Proc(0, "[]"), Proc(0, "nao json"), Proc(0, '[[1], {"a": 1}]')])
def test_the_production_client_fails_closed_on_errors_and_odd_shapes(proc):
    with pytest.raises((RuntimeError, ValueError)):
        am.slurp_client("repos/o/r/pulls", runner=lambda a, **k: proc, gh_bin="gh")
