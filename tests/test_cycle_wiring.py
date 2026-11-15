"""FP-060 (#638, #647): a reconciliacao do SQLite e o merge automatico protegido no ciclo do executor. Os passos sao limitados por intervalo, nunca
interrompem o ciclo e o merge automatico nem le o GitHub enquanto estiver desligado."""
from __future__ import annotations

import pytest

from tools.orchestration import auto_merge, store_reconcile
from tools.orchestration import event_executor as ex
from tools.orchestration import sqlite_source as sq

POLICY = {"reviewers": ["fmmodesto"], "executor_logins": ["fmodesto30"]}


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("EVENT_BRIDGE_STATE_PATH", str(tmp_path / "gov" / "bridge.json"))
    monkeypatch.delenv(auto_merge.ENABLE_ENV, raising=False)
    monkeypatch.delenv(sq.SOURCE_ENV, raising=False)
    ex._LAST_STEP.clear()
    yield
    ex._LAST_STEP.clear()


def never(path):
    raise AssertionError(f"o GitHub nao deveria ser lido: {path}")


# ----------------------------------------------------------------------------------------------------------------- merge automatico
def test_a_disabled_auto_merge_does_not_even_read_github(monkeypatch):
    monkeypatch.setattr(auto_merge, "cycle", lambda *a, **k: pytest.fail("ciclo de merge chamado com o merge desligado"))
    out = ex._auto_merge_summary(never, POLICY, "o/r", True)
    assert out["enabled"] is False and "padrao" in out["reason"]


def test_an_enabled_auto_merge_only_applies_with_the_executor_execute_flag(monkeypatch):
    monkeypatch.setenv(auto_merge.ENABLE_ENV, "1")
    seen = []
    monkeypatch.setattr(auto_merge, "cycle", lambda gh, policy, repo, apply=False, **k: (seen.append(apply), {"prs": [{"pr": 7, "code": "MERGE", "merged": apply, "x": 1}]})[1])
    plan = ex._auto_merge_summary(never, POLICY, "o/r", False)
    ex._LAST_STEP.clear()
    applied = ex._auto_merge_summary(never, POLICY, "o/r", True)
    assert seen == [False, True] and plan["prs"] == [{"pr": 7, "code": "MERGE", "merged": False}] and applied["applied"] is True


def test_the_kill_switch_stops_an_enabled_auto_merge(monkeypatch):
    monkeypatch.setenv(auto_merge.ENABLE_ENV, "1")
    auto_merge.kill_switch().parent.mkdir(parents=True)
    auto_merge.kill_switch().write_text("x", encoding="utf-8")
    monkeypatch.setattr(auto_merge, "cycle", lambda *a, **k: pytest.fail("interruptor ignorado"))
    assert ex._auto_merge_summary(never, POLICY, "o/r", True)["enabled"] is False


def test_the_auto_merge_step_is_throttled_and_a_failure_never_escapes(monkeypatch):
    monkeypatch.setenv(auto_merge.ENABLE_ENV, "1")
    calls = []

    def boom(*a, **k):
        calls.append(1)
        raise RuntimeError("502")
    monkeypatch.setattr(auto_merge, "cycle", boom)
    first = ex._auto_merge_summary(never, POLICY, "o/r", True)
    second = ex._auto_merge_summary(never, POLICY, "o/r", True)
    assert "RuntimeError" in first["errors"][0] and second == {"skipped": "intervalo"} and len(calls) == 1


# ------------------------------------------------------------------------------------------------------- reconciliacao do SQLite
def test_without_a_store_the_reconcile_step_is_skipped():
    assert ex._store_reconcile_summary(never, "o/r", None) == {"skipped": "sem store"}


@pytest.mark.parametrize("source,apply", [("json", False), ("sqlite", True)])
def test_the_reconcile_applies_only_when_sqlite_is_primary(monkeypatch, source, apply):
    monkeypatch.setenv(sq.SOURCE_ENV, source)
    seen = []
    monkeypatch.setattr(store_reconcile, "reconcile", lambda store, gh, repo, apply=False: (seen.append(apply), {"applied": apply, "counts": {"CURRENT": 1}, "events": []})[1])
    out = ex._store_reconcile_summary(never, "o/r", object())
    assert seen == [apply] and out == {"applied": apply, "counts": {"CURRENT": 1}}


def test_the_reconcile_step_is_throttled_and_a_failure_never_escapes(monkeypatch):
    calls = []

    def boom(*a, **k):
        calls.append(1)
        raise OSError("disco")
    monkeypatch.setattr(store_reconcile, "reconcile", boom)
    first = ex._store_reconcile_summary(never, "o/r", object())
    second = ex._store_reconcile_summary(never, "o/r", object())
    assert "OSError" in first["errors"][0] and second == {"skipped": "intervalo"} and len(calls) == 1


def test_a_step_runs_again_after_its_interval(monkeypatch):
    clock = {"t": 1000.0}
    monkeypatch.setattr(ex.time, "monotonic", lambda: clock["t"])
    assert ex._due("store_reconcile") is True and ex._due("store_reconcile") is False
    clock["t"] += ex.STEP_EVERY_S["store_reconcile"] + 1
    assert ex._due("store_reconcile") is True


# ---------------------------------------------------------------------------------------------------------------- run_cycle
def test_run_cycle_reports_both_steps_without_changing_the_rest(monkeypatch):
    monkeypatch.setattr(ex, "_get_store", lambda: None)
    monkeypatch.setattr(ex.eb, "run_cycle", lambda *a, **k: {"polled": 0})
    monkeypatch.setattr(ex, "process_one", lambda *a, **k: {"action": "IDLE"})
    monkeypatch.setattr(ex, "_reconcile_summary", lambda *a, **k: {"tracked": 0})
    out = ex.run_cycle(never, POLICY, "o/r", False)
    assert out["action"] == "IDLE" and out["store_reconcile"] == {"skipped": "sem store"} and out["auto_merge"]["enabled"] is False
    assert out["store"] == "unavailable"


# ------------------------------------------------------------------------------------------ intake e revisao publicada (MT-16, #656)
from tools.orchestration import intake as intake_mod  # noqa: E402
from tools.orchestration import lifecycle as lifecycle_mod  # noqa: E402
from tools.validation import backlog_discovery as bd  # noqa: E402


class Cand:
    class node:  # noqa: N801
        number = 5


def test_a_disabled_intake_does_not_read_the_backlog(monkeypatch):
    monkeypatch.setattr(bd, "load", lambda *a, **k: pytest.fail("backlog lido com o intake desligado"))
    assert ex._intake_summary(never, object(), True) == {"enabled": False}


@pytest.mark.parametrize("source,execute,store", [("json", True, object()), ("sqlite", False, object()), ("sqlite", True, None)])
def test_an_enabled_intake_still_needs_execute_sqlite_and_the_store(monkeypatch, source, execute, store):
    monkeypatch.setenv(ex.INTAKE_ENV, "1")
    monkeypatch.setenv(sq.SOURCE_ENV, source)
    monkeypatch.setattr(bd, "load", lambda *a, **k: pytest.fail("backlog lido sem as condicoes do worker"))
    assert "exige" in ex._intake_summary(never, store, execute)["skipped"]


def test_the_intake_publishes_one_authorized_issue_and_is_throttled(monkeypatch, tmp_path):
    monkeypatch.setenv(ex.INTAKE_ENV, "1")
    monkeypatch.setenv(sq.SOURCE_ENV, "sqlite")
    monkeypatch.setenv("EXECUTION_STATE_PATH", str(tmp_path / "exec.json"))
    monkeypatch.setattr(bd, "load", lambda statuses=False: ([{"number": 5}], None, []))
    monkeypatch.setattr(bd, "load_readiness", lambda: {})
    monkeypatch.setattr(intake_mod, "plan", lambda *a, **k: intake_mod.IntakePlan(Cand(), []))
    monkeypatch.setattr(intake_mod, "publish", lambda store, cand, issues: (11, True))
    first = ex._intake_summary(never, object(), True)
    second = ex._intake_summary(never, object(), True)
    assert first == {"candidate": 5, "event": 11, "created": True} and second == {"skipped": "intervalo"}


def test_an_intake_without_candidate_or_with_a_failure_never_escapes(monkeypatch, tmp_path):
    monkeypatch.setenv(ex.INTAKE_ENV, "1")
    monkeypatch.setenv(sq.SOURCE_ENV, "sqlite")
    monkeypatch.setenv("EXECUTION_STATE_PATH", str(tmp_path / "exec.json"))
    monkeypatch.setattr(bd, "load_readiness", lambda: {})
    monkeypatch.setattr(bd, "load", lambda statuses=False: ([], None, []))
    monkeypatch.setattr(intake_mod, "plan", lambda *a, **k: intake_mod.IntakePlan(None, ["#1: x"]))
    assert ex._intake_summary(never, object(), True) == {"candidate": None, "skipped": 1}
    ex._LAST_STEP.clear()
    monkeypatch.setattr(bd, "load", lambda statuses=False: (_ for _ in ()).throw(RuntimeError("502")))
    assert "RuntimeError" in ex._intake_summary(never, object(), True)["errors"][0]


def reconcile_spy(monkeypatch):
    seen = {}

    def fake(gh, policy, repo, execute=False, now=None, codex_review=None, state_file=None):
        seen.update(execute=execute, codex_review=codex_review)
        return {"tracked": 0, "transitions": [], "actions": [], "errors": []}
    monkeypatch.setattr(lifecycle_mod, "reconcile", fake)
    return seen


def test_the_review_is_only_planned_by_default_even_with_execute(monkeypatch):
    seen = reconcile_spy(monkeypatch)
    ex._reconcile_summary(never, POLICY, "o/r", None, execute=True)
    assert seen == {"execute": False, "codex_review": None}


def test_the_publish_flag_alone_does_not_run_the_reviewer_without_execute(monkeypatch):
    monkeypatch.setenv(ex.REVIEW_PUBLISH_ENV, "1")
    seen = reconcile_spy(monkeypatch)
    ex._reconcile_summary(never, POLICY, "o/r", None, execute=False)
    assert seen == {"execute": False, "codex_review": None}


def test_with_execute_and_the_flag_the_reviewer_publishes_through_the_outbox(monkeypatch):
    from tools.orchestration import codex_reviewer
    monkeypatch.setenv(ex.REVIEW_PUBLISH_ENV, "1")
    seen = reconcile_spy(monkeypatch)
    calls = []
    monkeypatch.setattr(codex_reviewer, "review_pr", lambda *a, **k: (calls.append(k), {"action": "DONE"})[1])
    ex._reconcile_summary(never, POLICY, "o/r", None, execute=True)
    assert seen["execute"] is True and seen["codex_review"](7, never, POLICY, "o/r") == {"action": "DONE"} and calls == [{"do_publish": True}]


def test_run_cycle_reports_the_intake_step(monkeypatch):
    monkeypatch.setattr(ex, "_get_store", lambda: None)
    monkeypatch.setattr(ex.eb, "run_cycle", lambda *a, **k: {"polled": 0})
    monkeypatch.setattr(ex, "process_one", lambda *a, **k: {"action": "IDLE"})
    monkeypatch.setattr(ex, "_reconcile_summary", lambda *a, **k: {"tracked": 0})
    assert ex.run_cycle(never, POLICY, "o/r", False)["intake"] == {"enabled": False}
