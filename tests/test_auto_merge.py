"""FP-060 MT-15 (#647): merge automatico PROTEGIDO. Desligado por padrao; cada recusa e cada espera tem teste; o GitHub e injetado."""
from __future__ import annotations

from pathlib import Path

import pytest

from tools.orchestration import auto_merge as am
from tools.orchestration import execution_guards as guards
from tools.orchestration import lifecycle

HEAD, OLD = "a" * 40, "b" * 40
REPO = "o/r"
POLICY = {"reviewers": ["fmmodesto"], "executor_logins": ["fmodesto30"]}
CFG = guards.load_config()
ON = (True, "")


def ALWAYS(repo, number, head, review_id=None):
    """Proveniencia concedida (o registro local do publicador confirma): os testes de decisao pura nao constroem um EventStore."""
    return True


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
    args["pr"] = {"changed_files": len(args["files"]), **args["pr"]}                       # a API declara quantos arquivos o PR tem; o helper acompanha a lista
    args.setdefault("provenance", ALWAYS)
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
GOOD_PROTECTION = {"required_pull_request_reviews": {"required_approving_review_count": 1, "dismiss_stale_reviews": True},
                   "enforce_admins": {"enabled": True}, "required_status_checks": {"contexts": sorted(lifecycle.MANDATORY_CHECKS)}}


class Gh:
    def __init__(self, head=HEAD, fresh_head=None, boom=None, labelled=True, draft=False, protection=None, protection_boom=None, rules=None, rules_boom=None,
                 scheduled_only=False, mutate_last=None, cancel_works=True, merge_lands=True, issue_flip_at=None, merged_head=None, mutate_pre=None, **overrides):
        self.issue_flip_at, self.issue_reads, self.merged_head = issue_flip_at, 0, merged_head
        self.merge_lands = merge_lands                                                       # False: o comando NAO produziu merge nenhum (recusa/queda antes de aplicar)
        self.head, self.fresh_head, self.boom, self.labelled, self.overrides, self.calls = head, fresh_head, boom, labelled, overrides, []
        self.draft = draft
        self.pulls = 0
        self.protection = GOOD_PROTECTION if protection is None else protection
        self.protection_boom = protection_boom
        self.rules, self.rules_boom, self.scheduled_only = [] if rules is None else rules, rules_boom, scheduled_only
        self.mutate_last, self.cancel_works, self.mutate_pre = mutate_last, cancel_works, mutate_pre

    def __call__(self, path):
        self.calls.append(path)
        if self.boom:
            raise self.boom
        if path.startswith(f"repos/{REPO}/pulls?state=open"):
            return [{"number": 7, "draft": self.draft, "user": {"login": "fmodesto30" if self.labelled else "outro"}, "labels": []}]
        if path == f"repos/{REPO}/pulls/7":
            self.pulls += 1
            sha = self.fresh_head if (self.fresh_head and self.pulls > 1) else self.head
            if self.pulls == 3 and self.mutate_last:                                               # a 3a leitura e a ULTIMA antes do merge: algo muda nela
                return pr(head={"sha": sha, "repo": {"full_name": REPO}}, **{"changed_files": 1, **self.overrides, **self.mutate_last})
            if self.pulls == 4:                                                                    # a 4a leitura e a releitura SO do PR imediatamente antes do comando
                return pr(head={"sha": sha, "repo": {"full_name": REPO}}, **{"changed_files": 1, **self.overrides, **(self.mutate_pre or {})})
            if self.pulls >= 5:                                                                    # a 5a leitura e a CONFIRMACAO depois do comando de merge; a 6a, a releitura apos cancelar
                if self.scheduled_only:
                    cancelled = self.pulls >= 6 and self.cancel_works
                    return pr(head={"sha": sha, "repo": {"full_name": REPO}}, auto_merge=None if cancelled else {"enabled_by": "x"}, changed_files=1)
                if self.merge_lands:
                    return pr(head={"sha": self.merged_head or sha, "repo": {"full_name": REPO}}, merged=True, state="closed", merge_commit_sha="c" * 40, changed_files=1)
                return pr(head={"sha": sha, "repo": {"full_name": REPO}}, changed_files=1)
            return pr(head={"sha": sha, "repo": {"full_name": REPO}}, **{"changed_files": 1, **self.overrides})
        if path.startswith(f"repos/{REPO}/pulls/7/files"):
            return files()
        if path.startswith(f"repos/{REPO}/pulls/7/reviews"):
            return [approval(commit=self.head, body=strong(self.head))]
        if "check-runs" in path:
            return {"total_count": len(lifecycle.MANDATORY_CHECKS), "check_runs": runs()}
        if path == f"repos/{REPO}/issues/5":
            self.issue_reads += 1
            if self.issue_flip_at and self.issue_reads >= self.issue_flip_at:                       # a Issue ganha label de decisao humana depois de algumas leituras
                return issues(labels=(am.GPT_LABEL, "aprovação-humana-pendente"))[5]
            return issues(labels=(am.GPT_LABEL,))[5]
        if path == f"repos/{REPO}/rules/branches/develop":
            if self.rules_boom:
                raise self.rules_boom
            return self.rules
        if path == f"repos/{REPO}/branches/develop/protection":
            if self.protection_boom:
                raise self.protection_boom
            return self.protection
        raise AssertionError(path)


class Runner:
    """`calls` = so as chamadas de MERGE; `who_calls` = a consulta de identidade (`gh api user`), que responde `login` com o MESMO ambiente do merge."""
    def __init__(self, rc=0, err="", login="fmodesto30", who_rc=0, on_who=None):
        self.rc, self.err, self.calls = rc, err, []
        self.login, self.who_rc, self.who_calls, self.on_who = login, who_rc, [], on_who

    def __call__(self, argv, **kw):
        if argv[1:3] == ["api", "user"]:
            self.who_calls.append((argv, kw))
            if self.on_who:
                self.on_who()
            return type("P", (), {"returncode": self.who_rc, "stdout": self.login + "\n", "stderr": ""})()
        self.calls.append((argv, kw))
        return type("P", (), {"returncode": self.rc, "stdout": "", "stderr": self.err})()


def test_a_disabled_cycle_reads_nothing_and_merges_nothing():
    gh, runner = Gh(), Runner()
    out = am.cycle(gh, POLICY, REPO, apply=True, runner=runner, is_enabled=(False, "desligado"))
    assert out == {"enabled": False, "reason": "desligado", "prs": []} and gh.calls == [] and runner.calls == []


def test_the_plan_never_merges_even_when_the_decision_is_merge():
    gh, runner = Gh(), Runner()
    out = am.cycle(gh, POLICY, REPO, apply=False, runner=runner, is_enabled=ON, provenance=ALWAYS)
    assert out["prs"][0]["code"] == "MERGE" and runner.calls == [] and "merged" not in out["prs"][0]


def test_apply_merges_with_match_head_commit_and_the_executor_environment(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "ghp_" + "x" * 30)
    gh, runner = Gh(), Runner()
    out = am.cycle(gh, POLICY, REPO, apply=True, runner=runner, is_enabled=ON, provenance=ALWAYS)
    argv, kw = runner.calls[0]
    assert out["prs"][0]["merged"] is True and argv[:4] == ["gh", "pr", "merge", "7"]
    assert argv[argv.index("--match-head-commit") + 1] == HEAD and "--merge" in argv and "--admin" not in argv and "--auto" not in argv
    assert "GH_TOKEN" not in kw["env"]


def test_a_head_that_moves_between_the_decision_and_the_merge_is_not_merged():
    gh, runner = Gh(fresh_head=OLD), Runner()
    out = am.cycle(gh, POLICY, REPO, apply=True, runner=runner, is_enabled=ON, provenance=ALWAYS)
    assert out["prs"][0]["code"] == "WAIT" and runner.calls == []


def test_a_refused_merge_from_github_is_reported_not_hidden():
    out = am.cycle(Gh(merge_lands=False), POLICY, REPO, apply=True, runner=Runner(rc=1, err="not mergeable: protecao"), is_enabled=ON, provenance=ALWAYS)
    assert out["prs"][0]["merged"] is False and "recusado" in out["prs"][0]["merge_message"]


def test_a_github_failure_is_an_error_row_and_never_a_merge():
    runner = Runner()
    out = am.cycle(Gh(boom=RuntimeError("502")), POLICY, REPO, apply=True, runner=runner, is_enabled=ON, provenance=ALWAYS)
    assert out["prs"][0]["code"] == "ERROR" and "listagem" in out["prs"][0]["reasons"][0]
    assert runner.calls == []


def test_a_failure_while_gathering_the_facts_of_one_pr_is_an_error_row_and_never_a_merge():
    class Half(Gh):
        def __call__(self, path):
            if path.endswith("/files?per_page=100&page=1") or "/files" in path:
                raise RuntimeError("502 nos arquivos")
            return super().__call__(path)
    runner = Runner()
    out = am.cycle(Half(), POLICY, REPO, apply=True, runner=runner, is_enabled=ON, provenance=ALWAYS)
    assert out["prs"][0]["code"] == "ERROR" and runner.calls == []


def test_only_open_non_draft_prs_of_the_executor_are_candidates():
    for gh in (Gh(labelled=False), Gh(draft=True)):
        runner = Runner()
        assert am.cycle(gh, POLICY, REPO, apply=True, runner=runner, is_enabled=ON, provenance=ALWAYS)["prs"] == [] and runner.calls == []


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
    assert am.reinforced(stale, REPO, 7, HEAD, ALWAYS) is False and am.reinforced(approval(body=strong()), REPO, 7, HEAD, ALWAYS) is True


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
    out = am.cycle(gh, POLICY, REPO, apply=True, runner=runner, is_enabled=ON, provenance=ALWAYS)
    assert out["prs"][0]["code"] == "WAIT" and "mudaram" in out["prs"][0]["reasons"][0] and runner.calls == []


def test_an_unchanged_world_still_merges_after_the_second_decision():
    runner = Runner()
    assert am.cycle(MovingGh("nada"), POLICY, REPO, apply=True, runner=runner, is_enabled=ON, provenance=ALWAYS)["prs"][0]["merged"] is True and len(runner.calls) == 1


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


# -- achados da 3a revisao do Codex: lista de arquivos completa, identidade do gh no ambiente do merge, interruptor relido, marcador real ----------
@pytest.mark.parametrize("declared", [None, 0, 2, 3001, "1", True])
def test_a_file_list_that_is_not_proven_complete_is_refused(declared):
    target = pr(changed_files=declared) if declared is not None else pr()                       # None: o PR NAO traz `changed_files`
    d = am.decide(target, files(), runs(), [approval()], issues(), POLICY, CFG, ON)
    assert d.code == "REFUSE" and any("nao comprovada completa" in r for r in d.reasons)


def test_a_pr_above_the_api_cap_cannot_hide_a_governance_path_behind_a_truncated_list():
    listed = files(*[f"docs/a{n}.md" for n in range(am.FILES_API_CAP)])                          # a API devolve no maximo 3000 e omite o resto
    big = pr(changed_files=am.FILES_API_CAP + 40)                                                 # o PR de verdade tem 3040 (os 40 ocultos incluem .github/)
    d = am.decide(big, listed, runs(), [approval(body=STRONG)], issues(labels=(am.GPT_LABEL,)), POLICY, CFG, ON)
    assert d.code == "REFUSE" and any("nao comprovada completa" in r for r in d.reasons)
    exact = am.decide(pr(changed_files=am.FILES_API_CAP), listed, runs(), [approval(body=STRONG)], issues(labels=(am.GPT_LABEL,)), POLICY, CFG, ON)
    assert not any("nao comprovada completa" in r for r in exact.reasons)                         # declarado == recebido == 3000: o PR tem exatamente isso


def test_the_merge_runs_only_after_the_gh_identity_is_verified_in_the_same_environment(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "ghp_" + "x" * 30)
    runner = Runner()
    out = am.cycle(Gh(), POLICY, REPO, apply=True, runner=runner, is_enabled=ON, provenance=ALWAYS)
    assert out["prs"][0]["merged"] is True and len(runner.who_calls) == 1 and len(runner.calls) == 1
    who_argv, who_kw = runner.who_calls[0]
    assert who_argv[1:4] == ["api", "user", "--jq"] and "GH_TOKEN" not in who_kw["env"]               # consulta com o ambiente do executor (sem token de env)
    assert who_kw["env"] == runner.calls[0][1]["env"]                                                # exatamente o mesmo ambiente do merge


@pytest.mark.parametrize("login", ["fmmodesto", "FMMODESTO", "alguem-com-bypass", ""])
def test_a_gh_authenticated_as_a_reviewer_or_anyone_else_never_merges(login):
    runner = Runner(login=login)
    out = am.cycle(Gh(), POLICY, REPO, apply=True, runner=runner, is_enabled=ON, provenance=ALWAYS)
    assert out["prs"][0]["code"] == "REFUSE" and runner.calls == [] and "merged" not in out["prs"][0]


def test_a_failed_identity_lookup_never_merges():
    runner = Runner(who_rc=1)
    out = am.cycle(Gh(), POLICY, REPO, apply=True, runner=runner, is_enabled=ON, provenance=ALWAYS)
    assert out["prs"][0]["code"] == "REFUSE" and "nao verificada" in out["prs"][0]["reasons"][0] and runner.calls == []


def test_an_executor_login_that_is_also_a_reviewer_is_refused():
    ok, why = am.merge_identity({"reviewers": ["fmodesto30"], "executor_logins": ["fmodesto30"]}, Runner())
    assert ok is False and "revisor" in why


def test_the_identity_lookup_raising_is_a_refusal_not_a_crash():
    def boom(argv, **kw):
        raise OSError("gh sumiu")
    ok, why = am.merge_identity(POLICY, boom)
    assert ok is False and "nao verificada" in why


def test_the_kill_switch_is_read_again_before_each_merge_not_only_at_the_start(tmp_path, monkeypatch):
    monkeypatch.setenv("EVENT_BRIDGE_STATE_PATH", str(tmp_path / "gov" / "bridge.json"))
    monkeypatch.setenv(am.ENABLE_ENV, "1")
    runner = Runner(on_who=lambda: (am.kill_switch().parent.mkdir(parents=True, exist_ok=True), am.kill_switch().write_text("x", encoding="utf-8")))
    out = am.cycle(Gh(), POLICY, REPO, apply=True, runner=runner)                               # interruptor criado DURANTE a consulta de identidade (ate 60 s)
    assert all(r["code"] == "DISABLED" and "durante o ciclo" in r["reasons"][0] for r in out["prs"]) and runner.calls == []   # nenhum merge: o interruptor e relido depois dela


def test_the_kill_switch_created_between_the_second_decision_and_the_merge_blocks_that_merge(tmp_path, monkeypatch):
    monkeypatch.setenv("EVENT_BRIDGE_STATE_PATH", str(tmp_path / "gov" / "bridge.json"))
    monkeypatch.setenv(am.ENABLE_ENV, "1")

    class Flip(Gh):
        def __call__(self, path):
            out = super().__call__(path)
            if path == f"repos/{REPO}/pulls/7" and self.pulls == 2:                                  # a releitura de fatos: logo depois, o interruptor aparece
                am.kill_switch().parent.mkdir(parents=True, exist_ok=True)
                am.kill_switch().write_text("x", encoding="utf-8")
            return out
    runner = Runner()
    out = am.cycle(Flip(), POLICY, REPO, apply=True, runner=runner)
    assert out["prs"][0]["code"] == "DISABLED" and "durante o ciclo" in out["prs"][0]["reasons"][0] and runner.calls == []


# O corpo REAL de um APPROVE publicado pelo fluxo de producao (PR #654, revisor fmmodesto): texto do parecer + marcador do outbox acrescentado na publicacao
REAL_PUBLISHED_APPROVE = (
    "Codex CLI (revisor independente) — HEAD 998f91cdd16675a6c305dee10b39ad07254c3d99 — confianca HIGH\n"
    "Testes revistos: tests/test_event_bridge.py\n\n"
    "<!-- fp060-outbox-key:review:GFCDOTA/sketchup-mcp#654:998f91cdd16675a6c305dee10b39ad07254c3d99:APPROVE -->")


def test_the_reinforced_check_accepts_the_real_body_that_the_production_publisher_posts():
    head = "998f91cdd16675a6c305dee10b39ad07254c3d99"
    review = approval(commit=head, body=REAL_PUBLISHED_APPROVE)
    assert am.reinforced(review, "GFCDOTA/sketchup-mcp", 654, head, ALWAYS) is True
    assert am.reinforced(review, "GFCDOTA/sketchup-mcp", 655, head, ALWAYS) is False                       # outro PR
    assert am.reinforced(review, "GFCDOTA/other", 654, head, ALWAYS) is False                              # outro repositorio


def test_the_marker_is_what_the_outbox_target_appends_to_the_review_body():
    target = pytest.importorskip("tools.orchestration.github_review_target", reason="o publicador do outbox ainda nao esta nesta base (pilha #617)")
    head = "a" * 40
    key = f"review:{REPO}#7:{head}:APPROVE"
    body = f"Codex CLI (revisor independente) — HEAD {head} — confianca HIGH\n\n{target.marker(key)}"
    assert am.reinforced(approval(commit=head, body=body), REPO, 7, head, ALWAYS) is True


# -- a protecao da branch precisa EXIGIR aprovacao independente antes de qualquer merge automatico (diretriz do proprietario) -----------------------------
def test_with_a_protection_that_requires_approval_the_merge_goes_ahead():
    runner = Runner()
    out = am.cycle(Gh(), POLICY, REPO, apply=True, runner=runner, is_enabled=ON, provenance=ALWAYS)
    assert out["prs"][0]["merged"] is True and am.protection_gaps(Gh(), REPO) == []


@pytest.mark.parametrize("protection, needle", [
    ({"enforce_admins": {"enabled": True}}, "nao exige aprovacao"),                                                   # a configuracao REAL de hoje: so checks
    ({"required_pull_request_reviews": {"required_approving_review_count": 0, "dismiss_stale_reviews": True}, "enforce_admins": {"enabled": True}}, "nao exige aprovacao"),
    ({"required_pull_request_reviews": {"required_approving_review_count": True, "dismiss_stale_reviews": True}, "enforce_admins": {"enabled": True}}, "nao exige aprovacao"),
    ({"required_pull_request_reviews": {"required_approving_review_count": 1}, "enforce_admins": {"enabled": True}}, "dismiss_stale_reviews"),
    ({"required_pull_request_reviews": {"required_approving_review_count": 1, "dismiss_stale_reviews": True}, "enforce_admins": {"enabled": False}}, "administradores"),
    ({"required_pull_request_reviews": {"required_approving_review_count": 1, "dismiss_stale_reviews": True}}, "administradores"),
])
def test_a_protection_that_would_allow_a_merge_without_independent_review_blocks_the_automatic_merge(protection, needle):
    runner = Runner()
    plan = am.cycle(Gh(protection=protection), POLICY, REPO, apply=False, runner=runner, is_enabled=ON, provenance=ALWAYS)
    assert plan["prs"][0]["code"] == "WAIT" and any(needle in r for r in plan["prs"][0]["reasons"])                    # o plano ja mostra o motivo
    out = am.cycle(Gh(protection=protection), POLICY, REPO, apply=True, runner=runner, is_enabled=ON, provenance=ALWAYS)
    assert out["prs"][0]["code"] == "WAIT" and runner.calls == [] and runner.who_calls == []                           # e o merge nao acontece, mesmo com CI verde e aprovacao


@pytest.mark.parametrize("boom", [RuntimeError("403 sem permissao"), OSError("rede"), ValueError("json")])
def test_an_unreadable_protection_is_fail_closed(boom):
    runner = Runner()
    out = am.cycle(Gh(protection_boom=boom), POLICY, REPO, apply=True, runner=runner, is_enabled=ON, provenance=ALWAYS)
    assert out["prs"][0]["code"] == "WAIT" and "nao pode ser lida" in out["prs"][0]["reasons"][0] and runner.calls == []


def test_a_protection_in_an_unexpected_shape_is_fail_closed():
    assert any("formato inesperado" in g for g in am.protection_gaps(lambda p: ["x"], REPO))


def test_a_protection_removed_between_the_decision_and_the_merge_blocks_that_merge():
    class Drops(Gh):
        def __call__(self, path):
            if path.endswith("/protection") and self.pulls >= 2:
                return {"enforce_admins": {"enabled": True}}                                                          # a exigencia de aprovacao sumiu depois da 1a decisao
            return super().__call__(path)
    runner = Runner()
    out = am.cycle(Drops(), POLICY, REPO, apply=True, runner=runner, is_enabled=ON, provenance=ALWAYS)
    assert out["prs"][0]["code"] == "WAIT" and "nao exige aprovacao" in out["prs"][0]["reasons"][0] and runner.calls == []


def test_the_module_never_writes_branch_protection():
    source = Path(am.__file__).read_text(encoding="utf-8")
    assert "branches/{base}/protection" in source and "-X" not in source and "PUT" not in source and "PATCH" not in source


# -- 4a revisao do Codex (#648): fila de merge, confirmacao do merge, ordem das leituras e renomeacao -----------------------------------------------
def test_an_exit_zero_that_only_scheduled_the_merge_is_not_reported_as_merged():
    runner = Runner()
    out = am.cycle(Gh(scheduled_only=True), POLICY, REPO, apply=True, runner=runner, is_enabled=ON, provenance=ALWAYS)
    row = out["prs"][0]
    assert row["merged"] is False and "NAO esta mesclado" in row["merge_message"]
    assert [c[0][1:3] for c in runner.calls] == [["pr", "merge"], ["pr", "merge"]] and "--disable-auto" in runner.calls[1][0]      # o agendamento foi CANCELADO
    assert "cancelado e confirmado" in row["merge_message"] and row["code"] == "MERGE"


def test_a_confirmed_merge_reports_the_merge_commit():
    out = am.cycle(Gh(), POLICY, REPO, apply=True, runner=Runner(), is_enabled=ON, provenance=ALWAYS)
    assert out["prs"][0]["merged"] is True and out["prs"][0]["merge_message"].startswith("mesclado em ccc")


@pytest.mark.parametrize("answer", [{"merged": False, "state": "open"}, {"merged": True, "base": {"ref": "release"}, "merge_commit_sha": "c" * 40},
                                    {"merged": True, "base": {"ref": "develop"}}, "texto",
                                    {"merged": False, "base": {"ref": "develop"}, "merge_commit_sha": "c" * 40}])
def test_the_merge_confirmation_needs_merged_true_the_right_base_and_a_merge_commit(answer):
    ok, msg = am.confirm_merged(lambda p: answer, REPO, 7, HEAD)
    assert ok is False and "nao conto" in msg or "NAO esta mesclado" in msg


def test_a_failure_confirming_the_merge_is_not_a_success():
    def boom(path):
        raise RuntimeError("502")
    assert am.confirm_merged(boom, REPO, 7, HEAD)[0] is False


def test_a_branch_with_a_merge_queue_blocks_the_automatic_merge():
    runner = Runner()
    out = am.cycle(Gh(rules=[{"type": "merge_queue"}]), POLICY, REPO, apply=True, runner=runner, is_enabled=ON, provenance=ALWAYS)
    assert out["prs"][0]["code"] == "WAIT" and any("merge queue" in r for r in out["prs"][0]["reasons"]) and runner.calls == []


@pytest.mark.parametrize("boom", [RuntimeError("403"), OSError("rede")])
def test_unreadable_branch_rules_are_fail_closed(boom):
    runner = Runner()
    out = am.cycle(Gh(rules_boom=boom), POLICY, REPO, apply=True, runner=runner, is_enabled=ON, provenance=ALWAYS)
    assert out["prs"][0]["code"] == "WAIT" and any("nao podem ser lidas" in r for r in out["prs"][0]["reasons"]) and runner.calls == []


def test_branch_rules_in_an_unexpected_shape_are_fail_closed():
    assert any("formato inesperado" in g for g in am.protection_gaps(lambda p: GOOD_PROTECTION if "protection" in p else {"x": 1}, REPO))


def test_a_pr_that_already_has_auto_merge_enabled_on_github_is_not_merged_by_this_module():
    runner = Runner()
    out = am.cycle(Gh(auto_merge={"enabled_by": "alguem"}), POLICY, REPO, apply=True, runner=runner, is_enabled=ON, provenance=ALWAYS)
    assert out["prs"][0]["code"] == "WAIT" and any("auto-merge" in r for r in out["prs"][0]["reasons"]) and runner.calls == []


def test_a_label_added_while_the_identity_is_being_checked_blocks_the_merge():
    """O merge so e decidido DEPOIS da consulta de identidade (a chamada lenta): uma label humana posta durante ela e vista."""
    gh = Gh()
    runner = Runner(on_who=lambda: gh.overrides.update(labels=[{"name": "security"}]))
    out = am.cycle(gh, POLICY, REPO, apply=True, runner=runner, is_enabled=ON, provenance=ALWAYS)
    assert out["prs"][0]["code"] == "WAIT" and runner.calls == []


def test_a_base_changed_while_the_identity_is_being_checked_blocks_the_merge():
    gh = Gh()
    runner = Runner(on_who=lambda: gh.overrides.update(base={"ref": "release", "repo": {"full_name": REPO}}))
    out = am.cycle(gh, POLICY, REPO, apply=True, runner=runner, is_enabled=ON, provenance=ALWAYS)
    assert out["prs"][0]["code"] == "WAIT" and runner.calls == []


@pytest.mark.parametrize("old, new", [("scripts/deploy.sh", "scripts/deploy.py"), ("docs/a.md", "bin/run.exe"), ("tools/x.py", "tools/x.sh")])
def test_a_rename_between_allowed_and_forbidden_types_is_refused(old, new):
    f = {"filename": new, "previous_filename": old, "status": "renamed", "additions": 0, "deletions": 0, "changes": 0, "patch": "@@"}
    d = decide(files=[f])
    assert d.code == "REFUSE" and any("tipo nao permitido" in r for r in d.reasons)


def test_a_rename_between_two_allowed_types_is_not_refused_for_type():
    f = {"filename": "docs/b.md", "previous_filename": "docs/a.md", "status": "renamed", "additions": 0, "deletions": 0, "changes": 0, "patch": "@@"}
    assert not any("tipo nao permitido" in r for r in decide(files=[f]).reasons)


# -- 5a revisao do Codex (#648): proveniencia fora do texto, ultima leitura, cancelamento do agendamento, remocao ambigua -------------------------------
def test_a_manual_approval_that_copies_the_public_marker_is_not_reinforced_without_provenance():
    manual = approval(body=strong())                                                                   # texto identico ao do publicador, escrito a mao
    assert am.reinforced(manual, REPO, 7, HEAD) is False and am.reinforced(manual, REPO, 7, HEAD, lambda *a: False) is False
    d = decide(files=files("tools/orchestration/x.py"), reviews=[manual], issues=issues(labels=(am.GPT_LABEL,)), provenance=lambda *a: False)
    assert d.code == "WAIT" and any("registro local" in r for r in d.reasons)
    assert decide(files=files("tools/orchestration/x.py"), reviews=[manual], issues=issues(labels=(am.GPT_LABEL,))).code == "MERGE"      # com proveniencia (ALWAYS): ok


def test_without_any_provenance_callable_a_critical_path_is_never_reinforced():
    assert am.reinforced(approval(body=strong()), REPO, 7, HEAD) is False


def test_the_outbox_provenance_reads_the_local_publisher_record_not_the_review_text(tmp_path):
    from tools.orchestration.event_store import EventStore
    store = EventStore(tmp_path / "e.db")
    key, job = f"review:{REPO}#7:{HEAD}:APPROVE", f"review:{REPO}#7"
    check = am.outbox_provenance(store)
    assert check(REPO, 7, HEAD) is False                                                                # sem registro
    eid, _ = store.publish("REVIEW_REQUESTED", key, job, {"pr": 7}, producer="codex_reviewer")
    assert check(REPO, 7, HEAD) is False                                                                # registrado mas ainda nao concluido (PENDING/RUNNING)
    store.complete(store.claim_by_id(eid, "w", 60), {"verdict": "APPROVE"})
    assert check(REPO, 7, HEAD) is True and check(REPO, 8, HEAD) is False and check(REPO, 7, OLD) is False and check("x/y", 7, HEAD) is False


def test_a_provenance_record_from_another_producer_does_not_count(tmp_path):
    from tools.orchestration.event_store import EventStore
    store = EventStore(tmp_path / "e.db")
    eid, _ = store.publish("REVIEW_REQUESTED", f"review:{REPO}#7:{HEAD}:APPROVE", f"review:{REPO}#7", {"pr": 7}, producer="alguem-falso")
    store.complete(store.claim_by_id(eid, "w", 60), {"verdict": "APPROVE"})
    assert am.outbox_provenance(store)(REPO, 7, HEAD) is False


def test_an_unreadable_provenance_store_is_no_proof():
    class Broken:
        def events(self, job_id=None):
            raise OSError("banco ilegivel")
    assert am.outbox_provenance(Broken())(REPO, 7, HEAD) is False


@pytest.mark.parametrize("mutation", [{"labels": [{"name": "security"}]}, {"base": {"ref": "release", "repo": {"full_name": REPO}}}, {"draft": True},
                                      {"body": "Refs #5\n\nRefs #5 (editado)"}, {"body": ""}, {"body": None}])
def test_the_last_read_of_the_pr_before_the_merge_blocks_a_change_of_base_labels_draft_or_body(mutation):
    runner = Runner()
    out = am.cycle(Gh(mutate_last=mutation), POLICY, REPO, apply=True, runner=runner, is_enabled=ON, provenance=ALWAYS)
    assert out["prs"][0]["code"] == "WAIT" and "ultima leitura" in out["prs"][0]["reasons"][0] and runner.calls == []


def test_a_scheduled_merge_that_cannot_be_cancelled_requires_intervention():
    runner = Runner()
    out = am.cycle(Gh(scheduled_only=True, cancel_works=False), POLICY, REPO, apply=True, runner=runner, is_enabled=ON, provenance=ALWAYS)
    row = out["prs"][0]
    assert row["code"] == "ERROR" and "REQUER INTERVENCAO" in row["reasons"][0] and row["merged"] is False


def test_cancel_scheduled_reports_a_failure_to_run_the_command():
    def boom(argv, **kw):
        raise OSError("gh sumiu")
    ok, why = am.cancel_scheduled(lambda p: {}, REPO, 7, POLICY, boom)
    assert ok is False and "REQUER INTERVENCAO" in why


@pytest.mark.parametrize("status", ["removed", "added", "modified"])
def test_a_file_without_patch_and_without_counts_is_ambiguous_in_every_status_and_refused(status):
    f = {"filename": "scripts/run.py", "status": status, "additions": 0, "deletions": 0, "changes": 0}          # sem `patch`: pode ser binario com extensao permitida
    d = decide(files=[f])
    assert d.code == "REFUSE" and any("binario" in r for r in d.reasons)


# -- 9a revisao do Codex (#648): o comando pode ter sido aceito mesmo quando a resposta se perdeu ------------------------------------------------------
class TimingOutRunner(Runner):
    def __call__(self, argv, **kw):
        if argv[1:3] == ["api", "user"] or "--disable-auto" in argv:
            return super().__call__(argv, **kw)
        self.calls.append((argv, kw))
        raise __import__("subprocess").TimeoutExpired(argv, 120)


@pytest.mark.parametrize("error", [TimeoutError("sem resposta"), OSError("conexao perdida")])
def test_a_merge_command_that_times_out_after_github_applied_it_is_reconciled_as_merged(error):
    class Boom(Runner):
        def __call__(self, argv, **kw):
            if argv[1:3] == ["api", "user"] or "--disable-auto" in argv:
                return super().__call__(argv, **kw)
            self.calls.append((argv, kw))
            raise error
    out = am.cycle(Gh(merge_lands=True), POLICY, REPO, apply=True, runner=Boom(), is_enabled=ON, provenance=ALWAYS)
    row = out["prs"][0]
    assert row["merged"] is True and row["code"] != "ERROR"                                         # o PR foi mesclado de fato: confirmado pelo remoto, nao dado como falha


def test_a_merge_command_that_times_out_and_left_the_pr_scheduled_cancels_and_confirms_it():
    runner = TimingOutRunner()
    out = am.cycle(Gh(scheduled_only=True), POLICY, REPO, apply=True, runner=runner, is_enabled=ON, provenance=ALWAYS)
    row = out["prs"][0]
    assert row["merged"] is False and row["code"] != "ERROR" and "cancelado" in row["merge_message"]


def test_a_merge_command_that_times_out_and_cannot_be_reconciled_demands_owner_intervention():
    out = am.cycle(Gh(scheduled_only=True, cancel_works=False), POLICY, REPO, apply=True, runner=TimingOutRunner(), is_enabled=ON, provenance=ALWAYS)
    row = out["prs"][0]
    assert row["merged"] is False and row["code"] == "ERROR" and "INTERVENCAO" in row["reasons"][0]


def test_a_merge_command_that_did_nothing_leaves_the_pr_untouched_without_an_error():
    out = am.cycle(Gh(merge_lands=False), POLICY, REPO, apply=True, runner=TimingOutRunner(), is_enabled=ON, provenance=ALWAYS)
    row = out["prs"][0]
    assert row["merged"] is False and row["code"] != "ERROR"


# -- 10a revisao do Codex (#648): interruptor depois da ultima leitura, Issues na ultima leitura, HEAD efetivamente mesclado ---------------------------
def test_a_kill_switch_created_during_the_last_remote_read_blocks_the_merge(monkeypatch):
    reads = {"n": 0}

    def switch():
        reads["n"] += 1                                                                              # 1: inicio do ciclo; 2: antes da ultima leitura; 3: DEPOIS dela
        return (False, "AUTOMERGE_DISABLED criado durante a ultima leitura") if reads["n"] >= 3 else (True, "")
    monkeypatch.setattr(am, "enabled", switch)
    runner = Runner()
    out = am.cycle(Gh(), POLICY, REPO, apply=True, runner=runner, provenance=ALWAYS)
    assert out["prs"][0]["code"] == "DISABLED" and "ultima leitura" in out["prs"][0]["reasons"][0] and runner.calls == [] and reads["n"] == 3


# -- 11a revisao do Codex (#648, 64bbc966): interruptor criado durante a releitura FINAL do PR (pr4) ----------------------------------------------------
def test_a_kill_switch_created_during_the_final_pr_reread_blocks_the_merge(monkeypatch):
    reads = {"n": 0}
    gh = Gh()

    def switch():
        reads["n"] += 1                                                                              # 4: depois da releitura final (pr4), imediatamente antes do merge
        return (False, "AUTOMERGE_DISABLED criado durante a releitura final") if reads["n"] >= 4 else (True, "")
    monkeypatch.setattr(am, "enabled", switch)
    runner = Runner()
    out = am.cycle(gh, POLICY, REPO, apply=True, runner=runner, provenance=ALWAYS)
    row = out["prs"][0]
    assert row["code"] == "DISABLED" and "releitura final" in row["reasons"][0] and runner.calls == [] and reads["n"] == 4
    assert gh.pulls == 4                                                                             # a releitura pr4 aconteceu ANTES da checagem que bloqueou


def test_an_issue_that_gains_a_human_decision_label_in_the_last_read_blocks_the_merge():
    runner = Runner()
    out = am.cycle(Gh(issue_flip_at=3), POLICY, REPO, apply=True, runner=runner, is_enabled=ON, provenance=ALWAYS)
    assert out["prs"][0]["code"] == "WAIT" and "Issues" in out["prs"][0]["reasons"][0] and runner.calls == []


def test_a_pr_merged_with_a_different_head_than_the_authorized_one_demands_owner_intervention():
    out = am.cycle(Gh(merged_head="d" * 40), POLICY, REPO, apply=True, runner=Runner(), is_enabled=ON, provenance=ALWAYS)
    row = out["prs"][0]
    assert row["merged"] is False and row["code"] == "ERROR" and "HEAD_DIVERGENTE" in row["reasons"][0] and "INTERVENCAO" in row["reasons"][0]


# -- 5a revisao do Codex (#648): releitura do PR antes do comando; merge durante o cancelamento; proveniencia do publicador REAL desta base ----------------
@pytest.mark.parametrize("change", [{"base": {"ref": "main", "repo": {"full_name": REPO}}}, {"labels": [{"name": "do-not-merge"}]},
                                    {"labels": [{"name": "aprovação-humana-pendente"}]}, {"body": "Refs #5\nRefs #99\n"}])
def test_a_base_or_label_change_after_the_slow_queries_of_the_last_read_is_caught_by_the_pre_merge_reread(monkeypatch, change):
    monkeypatch.setenv("GH_TOKEN", "ghp_" + "x" * 30)
    gh, runner = Gh(mutate_pre=change), Runner()
    out = am.cycle(gh, POLICY, REPO, apply=True, runner=runner, is_enabled=ON, provenance=ALWAYS)
    assert out["prs"][0]["code"] == "WAIT" and "depois das consultas" in out["prs"][0]["reasons"][0] and runner.calls == []


class _Done:
    returncode, stdout, stderr = 0, "", ""


def test_a_merge_landing_while_cancelling_is_confirmed_for_the_authorized_head():
    merged = pr(merged=True, state="closed", merge_commit_sha="c" * 40)
    ok, why = am.cancel_scheduled(lambda p: merged, REPO, 7, POLICY, lambda *a, **k: _Done(), head=HEAD)
    assert ok == am.MERGED_DURING_CANCEL and "conferido" in why


def test_a_merge_landing_while_cancelling_with_another_head_or_without_proof_requires_intervention():
    other = pr(merged=True, state="closed", merge_commit_sha="c" * 40, head={"sha": OLD, "repo": {"full_name": REPO}})
    ok, why = am.cancel_scheduled(lambda p: other, REPO, 7, POLICY, lambda *a, **k: _Done(), head=HEAD)
    assert ok is False and "INTERVENCAO" in why
    no_commit = pr(merged=True, state="closed")
    ok, why = am.cancel_scheduled(lambda p: no_commit, REPO, 7, POLICY, lambda *a, **k: _Done(), head=HEAD)
    assert ok is False and "INTERVENCAO" in why
    ok, why = am.cancel_scheduled(lambda p: pr(merged=True, state="closed", merge_commit_sha="c" * 40), REPO, 7, POLICY, lambda *a, **k: _Done())
    assert ok is False and "INTERVENCAO" in why                                                          # sem HEAD autorizado para conferir


GOOD_EVIDENCE = {"evidence": {"isolation": "os_sandbox", "tests_passed": True, "uncovered": [], "selected": ["tests/test_x.py"]}, "pkg": {"files": ["tests/test_x.py"]}}


def test_the_real_publisher_of_this_base_produces_the_marker_and_the_local_record_that_satisfy_the_reinforced_gate(tmp_path, monkeypatch):
    from tools.orchestration import codex_reviewer as cr
    from tools.orchestration.event_store import EventStore
    store = EventStore(tmp_path / "store.db")
    monkeypatch.setattr(cr.store_factory, "get_store", lambda: store)
    posted = {}

    def fake_run(argv, **kw):
        posted["body"] = next(a[len("body="):] for a in argv if str(a).startswith("body="))
        return type("P", (), {"returncode": 0, "stdout": "https://github.com/x/y/pull/7#pullrequestreview-1\n", "stderr": ""})()
    monkeypatch.setattr(cr.subprocess, "run", fake_run)
    v = {"pr": 7, "head_sha": HEAD, "verdict": "APPROVE", "confidence": "HIGH", "findings": [], "tests_reviewed": ["tests/test_x.py"], "files_reviewed": [{"path": "tests/test_x.py"}]}
    cr.publish(v, "tok", REPO, **GOOD_EVIDENCE)
    review = {**approval(commit=HEAD, body=posted["body"]), "id": 1}                                      # o id que o GitHub devolveu na publicacao
    assert am.reinforced(review, REPO, 7, HEAD, am.outbox_provenance(store)) is True                     # o fluxo REAL (marcador + registro local) satisfaz o gate
    assert am.reinforced(review, REPO, 7, HEAD, am.outbox_provenance(EventStore(tmp_path / "vazio.db"))) is False   # so o texto copiado nao basta
    cr.publish(v, "tok", REPO, **GOOD_EVIDENCE)                                                           # idempotente
    assert sum(1 for e in store.events() if e["producer"] == "codex_reviewer") == 1



def test_a_dismissed_codex_approval_does_not_lend_its_provenance_to_a_manual_review_copying_the_marker(tmp_path, monkeypatch):
    from tools.orchestration import codex_reviewer as cr
    from tools.orchestration.event_store import EventStore
    store = EventStore(tmp_path / "store.db")
    monkeypatch.setattr(cr.store_factory, "get_store", lambda: store)
    posted = {}

    def fake_run(argv, **kw):
        posted["body"] = next(a[len("body="):] for a in argv if str(a).startswith("body="))
        return type("P", (), {"returncode": 0, "stdout": "https://github.com/x/y/pull/7#pullrequestreview-111\n", "stderr": ""})()
    monkeypatch.setattr(cr.subprocess, "run", fake_run)
    cr.publish({"pr": 7, "head_sha": HEAD, "verdict": "APPROVE", "confidence": "HIGH", "findings": [], "tests_reviewed": ["tests/test_x.py"], "files_reviewed": [{"path": "tests/test_x.py"}]},
               "tok", REPO, **GOOD_EVIDENCE)
    codex_review = {**approval(commit=HEAD, body=posted["body"]), "id": 111}
    manual_copy = {**approval(commit=HEAD, body=posted["body"]), "id": 222}                                   # outro review, mesmo HEAD, marcador copiado
    check = am.outbox_provenance(store)
    assert am.reinforced(codex_review, REPO, 7, HEAD, check) is True
    assert am.reinforced(manual_copy, REPO, 7, HEAD, check) is False
    assert am.reinforced({k: v for k, v in codex_review.items() if k != "id"}, REPO, 7, HEAD, check) is False   # review sem id: sem prova


# -- 12a revisao do Codex (#648, 39b595c1): instrucoes de agente sao governanca; o servidor exige os checks; protecao relida apos a coleta final ---------
@pytest.mark.parametrize("path", ["CLAUDE.md", "claude.md", "tools/rooms/CLAUDE.md", "AGENTS.md", "apps/x/agents.md", "GEMINI.md", "CLAUDE.local.md",
                                  ".github/copilot-instructions.md", ".cursorrules", ".cursor/rules/x.mdc", ".windsurfrules"])
def test_agent_instruction_files_anywhere_are_governance_and_need_a_human(path):
    d = decide(files=files(path))
    assert d.code == "REFUSE" and any("governanca" in r for r in d.reasons), (path, d.reasons)


def test_a_file_that_only_mentions_claude_in_its_name_is_not_governance():
    assert decide(files=files("docs/claude_notes.md", "tools/claude_md_parser.py")).code == "MERGE"


@pytest.mark.parametrize("rsc", [{"contexts": []}, None, {}, {"contexts": ["pytest (py3.11)"]},
                                 {"contexts": sorted(lifecycle.MANDATORY_CHECKS - {"windows process supervisor"})}])
def test_a_protection_that_does_not_enforce_every_mandatory_check_on_the_server_blocks_the_merge(rsc):
    prot = {**GOOD_PROTECTION, "required_status_checks": rsc}
    runner = Runner()
    out = am.cycle(Gh(protection=prot), POLICY, REPO, apply=True, runner=runner, is_enabled=ON, provenance=ALWAYS)
    assert out["prs"][0]["code"] == "WAIT" and any("checks obrigatorios" in r for r in out["prs"][0]["reasons"]) and runner.calls == []


def test_mandatory_checks_listed_in_the_checks_array_also_count_as_enforced():
    prot = {**GOOD_PROTECTION, "required_status_checks": {"contexts": [], "checks": [{"context": c, "app_id": 15368} for c in sorted(lifecycle.MANDATORY_CHECKS)]}}
    assert am.protection_gaps(Gh(protection=prot), REPO) == []


def test_a_protection_removed_during_the_final_collection_blocks_the_merge():
    class DropsLate(Gh):
        def __call__(self, path):
            if path.endswith("/protection") and self.pulls >= 3:                                   # 3a leitura do PR = a coleta final; as duas checagens anteriores passaram
                return {"enforce_admins": {"enabled": True}}
            return super().__call__(path)
    gh, runner = DropsLate(), Runner()
    out = am.cycle(gh, POLICY, REPO, apply=True, runner=runner, is_enabled=ON, provenance=ALWAYS)
    row = out["prs"][0]
    assert row["code"] == "WAIT" and "coleta final" in row["reasons"][0] and runner.calls == [] and gh.pulls == 3


# -- 13a revisao do Codex (#648, 79ba2cda): a fronteira de publicacao valida a evidencia antes de postar e de gravar a proveniencia --------------------------
@pytest.mark.parametrize("kw", [{}, {"evidence": {"isolation": "os_sandbox", "tests_passed": True, "uncovered": [], "selected": ["tests/test_x.py"]}},
                                {"evidence": {"isolation": "env", "tests_passed": True, "uncovered": [], "selected": ["tests/test_x.py"]}, "pkg": {"files": ["tests/test_x.py"]}},
                                {"evidence": {"isolation": "os_sandbox", "tests_passed": False, "uncovered": [], "selected": ["tests/test_x.py"]}, "pkg": {"files": ["tests/test_x.py"]}},
                                {"evidence": {"isolation": "os_sandbox", "tests_passed": True, "uncovered": ["tools/y.py"], "selected": ["tests/test_x.py"]},
                                 "pkg": {"files": ["tests/test_x.py"]}},
                                {"evidence": {"isolation": "os_sandbox", "tests_passed": True, "uncovered": [], "selected": ["tests/test_x.py"]},
                                 "pkg": {"files": ["tests/test_x.py", "tools/nao_inspecionado.py"]}}])
def test_a_direct_approve_publish_without_valid_evidence_posts_nothing_and_records_no_provenance(tmp_path, monkeypatch, kw):
    from tools.orchestration import codex_reviewer as cr
    from tools.orchestration.event_store import EventStore
    store = EventStore(tmp_path / "store.db")
    monkeypatch.setattr(cr.store_factory, "get_store", lambda: store)
    calls = []
    monkeypatch.setattr(cr.subprocess, "run", lambda argv, **k: calls.append(argv))
    v = {"pr": 7, "head_sha": HEAD, "verdict": "APPROVE", "confidence": "HIGH", "findings": [], "tests_reviewed": ["tests/test_x.py"], "files_reviewed": [{"path": "tests/test_x.py"}]}
    with pytest.raises(cr.ReviewError):
        cr.publish(v, "tok", REPO, **kw)
    assert calls == [] and not [e for e in store.events() if e["producer"] == "codex_reviewer"]
    assert am.outbox_provenance(store)(REPO, 7, HEAD) is False


def test_a_request_changes_publish_needs_no_test_evidence():
    import inspect

    from tools.orchestration import codex_reviewer as cr
    assert "if event == \"APPROVE\":" in inspect.getsource(cr.publish)                                     # so o APPROVE exige a evidencia


def test_an_issue_that_gains_a_human_decision_label_after_the_final_collection_blocks_the_merge():
    gh, runner = Gh(issue_flip_at=4), Runner()                                                          # 4a leitura da Issue = depois da releitura final do PR (pr4)
    out = am.cycle(gh, POLICY, REPO, apply=True, runner=runner, is_enabled=ON, provenance=ALWAYS)
    row = out["prs"][0]
    assert row["code"] == "WAIT" and "depois da coleta final" in row["reasons"][0] and runner.calls == [] and gh.issue_reads == 4
