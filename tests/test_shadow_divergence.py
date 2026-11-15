"""FP-060 MT-07 / S1 (#626): detector de divergencia entre a fila JSON do executor e o espelho no EventStore (so leitura)."""
from __future__ import annotations

import json

import pytest

from tools.orchestration import shadow_divergence as sd
from tools.orchestration.event_store import EventStore
from tools.orchestration.store_factory import bridge_to_store_args


def item(n=1, state="QUEUED", kind="review", pr=7, sha="a" * 40, **kw):
    return {"key": f"k{n}", "kind": kind, "event_id": f"review:{1000 + n}", "pr": pr, "head_sha": sha, "state": state, **kw}


def event(n=1, status="PENDING", pr=7, sha="a" * 40, **kw):
    return {"id": n, "event_type": "CORRECTION_REQUESTED", "producer": "event_bridge", "status": status,
            "idempotency_key": f"review:{1000 + n}:{pr}:{sha}", **kw}


def codes(found):
    return sorted((d.code, d.key) for d in found)


# -- o que NAO e divergencia ------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("state, status", [
    ("QUEUED", "PENDING"), ("RUNNING", "PENDING"),                         # o espelho so e atualizado quando o item JSON termina
    ("DONE_AWAITING_REREVIEW", "DONE"), ("SUPERSEDED", "SUPERSEDED"), ("REFUSED", "SUPERSEDED"), ("PARKED_UNSUPPORTED", "SUPERSEDED"),
    ("FAILED", "PENDING"), ("FAILED", "DLQ"), ("BLOCKED_CLI", "PENDING"), ("BLOCKED_CREDENTIALS", "DLQ"),
    ("BLOCKED_WORKTREE", "PENDING"), ("BLOCKED_REVIEW_FETCH", "PENDING"),
])
def test_a_json_state_and_the_mirror_status_that_the_shadow_sync_produces_agree(state, status):
    assert sd.compare([item(state=state)], [event(status=status)]) == []


def test_items_that_are_not_mirrored_by_design_are_ignored():
    assert sd.compare([item(kind="comment")], []) == []


# -- divergencias ---------------------------------------------------------------------------------------------------------------
def test_a_review_item_without_its_event_is_missing_in_the_store():
    assert codes(sd.compare([item(1), item(2)], [event(1)])) == [("MISSING_IN_STORE", "k2")]


@pytest.mark.parametrize("state, status", [("DONE_AWAITING_REREVIEW", "PENDING"), ("SUPERSEDED", "PENDING"), ("REFUSED", "PENDING")])
def test_a_finished_json_item_whose_event_is_still_pending_means_the_sync_was_lost(state, status):
    assert codes(sd.compare([item(state=state)], [event(status=status)])) == [("STALE_PENDING", "k1")]


@pytest.mark.parametrize("state, status", [("QUEUED", "DONE"), ("RUNNING", "SUPERSEDED"), ("DONE_AWAITING_REREVIEW", "SUPERSEDED"),
                                           ("SUPERSEDED", "DONE"), ("FAILED", "DONE")])
def test_any_other_pair_is_a_state_mismatch(state, status):
    assert codes(sd.compare([item(state=state)], [event(status=status)])) == [("STATE_MISMATCH", "k1")]


def test_an_unknown_json_state_is_reported_never_assumed_equal():
    assert codes(sd.compare([item(state="TELEPORTED")], [event()])) == [("UNKNOWN_STATE", "k1")]


def test_a_bridge_event_without_a_json_item_is_an_orphan():
    assert codes(sd.compare([], [event(3)])) == [("ORPHAN_IN_STORE", "review:1003:7:" + "a" * 40)]


def test_events_of_other_producers_or_types_are_not_the_mirror_and_are_ignored():
    other = [event(2, producer="coordinator"), event(3, event_type="REVIEW_REQUESTED")]
    assert sd.compare([], other) == []


def test_the_same_key_for_a_new_head_is_a_different_item():
    assert codes(sd.compare([item(1, sha="b" * 40)], [event(1, sha="a" * 40)])) == [
        ("MISSING_IN_STORE", "k1"), ("ORPHAN_IN_STORE", "review:1001:7:" + "a" * 40)]


# -- o mesmo calculo de chave do bridge e do sync -------------------------------------------------------------------------------
def test_the_mirror_key_is_the_one_the_bridge_publishes():
    bridge_event = {"kind": "review", "state": "CHANGES_REQUESTED", "event_id": "review:555", "pr": 9, "author": "x", "url": "u"}
    published = bridge_to_store_args(bridge_event, {"head_sha": "d" * 40, "refs": []})["idempotency_key"]
    assert sd.mirror_key({"event_id": "review:555", "pr": 9, "head_sha": "d" * 40}) == published


# -- contra um EventStore real e uma fila lida do disco ----------------------------------------------------------------------------
def test_collect_reads_the_real_store_and_the_bridge_queue(tmp_path, monkeypatch):
    store = EventStore(tmp_path / "events.db")
    args = bridge_to_store_args({"kind": "review", "state": "CHANGES_REQUESTED", "event_id": "review:42", "pr": 7, "author": "x", "url": "u"},
                                {"head_sha": "a" * 40, "refs": []})
    store.publish(**args)
    queue = [{"key": "k", "kind": "review", "event_id": "review:42", "pr": 7, "head_sha": "a" * 40, "state": "QUEUED"},
             {"key": "k2", "kind": "review", "event_id": "review:43", "pr": 7, "head_sha": "a" * 40, "state": "QUEUED"}]

    found = sd.collect(queue, store)

    assert [(d.code, d.key) for d in found] == [("MISSING_IN_STORE", "k2")]


def test_main_prints_the_report_and_exits_nonzero_only_on_real_divergences(tmp_path, monkeypatch, capsys):
    store = EventStore(tmp_path / "events.db")
    monkeypatch.setattr(sd, "_load", lambda: ([item(1)], store))

    assert sd.main(["--json"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["ok"] is False and report["divergences"] == [{"code": "MISSING_IN_STORE", "key": "k1", "detail": report["divergences"][0]["detail"]}]

    monkeypatch.setattr(sd, "_load", lambda: ([], store))
    assert sd.main(["--json"]) == 0 and json.loads(capsys.readouterr().out)["ok"] is True


def test_an_orphan_alone_is_a_warning_and_fails_only_in_strict_mode(tmp_path, monkeypatch, capsys):
    store = EventStore(tmp_path / "events.db")
    args = bridge_to_store_args({"kind": "review", "state": "CHANGES_REQUESTED", "event_id": "review:42", "pr": 7, "author": "x", "url": "u"},
                                {"head_sha": "a" * 40, "refs": []})
    store.publish(**args)
    monkeypatch.setattr(sd, "_load", lambda: ([], store))

    assert sd.main(["--json"]) == 0
    assert json.loads(capsys.readouterr().out)["warnings"] == 1
    assert sd.main(["--json", "--strict"]) == 1


def test_the_detector_never_writes_to_the_store_or_the_queue(tmp_path):
    store = EventStore(tmp_path / "events.db")
    before = (store.events(), store.transitions(), store.pending_outbox())
    sd.collect([item(1)], store)
    assert (store.events(), store.transitions(), store.pending_outbox()) == before


def test_a_missing_store_is_an_error_not_an_empty_comparison_and_is_not_created(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("EVENT_STORE_DB_PATH", str(tmp_path / "gov" / "event_store.db"))
    monkeypatch.setenv("EVENT_BRIDGE_STATE_PATH", str(tmp_path / "gov" / "bridge.json"))

    assert sd.main(["--json"]) == 2

    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and "EventStore ausente" in out["error"] and not (tmp_path / "gov").exists()
