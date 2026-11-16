"""FP-060 MT-12 (#638): eventos pendentes do SQLite reconciliados com os fatos do GitHub. SQLite real, GitHub injetado."""
from __future__ import annotations

import json
import sqlite3
import subprocess

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


@pytest.fixture(autouse=True)
def isolated_bridge(tmp_path, monkeypatch):
    empty = tmp_path / "bridge-empty.json"
    empty.write_bytes(b'{"queue": []}')                                                       # fila JSON EXPLICITAMENTE vazia por padrao: nunca le a do workspace
    monkeypatch.setenv("EVENT_BRIDGE_STATE_PATH", str(empty))
    monkeypatch.delenv("EXECUTOR_SOURCE", raising=False)


@pytest.fixture()
def clock():
    return Clock()


@pytest.fixture()
def store(tmp_path, clock):
    return EventStore(tmp_path / "s.db", clock=clock)


def publish(store, key=KEY, payload=None, event_type="CORRECTION_REQUESTED", repo=sr.eb.REPO):
    payload = {"pr": 7, "head_sha": HEAD, "review_id": "9"} if payload is None else payload
    if repo is not None:
        payload = {"repo": repo, **payload}                                         # o bridge grava o repositorio de origem em todo evento
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
def test_an_event_that_gained_a_live_owner_in_between_is_skipped_not_forced(store, clock):
    publish(store)

    class Racing(FakeGh):
        def __call__(self, path):
            out = super().__call__(path)
            if path.endswith("/pulls/7"):
                store.claim(("CORRECTION_REQUESTED",), "executor-vivo", 300)               # entre julgar e descartar, um executor reivindica
            return out
    report = sr.reconcile(store, Racing(head=NEW), apply=True)
    assert report["events"][0]["applied"] == "SKIPPED" and status(store) == "RUNNING"


def test_a_pending_event_in_retry_backoff_is_also_discarded_when_obsolete(store, clock):
    publish(store)
    store.fail(store.claim(("CORRECTION_REQUESTED",), "x", 60), "falha", retry_delay=900)         # PENDING, mas so disponivel daqui a 15 min
    assert store.claim(("CORRECTION_REQUESTED",), "y", 60) is None
    report = sr.reconcile(store, FakeGh(head=NEW), apply=True)
    assert report["events"][0]["applied"] == "SUPERSEDED" and status(store) == "SUPERSEDED"       # no E2E real isto ficava PENDING ate o backoff acabar


def test_discarding_one_request_never_touches_unrelated_events_with_an_expired_exhausted_lease(store, clock):
    publish(store)
    other = store.publish("REVIEW_REQUESTED", "outro-job", "job:outro", {"x": 1}, max_attempts=1)[0]
    assert store.claim(("REVIEW_REQUESTED",), "morto", 5)["id"] == other                            # de outro tipo e job; esgotou as tentativas
    clock.t += 10                                                                                    # o lease dele venceu

    sr.reconcile(store, FakeGh(head=NEW), apply=True)

    now = next(e for e in store.events() if e["id"] == other)
    assert now["status"] == "RUNNING" and not any(e["event_type"] == "JOB_FAILED" for e in store.events())   # claim_by_id mandaria este para o DLQ


def test_supersede_obsolete_is_bounded_audited_and_fences_the_old_owner(store, clock):
    eid = publish(store)
    ev = store.claim(("CORRECTION_REQUESTED",), "dono-antigo", 5)
    assert store.supersede_obsolete(eid, "x") is False                                              # lease vivo: de outro dono
    clock.t += 6
    assert store.supersede_obsolete(eid, "HEAD mudou", actor="reconciler") is True
    assert status(store) == "SUPERSEDED" and any(t["actor"] == "reconciler" and t["to_status"] == "SUPERSEDED" for t in store.transitions())
    with pytest.raises(LeaseLost):
        store.complete(ev, {"by": "o dono antigo voltou"})                                           # o resultado atrasado do dono antigo e recusado
    assert store.supersede_obsolete(eid, "de novo") is False and store.supersede_obsolete(9999, "x") is False


@pytest.mark.parametrize("answer", [{}, {"state": "open"}, {"state": "closed"}, {"state": "open", "merged": False},
                                     {"state": "open", "merged": False, "head": {}}, {"state": "open", "merged": False, "head": {"sha": "curto"}},
                                     {"state": "weird", "merged": False, "head": {"sha": HEAD}}, {"state": "open", "merged": "no", "head": {"sha": HEAD}}])
def test_an_incomplete_pr_answer_is_an_error_and_never_discards_the_event(store, answer):
    publish(store)
    report = sr.reconcile(store, lambda path: answer, apply=True)
    assert report["counts"] == {"ERROR": 1} and status(store) == "PENDING"


@pytest.mark.parametrize("payload", [{"pr": 7}, {"pr": 7, "head_sha": ""}, {"pr": 7, "head_sha": "xyz"}, {"pr": 7, "head_sha": 123}, {"pr": True, "head_sha": HEAD}])
def test_a_payload_without_a_valid_head_sha_is_malformed_and_preserved(store, payload):
    publish(store, payload=payload)
    gh = FakeGh(state="closed")
    report = sr.reconcile(store, gh, apply=True)
    assert report["counts"] == {"MALFORMED": 1} and status(store) == "PENDING" and gh.calls == []


def test_a_github_timeout_on_one_event_is_an_error_row_and_the_next_events_are_still_processed(store):
    publish(store)
    publish(store, key=f"review:10:8:{HEAD}", payload={"pr": 8, "head_sha": HEAD, "review_id": "10"})

    def gh(path):
        if "/pulls/7" in path:
            raise subprocess.TimeoutExpired("gh", 120)
        return {"number": 8, "state": "closed", "merged": False, "head": {"sha": HEAD}}
    report = sr.reconcile(store, gh, apply=True)
    assert report["counts"] == {"ERROR": 1, "PR_NOT_OPEN": 1} and status(store) == "PENDING" and status(store, f"review:10:8:{HEAD}") == "SUPERSEDED"


# ------------------------------------------------------------------------------------------------------------------- CLI
def test_the_plan_never_creates_the_database_or_the_schema(tmp_path, monkeypatch, capsys):
    from tools.orchestration import store_factory
    missing = tmp_path / "nao" / "existe" / "store.db"
    monkeypatch.setenv("EVENT_STORE_DB_PATH", str(missing))
    store_factory.reset_store()
    monkeypatch.setattr(sr.eb, "gh_json", lambda path: pytest.fail("sem banco nao ha o que ler do GitHub"))
    assert sr.main([]) == 0
    assert json.loads(capsys.readouterr().out)["store"].startswith("ausente") and not missing.parent.exists()


def test_the_plan_opens_an_existing_database_read_only(tmp_path, monkeypatch, capsys):
    from tools.orchestration import store_factory
    db = tmp_path / "store.db"
    store = EventStore(db)
    store.publish("CORRECTION_REQUESTED", KEY, "pr:7", {"repo": sr.eb.REPO, "pr": 7, "head_sha": HEAD, "review_id": "9"})
    before = db.read_bytes() if not db.with_name("store.db-wal").exists() else None
    monkeypatch.setenv("EVENT_STORE_DB_PATH", str(db))
    store_factory.reset_store()
    monkeypatch.setattr(sr.eb, "gh_json", FakeGh(head=NEW))
    assert sr.main([]) == 0
    assert json.loads(capsys.readouterr().out)["events"][0]["code"] == "HEAD_MOVED" and status(store) == "PENDING"
    ro = EventStore.open_existing(db)
    with pytest.raises(sqlite3.OperationalError):
        ro.publish("CORRECTION_REQUESTED", "k-novo", "pr:9", {"x": 1})                              # a instancia somente leitura nao grava
    assert before is None or db.read_bytes() == before


def test_the_cli_applies_only_with_apply_and_returns_1_only_when_a_github_read_failed(tmp_path, monkeypatch, capsys):
    from tools.orchestration import store_factory
    db = tmp_path / "store.db"
    store = EventStore(db)
    store.publish("CORRECTION_REQUESTED", KEY, "pr:7", {"repo": sr.eb.REPO, "pr": 7, "head_sha": HEAD, "review_id": "9"})
    monkeypatch.setenv("EVENT_STORE_DB_PATH", str(db))
    store_factory.reset_store()
    monkeypatch.setattr(sr.eb, "gh_json", FakeGh(head=NEW))
    assert sr.main(["--apply"]) == 0 and status(store) == "SUPERSEDED"
    capsys.readouterr()
    store.publish("CORRECTION_REQUESTED", f"review:10:7:{HEAD}", "pr:7", {"repo": sr.eb.REPO, "pr": 7, "head_sha": HEAD, "review_id": "10"})
    monkeypatch.setattr(sr.eb, "gh_json", FakeGh(boom=RuntimeError("rede")))
    assert sr.main([]) == 1


# -- achados da 2a revisao do Codex: identidade do repositorio e dono do trabalho (executor JSON) ---------------------------------
OTHER = "outra-org/outro-repo"


def test_the_bridge_binds_every_event_to_its_repository():
    from tools.orchestration.store_factory import bridge_to_store_args
    args = bridge_to_store_args({"event_id": "review:9", "kind": "review", "state": "CHANGES_REQUESTED", "pr": 7, "repo": sr.eb.REPO, "author": "r"}, {"head_sha": HEAD, "refs": [1]})
    assert args["payload"]["repo"] == sr.eb.REPO


def test_the_same_pr_number_in_another_repository_is_never_consulted_nor_discarded(store):
    publish(store, repo=OTHER)                                                   # PR #7 de OUTRO repositorio, com HEAD diferente do #7 consultado
    gh = FakeGh(head=NEW)                                                        # o #7 deste repositorio andou: se fosse confundido, o pedido seria descartado
    report = sr.reconcile(store, gh, apply=True)
    assert report["counts"] == {"OTHER_REPO": 1} and gh.calls == [] and status(store) == "PENDING"


def test_a_legacy_event_without_a_provable_repository_is_preserved_and_reported(store):
    publish(store, repo=None)
    gh = FakeGh(state="closed")
    report = sr.reconcile(store, gh, apply=True)
    assert report["counts"] == {"UNKNOWN_REPO": 1} and gh.calls == [] and status(store) == "PENDING"


def test_the_repository_comparison_ignores_case(store):
    publish(store, repo=sr.eb.REPO.upper())
    assert sr.reconcile(store, FakeGh(head=NEW), apply=True)["counts"] == {"HEAD_MOVED": 1} and status(store) == "SUPERSEDED"


def json_item(state, **kw):
    return {"kind": "review", "key": "k1", "pr": 7, "head_sha": HEAD, "state": state, "event_id": "review:9", **kw}


@pytest.mark.parametrize("state", ["QUEUED", "RUNNING", "FAILED", "BLOCKED_CLI", "BLOCKED_WORKTREE"])
def test_an_event_whose_json_item_is_still_active_is_not_discarded_while_the_json_executor_owns_it(store, state):
    publish(store)
    report = sr.reconcile(store, FakeGh(head=NEW), apply=True, json_queue=[json_item(state)], sqlite_authoritative=False)
    row = report["events"][0]
    assert row["code"] == "HEAD_MOVED" and row["applied"] == "SKIPPED" and "JSON_ACTIVE" in row["skipped_because"] and status(store) == "PENDING"


@pytest.mark.parametrize("state", ["SUPERSEDED", "REFUSED", "PARKED_UNSUPPORTED"])
def test_an_event_whose_json_item_finished_can_be_reconciled(store, state):
    publish(store)
    report = sr.reconcile(store, FakeGh(head=NEW), apply=True, json_queue=[json_item(state)], sqlite_authoritative=False)
    assert report["events"][0]["applied"] == "SUPERSEDED" and status(store) == "SUPERSEDED"


def test_an_active_item_of_another_head_or_pr_does_not_protect_the_event(store):
    publish(store)
    other = [json_item("RUNNING", pr=8), json_item("RUNNING", head_sha=NEW)]
    assert sr.reconcile(store, FakeGh(head=NEW), apply=True, json_queue=other, sqlite_authoritative=False)["events"][0]["applied"] == "SUPERSEDED"


def test_when_sqlite_is_authoritative_the_json_queue_is_not_consulted(store):
    publish(store)
    report = sr.reconcile(store, FakeGh(head=NEW), apply=True, json_queue=[json_item("RUNNING")], sqlite_authoritative=True)
    assert report["events"][0]["applied"] == "SUPERSEDED"


def test_an_unreadable_json_queue_applies_nothing(store, tmp_path, monkeypatch):
    publish(store)
    bad = tmp_path / "bridge.json"
    bad.write_bytes(b"\x00" * 32)
    monkeypatch.setenv("EVENT_BRIDGE_STATE_PATH", str(bad))
    monkeypatch.delenv("EXECUTOR_SOURCE", raising=False)
    report = sr.reconcile(store, FakeGh(head=NEW), apply=True)
    assert report["events"][0]["applied"] == "SKIPPED" and "ilegivel" in report["events"][0]["skipped_because"] and status(store) == "PENDING"


def test_the_default_reads_the_real_json_queue_and_respects_an_active_item(store, tmp_path, monkeypatch):
    from tools.orchestration import event_bridge as eb
    publish(store)
    path = tmp_path / "bridge.json"
    eb.save({**eb.default_bridge_state(), "queue": [json_item("RUNNING")]}, path)
    monkeypatch.setenv("EVENT_BRIDGE_STATE_PATH", str(path))
    monkeypatch.delenv("EXECUTOR_SOURCE", raising=False)
    report = sr.reconcile(store, FakeGh(head=NEW), apply=True)
    assert report["events"][0]["applied"] == "SKIPPED" and status(store) == "PENDING"
    monkeypatch.setenv("EXECUTOR_SOURCE", "sqlite")
    assert sr.reconcile(store, FakeGh(head=NEW), apply=True)["events"][0]["applied"] == "SUPERSEDED"


def test_a_running_json_executor_still_syncs_its_result_after_a_reconcile_attempt(store, tmp_path, monkeypatch):
    """Integracao com o executor JSON ativo: o reconciliador nao rouba o evento; ao terminar, o sync do executor o conclui como DONE."""
    from tools.orchestration import event_executor as ex
    publish(store, key=f"review:9:7:{HEAD}")
    running = json_item("RUNNING", event_id="review:9")
    report = sr.reconcile(store, FakeGh(head=NEW), apply=True, json_queue=[running], sqlite_authoritative=False)
    assert report["events"][0]["applied"] == "SKIPPED" and status(store) == "PENDING"
    monkeypatch.setattr("tools.orchestration.store_factory._inc", lambda *a, **k: None, raising=False)
    ex._sync_result_to_store(store, running, {"action": "DONE", "new_head": NEW})
    assert status(store) == "DONE"                                                # o historico do SQLite ficou correto (sem o reconciliador ter descartado)


# -- 6a revisao do Codex (#642): DONE nao sincronizado e fila JSON estruturalmente invalida ---------------------------------------------------------------
def test_an_event_whose_json_item_is_done_but_not_yet_synced_is_not_discarded(store):
    publish(store)
    report = sr.reconcile(store, FakeGh(head=NEW), apply=True, json_queue=[json_item("DONE_AWAITING_REREVIEW")], sqlite_authoritative=False)
    row = report["events"][0]
    assert row["applied"] == "SKIPPED" and "JSON_ACTIVE" in row["skipped_because"] and status(store) == "PENDING"


def test_the_executor_sync_after_the_skipped_reconcile_records_done_with_the_real_result(store, monkeypatch):
    from tools.orchestration import event_executor as ex
    publish(store, key=f"review:9:7:{HEAD}")
    running = json_item("DONE_AWAITING_REREVIEW", event_id="review:9")
    sr.reconcile(store, FakeGh(head=NEW), apply=True, json_queue=[running], sqlite_authoritative=False)
    monkeypatch.setattr("tools.orchestration.store_factory._inc", lambda *a, **k: None, raising=False)
    ex._sync_result_to_store(store, running, {"action": "DONE", "new_head": NEW})
    assert status(store) == "DONE"                                                         # o historico do SQLite guarda o resultado efetivo


@pytest.mark.parametrize("bad", [{"a": 1}, "texto", [None], ["x"], [{"state": "RUNNING"}], [{"kind": "review", "state": "QUEUED", "head_sha": HEAD, "pr": "7"}],
                                 [{"kind": "review", "state": "QUEUED", "pr": 7}], [{"kind": "review", "state": 3, "head_sha": HEAD, "pr": 7}]])
def test_a_structurally_invalid_json_queue_applies_nothing(store, bad):
    publish(store)
    report = sr.reconcile(store, FakeGh(head=NEW), apply=True, json_queue=bad, sqlite_authoritative=False)
    row = report["events"][0]
    assert row["applied"] == "SKIPPED" and "invalida" in row["skipped_because"] and status(store) == "PENDING"


def test_a_null_queue_on_disk_is_not_an_empty_queue(store, tmp_path, monkeypatch):
    import json as _json
    publish(store)
    bad = tmp_path / "bridge-null.json"
    bad.write_text(_json.dumps({"schema_version": 1, "queue": None}), encoding="utf-8")
    monkeypatch.setenv("EVENT_BRIDGE_STATE_PATH", str(bad))
    report = sr.reconcile(store, FakeGh(head=NEW), apply=True)
    assert report["events"][0]["applied"] == "SKIPPED" and status(store) == "PENDING"


def test_a_valid_empty_queue_still_lets_an_obsolete_event_be_reconciled(store):
    publish(store)
    assert sr.reconcile(store, FakeGh(head=NEW), apply=True, json_queue=[], sqlite_authoritative=False)["events"][0]["applied"] == "SUPERSEDED"


# -- 8a revisao do Codex (#642): fila JSON ausente ou sem `queue` NAO e fila vazia ---------------------------------------------------------------------
@pytest.mark.parametrize("content", [None, b"{}", b'{"outro": 1}', b'{"queue": null}', b'{"queue": {"a": 1}}', b"[]"])
def test_a_missing_json_queue_file_or_one_without_the_queue_key_applies_nothing(store, tmp_path, monkeypatch, content):
    publish(store)
    path = tmp_path / "bridge.json"
    if content is not None:
        path.write_bytes(content)
    monkeypatch.setenv("EVENT_BRIDGE_STATE_PATH", str(path))
    monkeypatch.delenv("EXECUTOR_SOURCE", raising=False)
    report = sr.reconcile(store, FakeGh(head=NEW), apply=True)
    assert report["events"][0]["applied"] == "SKIPPED" and "fila JSON" in report["events"][0]["skipped_because"] and status(store) == "PENDING"


def test_an_explicitly_empty_json_queue_still_allows_superseding_a_stale_event(store, tmp_path, monkeypatch):
    publish(store)
    path = tmp_path / "bridge.json"
    path.write_bytes(b'{"queue": []}')
    monkeypatch.setenv("EVENT_BRIDGE_STATE_PATH", str(path))
    monkeypatch.delenv("EXECUTOR_SOURCE", raising=False)
    report = sr.reconcile(store, FakeGh(head=NEW), apply=True)
    assert report["events"][0]["applied"] == "SUPERSEDED"
