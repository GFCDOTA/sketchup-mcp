"""FP-057 P2: claims com lease, checkpoint duravel e recuperacao sem duplicar nem perder trabalho."""
from __future__ import annotations

import datetime as dt
import threading

import pytest

from tools.validation import execution_state as es
from tools.validation import task_scheduler as ts

T0 = dt.datetime(2026, 10, 25, 12, 0, tzinfo=dt.timezone.utc)
CRIT = "## Critérios de aceite\n- [ ] algo\n"


def issue(n, labels=(), deps=(), state="OPEN", title="t"):
    d = ("**Dependências:** " + ", ".join("#%d" % x for x in deps) + "\n\n") if deps else ""
    return {"number": n, "title": title, "state": state, "stateReason": "COMPLETED" if state == "CLOSED" else None,
            "labels": [{"name": x} for x in labels], "body": d + CRIT}


@pytest.fixture()
def path(tmp_path, monkeypatch):
    p = tmp_path / "runs/governance/execution_state.json"
    monkeypatch.setenv("EXECUTION_STATE_PATH", str(p))
    return p


# ------------------------------------------------------------------------------------------------------ estado
def test_state_roundtrip_is_atomic_and_never_stores_secrets(path):
    st = es.default_state()
    st["active_spec"] = "FP-057"
    es.save(st, path)
    assert es.load(path)["active_spec"] == "FP-057" and not path.with_suffix(".tmp").exists()
    st["recovery_instructions"] = ["use o token ghp_abcdef"]
    with pytest.raises(ValueError, match="segredos"):
        es.save(st, path)


def test_missing_manifest_loads_the_default_schema(path):
    st = es.load(path)
    assert st["schema_version"] == 1 and st["claims"] == {} and st["current_issue"] is None


def test_claim_is_idempotent_for_the_same_agent_refused_for_another_and_reopens_after_the_lease():
    st = es.default_state()
    es.claim(st, 7, "A", "feat/x", "abc", ["FP-056|P3"], T0)
    again = es.claim(st, 7, "A", "feat/x", "abc", ["FP-056|P3"], T0 + dt.timedelta(hours=1))
    assert again["claimed_at"] == "2026-10-25T12:00:00Z"                              # nao reinicia a reivindicacao
    with pytest.raises(ValueError, match="reivindicada por A"):
        es.claim(st, 7, "B", "feat/y", "abc", [], T0 + dt.timedelta(hours=1))
    assert es.claim(st, 7, "B", "feat/y", "abc", [], T0 + dt.timedelta(hours=es.LEASE_HOURS + 2))["agent"] == "B"


def test_phase_only_moves_forward_and_renews_the_lease():
    st = es.default_state()
    es.claim(st, 7, "A", "b", "c", [], T0)
    es.advance(st, 7, "PR_OPEN", T0 + dt.timedelta(hours=3))
    assert st["claims"]["7"]["lease_expires"] == "2026-10-25T21:00:00Z"
    with pytest.raises(ValueError, match="volta no tempo"):
        es.advance(st, 7, "EDITING")
    with pytest.raises(ValueError, match="desconhecida"):
        es.advance(st, 7, "VOANDO")


def test_once_records_an_operation_and_refuses_to_repeat_it():
    st = es.default_state()
    assert es.once(st, "pr:feat/x:open") and not es.once(st, "pr:feat/x:open") and es.once(st, "pr:feat/x:merge")


def test_two_executors_racing_for_the_same_task_only_one_wins(path):
    winners, errors = [], []

    def run(agent):
        try:
            with es.locked(path):
                st = es.load(path)
                es.claim(st, 7, agent, f"feat/{agent}", "abc", ["FP-056|P3"])
                es.save(st, path)
                winners.append(agent)
        except ValueError as exc:
            errors.append(str(exc))
    ts_ = [threading.Thread(target=run, args=(a,)) for a in ("A", "B", "C")]
    [t.start() for t in ts_]
    [t.join() for t in ts_]
    assert len(winners) == 1 and len(errors) == 2 and es.load(path)["claims"]["7"]["agent"] == winners[0]


def test_a_stale_lock_from_a_dead_execution_is_broken(path):
    import os
    import time
    lock = path.with_suffix(".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("x")
    old = time.time() - 120
    os.utime(lock, (old, old))
    with es.locked(path, wait_s=1.0):
        pass
    assert not lock.exists()


# --------------------------------------------------------------------------------------------------- scheduler
def test_decide_skips_tasks_claimed_by_another_execution_and_resumes_its_own_first():
    issues = [issue(1, ["spec:FP-056", "fase:P3"]), issue(2, ["spec:FP-056", "fase:P4"]), issue(3, ["spec:FP-055", "fase:P7"])]
    st = es.default_state()
    es.claim(st, 1, "outra", "b1", "abc", ["FP-056|P3"], dt.datetime.now(dt.timezone.utc))
    task, verdicts = ts.decide(issues, [], st, agent="claude")
    assert task.node.number in (2, 3) and next(v for v in verdicts if v.node.number == 1).reasons[0].startswith("CLAIMED")
    es.claim(st, 3, "claude", "b3", "abc", ["FP-055|P7"], dt.datetime.now(dt.timezone.utc))
    task, _ = ts.decide(issues, [{"number": 9, "body": "Refs #3"}], st, agent="claude")
    assert task.node.number == 3 and task.action == "resume"                       # PR proprio nao a bloqueia: e retomada


def test_decide_with_expired_claim_treats_the_task_as_free_again():
    issues = [issue(1, ["spec:FP-056", "fase:P3"])]
    st = es.default_state()
    es.claim(st, 1, "morta", "b1", "abc", ["FP-056|P3"], dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc))   # lease ja venceu
    task, _ = ts.decide(issues, [], st, agent="claude")
    assert task is not None and task.node.number == 1


def test_take_records_the_checkpoint_and_next_lists(path):
    issues = [issue(1, ["spec:FP-056", "fase:P3"]), issue(2, ["blocked", "bloqueio:human-decision", "aprovação-humana-pendente"])]
    st = es.default_state()
    task, verdicts = ts.decide(issues, [], st)
    ts.take(st, task, "claude", "feat/x", "abc")
    ts.checkpoint_after(st, verdicts, [{"number": 5}])
    assert st["current_issue"] == 1 and st["active_spec"] == "FP-056" and st["blocked_issues"] == [2] and st["open_pull_requests"] == [5]
    es.save(st, path)
    assert es.load(path)["claims"]["1"]["components"] == ["FP-056|P3"]


# ------------------------------------------------------------------------------------------------- recuperacao
@pytest.mark.parametrize("facts,expected", [
    ({}, ("SELECTED", "criar a branch")),
    ({"branch_exists": True}, ("EDITING", "retomar na branch existente")),
    ({"branch_exists": True, "pr": {"state": "OPEN", "merged": False, "checks": "pending"}}, ("CI_PENDING", "aguardar")),
    ({"branch_exists": True, "pr": {"state": "OPEN", "merged": False, "checks": "fail"}}, ("EDITING", "MESMO PR")),
    ({"branch_exists": True, "pr": {"state": "OPEN", "merged": False, "checks": "pass"}}, ("MERGING", "--match-head-commit")),
    ({"branch_exists": True, "pr": {"merged": True}}, ("BOARD_SYNC", "nao mergear de novo")),
    ({"branch_exists": True, "pr": {"merged": True}, "issue_closed": True, "board_synced": True}, ("DONE", "nada a fazer")),
])
def test_recovery_plan_for_each_interruption_point(facts, expected):
    phase, action = es.plan_recovery({}, facts)
    assert phase == expected[0] and expected[1] in action


class FakeGitHub:
    """GitHub em memoria, idempotente como a API real para os efeitos que importam (branch/PR/merge/board)."""

    def __init__(self):
        self.branches, self.prs, self.merges, self.board, self.calls = set(), {}, [], {}, []

    def create_branch(self, b):
        self.calls.append(("branch", b))
        self.branches.add(b)

    def open_pr(self, b):
        self.calls.append(("open_pr", b))
        return self.prs.setdefault(b, {"number": len(self.prs) + 1, "merged": False, "checks": "pass"})

    def merge(self, b):
        self.calls.append(("merge", b))
        if not self.prs[b]["merged"]:
            self.prs[b]["merged"] = True
            self.merges.append(b)

    def set_board(self, n, status):
        self.calls.append(("board", n, status))
        self.board[n] = status


STEPS = ("branch", "pr", "merge", "board")


def execute(gh, st, issue_n, branch, die_after=None):
    """Executor minimo com o padrao da FP-057: cada efeito atras de `once` e de fatos do GitHub; morre apos `die_after` passos."""
    done = 0
    for step in STEPS:
        if die_after is not None and done >= die_after:
            return "INTERROMPIDO"
        if step == "branch" and (es.once(st, f"branch:{branch}") or branch not in gh.branches):
            gh.create_branch(branch)
        if step == "pr" and branch not in gh.prs:
            gh.open_pr(branch)
            es.once(st, f"pr:{branch}")
        if step == "merge" and not gh.prs[branch]["merged"]:
            gh.merge(branch)
            es.once(st, f"merge:{branch}")
        if step == "board" and gh.board.get(issue_n) != "Done":
            gh.set_board(issue_n, "Done")
        done += 1
    return "CONCLUIDO"


@pytest.mark.parametrize("die_after", [0, 1, 2, 3])
def test_restart_after_an_interruption_never_duplicates_or_loses_work(path, die_after):
    gh, st = FakeGitHub(), es.default_state()
    es.claim(st, 7, "claude", "feat/x", "abc", ["FP-056|P3"])
    assert execute(gh, st, 7, "feat/x", die_after=die_after) == "INTERROMPIDO"
    es.save(st, path)                                                                 # checkpoint no momento da queda
    st2 = es.load(path)                                                               # novo processo
    assert execute(gh, st2, 7, "feat/x") == "CONCLUIDO"
    assert execute(gh, st2, 7, "feat/x") == "CONCLUIDO"                               # e rodar de novo tambem e inofensivo
    assert len(gh.prs) == 1 and gh.merges == ["feat/x"] and gh.board == {7: "Done"} and gh.branches == {"feat/x"}
