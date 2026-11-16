"""FP-060 MT-09 (#628): o Agent Bar mostra o EventStore (SQLite) real, somente leitura, e nunca apresenta banco ausente/ilegivel como saudavel."""
from __future__ import annotations

import datetime as dt
import sqlite3

import pytest

from tools.orchestration.agent_bar import collectors as col
from tools.orchestration.agent_bar.models import AgentStatus, Snapshot
from tools.orchestration.event_store import EventStore

NOW = dt.datetime(2026, 11, 16, 12, 0, tzinfo=dt.timezone.utc)
T0 = NOW.timestamp()


class Clock:
    t = T0

    def __call__(self):
        return self.t


@pytest.fixture()
def store(tmp_path):
    clock = Clock()
    s = EventStore(tmp_path / "event_store.db", clock=clock)
    s.clock_handle = clock
    return s


def snap(store_dict) -> Snapshot:
    a = AgentStatus(name="x", label="y", level="ok", detail="d", pid=None, command=None, since=None)
    return Snapshot(at="t", claude=a, codex=a, listener=a, github=a, store=store_dict)


def test_a_missing_database_is_reported_as_absent_and_never_healthy(tmp_path):
    out = col.collect_store(tmp_path, NOW)
    assert out["state"] == "ausente" and not (tmp_path / "event_store.db").exists()                 # nada foi criado
    s = snap(out)
    assert s.store_ok() is False and "NAO e saudavel" in s.store_line()


def test_an_unreadable_database_is_reported_as_unavailable(tmp_path):
    (tmp_path / "event_store.db").write_bytes(b"isto nao e um banco sqlite" * 50)
    out = col.collect_store(tmp_path, NOW)
    assert out["state"] == "indisponivel" and snap(out).store_ok() is False and "NAO e saudavel" in snap(out).store_line()


def test_an_empty_healthy_store_reads_as_ok_with_zero_counts(store, tmp_path):
    out = col.collect_store(tmp_path, NOW)
    assert out["state"] == "ok" and out["counts"] == {} and out["dlq"] == [] and out["zombies"] == 0
    assert snap(out).store_ok() is True and "0 pendente(s)" in snap(out).store_line()


def test_the_queue_leases_backoff_retries_dlq_and_last_error_come_from_the_real_rows(store, tmp_path):
    clock = store.clock_handle
    store.publish("CORRECTION_REQUESTED", "k-live", "pr:1", {"x": 1})
    store.publish("CORRECTION_REQUESTED", "k-backoff", "pr:2", {"x": 1})
    store.publish("CORRECTION_REQUESTED", "k-dlq", "pr:3", {"x": 1}, max_attempts=1)
    store.publish("CORRECTION_REQUESTED", "k-wait", "pr:4", {"x": 1})
    live = store.claim(("CORRECTION_REQUESTED",), "worker-A", 300, job_id="pr:1")
    bo = store.claim(("CORRECTION_REQUESTED",), "w", 60, job_id="pr:2")
    store.fail(bo, "falha transitoria", retry_delay=900)                                            # PENDING em backoff, attempt 1
    dl = store.claim(("CORRECTION_REQUESTED",), "w", 60, job_id="pr:3")
    store.fail(dl, "esgotou", retry_delay=0)                                                       # DLQ
    clock.t += 5

    out = col.collect_store(tmp_path, dt.datetime.fromtimestamp(clock.t, dt.timezone.utc))

    assert out["counts"] == {"RUNNING": 1, "PENDING": 2, "DLQ": 1, "RECORDED": 1}                   # RECORDED = o fato JOB_FAILED do DLQ
    assert out["backoff"] == 1 and out["zombies"] == 0 and len(out["live_leases"]) == 1
    assert out["live_leases"][0]["owner"] == "worker-A" and 0 < out["live_leases"][0]["seconds_left"] <= 300
    assert [d["key"] for d in out["dlq"]] == ["k-dlq"] and out["retries"] == 0 and live["id"]
    assert out["last_error"]["error"] in ("esgotou", "falha transitoria")
    s = snap(out)
    assert s.store_ok() is False and "DLQ: #" in s.store_line() and "worker-A" in s.store_line()


def test_a_running_event_whose_lease_expired_is_flagged_as_a_dead_worker(store, tmp_path):
    clock = store.clock_handle
    store.publish("CORRECTION_REQUESTED", "k1", "pr:1", {"x": 1})
    store.claim(("CORRECTION_REQUESTED",), "morto", 5)
    clock.t += 60
    out = col.collect_store(tmp_path, dt.datetime.fromtimestamp(clock.t, dt.timezone.utc))
    assert out["zombies"] == 1 and out["live_leases"] == []
    s = snap(out)
    assert s.store_ok() is False and "ATENCAO 1 RUNNING com lease vencido" in s.store_line()


def test_collecting_never_writes_to_the_database(store, tmp_path):
    store.publish("CORRECTION_REQUESTED", "k1", "pr:1", {"x": 1})
    db = tmp_path / "event_store.db"
    before = db.read_bytes()
    col.collect_store(tmp_path, NOW)
    assert db.read_bytes() == before
    conn = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("DELETE FROM events")
    conn.close()


@pytest.mark.parametrize("dirname", ["a#b", "p%20q", "com espaco"])
def test_a_directory_with_uri_special_characters_is_still_opened_read_only(tmp_path, dirname):
    folder = tmp_path / dirname
    folder.mkdir()
    EventStore(folder / "event_store.db").publish("CORRECTION_REQUESTED", "k", "pr:1", {"x": 1})
    assert col.collect_store(folder, NOW)["state"] == "ok"


def test_the_snapshot_diagnostic_carries_the_store_line_and_the_default_is_never_healthy():
    s = snap({"state": "ok", "counts": {"PENDING": 2}, "backoff": 1, "live_leases": [], "zombies": 0, "dlq": [], "retries": 0, "last_error": None})
    assert s.store_line() in s.diagnostic() and s.store_ok() is True
    default = Snapshot(at="t", claude=s.claude, codex=s.codex, listener=s.listener, github=s.github)
    assert default.store_ok() is False and "NAO e saudavel" in default.store_line()


def test_collect_snapshot_carries_the_real_store_into_the_snapshot_and_its_diagnostic(store, tmp_path):
    from tests.test_agent_bar import LISTENER_OK, gh_with, gov
    from tests.test_agent_bar import NOW as BAR_NOW
    store.publish("CORRECTION_REQUESTED", "k1", "pr:1", {"x": 1})
    (tmp_path / "bar").mkdir()
    g = gov(tmp_path / "bar")
    (g / "event_store.db").write_bytes((tmp_path / "event_store.db").read_bytes())
    s = col.collect_snapshot(g, procs_fn=lambda: LISTENER_OK, task_fn=lambda: "Running", gh=gh_with([{"conclusion": "SUCCESS"}]), now=BAR_NOW)
    assert s.store["state"] == "ok" and s.store["counts"] == {"PENDING": 1} and "EventStore: 1 pendente(s)" in s.diagnostic()


def test_collect_snapshot_without_a_database_says_so_in_the_diagnostic(tmp_path):
    from tests.test_agent_bar import LISTENER_OK, gh_with, gov
    from tests.test_agent_bar import NOW as BAR_NOW
    (tmp_path / "bar2").mkdir()
    g = gov(tmp_path / "bar2")
    s = col.collect_snapshot(g, procs_fn=lambda: LISTENER_OK, task_fn=lambda: "Running", gh=gh_with([{"conclusion": "SUCCESS"}]), now=BAR_NOW)
    assert s.store["state"] == "ausente" and "NAO e saudavel" in s.diagnostic()


def test_the_database_is_always_opened_with_the_sqlite_read_only_uri(store, tmp_path, monkeypatch):
    seen = []
    real = sqlite3.connect
    monkeypatch.setattr(col.__dict__.get("sqlite3", sqlite3), "connect", lambda target, *a, **k: (seen.append((target, k.get("uri"))), real(target, *a, **k))[1])
    col.collect_store(tmp_path, NOW)
    assert len(seen) == 1 and seen[0][0].endswith("?mode=ro") and seen[0][1] is True


# -- 3a revisao do Codex (#663): mesmo caminho do produtor, credenciais fora do painel, ultimo erro pela FALHA mais recente ---------------------------------
def test_the_store_path_follows_the_producer_contract_not_just_the_bar_directory(tmp_path, monkeypatch):
    other = tmp_path / "outro" / "real.db"
    other.parent.mkdir()
    (tmp_path / "gov").mkdir()
    producer = EventStore(other, clock=Clock())
    producer.publish("CORRECTION_REQUESTED", "k-real", "pr:1", {"x": 1})
    decoy = EventStore(tmp_path / "gov" / "event_store.db", clock=Clock())                           # outro banco no diretorio padrao da barra
    for n in range(3):
        decoy.publish("CORRECTION_REQUESTED", f"k-decoy{n}", f"pr:{n}", {"x": 1})
    monkeypatch.delenv("EVENT_BRIDGE_STATE_PATH", raising=False)
    monkeypatch.setenv("EVENT_STORE_DB_PATH", str(other))
    assert col.collect_store(tmp_path / "gov", NOW)["counts"] == {"PENDING": 1}                       # le o banco DO PRODUTOR (1 evento), nao o do diretorio da barra (3)
    monkeypatch.delenv("EVENT_STORE_DB_PATH")
    monkeypatch.setenv("EVENT_BRIDGE_STATE_PATH", str(tmp_path / "outro" / "bridge.json"))           # sem a variavel do banco: ao lado do estado do bridge, como o produtor
    other.rename(other.with_name("event_store.db"))
    assert col.collect_store(tmp_path / "gov", NOW)["counts"] == {"PENDING": 1}
    monkeypatch.delenv("EVENT_BRIDGE_STATE_PATH")
    assert col.collect_store(tmp_path / "gov", NOW)["counts"] == {"PENDING": 3}                       # nada configurado: o diretorio de governanca da barra


def test_a_configured_but_missing_database_is_absent_even_if_another_exists_in_the_default_directory(tmp_path, monkeypatch):
    (tmp_path / "gov").mkdir()
    EventStore(tmp_path / "gov" / "event_store.db", clock=Clock())
    monkeypatch.setenv("EVENT_STORE_DB_PATH", str(tmp_path / "configurado" / "nao-existe.db"))
    out = col.collect_store(tmp_path / "gov", NOW)
    assert out["state"] == "ausente" and snap(out).store_ok() is False


SECRETS = ["ghp_" + "a" * 36, "github_pat_" + "B" * 40, "sk-proj-" + "d" * 40, "Bearer " + "x" * 30, "xoxb-" + "1" * 12 + "-" + "g" * 12, "api_key=" + "z" * 20]


@pytest.mark.parametrize("secret", SECRETS)
def test_a_credential_in_an_error_never_reaches_the_panel_or_the_copied_diagnostic(store, tmp_path, secret):
    store.publish("CORRECTION_REQUESTED", "k1", "pr:1", {"x": 1}, max_attempts=1)
    ev = store.claim(("CORRECTION_REQUESTED",), "w", 60)
    store.fail(ev, f"falhou autenticando com {secret} no GitHub")
    out = col.collect_store(tmp_path, NOW)
    text = str(out) + snap(out).store_line()
    assert secret not in text and "<segredo>" in text
    assert out["dlq"][0]["error"].count("<segredo>") == 1 and "<segredo>" in out["last_error"]["error"]


def test_the_model_redacts_again_even_if_a_raw_error_reaches_it():
    raw = {"state": "ok", "counts": {}, "backoff": 0, "live_leases": [], "zombies": 0, "dlq": [], "retries": 0,
           "last_error": {"key": "k", "error": "token " + "ghp_" + "q" * 30}}
    line = snap(raw).store_line()
    assert "ghp_" not in line and "<segredo>" in line


def test_the_last_error_is_the_most_recent_FAILURE_not_the_most_recently_touched_event(store, tmp_path):
    clock = store.clock_handle
    store.publish("CORRECTION_REQUESTED", "k-old", "pr:1", {"x": 1})
    store.publish("CORRECTION_REQUESTED", "k-new", "pr:2", {"x": 1})
    old = store.claim(("CORRECTION_REQUESTED",), "w1", 60)
    clock.t += 10
    store.fail(old, "erro ANTIGO", retry_delay=1000)                                                   # falha do k-old em T0+10
    new = store.claim(("CORRECTION_REQUESTED",), "w2", 60)
    assert new["idempotency_key"] == "k-new"
    clock.t += 10
    store.fail(new, "erro RECENTE", retry_delay=100000)                                                # falha do k-new em T0+20 (a mais recente)
    clock.t += 1500
    again = store.claim(("CORRECTION_REQUESTED",), "w3", 60)                                           # o k-old e reivindicado de novo: updated_at dele passa a ser o MAIOR
    assert again["idempotency_key"] == "k-old"
    clock.t += 5
    assert store.renew(again, 60) is True                                                              # e a renovacao do lease tambem o "toca"
    out = col.collect_store(tmp_path, NOW)
    assert out["last_error"] == {"key": "k-new", "error": "erro RECENTE"}


def test_an_event_that_later_completed_is_not_the_current_error(store, tmp_path):
    clock = store.clock_handle
    store.publish("CORRECTION_REQUESTED", "k-ok", "pr:1", {"x": 1})
    ev = store.claim(("CORRECTION_REQUESTED",), "w1", 60)
    clock.t += 5
    store.fail(ev, "falha transitoria", retry_delay=0)
    again = store.claim(("CORRECTION_REQUESTED",), "w2", 60)
    clock.t += 5
    store.complete(again, {"ok": True})
    assert col.collect_store(tmp_path, NOW)["last_error"] is None


# -- 3a revisao automatica do Codex (#663): JSON estruturado, TODO campo textual do banco, EXECUTION_STATE_PATH -----------------------------------------
@pytest.mark.parametrize("text", ['{"password":"minha-senha-longa"}', "{'token': 'abcd1234efgh'}", 'cfg={"api_key" : "k-123456789"}', "secret=valor-secreto", 'x "access_token":"zzzzzzzz"'])
def test_credentials_in_structured_messages_are_redacted(store, tmp_path, text):
    store.publish("CORRECTION_REQUESTED", "k1", "pr:1", {"x": 1}, max_attempts=1)
    ev = store.claim(("CORRECTION_REQUESTED",), "w", 60)
    store.fail(ev, f"falhou com {text}")
    out = col.collect_store(tmp_path, NOW)
    shown = str(out) + snap(out).store_line()
    for leaked in ("minha-senha-longa", "abcd1234efgh", "k-123456789", "valor-secreto", "zzzzzzzz"):
        assert leaked not in shown, leaked
    assert "<segredo>" in shown


def test_the_lease_owner_and_the_idempotency_key_are_redacted_everywhere_they_are_shown(store, tmp_path):
    token = "ghp_" + "k" * 36
    store.publish("CORRECTION_REQUESTED", f"key-{token}", "pr:1", {"x": 1}, max_attempts=1)
    live = store.claim(("CORRECTION_REQUESTED",), f"owner-{token}", 600)                                 # RUNNING com lease vivo: o dono aparece
    out = col.collect_store(tmp_path, NOW)
    assert token not in str(out) and token not in snap(out).store_line() and out["live_leases"][0]["owner"].startswith("owner-<segredo>")
    store.fail(live, "falha final")                                                                       # vai para a DLQ: a chave aparece no painel
    out = col.collect_store(tmp_path, NOW)
    assert token not in str(out) and token not in snap(out).store_line() and out["dlq"][0]["key"].startswith("key-<segredo>")


def test_the_model_redacts_owner_and_key_even_if_raw_values_reach_it():
    token = "ghp_" + "q" * 30
    raw = {"state": "ok", "counts": {}, "backoff": 0, "live_leases": [{"key": "k", "owner": token, "seconds_left": 5}], "zombies": 0,
           "dlq": [{"id": 1, "key": "k-" + token, "error": "e"}], "retries": 0, "last_error": None}
    line = snap(raw).store_line()
    assert token not in line and line.count("<segredo>") == 2


def test_only_execution_state_path_configured_still_follows_the_producer_contract(tmp_path, monkeypatch):
    (tmp_path / "gov").mkdir()
    (tmp_path / "estado").mkdir()
    producer = EventStore(tmp_path / "estado" / "event_store.db", clock=Clock())                          # ao lado do estado: store_path -> bridge_path -> state_path
    producer.publish("CORRECTION_REQUESTED", "k-real", "pr:1", {"x": 1})
    decoy = EventStore(tmp_path / "gov" / "event_store.db", clock=Clock())
    for n in range(3):
        decoy.publish("CORRECTION_REQUESTED", f"k-decoy{n}", f"pr:{n}", {"x": 1})
    for var in ("EVENT_STORE_DB_PATH", "EVENT_BRIDGE_STATE_PATH"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("EXECUTION_STATE_PATH", str(tmp_path / "estado" / "execution_state.json"))
    assert col.collect_store(tmp_path / "gov", NOW)["counts"] == {"PENDING": 1}                           # le o banco do PRODUTOR (1), nao o do diretorio da barra (3)
