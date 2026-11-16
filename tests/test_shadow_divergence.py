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
    ("QUEUED", "PENDING"),                                                   # o espelho so e atualizado quando o item JSON termina (RUNNING NAO concorda: ver JSON_RUNNING)
    ("DONE_AWAITING_REREVIEW", "DONE"), ("SUPERSEDED", "SUPERSEDED"), ("REFUSED", "SUPERSEDED"), ("PARKED_UNSUPPORTED", "SUPERSEDED"),
    ("FAILED", "PENDING"), ("FAILED", "DLQ"), ("BLOCKED_CLI", "PENDING"), ("BLOCKED_CREDENTIALS", "DLQ"),
    ("BLOCKED_WORKTREE", "PENDING"), ("BLOCKED_REVIEW_FETCH", "DLQ"),
])
def test_a_json_state_and_the_mirror_status_that_the_shadow_sync_produces_agree(state, status):
    # DLQ so concorda com o JSON esgotado; PENDING so concorda com um item que o JSON ainda pode escolher (menos de MAX_ATTEMPTS e estado pickable)
    attempts = sd.MAX_ATTEMPTS if status == "DLQ" else 1
    assert sd.compare([item(state=state, attempts=attempts)], [event(status=status, attempt=attempts)]) == []


def test_items_that_are_not_mirrored_by_design_are_ignored():
    assert sd.compare([item(kind="comment")], []) == []


# -- divergencias ---------------------------------------------------------------------------------------------------------------
def test_a_review_item_without_its_event_is_missing_in_the_store():
    assert codes(sd.compare([item(1), item(2)], [event(1)])) == [("MISSING_IN_STORE", "k2")]


@pytest.mark.parametrize("state, status", [("DONE_AWAITING_REREVIEW", "PENDING"), ("SUPERSEDED", "PENDING"), ("REFUSED", "PENDING")])
def test_a_finished_json_item_whose_event_is_still_pending_means_the_sync_was_lost(state, status):
    assert codes(sd.compare([item(state=state)], [event(status=status)])) == [("STALE_PENDING", "k1")]


@pytest.mark.parametrize("state, status", [("QUEUED", "DONE"), ("DONE_AWAITING_REREVIEW", "SUPERSEDED"), ("SUPERSEDED", "DONE"), ("FAILED", "DONE")])
def test_any_other_pair_is_a_state_mismatch(state, status):
    assert codes(sd.compare([item(state=state)], [event(status=status)])) == [("STATE_MISMATCH", "k1")]


def test_an_unknown_json_state_is_reported_never_assumed_equal():
    assert codes(sd.compare([item(state="TELEPORTED")], [event()])) == [("UNKNOWN_STATE", "k1")]


@pytest.mark.parametrize("status", ["DONE", "SUPERSEDED", "DLQ"])
def test_a_terminal_bridge_event_without_a_json_item_is_only_an_orphan_warning(status):
    assert codes(sd.compare([], [event(3, status=status)])) == [("ORPHAN_IN_STORE", "review:1003:7:" + "a" * 40)]


@pytest.mark.parametrize("status", ["PENDING", "RUNNING"])
def test_an_executable_event_without_a_json_item_is_always_a_divergence(status):
    """O bridge publica no SQLite ANTES de salvar a fila JSON: uma parada entre as duas deixa trabalho executavel so no store."""
    assert codes(sd.compare([], [event(3, status=status)])) == [("ORPHAN_EXECUTABLE", "review:1003:7:" + "a" * 40)]


@pytest.mark.parametrize("state,attempts,diverges", [("FAILED", 1, True), ("BLOCKED_CREDENTIALS", 0, True), ("BLOCKED_CLI", 2, True), ("FAILED", 3, False),
                                                      ("BLOCKED_WORKTREE", 5, False)])
def test_a_dlq_event_with_a_json_item_that_can_still_be_picked_is_a_divergence(state, attempts, diverges):
    """BLOCKED_* nao consome tentativas no JSON e volta a ser escolhido; o evento DLQ nao pode ser reivindicado: o cutover abandonaria trabalho retomavel."""
    found = sd.compare([item(state=state, attempts=attempts)], [event(status="DLQ")])
    assert (codes(found) == [("STATE_MISMATCH", "k1")]) is diverges and (found == []) is (not diverges)


def test_events_of_other_producers_or_types_are_not_the_mirror_and_are_ignored():
    other = [event(2, producer="coordinator"), event(3, event_type="REVIEW_REQUESTED")]
    assert sd.compare([], other) == []


def test_the_same_key_for_a_new_head_is_a_different_item():
    assert codes(sd.compare([item(1, sha="b" * 40)], [event(1, sha="a" * 40)])) == [
        ("MISSING_IN_STORE", "k1"), ("ORPHAN_EXECUTABLE", "review:1001:7:" + "a" * 40)]


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


def test_a_terminal_orphan_is_a_warning_that_fails_only_in_strict_mode_and_an_executable_one_always_fails(tmp_path, monkeypatch, capsys):
    store = EventStore(tmp_path / "events.db")
    args = bridge_to_store_args({"kind": "review", "state": "CHANGES_REQUESTED", "event_id": "review:42", "pr": 7, "author": "x", "url": "u"},
                                {"head_sha": "a" * 40, "refs": []})
    event_id, _ = store.publish(**args)
    monkeypatch.setattr(sd, "_load", lambda: ([], store))

    assert sd.main(["--json"]) == 1                                                                # PENDING sem item: executavel so no store
    assert json.loads(capsys.readouterr().out)["divergences"][0]["code"] == "ORPHAN_EXECUTABLE"
    store.supersede(store.claim(("CORRECTION_REQUESTED",), "x", 60), "terminal")                   # agora terminal
    assert sd.main(["--json"]) == 0 and json.loads(capsys.readouterr().out)["warnings"] == 1
    assert sd.main(["--json", "--strict"]) == 1 and event_id


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


# -- main() de ponta a ponta com arquivos reais (achados do review independente do #634) --------------------------------------------
def real_world(tmp_path, monkeypatch, queue=None, write_queue=True, make_db=True):
    from tools.orchestration import store_factory
    monkeypatch.setenv("EVENT_BRIDGE_STATE_PATH", str(tmp_path / "gov" / "bridge.json"))
    monkeypatch.setenv("EVENT_STORE_DB_PATH", str(tmp_path / "gov" / "store.db"))
    store_factory.reset_store()
    (tmp_path / "gov").mkdir(parents=True, exist_ok=True)
    if write_queue:
        (tmp_path / "gov" / "bridge.json").write_text(json.dumps({"queue": queue if queue is not None else []}), encoding="utf-8")
    if make_db:
        EventStore(tmp_path / "gov" / "store.db")
    return tmp_path / "gov"


def test_main_never_creates_or_modifies_the_database_or_the_queue(tmp_path, monkeypatch, capsys):
    gov = real_world(tmp_path, monkeypatch, queue=[item(1)])
    store = EventStore(gov / "store.db")
    store.publish(**bridge_to_store_args({"kind": "review", "state": "CHANGES_REQUESTED", "event_id": "review:1001", "pr": 7, "author": "x", "url": "u"},
                                         {"head_sha": "a" * 40, "refs": []}))

    def content():
        return {f.name: f.read_bytes() for f in sorted(gov.iterdir()) if f.is_file() and not f.name.endswith(("-shm", "-wal"))}
    before = content()
    assert sd.main(["--json"]) == 0
    capsys.readouterr()
    assert content() == before                                                                     # banco e fila: bytes identicos
    sidecars = [f for f in gov.iterdir() if f.name.endswith(("-shm", "-wal"))]
    assert all(f.stat().st_size == 0 or f.name.endswith("-shm") for f in sidecars)                 # no maximo os arquivos auxiliares VAZIOS que o SQLite abre para ler um banco WAL


def test_main_opens_the_database_read_only_even_when_the_file_cannot_be_written(tmp_path, monkeypatch, capsys):
    gov = real_world(tmp_path, monkeypatch, queue=[])
    import os
    import stat
    db = gov / "store.db"
    os.chmod(db, stat.S_IREAD)
    try:
        assert sd.main(["--json"]) == 0
        capsys.readouterr()
    finally:
        os.chmod(db, stat.S_IWRITE | stat.S_IREAD)


def test_read_only_store_cannot_write(tmp_path):
    db = tmp_path / "e.db"
    EventStore(db).publish("CORRECTION_REQUESTED", "k", "pr:1", {"x": 1})
    ro = sd.ReadOnlyStore(db)
    assert len(ro.events()) == 1
    import sqlite3
    conn = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("DELETE FROM events")
    conn.close()


@pytest.mark.parametrize("name,content", [("ausente", None), ("zerado", b"\x00" * 64), ("array", b"[]"), ("sem_queue", b'{"seen": []}'),
                                          ("queue_nao_lista", b'{"queue": {"a": 1}}'), ("queue_de_strings", b'{"queue": ["x"]}'), ("nao_utf8", b"\xff\xfe{}")])
def test_main_errors_when_the_json_source_is_absent_or_invalid_instead_of_reporting_success(tmp_path, monkeypatch, capsys, name, content):
    gov = real_world(tmp_path, monkeypatch, write_queue=False)
    if content is not None:
        (gov / "bridge.json").write_bytes(content)
    EventStore(gov / "store.db").publish("CORRECTION_REQUESTED", "review:1:7:" + "a" * 40, "pr:7", {"x": 1}, producer="event_bridge")
    assert sd.main(["--json"]) == 2 and json.loads(capsys.readouterr().out)["ok"] is False


def test_main_errors_when_the_database_is_absent_and_does_not_create_it(tmp_path, monkeypatch, capsys):
    gov = real_world(tmp_path, monkeypatch, queue=[], make_db=False)
    assert sd.main(["--json"]) == 2 and not (gov / "store.db").exists()
    capsys.readouterr()


def test_main_reports_an_interrupted_publish_between_the_store_and_the_queue(tmp_path, monkeypatch, capsys):
    gov = real_world(tmp_path, monkeypatch, queue=[])                                               # a fila JSON nao chegou a ser salva
    EventStore(gov / "store.db").publish(**bridge_to_store_args({"kind": "review", "state": "CHANGES_REQUESTED", "event_id": "review:9", "pr": 7,
                                                                    "author": "x", "url": "u"}, {"head_sha": "a" * 40, "refs": []}))
    assert sd.main(["--json"]) == 1
    assert json.loads(capsys.readouterr().out)["divergences"][0]["code"] == "ORPHAN_EXECUTABLE"


def test_the_store_is_always_opened_with_the_sqlite_read_only_uri(tmp_path, monkeypatch):
    db = tmp_path / "e.db"
    EventStore(db)
    seen = []
    real = sd.sqlite3.connect
    monkeypatch.setattr(sd.sqlite3, "connect", lambda target, *a, **k: (seen.append((target, k.get("uri"))), real(target, *a, **k))[1])
    sd.ReadOnlyStore(db).events()
    assert len(seen) == 1 and seen[0][0].endswith("?mode=ro") and seen[0][1] is True


# -- achados da 2a revisao do Codex: elegibilidade REAL dos dois lados e fila invalida ---------------------------------------------
@pytest.mark.parametrize("state", ["FAILED", "BLOCKED_CLI", "BLOCKED_CREDENTIALS", "BLOCKED_WORKTREE"])
def test_an_exhausted_json_item_with_a_still_claimable_pending_event_is_a_divergence(state):
    found = sd.compare([item(state=state, attempts=sd.MAX_ATTEMPTS)], [event(status="PENDING")])
    assert codes(found) == [("STATE_MISMATCH", "k1")] and "PENDING" in found[0].detail                 # o JSON nao volta a escolher; o store ainda executaria


@pytest.mark.parametrize("attempts", [0, 1, 2])
def test_a_failed_json_item_with_attempts_left_and_a_pending_event_agree(attempts):
    assert sd.compare([item(state="FAILED", attempts=attempts)], [event(status="PENDING", attempt=attempts)]) == []


@pytest.mark.parametrize("attempts", [0, 1, sd.MAX_ATTEMPTS])
def test_blocked_review_fetch_is_never_picked_by_the_json_executor_so_a_pending_event_diverges(attempts):
    found = sd.compare([item(state="BLOCKED_REVIEW_FETCH", attempts=attempts)], [event(status="PENDING")])
    assert codes(found) == [("STATE_MISMATCH", "k1")]


def test_the_json_pick_states_in_the_detector_match_the_executor_picker():
    import datetime as dt

    from tools.orchestration import event_executor as ex
    assert sd.MAX_ATTEMPTS == ex.MAX_ATTEMPTS
    now = dt.datetime(2026, 11, 15, 12, tzinfo=dt.timezone.utc)
    for state in sorted(sd.EXPECTED):
        queue = [{"key": "x", "state": state, "attempts": 0}]
        picked = ex.pick({"queue": queue, "runs": []}, now) is not None
        assert picked == (state in sd.PICKABLE), state                                                  # a tabela do detector nao pode divergir do executor real


@pytest.mark.parametrize("bad, fragment", [
    ({"state": "QUEUED"}, "kind"),
    ({"kind": 5}, "kind"),
    ({"kind": "review", "state": "QUEUED", "event_id": "review:1", "pr": 7, "head_sha": "a" * 40}, "key"),
    ({"kind": "review", "key": "k", "event_id": "review:1", "pr": 7, "head_sha": "a" * 40}, "state"),
    ({"kind": "review", "key": "k", "state": "QUEUED", "pr": 7, "head_sha": "a" * 40}, "event_id"),
    ({"kind": "review", "key": "k", "state": "QUEUED", "event_id": "review:1", "pr": "7", "head_sha": "a" * 40}, "pr"),
    ({"kind": "review", "key": "k", "state": "QUEUED", "event_id": "review:1", "pr": True, "head_sha": "a" * 40}, "pr"),
    ({"kind": "review", "key": "k", "state": "QUEUED", "event_id": "review:1", "pr": 7}, "head_sha"),
    ({"kind": "review", "key": "k", "state": "QUEUED", "event_id": "review:1", "pr": 7, "head_sha": "a" * 40, "attempts": "2"}, "attempts"),
    ({"kind": "review", "key": "k", "state": "QUEUED", "event_id": "review:1", "pr": 7, "head_sha": "a" * 40, "attempts": -1}, "attempts"),
])
def test_an_invalid_queue_item_is_a_structured_error_never_a_silent_ok(bad, fragment, tmp_path):
    p = tmp_path / "event_bridge.json"
    p.write_text(json.dumps({"queue": [bad]}), encoding="utf-8")
    with pytest.raises(ValueError, match=fragment):
        sd.read_queue(p)
    with pytest.raises(ValueError, match=fragment):
        sd.compare([bad], [])


def test_main_reports_an_invalid_item_as_a_json_error_with_exit_2(tmp_path, monkeypatch, capsys):
    p = tmp_path / "event_bridge.json"
    p.write_text(json.dumps({"queue": [{"state": "QUEUED"}]}), encoding="utf-8")
    monkeypatch.setenv("EVENT_BRIDGE_STATE_PATH", str(p))
    monkeypatch.setenv("EVENT_STORE_DB_PATH", str(tmp_path / "events.db"))
    EventStore(tmp_path / "events.db")
    assert sd.main(["--json"]) == 2
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and "kind" in out["error"]


# -- 6a revisao do Codex (#634): execucao ativa, orcamento de tentativas e janela de espera ------------------------------------------------------------
def test_a_json_item_still_running_blocks_the_cutover_even_when_the_mirror_is_pending():
    found = sd.compare([item(state="RUNNING")], [event(status="PENDING")])
    assert codes(found) == [("JSON_RUNNING", "k1")] and "drene" in found[0].detail


def test_a_drained_queue_with_the_mirror_in_step_is_ok():
    assert sd.compare([item(state="QUEUED", attempts=1)], [event(status="PENDING", attempt=1, max_attempts=sd.MAX_ATTEMPTS)], now=1000.0) == []


@pytest.mark.parametrize("json_attempts, event_attempt", [(0, 2), (1, 2), (0, 1)])
def test_an_event_that_spent_more_attempts_than_the_json_item_is_a_budget_divergence(json_attempts, event_attempt):
    found = sd.compare([item(state="BLOCKED_CREDENTIALS", attempts=json_attempts)], [event(status="PENDING", attempt=event_attempt, max_attempts=3)], now=1000.0)
    assert codes(found) == [("STATE_MISMATCH", "k1")] and "orcamento" in found[0].detail


def test_an_event_with_the_same_budget_agrees_and_a_larger_one_is_a_divergence():
    assert sd.compare([item(state="FAILED", attempts=2)], [event(status="PENDING", attempt=2, max_attempts=3)], now=1000.0) == []
    found = sd.compare([item(state="FAILED", attempts=2)], [event(status="PENDING", attempt=0, max_attempts=3)], now=1000.0)               # o evento tem MAIS folga: custo extra apos o cutover
    assert codes(found) == [("STATE_MISMATCH", "k1")] and "mais vezes" in found[0].detail


def test_a_json_retry_after_in_the_future_with_an_event_already_available_is_a_divergence():
    now = 1_000_000.0
    soon = "2026-11-16T00:00:00Z"
    future = sd._epoch(soon)
    found = sd.compare([item(state="FAILED", attempts=1, retry_after=soon)], [event(status="PENDING", attempt=1, available_at=future - 900)], now=future - 10)
    assert codes(found) == [("STATE_MISMATCH", "k1")] and "retry_after" in found[0].detail
    waiting = sd.compare([item(state="FAILED", attempts=1, retry_after=soon)], [event(status="PENDING", attempt=1, available_at=future)], now=future - 10)
    assert waiting == []                                                                                                    # os dois esperam ate o mesmo instante
    passed = sd.compare([item(state="FAILED", attempts=1, retry_after=soon)], [event(status="PENDING", attempt=1, available_at=future - 900)], now=future + 10)
    assert passed == [] and now > 0                                                                                         # retry_after ja passou: ambos disponiveis


@pytest.mark.parametrize("bad", [None, ""])
def test_an_absent_retry_after_is_not_a_wait(bad):
    assert sd._epoch(bad) is None
    assert sd.compare([item(state="FAILED", attempts=1, retry_after=bad)], [event(status="PENDING", attempt=1)], now=1000.0) == []


@pytest.mark.parametrize("bad", ["ontem", "2026-13-45T99:00:00Z", 12345, "2026-11-16 00:00:00"])
def test_an_unreadable_retry_after_is_a_structured_error_never_a_silent_ok(bad):
    with pytest.raises(ValueError, match="retry_after"):
        sd.compare([item(state="FAILED", attempts=1, retry_after=bad)], [event(status="PENDING", attempt=1)], now=1000.0)


# -- 7a revisao do Codex (#634): QUEUED tambem e orcamento/janela; janelas futuras ----------------------------------------------------------------------
def test_a_queued_item_returned_by_a_dry_run_with_fewer_attempts_in_the_event_is_a_budget_divergence():
    found = sd.compare([item(state="QUEUED", attempts=0)], [event(status="PENDING", attempt=2, max_attempts=3)], now=1000.0)
    assert codes(found) == [("STATE_MISMATCH", "k1")] and "orcamento" in found[0].detail


def test_a_queued_item_with_an_exhausted_budget_and_a_pending_event_is_a_divergence():
    found = sd.compare([item(state="QUEUED", attempts=sd.MAX_ATTEMPTS)], [event(status="PENDING", attempt=0)], now=1000.0)
    assert codes(found) == [("STATE_MISMATCH", "k1")]


def test_a_queued_item_in_step_with_its_event_agrees():
    assert sd.compare([item(state="QUEUED", attempts=1)], [event(status="PENDING", attempt=1, max_attempts=3)], now=1000.0) == []


def test_when_both_wait_in_the_future_but_the_event_becomes_available_earlier_it_is_a_divergence():
    now = 1000.0
    retry = sd._epoch("2026-11-16T00:00:00Z")
    found = sd.compare([item(state="FAILED", attempts=1, retry_after="2026-11-16T00:00:00Z")], [event(status="PENDING", attempt=1, available_at=retry - 900)], now=retry - 1000)
    assert codes(found) == [("STATE_MISMATCH", "k1")] and "antes" in found[0].detail                       # ambos no futuro, mas available_at antecede retry_after
    later = sd.compare([item(state="FAILED", attempts=1, retry_after="2026-11-16T00:00:00Z")], [event(status="PENDING", attempt=1, available_at=retry + 5)], now=retry - 1000)
    assert later == [] and now > 0                                                                          # o store espera MAIS que o JSON: nao e risco


# -- 8a revisao do Codex (#634): atraso do evento tambem e divergencia -------------------------------------------------------------------------------
def test_an_event_that_becomes_available_much_later_than_a_json_item_that_can_run_now_is_a_divergence():
    found = sd.compare([item(state="FAILED", attempts=1)], [event(status="PENDING", attempt=1, available_at=1000.0 + 900)], now=1000.0)
    assert codes(found) == [("STATE_MISMATCH", "k1")] and "atrasaria" in found[0].detail


def test_an_event_waiting_much_longer_than_the_json_retry_after_is_a_divergence_but_a_small_skew_is_not():
    retry = sd._epoch("2026-11-16T00:00:00Z")
    late = sd.compare([item(state="FAILED", attempts=1, retry_after="2026-11-16T00:00:00Z")], [event(status="PENDING", attempt=1, available_at=retry + 3600)], now=retry - 1000)
    assert codes(late) == [("STATE_MISMATCH", "k1")] and "atrasaria" in late[0].detail
    skew = sd.compare([item(state="FAILED", attempts=1, retry_after="2026-11-16T00:00:00Z")], [event(status="PENDING", attempt=1, available_at=retry + 30)], now=retry - 1000)
    assert skew == []


# -- 9a revisao do Codex (#634): max_attempts=0 e formato canonico de retry_after ------------------------------------------------------------------------
def test_an_event_with_max_attempts_zero_is_never_claimable_and_is_a_divergence_not_a_default_of_three():
    found = sd.compare([item(state="QUEUED", attempts=0)], [event(status="PENDING", attempt=0, max_attempts=0)], now=1000.0)
    assert codes(found) == [("STATE_MISMATCH", "k1")] and "nao reivindicavel" in found[0].detail
    assert sd.compare([item(state="QUEUED", attempts=0)], [event(status="PENDING", attempt=0)], now=1000.0) == []                 # ausente = padrao


@pytest.mark.parametrize("bad", ["2026-1-01T00:00:00Z", "2026-01-1T00:00:00Z", "2026-01-01T0:00:00Z", "2026-01-01 00:00:00Z", "2026-01-01T00:00:00+00:00", " 2026-01-01T00:00:00Z"])
def test_a_non_canonical_retry_after_is_a_structured_error_because_the_json_executor_compares_text(bad):
    with pytest.raises(ValueError, match="retry_after"):
        sd.compare([item(state="FAILED", attempts=1, retry_after=bad)], [event(status="PENDING", attempt=1)], now=1000.0)
