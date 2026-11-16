"""FP-060 MT-07 / S2 (#626): o EventStore como fonte PRIMARIA de claim do executor. Tudo com runner/gh/worktree injetados; o SQLite e real
(arquivo temporario) e o relogio dele e controlado, entao lease vencido, reclaim e teto diario sao deterministicos."""
from __future__ import annotations

import json

import pytest

from tests.test_event_executor import HEAD, NEWHEAD, NOW, POLICY, REPO, FakeGh, Runner, item, wt_ok
from tools.orchestration import event_bridge as eb
from tools.orchestration import event_executor as ex
from tools.orchestration import shadow_divergence as sd
from tools.orchestration import sqlite_source as sq
from tools.orchestration import store_factory as sf


class Clock:
    def __init__(self, t: float = 1_000_000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("EVENT_BRIDGE_STATE_PATH", str(tmp_path / "bridge.json"))
    monkeypatch.setenv("EXECUTION_STATE_PATH", str(tmp_path / "exec.json"))
    monkeypatch.setenv("BRIDGE_WORKTREE_ROOT", str(tmp_path / "wt"))
    monkeypatch.setenv("EVENT_STORE_DB_PATH", str(tmp_path / "store.db"))
    monkeypatch.setenv("GH_TOKEN", "ghp_" + "x" * 30)
    monkeypatch.setenv(sq.SOURCE_ENV, "sqlite")
    monkeypatch.setattr(ex, "WATCH_PID", None)                                  # `main(--watch-pid)` deixa o global setado em outros testes
    monkeypatch.setattr(ex, "deliver", lambda *a, **k: ("PUSHED", "fake"))
    monkeypatch.setattr(ex, "comment_pr", lambda *a, **k: None)
    sf.reset_store()
    sq.reset_claims()
    yield
    sf.reset_store()
    sq.reset_claims()


@pytest.fixture
def clock(tmp_path):
    c = Clock()
    sf.reset_store()
    sf.get_store(tmp_path / "store.db", clock=c)
    return c


def seed_json(*items):
    eb.save({**eb.default_bridge_state(), "queue": list(items), "seen": [i["key"] for i in items]})


def seed_both(*items):
    seed_json(*items)
    store = sf.get_store()
    for it in items:
        store.publish(**sq.store_args_from_item(it))
    return store


def run_one(gh, runner=None, execute=True, **kw):
    return ex.process_one(gh, POLICY, REPO, execute, runner or Runner(gh), "claude", wt_ok, NOW, **kw)


def ev_of(store, key):
    return next(e for e in store.events() if e["idempotency_key"] == key)


def json_item(key):
    return next(t for t in eb.load()["queue"] if t["key"] == key)


KEY = f"review:9:7:{HEAD}"


# ------------------------------------------------------------------------------------------------- escolha da fonte
def test_the_default_source_is_json_so_nothing_changes_until_someone_opts_in(monkeypatch):
    monkeypatch.delenv(sq.SOURCE_ENV)
    assert sq.source() == "json" and sq.is_sqlite() is False


@pytest.mark.parametrize("value", ["SQLite3", "both", "postgres", "1"])
def test_an_unknown_source_is_refused_instead_of_falling_back_silently(monkeypatch, value):
    monkeypatch.setenv(sq.SOURCE_ENV, value)
    with pytest.raises(sq.SourceError):
        sq.source()
    seed_json(item())
    gh = FakeGh()
    res = run_one(gh, Runner(gh))
    assert res["action"] == "BLOCKED_SOURCE" and json_item(KEY)["state"] == "QUEUED"        # nao executou pela fila JSON


def test_main_refuses_to_start_with_an_unknown_source(monkeypatch, capsys):
    monkeypatch.setenv(sq.SOURCE_ENV, "typo")
    assert ex.main(["run", "--once"]) == 6
    assert "desconhecido" in capsys.readouterr().out


def test_json_mode_still_executes_from_the_json_queue_and_never_touches_the_store(monkeypatch):
    monkeypatch.setenv(sq.SOURCE_ENV, "json")
    seed_json(item())
    gh = FakeGh()
    res = run_one(gh, Runner(gh))
    assert res["action"] == "DONE" and json_item(KEY)["state"] == "DONE_AWAITING_REREVIEW"
    assert sf.get_store().events() == []


# ------------------------------------------------------------------------------------------------------- claim primario
def test_the_executor_claims_from_sqlite_runs_once_and_completes_the_event_and_mirrors_the_json_item(clock):
    store = seed_both(item())
    gh = FakeGh()
    runner = Runner(gh)

    res = run_one(gh, runner)

    assert res == {"action": "DONE", "item": KEY, "new_head": NEWHEAD, "delivery": "PUSHED"} and len(runner.calls) == 1
    ev = ev_of(store, KEY)
    assert ev["status"] == "DONE" and ev["attempt"] == 1 and json.loads(ev["result"])["new_head"] == NEWHEAD
    row = json_item(KEY)
    assert row["state"] == "DONE_AWAITING_REREVIEW" and row["new_head"] == NEWHEAD and "owner" not in row
    assert sd.collect(eb.load()["queue"], store) == []                                       # espelho consistente com o SQLite


def test_the_json_queue_does_not_choose_work_when_sqlite_is_primary(clock, monkeypatch):
    seed_both(item())
    monkeypatch.setattr(ex, "pick", lambda *a, **k: pytest.fail("a fila JSON escolheu trabalho com EXECUTOR_SOURCE=sqlite"))
    monkeypatch.setattr(ex, "recover", lambda *a, **k: pytest.fail("a fila JSON reconciliou leases com EXECUTOR_SOURCE=sqlite"))
    gh = FakeGh()

    assert run_one(gh, Runner(gh))["action"] == "DONE"


def test_an_event_that_exists_only_in_sqlite_is_executed_because_sqlite_is_the_authority(clock):
    store = sf.get_store()
    store.publish(**sq.store_args_from_item(item()))                                         # nenhuma linha na fila JSON
    gh = FakeGh()

    res = run_one(gh, Runner(gh))

    assert res["action"] == "DONE" and ev_of(store, KEY)["status"] == "DONE"


def test_a_queued_json_item_the_store_never_received_is_published_before_the_claim(clock):
    seed_json(item())                                                                        # o bridge aceitou, o publish se perdeu
    store = sf.get_store()
    assert store.events() == []
    gh = FakeGh()

    res = run_one(gh, Runner(gh))

    assert res["action"] == "DONE" and ev_of(store, KEY)["status"] == "DONE"
    assert sq.backfill_store(store) == 0                                                     # idempotente


def test_idle_when_there_is_nothing_to_claim(clock):
    seed_both()
    assert run_one(FakeGh())["action"] == "IDLE"


def test_a_malformed_event_is_discarded_and_never_executed(clock):
    store = sf.get_store()
    store.publish(event_type="CORRECTION_REQUESTED", idempotency_key="review:9:7:" + HEAD, job_id="pr:7", payload={"pr": 7})
    gh = FakeGh()
    runner = Runner(gh)

    res = run_one(gh, runner)

    assert res["action"] == "IDLE" and runner.calls == []
    assert ev_of(store, "review:9:7:" + HEAD)["status"] == "SUPERSEDED"


def test_an_event_whose_key_does_not_match_its_payload_is_discarded(clock):
    store = sf.get_store()
    args = sq.store_args_from_item(item())
    args["idempotency_key"] = f"review:9:7:{NEWHEAD}"                                          # chave de OUTRO head
    store.publish(**args)
    gh = FakeGh()
    runner = Runner(gh)

    assert run_one(gh, runner)["action"] == "IDLE" and runner.calls == []


# ----------------------------------------------------------------------------------------------------------------- dry-run
def test_dry_run_never_claims_so_repeating_it_never_burns_attempts(clock):
    store = seed_both(item())
    gh = FakeGh()
    runner = Runner(gh)

    for _ in range(6):
        res = run_one(gh, runner, execute=False)
        assert res["action"] == "DRY_RUN" and res["pr"] == 7

    ev = ev_of(store, KEY)
    assert ev["status"] == "PENDING" and ev["attempt"] == 0 and runner.calls == []


def test_dry_run_reports_a_refusal_without_touching_the_event(clock):
    store = seed_both(item())
    res = run_one(FakeGh(fork=True), execute=False)
    assert res["action"] == "REFUSED" and res["dry_run"] is True
    assert ev_of(store, KEY)["status"] == "PENDING" and ev_of(store, KEY)["attempt"] == 0


# --------------------------------------------------------------------------------------------------- resultados e retry
def test_a_head_that_moved_supersedes_the_event_and_the_json_mirror(clock):
    store = seed_both(item())
    res = run_one(FakeGh(head=NEWHEAD))
    assert res["action"] == "SUPERSEDED"
    assert ev_of(store, KEY)["status"] == "SUPERSEDED" and json_item(KEY)["state"] == "SUPERSEDED"
    assert sd.collect(eb.load()["queue"], store) == []


def test_a_failed_run_goes_back_to_pending_with_the_retry_delay_and_then_to_the_dlq(clock):
    store = seed_both(item())
    gh = FakeGh()
    for attempt in (1, 2):
        res = ex.process_one(gh, POLICY, REPO, True, Runner(gh, push=False, rc=1), "claude", wt_ok, NOW)
        assert res["action"] == "FAILED"
        ev = ev_of(store, KEY)
        assert ev["status"] == "PENDING" and ev["attempt"] == attempt and ev["available_at"] > clock.t        # nao reexecuta ja
        assert run_one(gh)["action"] == "IDLE"                                                  # dentro do retry: nada para reivindicar
        clock.t += ex.RETRY_S * attempt + 5
    res = ex.process_one(gh, POLICY, REPO, True, Runner(gh, push=False, rc=1), "claude", wt_ok, NOW)
    ev = ev_of(store, KEY)
    assert res["action"] == "FAILED" and ev["status"] == "DLQ" and ev["attempt"] == 3
    assert json_item(KEY)["state"] == "FAILED" and json_item(KEY)["attempts"] >= 3
    assert any(e["event_type"] == "JOB_FAILED" for e in store.events())                          # fato registrado
    clock.t += 10_000
    assert run_one(gh)["action"] == "IDLE"                                                      # DLQ nunca volta sozinho


def test_blocked_worktree_is_retried_later_not_executed(clock):
    store = seed_both(item())
    gh = FakeGh()
    runner = Runner(gh)

    res = ex.process_one(gh, POLICY, REPO, True, runner, "claude", lambda *a: (False, "sujo", None), NOW)

    assert res["action"] == "BLOCKED_WORKTREE" and runner.calls == []
    assert ev_of(store, KEY)["status"] == "PENDING" and "sujo" in ev_of(store, KEY)["error"]


# ----------------------------------------------------------------------------------------------- lease, fencing, recovery
def test_a_result_from_an_owner_that_lost_its_lease_is_discarded_and_changes_nothing(clock):
    store = seed_both(item())
    first = ex.claim_next("owner-a")
    assert first["key"] == KEY
    clock.t += ex.LEASE_S + 1                                                                  # o dono A morreu: lease vencido
    second = ex.claim_next("owner-b")                                                          # B reivindica o MESMO evento
    assert second["key"] == KEY and ev_of(store, KEY)["attempt"] == 2

    def done(it, b):
        it["state"], it["new_head"] = "DONE_AWAITING_REREVIEW", NEWHEAD
    sq.reset_claims()                                                                         # simula o processo A: so a memoria dele sabe do token
    sq._CLAIMED[KEY] = {"ev": store_event_at_claim_a(store, first), "owner": "owner-a", "item": dict(first)}
    assert ex.update_owned(KEY, "owner-a", done, release=True) is False                        # fencing: token velho
    assert ev_of(store, KEY)["status"] == "RUNNING" and ev_of(store, KEY)["lease_owner"] == "owner-b"
    assert ev_of(store, KEY)["result"] is None


def store_event_at_claim_a(store, first):
    """O evento como o dono A o viu ao reivindicar: token do claim de A (o de B ja o substituiu)."""
    ev = ev_of(store, KEY)
    return {**ev, "lease_token": "token-que-ja-nao-vale", "lease_owner": "owner-a", "attempt": 1}


def test_an_executor_killed_mid_run_is_recovered_by_the_next_one_after_the_lease_and_runs_once(clock):
    store = seed_both(item())
    gh = FakeGh()
    claimed = ex.claim_next("dead-executor")                                                   # morreu depois do claim, antes de qualquer resultado
    assert claimed and ev_of(store, KEY)["status"] == "RUNNING"
    sq.reset_claims()                                                                         # o processo novo nao herda a memoria do morto

    assert run_one(gh)["action"] == "IDLE"                                                     # lease ainda vale: ninguem rouba antes da hora
    clock.t += ex.LEASE_S + 1
    runner = Runner(gh)
    res = run_one(gh, runner)

    assert res["action"] == "DONE" and len(runner.calls) == 1
    ev = ev_of(store, KEY)
    assert ev["status"] == "DONE" and ev["attempt"] == 2
    assert run_one(gh)["action"] == "IDLE"                                                     # e nao roda de novo


def test_the_heartbeat_renews_the_sqlite_lease_and_cancels_the_child_when_it_is_lost(clock):
    store = seed_both(item())
    claimed = ex.claim_next("owner-a")
    before = ev_of(store, KEY)["lease_until"]
    clock.t += 100
    hb = ex.Heartbeat(claimed["key"], "owner-a", interval=0.01)
    hb.start()
    for _ in range(200):
        if ev_of(store, KEY)["lease_until"] > before:
            break
        hb.stop_evt.wait(0.01)
    assert ev_of(store, KEY)["lease_until"] == clock.t + ex.LEASE_S and not hb.lost

    clock.t += ex.LEASE_S + 1
    assert ex.claim_next("owner-b")["key"] == KEY                                              # outro executor assumiu
    for _ in range(200):
        if hb.lost:
            break
        hb.stop_evt.wait(0.01)
    hb.stop()
    assert hb.lost is True


def test_the_daily_cap_applies_to_the_sqlite_claims(clock, monkeypatch):
    monkeypatch.setattr(ex, "DAILY_CAP", 2)
    for n in (1, 2, 3):
        store = sf.get_store()
        store.publish(**sq.store_args_from_item(item(key=f"review:{n}:7:{HEAD}", event_id=f"review:{n}")))
    claimed = []
    for _ in range(3):
        c = ex.claim_next(f"o{len(claimed)}")
        if c is None:
            break
        claimed.append(c)
        sq._store().complete(sq._CLAIMED[c["key"]]["ev"], {})                                  # termina; so o teto limita
        sq.reset_claims()
    assert len(claimed) == 2
    clock.t += sq.DAY_S + 1
    assert ex.claim_next("o-next") is not None                                                 # 24 h depois o teto libera


# ------------------------------------------------------------------------------------------- SQLite e a verdade (fail-closed)
def test_an_unavailable_store_stops_the_executor_instead_of_falling_back_to_the_json_queue(clock, monkeypatch):
    seed_json(item())
    gh = FakeGh()
    runner = Runner(gh)

    def boom():
        raise OSError("disco indisponivel")
    monkeypatch.setattr(sq, "_store", boom)

    res = run_one(gh, runner)

    assert res["action"] == "BLOCKED_STORE" and runner.calls == []
    assert json_item(KEY)["state"] == "QUEUED"


# ------------------------------------------------------------------------------------------------------------- rollback
def test_rollback_marks_in_the_json_queue_what_sqlite_already_finished(clock):
    store = seed_both(item())
    claimed = store.claim(("CORRECTION_REQUESTED",), "x", 60)
    store.complete(claimed, {"action": "DONE", "new_head": NEWHEAD})                           # o SQLite concluiu; o JSON ficou para tras
    assert json_item(KEY)["state"] == "QUEUED"

    plan = sq.rollback_plan(store, eb.load())
    assert plan["blocked"] == [] and plan["changes"] == [{"key": KEY, "from": "QUEUED", "to": "DONE_AWAITING_REREVIEW", "store_status": "DONE"}]
    out = sq.rollback_apply(store)

    assert out["applied"] == 1 and json_item(KEY)["state"] == "DONE_AWAITING_REREVIEW"
    assert sq.rollback_apply(store)["applied"] == 0                                            # idempotente
    assert ex.pick(eb.load(), NOW) is None                                                     # a volta ao JSON nao repete o trabalho


def test_rollback_maps_dlq_and_superseded_and_leaves_pending_alone(clock):
    k10, k11 = f"review:10:7:{HEAD}", f"review:11:7:{HEAD}"
    store = seed_both(item(), item(key=k10, event_id="review:10"), item(key=k11, event_id="review:11"))
    store.supersede(store.claim(("CORRECTION_REQUESTED",), "x", 60), "head mudou")              # KEY
    for _ in range(3):                                                                         # k10 esgota as tentativas
        store.fail(store.claim(("CORRECTION_REQUESTED",), "x", 60), "boom", retry_delay=0)
    assert ev_of(store, k10)["status"] == "DLQ" and ev_of(store, k11)["status"] == "PENDING"

    plan = {c["key"]: c["to"] for c in sq.rollback_plan(store, eb.load())["changes"]}

    assert plan == {KEY: "SUPERSEDED", k10: "FAILED"}                                          # k11 segue QUEUED = PENDING
    sq.rollback_apply(store)
    assert json_item(k10)["state"] == "FAILED" and json_item(k10)["attempts"] >= ex.MAX_ATTEMPTS
    assert ex.pick(eb.load(), NOW)["key"] == k11                                               # so o que ainda e trabalho volta a ser escolhido


def test_rollback_is_refused_while_an_event_has_a_live_lease(clock):
    store = seed_both(item())
    ex.claim_next("running-now")                                                               # executor ainda vivo

    out = sq.rollback_apply(store)

    assert out["applied"] == 0 and "lease vivo" in out["refused"] and out["blocked"][0]["key"] == KEY
    assert json_item(KEY)["state"] == "QUEUED"


def test_status_cli_reports_the_source_divergences_and_live_leases(clock, capsys):
    seed_both(item())
    ex.claim_next("running-now")

    assert sq.main(["status"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["source"] == "sqlite" and out["live_leases"][0]["owner"] == "running-now"


def test_rollback_cli_exit_codes(clock, capsys):
    store = seed_both(item())
    assert sq.main(["rollback-check"]) == 0
    ex.claim_next("running-now")
    assert sq.main(["rollback-check"]) == 1
    assert sq.main(["rollback-apply"]) == 1
    capsys.readouterr()
    assert ev_of(store, KEY)["status"] == "RUNNING"                                            # o CLI recusou e nao mexeu


# -- 6a revisao do Codex (#636): bloqueio de ambiente nao gasta tentativa; rollback enxerga eventos so do SQLite ---------------------------------------
@pytest.mark.parametrize("state", ["BLOCKED_CLI", "BLOCKED_CREDENTIALS", "BLOCKED_WORKTREE", "BLOCKED_REVIEW_FETCH"])
def test_a_recoverable_environment_block_never_exhausts_the_attempts_of_the_event(clock, state):
    store = seed_both(item())
    for _ in range(6):                                                                           # bem alem de max_attempts (3)
        ev = store.claim((sq.EVENT_TYPE,), "owner", 60)
        assert ev is not None, "o evento nao pode ter ido para a DLQ por bloqueios de ambiente"
        store.release(ev, f"{state}: ambiente indisponivel", retry_delay=0)
    e = ev_of(store, KEY)
    assert e["status"] == "PENDING" and e["attempt"] == 0
    ev = store.claim((sq.EVENT_TYPE,), "owner", 60)                                               # corrigido o ambiente: executa
    assert ev is not None and ev["attempt"] == 1


def test_settle_releases_a_blocked_item_and_still_fails_a_real_failure(clock):
    store = seed_both(item())
    ev = store.claim((sq.EVENT_TYPE,), "o", 60)
    assert sq._settle(store, ev, {"state": "BLOCKED_CLI", "last_error": "sem claude"}, None, 60) == "PENDING"
    assert ev_of(store, KEY)["attempt"] == 0
    clock.t += 120                                                                                # passa o atraso do retry
    ev = store.claim((sq.EVENT_TYPE,), "o", 60)
    assert sq._settle(store, ev, {"state": "FAILED", "last_error": "falhou"}, None, 60) == "PENDING"
    assert ev_of(store, KEY)["attempt"] == 1                                                      # falha real continua gastando a tentativa


def test_a_release_with_a_lost_lease_is_discarded(clock):
    store = seed_both(item())
    ev = store.claim((sq.EVENT_TYPE,), "o", 60)
    clock.t += 120
    with pytest.raises(sq.LeaseLost):
        store.release(ev, "tarde demais")


def sqlite_only_event(store, n=5, **kw):
    other = item(key=f"review:{n}:8:{HEAD}", event_id=f"review:{n}", pr=8)
    store.publish(**sq.store_args_from_item(other))                                              # existe SO no SQLite (o JSON nunca o teve)
    return other


def test_rollback_is_blocked_by_a_live_lease_on_an_event_that_exists_only_in_sqlite(clock):
    store = seed_both(item())
    other = sqlite_only_event(store)
    ev = store.claim((sq.EVENT_TYPE,), "executor-vivo", 600, job_id="pr:8")
    plan = sq.rollback_plan(store, eb.load())
    assert [b["owner"] for b in plan["blocked"]] == ["executor-vivo"] and plan["blocked"][0]["key"] == other["key"] and ev
    out = sq.rollback_apply(store)
    assert out["applied"] == 0 and "lease vivo" in out["refused"]


def test_a_pending_event_only_in_sqlite_is_brought_into_the_json_queue_with_its_attempts(clock):
    store = seed_both(item())
    other = sqlite_only_event(store)
    ev = store.claim((sq.EVENT_TYPE,), "o", 60, job_id="pr:8")
    store.fail(ev, "falha transitoria", retry_delay=900)                                          # PENDING, attempt 1, em backoff
    out = sq.rollback_apply(store)
    assert out["applied"] == 1 and [a["key"] for a in out["additions"]] == [other["key"]]
    row = json_item(other["key"])
    assert row["state"] == "FAILED" and row["attempts"] == 1 and row["retry_after"] == sq._iso(clock.t + 900) and row["pr"] == 8


def test_a_pending_event_whose_json_row_is_blocked_review_fetch_becomes_retryable_after_rollback(clock):
    store = seed_both(item())
    ev = store.claim((sq.EVENT_TYPE,), "o", 60)
    it = json_item(KEY)
    it["state"] = "BLOCKED_REVIEW_FETCH"                                                          # o espelho reverso gravou isto
    b = eb.load()
    b["queue"] = [it]
    eb.save(b)
    store.release(ev, "busca do review falhou", retry_delay=0)
    out = sq.rollback_apply(store)
    assert out["applied"] == 1 and json_item(KEY)["state"] == "QUEUED" and json_item(KEY)["attempts"] == 0
    assert ex.pick(eb.load(), NOW)["key"] == KEY


def test_an_unreconcilable_pending_event_refuses_the_rollback(clock):
    store = seed_both(item())
    store.publish(event_type=sq.EVENT_TYPE, idempotency_key="review:x:9:abc", job_id="pr:9", payload={"pr": "nao-inteiro"}, producer=sq.PRODUCER)
    out = sq.rollback_apply(store)
    assert out["applied"] == 0 and "sem review executavel" in out["refused"] and len(out["unreconcilable"]) == 1


# -- 7a revisao do Codex (#636): lease vencido, tentativas/retry_after desatualizados, DLQ com linha FAILED ------------------------------------------
def test_an_sqlite_only_event_whose_executor_died_after_the_claim_is_brought_into_the_json_queue(clock):
    store = seed_both(item())
    other = sqlite_only_event(store)
    ev = store.claim((sq.EVENT_TYPE,), "morto", 60, job_id="pr:8")
    clock.t += 600                                                                                # o lease venceu e o executor nunca terminou
    plan = sq.rollback_plan(store, eb.load())
    assert [a["key"] for a in plan["additions"]] == [other["key"]] and plan["blocked"] == [] and ev
    out = sq.rollback_apply(store)
    row = json_item(other["key"])
    assert out["applied"] >= 1 and row["state"] == "FAILED" and row["attempts"] == 1 and "retry_after" not in row


def test_an_expired_lease_on_the_last_attempt_is_exhausted_so_the_json_row_cannot_run_it_again(clock):
    store = seed_both(item())
    for _ in range(3):                                                                            # 3 claims sem terminar: o evento esgotou as tentativas
        store.claim((sq.EVENT_TYPE,), "morto", 60)
        clock.t += 600
    ev = ev_of(store, KEY)
    assert ev["attempt"] == ev["max_attempts"] == 3 and ev["status"] == "RUNNING"
    out = sq.rollback_apply(store)
    assert out["applied"] == 1 and json_item(KEY)["state"] == "FAILED" and json_item(KEY)["attempts"] >= 3


def test_a_pickable_json_row_with_stale_attempts_and_retry_after_is_reconciled_to_the_event(clock):
    store = seed_both(item())
    ev = store.claim((sq.EVENT_TYPE,), "o", 60)
    store.fail(ev, "falha", retry_delay=900)                                                      # evento: attempt 1, espera 900 s
    it = json_item(KEY)
    it.update(state="QUEUED", attempts=0)                                                         # o espelho reverso falhou: JSON ainda acha que e novo e sem espera
    b = eb.load()
    b["queue"] = [it]
    eb.save(b)
    out = sq.rollback_apply(store)
    row = json_item(KEY)
    assert out["applied"] == 1 and row["state"] == "FAILED" and row["attempts"] == 1 and row["retry_after"] == sq._iso(clock.t + 900)


def test_a_json_retry_after_later_than_the_event_availability_is_pulled_back(clock):
    store = seed_both(item())
    ev = store.claim((sq.EVENT_TYPE,), "o", 60)
    store.release(ev, "ambiente", retry_delay=0)                                                  # PENDING, attempt 0, disponivel agora
    it = json_item(KEY)
    it.update(state="BLOCKED_CLI", retry_after=sq._iso(clock.t + 5000), attempts=0)
    b = eb.load()
    b["queue"] = [it]
    eb.save(b)
    out = sq.rollback_apply(store)
    assert out["applied"] == 1 and "retry_after" not in json_item(KEY) and json_item(KEY)["state"] == "QUEUED"


def test_a_dlq_event_forces_a_failed_json_row_even_when_it_is_already_failed_with_fewer_attempts(clock):
    store = seed_both(item())
    for _ in range(3):
        ev = store.claim((sq.EVENT_TYPE,), "o", 60)
        clock.t += 1
        store.fail(ev, "falha", retry_delay=0)
    assert ev_of(store, KEY)["status"] == "DLQ"
    it = json_item(KEY)
    it.update(state="FAILED", attempts=1)                                                         # o JSON ainda pode escolhe-lo de novo
    b = eb.load()
    b["queue"] = [it]
    eb.save(b)
    out = sq.rollback_apply(store)
    assert out["applied"] == 1 and json_item(KEY)["attempts"] >= 3
    assert ex.pick(eb.load(), NOW) is None                                                        # nada executavel: o trabalho esgotado nao repete


def test_a_json_row_already_in_step_with_its_pending_event_is_not_touched(clock):
    store = seed_both(item())
    it = json_item(KEY)
    it.update(state="QUEUED", attempts=0)
    b = eb.load()
    b["queue"] = [it]
    eb.save(b)
    assert sq.rollback_apply(store)["applied"] == 0


# -- 8a revisao do Codex (#636): o dry-run enxerga os mesmos candidatos do claim real -------------------------------------------------------------------
def test_the_dry_run_sees_a_running_event_whose_lease_expired_like_the_real_claim_does(clock):
    store = seed_both(item())
    store.claim((sq.EVENT_TYPE,), "morto", 60)
    assert sq.peek_next() is None                                                                 # lease vivo: nada a escolher
    clock.t += 600
    peeked = sq.peek_next()
    assert peeked is not None and peeked["key"] == KEY
    assert ev_of(store, KEY)["attempt"] == 1 and ev_of(store, KEY)["status"] == "RUNNING"           # nao reivindicou nem gastou tentativa
    assert sq.claim_next("novo", None, lease_s=60, daily_cap=50)["key"] == KEY                      # e o claim real escolhe exatamente esse


def test_the_dry_run_sees_a_queued_json_item_that_the_store_does_not_have_yet(clock):
    seed_json(item())                                                                             # espelho falhou: o SQLite nao tem o evento
    assert sf.get_store().events() == []
    peeked = sq.peek_next()
    assert peeked is not None and peeked["key"] == KEY and sf.get_store().events() == []            # nada foi publicado pelo dry-run
    assert sq.claim_next("o", None, lease_s=60, daily_cap=50)["key"] == KEY                         # o claim real publica e reivindica


def test_the_dry_run_ignores_an_exhausted_running_event_and_a_live_job(clock):
    store = seed_both(item())
    for _ in range(3):
        store.claim((sq.EVENT_TYPE,), "morto", 60)
        clock.t += 600
    assert sq.peek_next() is None


# -- 9a revisao do Codex (#636): banco primario ausente nunca vira um banco novo; o dry-run respeita teto e leases de qualquer tipo ------------------------
def test_a_missing_primary_database_is_refused_instead_of_being_created_empty(tmp_path, monkeypatch):
    sf.reset_store()
    monkeypatch.setenv("EVENT_STORE_DB_PATH", str(tmp_path / "perdido" / "store.db"))
    monkeypatch.delenv(sq.BOOTSTRAP_ENV, raising=False)
    with pytest.raises(FileNotFoundError, match="nao crio um banco vazio"):
        sq._store()
    assert not (tmp_path / "perdido").exists()                                                    # nem o diretorio nem o arquivo foram criados
    seed_json(item())
    gh = FakeGh()
    res = run_one(gh, Runner(gh))
    assert res["action"] == "BLOCKED_STORE" and json_item(KEY)["state"] == "QUEUED"                # o executor para; nao age sobre um banco vazio


def test_an_explicit_bootstrap_may_create_the_primary_database(tmp_path, monkeypatch):
    sf.reset_store()
    monkeypatch.setenv("EVENT_STORE_DB_PATH", str(tmp_path / "novo" / "store.db"))
    monkeypatch.setenv(sq.BOOTSTRAP_ENV, "1")
    assert sq._store().events() == [] and (tmp_path / "novo" / "store.db").is_file()


def test_an_existing_primary_database_opens_normally(tmp_path, monkeypatch):
    sf.reset_store()
    path = tmp_path / "store.db"
    sq.EventStore(path)
    monkeypatch.setenv("EVENT_STORE_DB_PATH", str(path))
    assert sq._store().events() == []


def test_the_dry_run_honours_the_daily_cap_like_the_real_claim(clock):
    store = seed_both(item())
    assert sq.peek_next(daily_cap=1) is not None
    ev = store.claim((sq.EVENT_TYPE,), "o", 60)
    store.fail(ev, "falha", retry_delay=0)
    clock.t += 1
    assert sq.claim_next("o2", None, lease_s=60, daily_cap=50) is not None                          # uma segunda reivindicacao hoje
    assert sq.peek_next(daily_cap=2) is None                                                      # 2 claims nas ultimas 24 h: o teto de 2 fecha, como no claim real


def test_the_dry_run_sees_a_live_lease_of_any_event_type_on_the_same_aggregate(clock):
    store = seed_both(item())
    store.publish("IMPLEMENT_REQUESTED", "implement:issue:1:abc", f"pr:{7}", {"issue": 1}, producer="intake")           # outro tipo, MESMO agregado (job_id pr:7)
    other = store.claim(("IMPLEMENT_REQUESTED",), "w", 600, job_id="pr:7")
    assert other is not None
    assert sq.peek_next() is None and sq.claim_next("o", None, lease_s=60, daily_cap=50) is None  # o claim real tambem nao escolhe o agregado ocupado


def test_the_full_run_cycle_with_a_missing_primary_database_creates_nothing_and_blocks(tmp_path, monkeypatch):
    sf.reset_store()
    missing = tmp_path / "perdido" / "store.db"
    monkeypatch.setenv("EVENT_STORE_DB_PATH", str(missing))
    monkeypatch.delenv(sq.BOOTSTRAP_ENV, raising=False)
    seed_json(item())
    gh = FakeGh()
    runner = Runner(gh)
    out = ex.run_cycle(gh, POLICY, REPO, True, runner, "claude", wt_ok, NOW)
    assert out["action"] == "BLOCKED_STORE" and runner.calls == []                                  # nada executou
    assert not missing.parent.exists() and not missing.exists()                                     # e o banco NAO foi criado pelo caminho normal do ciclo
    assert json_item(KEY)["state"] == "QUEUED"


@pytest.mark.parametrize("action", ["BLOCKED_CLI", "BLOCKED_CREDENTIALS", "BLOCKED_WORKTREE", "BLOCKED_REVIEW_FETCH"])
def test_repeated_environment_blocks_in_shadow_mode_never_exhaust_the_mirror_event(clock, action):
    store = seed_both(item())
    it = json_item(KEY)
    for _ in range(6):                                                                             # bem alem de max_attempts (3)
        ex._sync_result_to_store(store, it, {"action": action, "reason": "ambiente indisponivel"})
        clock.t += 10
    e = ev_of(store, KEY)
    assert e["status"] == "PENDING" and e["attempt"] == 0                                           # nunca DLQ: o item JSON segue elegivel e o espelho tambem


def test_a_real_failure_in_shadow_mode_still_spends_the_attempt(clock):
    store = seed_both(item())
    ex._sync_result_to_store(store, json_item(KEY), {"action": "FAILED", "reason": "falhou"})
    assert ev_of(store, KEY)["attempt"] == 1
