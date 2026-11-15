"""FP-060 MT-12 (#638): eventos pendentes do SQLite reconciliados com os fatos do GitHub. SQLite real, GitHub injetado."""
from __future__ import annotations

import json

import pytest

from tools.orchestration import lifecycle
from tools.orchestration import store_reconcile as sr
from tools.orchestration.event_store import EventStore, LeaseLost

HEAD, NEW = "a" * 40, "b" * 40
KEY = f"review:9:7:{HEAD}"


class Clock:
    t = 1_000_000.0

    def __call__(self):
        return self.t


class FakeGh:
    def __init__(self, head=HEAD, state="open", merged=False, runs="green", boom=None):
        self.head, self.state, self.merged, self.runs, self.boom = head, state, merged, runs, boom
        self.calls = []

    def __call__(self, path):
        self.calls.append(path)
        if self.boom:
            raise self.boom
        if "check-runs" in path:
            names = sorted(lifecycle.MANDATORY_CHECKS)
            bad = self.runs == "red"
            return {"total_count": len(names), "check_runs": [
                {"name": n, "status": "completed", "conclusion": "failure" if bad and i == 0 else "success"} for i, n in enumerate(names)]}
        return {"number": 7, "state": self.state, "merged": self.merged, "head": {"sha": self.head}}


@pytest.fixture()
def clock():
    return Clock()


@pytest.fixture()
def store(tmp_path, clock):
    return EventStore(tmp_path / "s.db", clock=clock)


def publish(store, key=KEY, payload=None, event_type="CORRECTION_REQUESTED"):
    payload = {"pr": 7, "head_sha": HEAD, "review_id": "9"} if payload is None else payload
    return store.publish(event_type, key, "pr:7", payload, producer="event_bridge")[0]


def status(store, key=KEY):
    return next(e for e in store.events() if e["idempotency_key"] == key)["status"]


# ------------------------------------------------------------------------------------------------------------- julgamento
def test_a_moved_head_is_reported_and_only_applied_with_apply(store):
    publish(store)
    report = sr.reconcile(store, FakeGh(head=NEW))
    assert report["counts"] == {"HEAD_MOVED": 1} and "applied" not in report["events"][0] and status(store) == "PENDING"   # plano nao grava

    applied = sr.reconcile(store, FakeGh(head=NEW), apply=True)

    assert applied["events"][0]["applied"] == "SUPERSEDED" and status(store) == "SUPERSEDED"
    assert "reconciliado" in next(e for e in store.events())["error"]


@pytest.mark.parametrize("kw", [{"state": "closed"}, {"state": "closed", "merged": True}, {"merged": True}])
def test_a_pr_that_is_not_open_makes_the_request_obsolete(store, kw):
    publish(store)
    report = sr.reconcile(store, FakeGh(**kw), apply=True)
    assert report["counts"] == {"PR_NOT_OPEN": 1} and status(store) == "SUPERSEDED"


def test_the_head_is_compared_case_insensitively(store):
    publish(store)
    assert sr.reconcile(store, FakeGh(head=HEAD.upper()), apply=True)["counts"] == {"CURRENT": 1}
    assert status(store) == "PENDING"


def test_a_current_request_is_never_touched_and_reports_the_ci_state(store):
    publish(store)
    report = sr.reconcile(store, FakeGh(), apply=True)
    assert report["counts"] == {"CURRENT": 1} and report["events"][0]["ci"] == "passed" and status(store) == "PENDING"


def test_a_current_request_with_failed_checks_is_reported_but_not_discarded(store):
    publish(store)
    report = sr.reconcile(store, FakeGh(runs="red"), apply=True)
    assert report["counts"] == {"CURRENT_CI_FAILED": 1} and report["events"][0]["ci"] == "failed" and status(store) == "PENDING"


# ------------------------------------------------------------------------------------- o que nunca e tocado
def test_a_github_failure_changes_nothing_even_with_apply(store):
    publish(store)
    report = sr.reconcile(store, FakeGh(boom=RuntimeError("502")), apply=True)
    assert report["counts"] == {"ERROR": 1} and status(store) == "PENDING"


@pytest.mark.parametrize("bad", [None, "texto", ["lista"]])
def test_a_malformed_github_answer_is_an_error_not_a_decision(store, bad):
    publish(store)
    gh = lambda path: bad                                                          # noqa: E731
    assert sr.reconcile(store, gh, apply=True)["counts"] == {"ERROR": 1} and status(store) == "PENDING"


def test_an_event_with_a_live_lease_belongs_to_another_executor_and_is_left_alone(store):
    publish(store)
    store.claim(("CORRECTION_REQUESTED",), "executor-vivo", 300)
    gh = FakeGh(state="closed")
    assert sr.reconcile(store, gh, apply=True)["events"] == [] and gh.calls == [] and status(store) == "RUNNING"


def test_an_event_whose_lease_expired_is_considered_dead_and_reconciled(store, clock):
    publish(store)
    store.claim(("CORRECTION_REQUESTED",), "executor-morto", 300)
    clock.t += 301
    assert sr.reconcile(store, FakeGh(state="closed"), apply=True)["counts"] == {"PR_NOT_OPEN": 1} and status(store) == "SUPERSEDED"


def test_finished_events_and_other_event_types_are_ignored(store):
    publish(store)
    store.supersede(store.claim(("CORRECTION_REQUESTED",), "x", 60), "ja resolvido")
    publish(store, key="implement:issue:1:abc", payload={"issue": 1}, event_type="IMPLEMENT_REQUESTED")
    gh = FakeGh(state="closed")
    assert sr.reconcile(store, gh, apply=True)["events"] == [] and gh.calls == []


def test_a_payload_without_a_pr_is_reported_as_malformed_and_left_alone(store):
    publish(store, payload={"head_sha": HEAD})
    report = sr.reconcile(store, FakeGh(state="closed"), apply=True)
    assert report["counts"] == {"MALFORMED": 1} and status(store) == "PENDING"


def test_reconciling_twice_is_idempotent(store):
    publish(store)
    sr.reconcile(store, FakeGh(head=NEW), apply=True)
    assert sr.reconcile(store, FakeGh(head=NEW), apply=True)["events"] == []


# --------------------------------------------------------------------------------------------------------- concorrencia
class RacingStore:
    """Entre julgar e reivindicar, outro executor leva o evento."""
    def __init__(self, inner, mode):
        self.inner, self.mode = inner, mode

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def claim_by_id(self, *a, **k):
        return None if self.mode == "taken" else self.inner.claim_by_id(*a, **k)

    def supersede(self, ev, reason):
        if self.mode == "lease_lost":
            raise LeaseLost("outro dono")
        return self.inner.supersede(ev, reason)


def test_an_event_claimed_by_someone_else_in_between_is_skipped_not_forced(store):
    publish(store)
    report = sr.reconcile(RacingStore(store, "taken"), FakeGh(head=NEW), apply=True)
    assert report["events"][0]["applied"] == "SKIPPED" and status(store) == "PENDING"


def test_a_lease_lost_while_superseding_is_reported_and_never_raises(store):
    publish(store)
    report = sr.reconcile(RacingStore(store, "lease_lost"), FakeGh(head=NEW), apply=True)
    assert report["events"][0]["applied"] == "LEASE_LOST"


# ------------------------------------------------------------------------------------------------------------------- CLI
def test_the_cli_plans_by_default_and_returns_1_only_when_a_github_read_failed(tmp_path, monkeypatch, capsys, store):
    from tools.orchestration import store_factory
    publish(store)
    monkeypatch.setattr(store_factory, "get_store", lambda *a, **k: store)
    monkeypatch.setattr(sr.eb, "gh_json", FakeGh(head=NEW))
    assert sr.main([]) == 0
    assert json.loads(capsys.readouterr().out)["applied"] is False and status(store) == "PENDING"
    assert sr.main(["--apply"]) == 0 and status(store) == "SUPERSEDED"
    capsys.readouterr()
    publish(store, key=f"review:10:7:{HEAD}", payload={"pr": 7, "head_sha": HEAD, "review_id": "10"})
    monkeypatch.setattr(sr.eb, "gh_json", FakeGh(boom=RuntimeError("rede")))
    assert sr.main([]) == 1
