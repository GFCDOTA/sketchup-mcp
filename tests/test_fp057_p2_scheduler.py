"""FP-057 P2: claims com lease, checkpoint duravel e recuperacao sem duplicar nem perder trabalho."""
from __future__ import annotations

import datetime as dt
import threading
from pathlib import Path

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


def test_an_old_lock_file_never_blocks_the_next_holder(path):
    import os
    import time
    lock = path.with_suffix(".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("x")
    old = time.time() - 120
    os.utime(lock, (old, old))
    with es.locked(path, wait_s=1.0):
        pass
    assert lock.exists()                                                       # o arquivo persiste; o SO e a fonte de verdade (conteudo/idade sao ignorados)


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


# --------------------------------------------- trava por LOCK DO SO (achados HIGH do Codex no #643: corridas de quebra/liberacao do arquivo)
LOCK_CHILD = """
import sys, time
from pathlib import Path
from tools.validation import execution_state as es
with es.locked(Path(sys.argv[1]), wait_s=10):
    print("held", flush=True)
    time.sleep(120)
"""


def spawn_holder(path):
    import os
    import subprocess
    import sys
    root = Path(__file__).resolve().parents[1]
    return subprocess.Popen([sys.executable, "-c", LOCK_CHILD, str(path)], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            env={**os.environ, "PYTHONPATH": str(root), "PYTHONUTF8": "1"})


def test_many_threads_acquiring_the_state_lock_repeatedly_all_get_it_one_at_a_time(path):
    inside, peak, errors, wins, guard = [], [0], [], [], threading.Lock()

    def run(i):
        try:
            with es.locked(path, wait_s=10):
                with guard:
                    inside.append(1)
                    peak[0] = max(peak[0], len(inside))
                    wins.append(i)
                import time
                time.sleep(0.002)
                with guard:
                    inside.pop()
        except BaseException as exc:                                                       # noqa: BLE001 — o teste quer ver qualquer falha
            errors.append(f"{type(exc).__name__}: {exc}")
    for _ in range(25):
        ts_ = [threading.Thread(target=run, args=(i,)) for i in range(4)]
        [t.start() for t in ts_]
        [t.join() for t in ts_]
    assert errors == [] and len(wins) == 100 and peak[0] == 1                               # ninguem falhou e nunca dois dentro ao mesmo tempo


def test_a_live_holder_in_another_real_process_is_respected(path):
    holder = spawn_holder(path)
    try:
        assert holder.stdout.readline().strip() == "held"
        with pytest.raises(TimeoutError):
            with es.locked(path, wait_s=0.4):
                pytest.fail("entrou na secao critica de outro processo vivo")
    finally:
        holder.kill()
        holder.wait(timeout=10)


def test_a_holder_killed_hard_frees_the_lock_immediately_without_any_stale_rule(path):
    import time
    holder = spawn_holder(path)
    assert holder.stdout.readline().strip() == "held"
    holder.kill()                                                                            # morte dura durante a secao critica
    holder.wait(timeout=10)
    t0 = time.time()
    with es.locked(path, wait_s=5):
        pass
    assert time.time() - t0 < 2.0                                                            # o SO soltou o lock: nao ha espera de 60 s nem trava orfa


@pytest.mark.parametrize("content", [b"", b"\x00" * 64, b"123456", b"999999:token-de-um-formato-antigo", b"qualquer coisa"])
def test_the_content_of_an_old_lock_file_never_blocks_anyone(path, content):
    lock = path.with_suffix(".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_bytes(content)
    with es.locked(path, wait_s=1):
        pass


def test_the_lock_file_is_never_removed_so_nobody_races_on_its_creation_or_deletion(path):
    lock = path.with_suffix(".lock")
    with es.locked(path):
        assert lock.exists()
    assert lock.exists()
    with es.locked(path):
        pass
    assert lock.exists()


def test_a_failure_to_open_the_lock_file_raises_at_once_instead_of_looping(path, monkeypatch):
    import time
    monkeypatch.setattr(es.os, "open", lambda *a, **k: (_ for _ in ()).throw(PermissionError(13, "sem permissao no diretorio")))
    t0 = time.time()
    with pytest.raises(PermissionError):
        with es.locked(path, wait_s=5):
            pass
    assert time.time() - t0 < 1.0


def test_the_os_lock_is_released_even_when_the_body_raises(path):
    with pytest.raises(RuntimeError):
        with es.locked(path):
            raise RuntimeError("falha dentro da secao critica")
    with es.locked(path, wait_s=1):
        pass


def test_a_second_holder_in_the_same_process_waits_and_times_out(path):
    with es.locked(path):
        with pytest.raises(TimeoutError):
            with es.locked(path, wait_s=0.2):
                pass
