"""FP-060 MT-11 (#637), estagio 2: `IMPLEMENT_REQUESTED` -> branch -> Claude -> entrega guardada -> PR. Claude, GitHub, git e a entrega sao injetados;
o EventStore e real (arquivo temporario, relogio controlado)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.test_event_executor import POLICY, REPO
from tools.orchestration import event_bridge as eb
from tools.orchestration import event_executor as ex
from tools.orchestration import implement_worker as iw
from tools.orchestration import intake
from tools.orchestration import sqlite_source as sq
from tools.orchestration import store_factory as sf

BASE = "c" * 40
N = 5
TITLE, BODY = "Titulo da tarefa", "corpo da issue\n## Critérios de aceite\n- [ ] algo\n"
HASH = intake.spec_hash({"title": TITLE, "body": BODY})
KEY = f"implement:issue:{N}:{HASH}"
BRANCH = f"feat/issue-{N}-{HASH}"


class Clock:
    t = 1_000_000.0

    def __call__(self):
        return self.t


class Gh:
    def __init__(self, issue=None, prs=(), login="fmodesto30", boom=None):
        self.issue = {"number": N, "state": "open", "title": TITLE, "body": BODY,
                      "labels": [{"name": intake.AUTH_LABEL}, {"name": "spec:FP-060"}]} if issue is None else issue
        self.prs, self.login, self.boom, self.calls = list(prs), login, boom, []

    def __call__(self, path):
        self.calls.append(path)
        if self.boom:
            raise self.boom
        if path == "user":
            return {"login": self.login}
        if path == f"repos/{REPO}/issues/{N}":
            return self.issue
        if path.startswith(f"repos/{REPO}/pulls?state=open"):
            return self.prs
        raise AssertionError(path)


class Child:
    """O filho `claude`: grava o que recebeu e devolve um resultado stream-json."""
    def __init__(self, rc=0, result=None, err="", timed_out=False, boom=None):
        self.rc, self.err, self.timed_out, self.boom = rc, err, timed_out, boom
        self.result = {"type": "result", "is_error": False, "result": "ok"} if result is None else result
        self.calls = []

    def __call__(self, argv, cwd, env, stdin, timeout, cancel=None):
        self.calls.append({"argv": argv, "cwd": cwd, "env": env, "stdin": stdin, "timeout": timeout})
        if self.boom:
            raise self.boom
        return self.rc, json.dumps(self.result), self.err, self.timed_out


@pytest.fixture()
def clock():
    return Clock()


@pytest.fixture()
def world(tmp_path, monkeypatch, clock):
    monkeypatch.setenv("EVENT_BRIDGE_STATE_PATH", str(tmp_path / "gov" / "bridge.json"))
    monkeypatch.setenv("EXECUTION_STATE_PATH", str(tmp_path / "exec.json"))
    monkeypatch.setenv("BRIDGE_WORKTREE_ROOT", str(tmp_path / "wt"))
    monkeypatch.setenv("EVENT_STORE_DB_PATH", str(tmp_path / "store.db"))
    monkeypatch.setenv("GH_TOKEN", "ghp_" + "x" * 30)
    monkeypatch.setenv(sq.SOURCE_ENV, "sqlite")
    monkeypatch.setattr(ex, "WATCH_PID", None)
    sf.reset_store()
    sq.reset_claims()
    store = sf.get_store(tmp_path / "store.db", clock=clock)
    store.publish("IMPLEMENT_REQUESTED", KEY, f"issue:{N}", {"issue": N, "title": TITLE, "spec_hash": HASH, "spec": "FP-060", "fase": "P3"},
                  aggregate_type="issue", producer="intake")
    w = type("World", (), {})()
    w.store, w.tmp, w.prs, w.delivered, w.comments = store, tmp_path, [], [], []
    w.wt = tmp_path / "wt" / f"bridge-issue{N}"
    monkeypatch.setattr(iw, "prepare_worktree", lambda n, branch, root: (True, "", w.wt, BASE))
    monkeypatch.setattr(iw, "ensure_remote_branch", lambda wt, branch, base: ("CREATED", ""))
    monkeypatch.setattr(iw, "create_pr", lambda branch, title, issue, repo, extra_labels=(): (w.prs.append((branch, title, issue, tuple(extra_labels))) or 77, "https://x/pull/77"))
    monkeypatch.setattr(iw, "_comment_issue", lambda issue, repo, body: w.comments.append(body))
    monkeypatch.setattr(ex, "deliver", lambda wt, branch, base, py, item, **kw: (w.delivered.append({"branch": branch, "base": base, **kw}) or ("PUSHED", "1 arquivo")))
    yield w
    sf.reset_store()
    sq.reset_claims()


def run(world, gh=None, child=None):
    child = child or Child()
    gh = gh or Gh()
    return ex.process_one(gh, POLICY, REPO, True, child, "claude", None, None), gh, child


def event(world):
    return next(e for e in world.store.events() if e["idempotency_key"] == KEY)


# ------------------------------------------------------------------------------------------------------------ caminho feliz
def test_an_authorized_request_runs_claude_once_delivers_one_commit_and_opens_the_pr(world):
    res, gh, child = run(world)

    assert res == {"action": "DONE", "item": KEY, "pr": 77, "branch": BRANCH, "delivery": "PUSHED"}
    assert len(child.calls) == 1 and child.calls[0]["cwd"] == world.wt
    d = world.delivered[0]
    assert d["branch"] == BRANCH and d["base"] == BASE and d["message"] == f"feat: {TITLE} (executor, Refs #{N})"
    assert world.prs == [(BRANCH, TITLE, N, ())]                                                 # sem `executor-automerge` na Issue: merge segue humano
    ev = event(world)
    assert ev["status"] == "DONE" and json.loads(ev["result"])["pr"] == 77


def test_the_child_reads_the_issue_from_a_file_and_never_gets_the_body_or_a_token(world):
    _res, _gh, child = run(world)
    call = child.calls[0]
    assert BODY not in call["stdin"] and "Critérios" not in call["stdin"]                      # o corpo e DADO num arquivo, nunca na ordem
    files = list((ex.child_sandbox_dir() / "issues").glob(f"issue{N}_*.json"))
    assert len(files) == 1 and json.loads(files[0].read_text(encoding="utf-8"))["untrusted_data"] is True
    assert files[0].as_posix() in call["stdin"]
    assert not {"GH_TOKEN", "GITHUB_TOKEN"} & set(call["env"])
    argv = call["argv"]
    allow = argv[argv.index("--allowedTools") + 1].split(",")
    assert not any(a.startswith(("Bash(gh", "Bash(git push", "Bash(git commit", "Bash(git add")) for a in allow)


def test_secrets_in_the_issue_are_redacted_in_the_file_the_child_reads(world):
    token = "ghp_" + "a" * 36
    issue = Gh().issue | {"body": f"use {token}", "title": TITLE}
    h = intake.spec_hash(issue)
    key = f"implement:issue:{N}:{h}"
    world.store.publish("IMPLEMENT_REQUESTED", key, "issue:6", {"issue": N, "title": TITLE, "spec_hash": h}, aggregate_type="issue")
    for e in world.store.events():                                                              # so o segundo pedido interessa
        if e["idempotency_key"] == KEY:
            world.store.supersede(world.store.claim(("IMPLEMENT_REQUESTED",), "x", 60), "outro")
    run(world, Gh(issue=issue))
    text = next((ex.child_sandbox_dir() / "issues").glob(f"issue{N}_{h}.json")).read_text(encoding="utf-8")
    assert token not in text and "[REDACTED]" in text


# ------------------------------------------------------------------------------------------------------ preflight (fail-closed)
def labels(*names):
    return [{"name": n} for n in names]


@pytest.mark.parametrize("name,gh_kw,action,needle", [
    ("closed", {"issue": {"number": N, "state": "closed", "title": TITLE, "body": BODY, "labels": labels(intake.AUTH_LABEL, "spec:FP-060")}},
     "SUPERSEDED", "nao esta aberta"),
    ("label_removed", {"issue": {"number": N, "state": "open", "title": TITLE, "body": BODY, "labels": labels("spec:FP-060")}},
     "REFUSED", "perdeu a label"),
    ("geometry_spec", {"issue": {"number": N, "state": "open", "title": TITLE, "body": BODY, "labels": labels(intake.AUTH_LABEL, "spec:FP-043")}},
     "REFUSED", "SPEC"),
    ("edited", {"issue": {"number": N, "state": "open", "title": TITLE, "body": BODY + "x", "labels": labels(intake.AUTH_LABEL, "spec:FP-060")}},
     "SUPERSEDED", "editada"),
    ("is_a_pr", {"issue": {"number": N, "state": "open", "title": TITLE, "body": BODY, "pull_request": {}, "labels": labels(intake.AUTH_LABEL, "spec:FP-060")}},
     "REFUSED", "PR"),
    ("pr_cites_issue", {"prs": [{"number": 9, "body": f"Refs #{N}", "head": {"ref": "feat/outro"}}]}, "SUPERSEDED", "ja existe o PR #9"),
    ("pr_uses_branch", {"prs": [{"number": 9, "body": "", "head": {"ref": BRANCH}}]}, "SUPERSEDED", "ja existe o PR #9"),
    ("wrong_identity", {"login": "fmmodesto"}, "REFUSED", "preflight falhou"),
    ("github_down", {"boom": RuntimeError("502")}, "REFUSED", "fail-closed"),
])
def test_a_failed_preflight_never_runs_claude_and_parks_the_event(world, name, gh_kw, action, needle):
    res, _gh, child = run(world, Gh(**gh_kw))
    assert res["action"] == action and needle in res["reason"], res
    assert child.calls == [] and world.delivered == [] and world.prs == []
    assert event(world)["status"] == "SUPERSEDED"                                               # REFUSED e SUPERSEDED descartam o pedido


# ----------------------------------------------------------------------------------------------------------- preparacao
def test_a_dirty_or_unpreparable_worktree_blocks_without_running_claude(world, monkeypatch):
    monkeypatch.setattr(iw, "prepare_worktree", lambda n, b, r: (False, "worktree suja", world.wt, BASE))
    res, _gh, child = run(world)
    assert res["action"] == "BLOCKED_WORKTREE" and "suja" in res["reason"] and child.calls == []
    assert event(world)["status"] == "PENDING" and "suja" in event(world)["error"]


@pytest.mark.parametrize("state", ["CONFLICT", "ERROR"])
def test_a_remote_branch_conflict_or_error_blocks_without_running_claude(world, monkeypatch, state):
    monkeypatch.setattr(iw, "ensure_remote_branch", lambda wt, branch, base: (state, "motivo x"))
    res, _gh, child = run(world)
    assert res["action"] == "BLOCKED_WORKTREE" and child.calls == [] and world.delivered == []


def test_a_resumable_branch_opens_the_pr_without_running_claude_or_delivering_again(world, monkeypatch):
    monkeypatch.setattr(iw, "ensure_remote_branch", lambda wt, branch, base: ("RESUMABLE", "ja publicada"))
    res, _gh, child = run(world)
    assert res["action"] == "DONE" and res["pr"] == 77 and child.calls == [] and world.delivered == []
    assert event(world)["status"] == "DONE"


def test_a_resumable_branch_whose_pr_still_fails_is_retried_not_lost(world, monkeypatch):
    monkeypatch.setattr(iw, "ensure_remote_branch", lambda wt, branch, base: ("RESUMABLE", "ja publicada"))
    monkeypatch.setattr(iw, "create_pr", lambda *a, **k: (None, "gh pr create recusado: 502"))
    res, _gh, _child = run(world)
    assert res["action"] == "FAILED" and "PR nao abriu" in res["reason"]
    assert event(world)["status"] == "PENDING" and event(world)["attempt"] == 1


# --------------------------------------------------------------------------------------------------------- resultados do filho
@pytest.mark.parametrize("delivery,needle", [
    (("BLOCKED_GUARDS", "path critico"), "BLOCKED_GUARDS"), (("FAILED_CHECKS", "pytest reprovou"), "FAILED_CHECKS"),
    (("STALE", "HEAD remoto mudou"), "STALE"), (("ERROR", "push recusado"), "ERROR"), (("NOOP", "nenhuma alteracao"), "sem alteracao")])
def test_a_delivery_that_does_not_publish_fails_the_attempt_and_opens_no_pr(world, monkeypatch, delivery, needle):
    monkeypatch.setattr(ex, "deliver", lambda *a, **k: delivery)
    res, _gh, _child = run(world)
    assert res["action"] == "FAILED" and needle in res["reason"] and world.prs == []
    assert event(world)["status"] == "PENDING"


def test_a_pushed_branch_whose_pr_does_not_open_is_a_failure_not_a_success(world, monkeypatch):
    monkeypatch.setattr(iw, "create_pr", lambda *a, **k: (None, "gh pr create recusado: 502"))
    res, _gh, _child = run(world)
    assert res["action"] == "FAILED" and "branch publicada" in res["reason"] and event(world)["status"] == "PENDING"


@pytest.mark.parametrize("child,needle", [
    (Child(rc=1), "codigo 1"), (Child(timed_out=True, rc=-1), "timeout"),
    (Child(result={"type": "result", "is_error": True, "result": "x"}), "is_error")])
def test_a_failed_child_never_reaches_the_delivery(world, child, needle):
    res, _gh, _c = run(world, child=child)
    assert res["action"] == "FAILED" and needle in res["reason"] and world.delivered == [] and world.prs == []


def test_a_child_without_login_blocks_on_credentials(world):
    child = Child(rc=1, result={"type": "result", "is_error": True, "result": "Not logged in · Please run /login"})
    res, _gh, _c = run(world, child=child)
    assert res["action"] == "BLOCKED_CREDENTIALS" and world.delivered == []


def test_a_missing_cli_blocks_with_its_own_state(world):
    res, _gh, _c = run(world, child=Child(boom=FileNotFoundError()))
    assert res["action"] == "BLOCKED_CLI" and world.delivered == []


def test_a_question_from_the_child_is_posted_on_the_issue_and_nothing_is_published(world, monkeypatch):
    monkeypatch.setattr(ex, "deliver", lambda *a, **k: ("NOOP", "nenhuma alteracao"))
    child = Child(result={"type": "result", "is_error": False, "result": "nao sei\nDUVIDA: qual modulo?"})
    res, _gh, _c = run(world, child=child)
    assert res["action"] == "FAILED" and world.comments and "qual modulo?" in world.comments[0] and world.prs == []


def test_the_delivery_revalidates_authorization_against_github_each_time(world):
    run(world)
    revalidate = world.delivered[0]["revalidate"]
    assert revalidate()[0] is True
    world_gh_issue_closed = Gh(issue={"number": N, "state": "closed", "title": TITLE, "body": BODY, "labels": labels(intake.AUTH_LABEL, "spec:FP-060")})
    ok, why = iw._revalidate({"issue": N, "spec_hash": HASH}, world_gh_issue_closed, POLICY, REPO)
    assert ok is False and "nao esta aberta" in why


# --------------------------------------------------------------------------------------------- dry-run, recuperacao, duplicidade
def test_dry_run_runs_the_preflight_but_never_claims_or_runs_anything(world):
    gh, child = Gh(), Child()
    res = ex.process_one(gh, POLICY, REPO, False, child, "claude", None, None)
    assert res["action"] == "DRY_RUN" and res["branch"] == BRANCH and res["issue"] == N and child.calls == []
    assert event(world)["status"] == "PENDING" and event(world)["attempt"] == 0


def test_dry_run_reports_a_refusal_without_touching_the_event(world):
    res = ex.process_one(Gh(issue={"number": N, "state": "closed", "title": TITLE, "body": BODY, "labels": []}), POLICY, REPO, False, Child(), "claude", None, None)
    assert res["action"] == "SUPERSEDED" and res["dry_run"] is True and event(world)["status"] == "PENDING"


def test_an_executor_killed_mid_run_is_recovered_after_the_lease_and_the_issue_gets_one_pr(world, clock):
    claimed = ex.claim_next("dead-executor")
    assert claimed["kind"] == "implement" and claimed["issue"] == N
    sq.reset_claims()
    res, _gh, child = run(world)
    assert res["action"] == "IDLE" and child.calls == []                                           # o lease do morto ainda vale
    clock.t += ex.LEASE_S + 1
    res, _gh, child = run(world)
    assert res["action"] == "DONE" and len(child.calls) == 1 and len(world.prs) == 1
    assert run(world)[0]["action"] == "IDLE" and len(world.prs) == 1


def test_a_duplicate_request_for_the_same_spec_never_creates_a_second_event(world):
    _id, created = world.store.publish("IMPLEMENT_REQUESTED", KEY, f"issue:{N}", {"issue": N, "spec_hash": HASH}, aggregate_type="issue")
    assert created is False
    run(world)
    assert len(world.prs) == 1 and run(world)[0]["action"] == "IDLE"


def test_a_malformed_implement_event_is_discarded_and_never_executed(world):
    world.store.publish("IMPLEMENT_REQUESTED", "implement:issue:9:abc", "issue:9", {"issue": 9}, aggregate_type="issue")      # sem spec_hash
    world.store.publish("IMPLEMENT_REQUESTED", "implement:issue:8:zzz", "issue:8", {"issue": 8, "spec_hash": "outro"}, aggregate_type="issue")
    run(world)
    run(world)                                                                                   # o claim e por ordem de id: o 1o ciclo fez o pedido bom
    by_key = {e["idempotency_key"]: e["status"] for e in world.store.events()}
    assert by_key["implement:issue:9:abc"] == "SUPERSEDED" and by_key["implement:issue:8:zzz"] == "SUPERSEDED"
    assert by_key[KEY] == "DONE"


def test_the_json_queue_never_runs_an_implement_item(world, monkeypatch):
    monkeypatch.setenv(sq.SOURCE_ENV, "json")
    eb.save({**eb.default_bridge_state(), "queue": [{"key": KEY, "kind": "implement", "event_id": f"implement:{N}", "pr": None, "issue": N,
                                                      "head_sha": "", "state": "QUEUED"}]})
    res = ex.process_one(Gh(), POLICY, REPO, True, Child(), "claude", lambda *a: (True, "", Path("."), ""), None)
    assert res["action"] == "UNSUPPORTED" and "nao e uma revisao" in res["reason"] and not res.get("pr")


# ------------------------------------------------------------------------------------------------- git / gh (funcoes puras)
class Git:
    """`run(args, cwd)` falso: responde por prefixo do subcomando."""
    def __init__(self, answers):
        self.answers, self.calls = answers, []

    def __call__(self, args, cwd):
        self.calls.append(list(args))
        for prefix, out in self.answers.items():
            if " ".join(args).startswith(prefix):
                return out if isinstance(out, tuple) else (0, out)
        return 0, ""


def test_ensure_remote_branch_creates_the_branch_at_the_base_only_when_absent():
    git = Git({"ls-remote": (0, ""), "push": (0, "")})
    assert iw.ensure_remote_branch(Path("."), BRANCH, BASE, git)[0] == "CREATED"
    assert ["push", "origin", f"{BASE}:refs/heads/{BRANCH}"] in git.calls and not any(c[:2] == ["push", "--force"] for c in git.calls)
    assert iw.ensure_remote_branch(Path("."), BRANCH, BASE, Git({"ls-remote": (0, f"{BASE}\trefs/heads/{BRANCH}")}))[0] == "AT_BASE"


def test_ensure_remote_branch_adopts_only_a_single_commit_of_the_executor_and_never_overwrites():
    other = "d" * 40
    base_answers = {"ls-remote": (0, f"{other}\trefs/heads/{BRANCH}"), "fetch": (0, ""), "rev-list": (0, "1"), "rev-parse": (0, BASE),
                    "log": (0, "exec@x.dev"), "config": (0, "exec@x.dev")}
    assert iw.ensure_remote_branch(Path("."), BRANCH, BASE, Git(base_answers))[0] == "RESUMABLE"
    for change in ({"rev-list": (0, "2")}, {"merge-base": (1, "")}, {"log": (0, "alguem@x.dev")}, {"config": (0, "")}):
        git = Git({**base_answers, **change})
        assert iw.ensure_remote_branch(Path("."), BRANCH, BASE, git)[0] == "CONFLICT", change
        assert not any(c[0] == "push" for c in git.calls)                                          # nunca sobrescreve
    assert iw.ensure_remote_branch(Path("."), BRANCH, BASE, Git({"ls-remote": (1, "boom")}))[0] == "ERROR"
    assert iw.ensure_remote_branch(Path("."), BRANCH, BASE, Git({"ls-remote": (0, ""), "push": (1, "negado")}))[0] == "ERROR"


def test_prepare_worktree_refuses_a_dirty_worktree_and_an_invalid_base(tmp_path, monkeypatch):
    monkeypatch.setenv("BRIDGE_WORKTREE_ROOT", str(tmp_path / "wt"))
    wt = iw.worktree_path(N)
    wt.mkdir(parents=True)
    ok, msg, _wt, base = iw.prepare_worktree(N, BRANCH, tmp_path, Git({"fetch": (0, ""), "rev-parse": (0, BASE), "status": (0, " M x.py")}))
    assert not ok and "alteracoes nao commitadas" in msg and base == BASE
    ok, msg, *_ = iw.prepare_worktree(N, BRANCH, tmp_path, Git({"fetch": (0, ""), "rev-parse": (0, "nao-e-sha")}))
    assert not ok and "invalido" in msg
    ok, msg, *_ = iw.prepare_worktree(N, BRANCH, tmp_path, Git({"fetch": (1, "sem rede")}))
    assert not ok and "fetch" in msg
    ok, _msg, _wt, base = iw.prepare_worktree(N, BRANCH, tmp_path, Git({"fetch": (0, ""), "rev-parse": (0, BASE), "status": (0, ""), "checkout": (0, "")}))
    assert ok and base == BASE


def test_a_new_worktree_is_detached_at_the_fetched_base(tmp_path, monkeypatch):
    monkeypatch.setenv("BRIDGE_WORKTREE_ROOT", str(tmp_path / "wt"))
    git = Git({"fetch": (0, ""), "rev-parse": (0, BASE), "worktree": (0, "")})
    ok, _msg, wt, _base = iw.prepare_worktree(N, BRANCH, tmp_path, git)
    assert ok and ["worktree", "add", "--detach", str(wt), BASE] in git.calls


class Proc:
    def __init__(self, rc=0, out="", err=""):
        self.returncode, self.stdout, self.stderr = rc, out, err


def test_create_pr_cites_the_issue_labels_it_and_retries_a_transient_failure(monkeypatch):
    monkeypatch.setattr(iw.time, "sleep", lambda s: None)
    answers = [Proc(1, "", "502"), Proc(0, "https://github.com/o/r/pull/88\n")]
    seen = []

    def runner(argv, **kw):
        seen.append((argv, kw))
        return answers[len(seen) - 1]
    number, _msg = iw.create_pr(BRANCH, TITLE, N, REPO, runner=runner)
    assert number == 88 and len(seen) == 2
    argv, kw = seen[0]
    assert argv[argv.index("--head") + 1] == BRANCH and argv[argv.index("--base") + 1] == "develop"
    assert f"Refs #{N}" in argv[argv.index("--body") + 1] and "--label" in argv and argv[argv.index("--label") + 1] == ex.guards.load_config().label
    assert "GH_TOKEN" not in kw["env"] and "--draft" not in argv


def test_create_pr_gives_up_after_the_limit_and_redacts_the_error(monkeypatch):
    monkeypatch.setattr(iw.time, "sleep", lambda s: None)
    secret = "ghp_" + "b" * 36
    calls = []

    def runner(argv, **kw):
        calls.append(1)
        return Proc(1, "", f"falhou com {secret}")
    number, msg = iw.create_pr(BRANCH, TITLE, N, REPO, runner=runner)
    assert number is None and len(calls) == iw.PR_TRIES and secret not in msg


def test_branch_names_are_safe_and_deterministic():
    assert iw.branch_for(5, "ABC123def456xx") == "feat/issue-5-abc123def456" or iw.branch_for(5, "abc123def456") == "feat/issue-5-abc123def456"
    assert iw.branch_for(5, HASH) == iw.branch_for(5, HASH) and ex.BRANCH_OK.match(iw.branch_for(5, HASH))


# --------------------------------------------------------------------------------------- sqlite_source: o evento de implementacao
def test_item_from_event_accepts_only_an_implement_event_whose_key_matches_its_payload():
    ev = {"id": 1, "event_type": "IMPLEMENT_REQUESTED", "idempotency_key": KEY, "attempt": 2,
          "payload": json.dumps({"issue": N, "spec_hash": HASH, "title": TITLE})}
    item = sq.item_from_event(ev)
    assert item["kind"] == "implement" and item["issue"] == N and item["spec_hash"] == HASH and item["attempts"] == 1 and item["pr"] is None
    for bad in ({"idempotency_key": f"implement:issue:{N}:outro"}, {"payload": json.dumps({"issue": N})},
                {"payload": json.dumps({"issue": True, "spec_hash": HASH})}, {"payload": "nao e json"}):
        assert sq.item_from_event({**ev, **bad}) is None


def test_the_pr_carries_the_automerge_opt_in_only_when_the_issue_has_it(world):
    gh = Gh(issue={"number": N, "state": "open", "title": TITLE, "body": BODY,
                   "labels": labels(intake.AUTH_LABEL, "spec:FP-060", iw.AUTOMERGE_ISSUE_LABEL)})
    run(world, gh)
    assert world.prs[0][3] == (iw.AUTOMERGE_PR_LABEL,)


def test_create_pr_applies_every_label_it_is_given(monkeypatch):
    seen = []

    def runner(argv, **kw):
        seen.append(argv)
        return Proc(0, "https://github.com/o/r/pull/9\n")
    iw.create_pr(BRANCH, TITLE, N, REPO, runner=runner, extra_labels=("automerge-ok",))
    got = [seen[0][i + 1] for i, a in enumerate(seen[0]) if a == "--label"]
    assert got == [ex.guards.load_config().label, "automerge-ok"]


# -- 7a revisao do Codex (#646): opt-in lida de novo, retomada com develop avancado, `Relates to` no preflight ------------------------------------------
def test_an_automerge_opt_in_withdrawn_during_the_run_does_not_reach_the_pr(world, monkeypatch):
    gh = Gh(issue={"number": N, "state": "open", "title": TITLE, "body": BODY,
                   "labels": labels(intake.AUTH_LABEL, "spec:FP-060", iw.AUTOMERGE_ISSUE_LABEL)})

    def deliver_and_human_withdraws(wt, branch, base, py, item, **kw):
        gh.issue = {**gh.issue, "labels": labels(intake.AUTH_LABEL, "spec:FP-060")}                       # o humano retira `executor-automerge` durante a execucao
        return ("PUSHED", "1 arquivo")
    monkeypatch.setattr(ex, "deliver", deliver_and_human_withdraws)
    res, _gh, _child = run(world, gh)
    assert res["action"] == "DONE" and world.prs[0][3] == ()


@pytest.mark.parametrize("boom", [RuntimeError("gh caiu"), ValueError("json ruim")])
def test_an_unreadable_issue_when_opening_the_pr_leaves_the_automerge_opt_in_off(boom):
    class Flaky(Gh):
        def __call__(self, path):
            if path == f"repos/{REPO}/issues/{N}":
                raise boom
            return super().__call__(path)
    assert iw._fresh_automerge_optin(Flaky(), REPO, N) is False
    assert iw._fresh_automerge_optin(None, REPO, N) is False
    assert iw._fresh_automerge_optin(Gh(issue={"state": "closed", "labels": labels(intake.AUTH_LABEL, iw.AUTOMERGE_ISSUE_LABEL)}), REPO, N) is False
    assert iw._fresh_automerge_optin(Gh(issue={"state": "open", "labels": labels(iw.AUTOMERGE_ISSUE_LABEL)}), REPO, N) is False                # sem a autorizacao do intake


def test_a_published_commit_on_an_older_develop_is_still_resumable_after_develop_advances():
    other = "d" * 40
    old_parent = "c" * 40                                                                                  # develop avancou: o pai do commit publicado nao e mais a base atual
    answers = {"ls-remote": (0, f"{other}	refs/heads/{BRANCH}"), "fetch": (0, ""), "rev-list": (0, "1"), "rev-parse": (0, old_parent),
               "merge-base": (0, ""), "log": (0, "exec@x.dev"), "config": (0, "exec@x.dev")}
    git = Git(answers)
    assert iw.ensure_remote_branch(Path("."), BRANCH, BASE, git)[0] == "RESUMABLE"
    assert ["merge-base", "--is-ancestor", old_parent, BASE] in git.calls
    assert iw.ensure_remote_branch(Path("."), BRANCH, BASE, Git({**answers, "merge-base": (1, "")}))[0] == "CONFLICT"      # pai fora do develop: trabalho alheio


@pytest.mark.parametrize("body", [f"Relates to #{N}", f"relates to: #{N}", f"Refs #{N}", f"Ref: #{N}"])
def test_an_open_pr_citing_the_issue_in_any_scheduler_format_supersedes_the_request(world, body):
    gh = Gh(prs=[{"number": 5, "body": body, "head": {"ref": "outra"}}])
    res, _gh, child = run(world, gh)
    assert res["action"] == "SUPERSEDED" and "ja existe o PR #5" in res["reason"] and child.calls == []


def test_a_pr_that_does_not_cite_the_issue_does_not_supersede_the_request(world):
    gh = Gh(prs=[{"number": 5, "body": f"Relates to #{N + 1} e Refs #{N + 2}", "head": {"ref": "outra"}}])
    res, _gh, _child = run(world, gh)
    assert res["action"] == "DONE"
