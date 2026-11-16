"""FP-060 MT-13 (#639): um erro num ciclo do executor nao derruba o processo; falhas seguidas demais saem com codigo proprio para a tarefa
agendada reiniciar. O interruptor, a trava de instancia e a morte do launcher continuam tendo precedencia."""
from __future__ import annotations

import json

import pytest

from tools.orchestration import event_executor as ex


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("EVENT_BRIDGE_STATE_PATH", str(tmp_path / "bridge.json"))
    monkeypatch.setenv("EXECUTION_STATE_PATH", str(tmp_path / "exec.json"))
    monkeypatch.setattr(ex.eb, "check_identity", lambda gh, policy: "fmodesto30")
    monkeypatch.setattr(ex, "resolve_claude", lambda: "claude")
    monkeypatch.setattr(ex, "WATCH_PID", None)


def lines(capsys):
    return [json.loads(ln) for ln in capsys.readouterr().out.splitlines() if ln.strip().startswith("{")]


# ------------------------------------------------------------------------------------------------------ funcoes puras
def test_backoff_doubles_with_each_consecutive_failure_and_is_capped():
    assert [ex.cycle_backoff(120, n) for n in (0, 1, 2, 3)] == [120.0, 240.0, 480.0, 900.0]
    assert ex.cycle_backoff(120, 30) == ex.MAX_CYCLE_BACKOFF_S
    assert ex.cycle_backoff(0, 1) >= 2.0                                        # intervalo 0 nao vira espera 0


def test_the_backoff_never_goes_below_the_configured_interval():
    assert all(ex.cycle_backoff(3600, n) == 3600.0 for n in range(0, 12))                  # o teto de 15 min nao encurta um intervalo maior
    assert ex.cycle_backoff(600, 1) == 900.0 and ex.cycle_backoff(600, 0) == 600.0


@pytest.mark.parametrize("poll", [{"ERROR": 1}, {"ACCEPT": 2, "ERROR": 3}])
def test_a_cycle_whose_poll_failed_counts_as_a_failure_even_without_an_exception(poll):
    res, n = ex.guarded_cycle(lambda: {"poll": poll, "action": "IDLE"}, 4)
    assert n == 5 and res["consecutive_errors"] == 5 and res["action"] == "IDLE"


def test_a_cycle_with_a_clean_poll_resets_the_count():
    assert ex.guarded_cycle(lambda: {"poll": {"ACCEPT": 1, "ERROR": 0}}, 6)[1] == 0


def test_the_loop_exits_for_a_restart_when_the_poll_keeps_failing_without_exceptions(monkeypatch, capsys):
    calls = scripted(monkeypatch, [{"poll": {"ERROR": 1}, "action": "IDLE"}] * ex.MAX_CONSECUTIVE_CYCLE_ERRORS)
    monkeypatch.setattr(ex, "sleep_watching", lambda *a, **k: True)
    assert ex.main(["run", "--interval", "1"]) == 7 and len(calls) == ex.MAX_CONSECUTIVE_CYCLE_ERRORS
    capsys.readouterr()


def test_guarded_cycle_returns_the_result_and_resets_the_failure_count_on_success():
    assert ex.guarded_cycle(lambda: {"poll": {}}, 5) == ({"poll": {}}, 0)


def test_guarded_cycle_turns_an_exception_into_a_record_and_counts_it():
    def boom():
        raise RuntimeError("gh api falhou")
    res, n = ex.guarded_cycle(boom, 2)
    assert n == 3 and res == {"cycle_error": "RuntimeError: gh api falhou", "consecutive_errors": 3}


def test_guarded_cycle_never_swallows_ctrl_c_or_an_explicit_exit():
    for exc in (KeyboardInterrupt(), SystemExit(3)):
        def boom(e=exc):
            raise e
        with pytest.raises(type(exc)):
            ex.guarded_cycle(boom, 0)


def test_the_error_record_never_carries_a_token():
    def boom():
        raise RuntimeError("401 com ghp_" + "a" * 36)
    res, _ = ex.guarded_cycle(boom, 0)
    assert "ghp_" + "a" * 36 not in res["cycle_error"]


# ----------------------------------------------------------------------------------------------------------- laco main
def scripted(monkeypatch, outcomes):
    """run_cycle devolve/levanta na ordem; ao esgotar, o proximo `sleep_watching` encerra o laco (launcher 'morreu')."""
    calls = []

    def cycle(*a, **k):
        calls.append(1)
        if len(calls) > len(outcomes):
            pytest.fail("o laco continuou depois do ultimo ciclo previsto (limite de falhas ausente?)")   # BaseException: nao e engolida
        out = outcomes[len(calls) - 1]
        if isinstance(out, Exception):
            raise out
        return out
    monkeypatch.setattr(ex, "run_cycle", cycle)
    return calls


def test_the_loop_survives_failing_cycles_and_recovers_on_the_next_one(monkeypatch, capsys):
    calls = scripted(monkeypatch, [RuntimeError("rede"), OSError("disco"), {"action": "IDLE"}])
    waits = []
    monkeypatch.setattr(ex, "sleep_watching", lambda seconds, pid, step=2.0: waits.append(seconds) or len(waits) < 3)

    code = ex.main(["run", "--interval", "10"])

    out = lines(capsys)
    assert code == 5 and len(calls) == 3                                         # saiu so porque o launcher "morreu" apos o 3o ciclo
    assert [("cycle_error" in o) for o in out if "at" in o and "fatal" not in o] == [True, True, False]
    assert waits[:2] == [ex.cycle_backoff(10, 1), ex.cycle_backoff(10, 2)]       # backoff crescente; o ciclo bom volta ao intervalo normal


def test_the_loop_exits_with_its_own_code_after_too_many_consecutive_failures(monkeypatch, capsys):
    calls = scripted(monkeypatch, [RuntimeError("x")] * ex.MAX_CONSECUTIVE_CYCLE_ERRORS)
    monkeypatch.setattr(ex, "sleep_watching", lambda *a, **k: True)

    code = ex.main(["run", "--interval", "1"])

    assert code == 7 and len(calls) == ex.MAX_CONSECUTIVE_CYCLE_ERRORS
    assert "reiniciar" in lines(capsys)[-1]["fatal"]


def test_a_success_in_the_middle_resets_the_failure_count(monkeypatch, capsys):
    n = ex.MAX_CONSECUTIVE_CYCLE_ERRORS - 1
    calls = scripted(monkeypatch, [RuntimeError("x")] * n + [{"action": "IDLE"}] + [RuntimeError("x")] * n)
    waits = []
    monkeypatch.setattr(ex, "sleep_watching", lambda seconds, pid, step=2.0: waits.append(1) or len(calls) < 2 * n + 1)

    assert ex.main(["run", "--interval", "1"]) == 5                              # nenhuma das duas rajadas chegou ao limite
    capsys.readouterr()


def test_once_reports_a_failing_cycle_with_exit_1_instead_of_a_traceback(monkeypatch, capsys):
    scripted(monkeypatch, [RuntimeError("rede")])
    assert ex.main(["run", "--once"]) == 1
    assert "cycle_error" in capsys.readouterr().out


def test_the_instance_lock_is_released_when_the_loop_gives_up(monkeypatch):
    scripted(monkeypatch, [RuntimeError("x")] * ex.MAX_CONSECUTIVE_CYCLE_ERRORS)
    monkeypatch.setattr(ex, "sleep_watching", lambda *a, **k: True)
    assert ex.main(["run", "--interval", "1"]) == 7
    again = ex.InstanceLock(ex.instance_lock_path())
    assert again.acquire()                                                       # nao ficou preso depois de sair
    again.release()


def test_the_disable_switch_and_the_launcher_death_still_win_over_the_recovery_loop(monkeypatch, capsys):
    monkeypatch.setattr(ex, "run_cycle", lambda *a, **k: pytest.fail("sem launcher vivo nao roda ciclo"))
    monkeypatch.setattr(ex, "pid_alive", lambda pid: False)
    assert ex.main(["run", "--watch-pid", "999999"]) == 5
    assert "encerrou" in capsys.readouterr().out


def test_an_unreadable_state_file_while_computing_the_wait_does_not_kill_a_loop_that_is_recovering(monkeypatch, capsys):
    scripted(monkeypatch, [{"action": "IDLE"}])
    monkeypatch.setattr(ex.eb, "load", lambda *a, **k: (_ for _ in ()).throw(ValueError("arquivo zerado")))
    waits = []
    monkeypatch.setattr(ex, "sleep_watching", lambda seconds, pid, step=2.0: waits.append(seconds) and False)

    assert ex.main(["run", "--interval", "10"]) == 5                             # chegou ao sleep: nao morreu no eb.load
    assert waits == [ex.cycle_backoff(10, 1)]
    capsys.readouterr()


def test_after_a_failure_the_wait_also_respects_the_persisted_bridge_backoff(monkeypatch):
    monkeypatch.setattr(ex.eb, "load", lambda *a, **k: {"backoff_s": 30})
    assert ex.loop_wait(1, 1) == 30.0                                            # ciclo pediria 2 s; o bridge pediu 30
    monkeypatch.setattr(ex.eb, "load", lambda *a, **k: {"backoff_s": 3600})
    assert ex.loop_wait(1, 1) == 3600.0                                          # backoff acumulado antes de um reinicio
    assert ex.loop_wait(1, 0) == 3600.0                                          # sem falha de ciclo tambem


def test_a_small_persisted_backoff_never_shortens_the_cycle_backoff(monkeypatch):
    monkeypatch.setattr(ex.eb, "load", lambda *a, **k: {"backoff_s": 5})
    assert ex.loop_wait(600, 1) == 900.0 and ex.loop_wait(600, 0) == 600.0


@pytest.mark.parametrize("bad", [ValueError("zerado"), OSError("disco"), TypeError("x")])
def test_unreadable_bridge_state_falls_back_to_the_cycle_backoff(monkeypatch, bad):
    monkeypatch.setattr(ex.eb, "load", lambda *a, **k: (_ for _ in ()).throw(bad))
    assert ex.loop_wait(10, 0) == ex.cycle_backoff(10, 1) and ex.loop_wait(10, 3) == ex.cycle_backoff(10, 3)


def test_the_loop_really_waits_the_persisted_backoff_after_a_poll_failure(monkeypatch, capsys):
    scripted(monkeypatch, [{"poll": {"ERROR": 1}}])
    monkeypatch.setattr(ex.eb, "load", lambda *a, **k: {"backoff_s": 30})
    waits = []
    monkeypatch.setattr(ex, "sleep_watching", lambda seconds, pid, step=2.0: waits.append(seconds) and False)
    assert ex.main(["run", "--interval", "1"]) == 5
    assert waits == [30.0]
    capsys.readouterr()
