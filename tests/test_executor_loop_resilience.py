"""FP-060 MT-13 (#639): um erro num ciclo do executor nao derruba o processo; falhas seguidas demais saem com codigo proprio para a tarefa
agendada reiniciar. O interruptor, a trava de instancia e a morte do launcher continuam tendo precedencia."""
from __future__ import annotations

import datetime as dt
import json
import subprocess

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
    assert ex.main(["run", "--interval", "1", "--exit-after-failures", str(ex.MAX_CONSECUTIVE_CYCLE_ERRORS)]) == 7 and len(calls) == ex.MAX_CONSECUTIVE_CYCLE_ERRORS
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

    code = ex.main(["run", "--interval", "1", "--exit-after-failures", str(ex.MAX_CONSECUTIVE_CYCLE_ERRORS)])

    assert code == 7 and len(calls) == ex.MAX_CONSECUTIVE_CYCLE_ERRORS
    assert "reiniciar" in lines(capsys)[-1]["fatal"]


def test_a_success_in_the_middle_resets_the_failure_count(monkeypatch, capsys):
    n = ex.MAX_CONSECUTIVE_CYCLE_ERRORS - 1
    calls = scripted(monkeypatch, [RuntimeError("x")] * n + [{"action": "IDLE"}] + [RuntimeError("x")] * n)
    waits = []
    monkeypatch.setattr(ex, "sleep_watching", lambda seconds, pid, step=2.0: waits.append(1) or len(calls) < 2 * n + 1)

    assert ex.main(["run", "--interval", "1", "--exit-after-failures", str(ex.MAX_CONSECUTIVE_CYCLE_ERRORS)]) == 5     # nenhuma das duas rajadas chegou ao limite
    capsys.readouterr()


def test_once_reports_a_failing_cycle_with_exit_1_instead_of_a_traceback(monkeypatch, capsys):
    scripted(monkeypatch, [RuntimeError("rede")])
    assert ex.main(["run", "--once"]) == 1
    assert "cycle_error" in capsys.readouterr().out


def test_the_instance_lock_is_released_when_the_loop_gives_up(monkeypatch):
    scripted(monkeypatch, [RuntimeError("x")] * ex.MAX_CONSECUTIVE_CYCLE_ERRORS)
    monkeypatch.setattr(ex, "sleep_watching", lambda *a, **k: True)
    assert ex.main(["run", "--interval", "1", "--exit-after-failures", str(ex.MAX_CONSECUTIVE_CYCLE_ERRORS)]) == 7
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


# -- 4a revisao do Codex (#640): backoff persistido apos reinicio e retomada sem depender dos reinicios da tarefa agendada -------------------------------
def test_by_default_the_loop_never_exits_after_many_failures_it_degrades_and_recovers_on_its_own(monkeypatch, capsys):
    n = ex.MAX_CONSECUTIVE_CYCLE_ERRORS + 4                                                          # atravessa o limite
    calls = scripted(monkeypatch, [RuntimeError("indisponivel")] * n + [{"action": "IDLE"}])
    monkeypatch.setattr(ex, "sleep_watching", lambda seconds, pid, step=2.0: len(calls) < n + 1)
    code = ex.main(["run", "--interval", "1"])
    out = [o for o in lines(capsys) if "at" in o and "fatal" not in o]
    assert code == 5 and len(calls) == n + 1                                                         # so parou porque o "launcher" morreu, nao pelo limite
    assert [bool(o.get("degraded")) for o in out] == [False] * (ex.MAX_CONSECUTIVE_CYCLE_ERRORS - 1) + [True] * 5 + [False]   # degradado ao atravessar o limite, normal ao voltar


def test_the_exit_after_failures_flag_is_still_available_for_a_restarting_task(monkeypatch, capsys):
    scripted(monkeypatch, [RuntimeError("x")] * 3)
    monkeypatch.setattr(ex, "sleep_watching", lambda *a, **k: True)
    assert ex.main(["run", "--interval", "1", "--exit-after-failures", "3"]) == 7
    assert lines(capsys)[-1]["fatal"].startswith("3 ciclos seguidos")


def persisted(monkeypatch, backoff, last_poll):
    monkeypatch.setattr(ex.eb, "load", lambda *a, **k: {"backoff_s": backoff, "last_poll": last_poll, "queue": []})


NOW_T = dt.datetime(2026, 11, 15, 12, 0, 0, tzinfo=dt.timezone.utc)


def test_a_restart_waits_for_the_remaining_persisted_backoff_before_the_first_poll(monkeypatch):
    persisted(monkeypatch, 3600, "2026-11-15T11:55:00Z")                                              # a API pediu 1 h; a tarefa reiniciou 5 min depois
    assert ex.initial_wait(NOW_T) == 3300.0                                                          # falta 55 min, nao 0
    persisted(monkeypatch, 3600, "2026-11-15T10:00:00Z")
    assert ex.initial_wait(NOW_T) == 0.0                                                             # o backoff ja passou


@pytest.mark.parametrize("backoff, last", [(0, "2026-11-15T11:59:00Z"), (30, None), (None, "2026-11-15T11:59:00Z")])
def test_no_persisted_backoff_or_no_last_poll_means_no_initial_wait(monkeypatch, backoff, last):
    persisted(monkeypatch, backoff, last)
    assert ex.initial_wait(NOW_T) == 0.0


def test_an_unreadable_state_or_a_bad_timestamp_never_blocks_the_start(monkeypatch):
    monkeypatch.setattr(ex.eb, "load", lambda *a, **k: (_ for _ in ()).throw(ValueError("zerado")))
    assert ex.initial_wait(NOW_T) == 0.0
    persisted(monkeypatch, 60, "ontem de manha")
    assert ex.initial_wait(NOW_T) == 0.0


def test_the_loop_sleeps_the_remaining_backoff_before_its_first_cycle(monkeypatch, capsys):
    persisted(monkeypatch, 600, ex.es.now_iso())
    order = []
    monkeypatch.setattr(ex, "run_cycle", lambda *a, **k: order.append("cycle") or {"action": "IDLE"})
    monkeypatch.setattr(ex, "sleep_watching", lambda seconds, pid, step=2.0: order.append(("sleep", round(seconds))) or (len(order) < 3))
    ex.main(["run", "--interval", "1"])
    assert order[0][0] == "sleep" and 590 <= order[0][1] <= 600 and order[1] == "cycle"                  # dorme o restante ANTES do primeiro ciclo
    capsys.readouterr()


def test_a_gh_outage_at_start_does_not_kill_the_process_it_waits_and_retries_the_identity(monkeypatch, capsys):
    attempts = []

    def flaky(gh, policy):
        attempts.append(1)
        if len(attempts) < 4:
            raise RuntimeError("gh api falhou: rede")
        return "fmodesto30"
    monkeypatch.setattr(ex.eb, "check_identity", flaky)
    calls = scripted(monkeypatch, [{"action": "IDLE"}])
    monkeypatch.setattr(ex, "initial_wait", lambda now=None: 0.0)
    waits = []

    def sleeper(seconds, pid, step=2.0):
        waits.append(seconds)
        return len(calls) < 1                                                                         # espera ate o 1o ciclo rodar; depois o "launcher morre"
    monkeypatch.setattr(ex, "sleep_watching", sleeper)
    assert ex.main(["run", "--interval", "10"]) == 5
    assert len(attempts) == 4 and len(calls) == 1                                                    # tentou 4 vezes e DEPOIS rodou o ciclo normal
    assert waits[:3] == [ex.cycle_backoff(10, 1), ex.cycle_backoff(10, 2), ex.cycle_backoff(10, 3)]    # backoff crescente entre as tentativas
    assert sum("degraded" in o for o in lines(capsys)) == 3


def test_a_wrong_account_at_start_is_still_fatal_not_retried(monkeypatch, capsys):
    monkeypatch.setattr(ex.eb, "check_identity", lambda gh, policy: (_ for _ in ()).throw(ex.eb.IdentityError("gh autenticado como fmmodesto")))
    monkeypatch.setattr(ex, "run_cycle", lambda *a, **k: pytest.fail("conta errada nao roda ciclo"))
    assert ex.main(["run", "--interval", "1"]) == 3 and "fatal" in lines(capsys)[-1]


def test_once_keeps_a_failed_identity_fatal(monkeypatch, capsys):
    monkeypatch.setattr(ex.eb, "check_identity", lambda gh, policy: (_ for _ in ()).throw(RuntimeError("rede")))
    monkeypatch.setattr(ex, "sleep_watching", lambda *a, **k: pytest.fail("--once nao espera nem repete"))
    assert ex.main(["run", "--once"]) == 3
    capsys.readouterr()


# -- 6a revisao do Codex (#640): timeout do gh, ordem espera -> identidade, segredo no log ----------------------------------------------------------------
@pytest.mark.parametrize("exc", [subprocess.TimeoutExpired("gh", 120), OSError("gh nao iniciou"), subprocess.SubprocessError("falha"), RuntimeError("gh falhou")])
def test_a_hung_or_missing_gh_at_start_is_retried_not_fatal(monkeypatch, capsys, exc):
    attempts = []

    def flaky(gh, policy):
        attempts.append(1)
        if len(attempts) < 3:
            raise exc
        return "fmodesto30"
    monkeypatch.setattr(ex.eb, "check_identity", flaky)
    calls = scripted(monkeypatch, [{"action": "IDLE"}])
    monkeypatch.setattr(ex, "initial_wait", lambda now=None: 0.0)
    monkeypatch.setattr(ex, "sleep_watching", lambda seconds, pid, step=2.0: len(calls) < 1)
    assert ex.main(["run", "--interval", "10"]) == 5 and len(attempts) == 3 and len(calls) == 1
    assert sum("degraded" in o for o in lines(capsys)) == 2


def test_a_wrong_account_is_still_fatal_even_though_permission_error_is_an_oserror(monkeypatch, capsys):
    monkeypatch.setattr(ex.eb, "check_identity", lambda gh, policy: (_ for _ in ()).throw(ex.eb.IdentityError("conta errada")))
    monkeypatch.setattr(ex, "run_cycle", lambda *a, **k: pytest.fail("nao roda ciclo"))
    assert ex.main(["run", "--interval", "1"]) == 3
    capsys.readouterr()


def test_the_remaining_persisted_backoff_is_slept_BEFORE_the_first_github_call(monkeypatch, capsys):
    order = []
    monkeypatch.setattr(ex, "initial_wait", lambda now=None: 600.0)
    monkeypatch.setattr(ex.eb, "check_identity", lambda gh, policy: order.append("identity") or "fmodesto30")
    monkeypatch.setattr(ex, "run_cycle", lambda *a, **k: order.append("cycle") or {"action": "IDLE"})
    monkeypatch.setattr(ex, "sleep_watching", lambda seconds, pid, step=2.0: order.append(("sleep", round(seconds))) or len(order) < 4)
    ex.main(["run", "--interval", "1"])
    assert order[:3] == [("sleep", 600), "identity", "cycle"]                                                 # espera -> identidade -> ciclo (nunca a identidade primeiro)
    capsys.readouterr()


def test_once_never_waits_for_a_backoff(monkeypatch, capsys):
    monkeypatch.setattr(ex, "initial_wait", lambda now=None: pytest.fail("--once nao espera backoff"))
    monkeypatch.setattr(ex.eb, "check_identity", lambda gh, policy: "fmodesto30")
    scripted(monkeypatch, [{"action": "IDLE"}])
    assert ex.main(["run", "--once"]) == 0
    capsys.readouterr()


@pytest.mark.parametrize("secret", ["ghp_" + "a" * 36, "github_pat_" + "B" * 40])
def test_a_credential_in_the_identity_error_never_reaches_the_log(monkeypatch, capsys, secret):
    attempts = []

    def leaky(gh, policy):
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError(f"gh api falhou: Authorization: token {secret}")
        return "fmodesto30"
    monkeypatch.setattr(ex.eb, "check_identity", leaky)
    calls = scripted(monkeypatch, [{"action": "IDLE"}])
    monkeypatch.setattr(ex, "initial_wait", lambda now=None: 0.0)
    monkeypatch.setattr(ex, "sleep_watching", lambda seconds, pid, step=2.0: len(calls) < 1)
    ex.main(["run", "--interval", "1"])
    out = capsys.readouterr().out
    assert secret not in out and "degraded" in out


def test_a_credential_in_a_fatal_once_identity_error_is_redacted_too(monkeypatch, capsys):
    secret = "ghp_" + "z" * 36
    monkeypatch.setattr(ex.eb, "check_identity", lambda gh, policy: (_ for _ in ()).throw(RuntimeError(f"falhou {secret}")))
    assert ex.main(["run", "--once"]) == 3 and secret not in capsys.readouterr().out


# -- 7a revisao do Codex (#640): trava de instancia primeiro, so a conta errada e fatal, resposta truncada e transitoria ----------------------------------
def test_a_second_instance_is_refused_at_once_before_any_wait_or_github_call(monkeypatch, capsys):
    holder = ex.InstanceLock(ex.instance_lock_path())
    assert holder.acquire()
    try:
        monkeypatch.setattr(ex, "initial_wait", lambda now=None: pytest.fail("a 2a instancia nao pode esperar backoff"))
        monkeypatch.setattr(ex.eb, "check_identity", lambda gh, policy: pytest.fail("nem chamar o GitHub"))
        monkeypatch.setattr(ex, "sleep_watching", lambda *a, **k: pytest.fail("nem dormir"))
        assert ex.main(["run", "--interval", "1"]) == 4
        assert "outra instancia" in lines(capsys)[-1]["fatal"]
    finally:
        holder.release()


def test_the_lock_is_released_when_the_loop_ends_during_the_initial_wait(monkeypatch):
    monkeypatch.setattr(ex, "initial_wait", lambda now=None: 600.0)
    monkeypatch.setattr(ex, "sleep_watching", lambda *a, **k: False)                                    # o launcher morre durante a espera
    assert ex.main(["run", "--interval", "1"]) == 5
    again = ex.InstanceLock(ex.instance_lock_path())
    assert again.acquire()
    again.release()


def test_only_the_identity_error_is_fatal_a_system_permission_error_is_retried(monkeypatch, capsys):
    attempts = []

    def starting_gh_denied(gh, policy):
        attempts.append(1)
        if len(attempts) < 3:
            raise PermissionError(13, "O acesso ao executavel do gh foi negado")                       # do SO: corrigivel, transitorio
        return "fmodesto30"
    monkeypatch.setattr(ex.eb, "check_identity", starting_gh_denied)
    calls = scripted(monkeypatch, [{"action": "IDLE"}])
    monkeypatch.setattr(ex, "initial_wait", lambda now=None: 0.0)
    monkeypatch.setattr(ex, "sleep_watching", lambda seconds, pid, step=2.0: len(calls) < 1)
    assert ex.main(["run", "--interval", "1"]) == 5 and len(attempts) == 3 and len(calls) == 1
    capsys.readouterr()


def test_the_wrong_account_error_is_the_identity_error_class(monkeypatch, capsys):
    monkeypatch.setattr(ex.eb, "check_identity", lambda gh, policy: (_ for _ in ()).throw(ex.eb.IdentityError("gh autenticado como fmmodesto")))
    monkeypatch.setattr(ex, "run_cycle", lambda *a, **k: pytest.fail("conta errada nao roda ciclo"))
    monkeypatch.setattr(ex, "initial_wait", lambda now=None: 0.0)
    assert issubclass(ex.eb.IdentityError, PermissionError)
    assert ex.main(["run", "--interval", "1"]) == 3
    capsys.readouterr()


@pytest.mark.parametrize("exc", [json.JSONDecodeError("Expecting value", "", 0), ValueError("resposta truncada")])
def test_a_truncated_or_invalid_gh_answer_at_start_is_retried(monkeypatch, capsys, exc):
    attempts = []

    def flaky(gh, policy):
        attempts.append(1)
        if len(attempts) < 2:
            raise exc
        return "fmodesto30"
    monkeypatch.setattr(ex.eb, "check_identity", flaky)
    calls = scripted(monkeypatch, [{"action": "IDLE"}])
    monkeypatch.setattr(ex, "initial_wait", lambda now=None: 0.0)
    monkeypatch.setattr(ex, "sleep_watching", lambda seconds, pid, step=2.0: len(calls) < 1)
    assert ex.main(["run", "--interval", "1"]) == 5 and len(attempts) == 2
    capsys.readouterr()


REAL_CHECK = ex.eb.check_identity                                                                  # capturada na importacao: a fixture autouse troca `check_identity` por um fake


# -- 8a revisao do Codex (#640): resposta incompleta do `gh api user` nao e conta errada -----------------------------------------------------------
@pytest.mark.parametrize("answer", [[], [{"login": "x"}], {}, {"login": ""}, {"login": "  "}, {"login": None}, {"id": 1}, "texto", None])
def test_an_empty_or_malformed_user_answer_is_a_transient_error_not_a_wrong_account(answer):
    with pytest.raises(RuntimeError, match="sem login valido") as err:
        REAL_CHECK(lambda path: answer, {"executor_logins": ["fmodesto30"], "reviewers": ["fmmodesto"]})
    assert not isinstance(err.value, ex.eb.IdentityError)


@pytest.mark.parametrize("answer", [[], {}, {"login": ""}])
def test_the_start_loop_retries_an_incomplete_user_answer_instead_of_exiting_3(monkeypatch, capsys, answer):
    answers = [answer, answer, {"login": "fmodesto30"}]
    attempts = []

    def gh(path):
        attempts.append(1)
        return answers[min(len(attempts) - 1, 2)]
    monkeypatch.setattr(ex.eb, "check_identity", lambda _gh, policy: REAL_CHECK(gh, policy))              # o `gh` padrao e ligado na definicao: injeta o fake pela propria funcao
    calls = scripted(monkeypatch, [{"action": "IDLE"}])
    monkeypatch.setattr(ex, "initial_wait", lambda now=None: 0.0)
    monkeypatch.setattr(ex, "sleep_watching", lambda seconds, pid, step=2.0: len(calls) < 1)
    assert ex.main(["run", "--interval", "1"]) == 5 and len(attempts) == 3 and len(calls) == 1
    capsys.readouterr()


def test_a_real_wrong_account_with_a_valid_login_is_still_fatal(monkeypatch, capsys):
    monkeypatch.setattr(ex.eb, "check_identity", lambda _gh, policy: REAL_CHECK(lambda path: {"login": "fmmodesto"}, policy))
    monkeypatch.setattr(ex, "initial_wait", lambda now=None: 0.0)
    assert ex.main(["run", "--interval", "1"]) == 3
    capsys.readouterr()


# -- revisao do Codex (#640, 629477cc): launcher fixa o caminho do gh e aplica o contrato de saida apos 8 falhas -------------------------------------------
LAUNCHER = "tools/orchestration/run_event_bridge.ps1"


def _launcher_text() -> str:
    from pathlib import Path
    return (Path(__file__).resolve().parents[1] / LAUNCHER).read_text(encoding="utf-8")


def test_the_launcher_pins_gh_bin_to_the_fallback_path_even_when_gh_is_missing_at_logon():
    src = _launcher_text()
    assert "\n$env:GH_BIN = $gh\n" in src                                                          # incondicional: o gh que reaparecer ali e achado depois
    assert "if (Test-Path $gh) { $env:GH_BIN = $gh }" not in src


def test_the_launcher_recovers_continuously_by_default_and_exit_code_7_is_opt_in():
    src = _launcher_text()
    assert "[int]$ExitAfterFailures = 0" in src                                                      # padrao: nunca sair (a tarefa agendada so reinicia 3 vezes)
    assert 'if ($ExitAfterFailures -gt 0) { $argsList += @("--exit-after-failures", $ExitAfterFailures) }' in src


def test_a_long_outage_never_ends_the_default_loop():
    """Indisponibilidade maior que (falhas para sair x 3 reinicios da tarefa): nem o executor nem o launcher saem por padrao."""
    import inspect

    from tools.orchestration import event_executor as ex
    src = inspect.getsource(ex)
    assert '"--exit-after-failures", type=int, default=0' in src and "[int]$ExitAfterFailures = 0" in _launcher_text()
