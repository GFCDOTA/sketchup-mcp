"""Trava do estado de execucao (`execution_state.locked`) por LOCK DO SO, e a transicao com o protocolo antigo de arquivo O_EXCL (FP-060, #643)."""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import pytest

from tools.validation import execution_state as es


@pytest.fixture()
def path(tmp_path, monkeypatch):
    p = tmp_path / "runs/governance/execution_state.json"
    monkeypatch.setenv("EXECUTION_STATE_PATH", str(p))
    return p


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


# ------------------------------------- transicao com o protocolo ANTIGO (O_EXCL + PID + apagar ao sair): revisao do Codex #643, 4a rodada
LEGACY = """
import os, sys, time
from pathlib import Path
# o protocolo ANTIGO, copiado da base: cria com O_EXCL, grava o PID, apaga ao sair; quebra trava de dono morto ou com mais de 60 s
def legacy_locked_enter(p, wait_s):
    deadline = time.time() + wait_s
    while True:
        try:
            fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(fd, str(os.getpid()).encode("ascii"))
            finally:
                os.close(fd)
            return True
        except FileExistsError:
            try:
                age = time.time() - p.stat().st_mtime
            except FileNotFoundError:
                continue
            raw = ""
            try:
                raw = p.read_text(encoding="utf-8").strip()
            except OSError:
                pass
            dead = raw.isdigit() and int(raw) != os.getpid() and not alive(int(raw))
            if age > 60 or dead:
                p.unlink(missing_ok=True)
                continue
            if time.time() > deadline:
                return False
            time.sleep(0.02)
def alive(pid):
    from tools.validation.execution_state import pid_alive
    return pid_alive(pid)
"""

LEGACY_HOLD = LEGACY + """
lock = Path(sys.argv[1]).with_suffix(".lock")
assert legacy_locked_enter(lock, 5)
print("held", flush=True)
time.sleep(float(sys.argv[2]))
lock.unlink(missing_ok=True)
"""

LEGACY_COUNTER = LEGACY + """
import json
state, n = Path(sys.argv[1]), int(sys.argv[2])
lock = state.with_suffix(".lock")
done = 0
for _ in range(n):
    if not legacy_locked_enter(lock, 0.3):
        continue
    try:
        cur = json.loads(state.read_text()) if state.exists() else {"n": 0}
        time.sleep(0.001)
        state.write_text(json.dumps({"n": cur["n"] + 1}))
        done += 1
    finally:
        lock.unlink(missing_ok=True)
print(done, flush=True)
"""

NEW_COUNTER = """
import json, sys, time
from pathlib import Path
from tools.validation import execution_state as es
state, n = Path(sys.argv[1]), int(sys.argv[2])
done = 0
for _ in range(n):
    try:
        with es.locked(state, wait_s=0.3):
            cur = json.loads(state.read_text()) if state.exists() else {"n": 0}
            time.sleep(0.001)
            state.write_text(json.dumps({"n": cur["n"] + 1}))
            done += 1
    except TimeoutError:
        continue
print(done, flush=True)
"""


def _child(code, *args):
    import os
    import subprocess
    import sys
    root = Path(__file__).resolve().parents[1]
    return subprocess.Popen([sys.executable, "-c", code, *map(str, args)], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            env={**os.environ, "PYTHONPATH": str(root), "PYTHONUTF8": "1"})


def test_a_legacy_process_inside_its_critical_section_keeps_the_new_protocol_out(path):
    import time
    path.parent.mkdir(parents=True, exist_ok=True)
    holder = _child(LEGACY_HOLD, path, 1.5)
    try:
        assert holder.stdout.readline().strip() == "held"
        t0 = time.time()
        with pytest.raises(TimeoutError, match="processo antigo"):
            with es.locked(path, wait_s=0.4):
                pytest.fail("entrou na secao critica junto com um dono do protocolo antigo")
        assert time.time() - t0 < 1.2
        with es.locked(path, wait_s=5):                                                           # o dono antigo saiu (apagou o arquivo): o novo entra
            pass
    finally:
        holder.kill()
        holder.wait(timeout=10)


def test_while_the_new_protocol_holds_the_lock_a_legacy_process_sees_a_live_owner_and_waits():
    import os
    import tempfile
    d = Path(tempfile.mkdtemp())
    state = d / "s.json"
    with es.locked(state):
        lock = state.with_suffix(".lock")
        assert lock.read_text(encoding="ascii").strip() == f"{os.getpid()}{es.NEW_PROTOCOL_MARK}"                         # PID VIVO gravado no inicio, como o protocolo antigo grava
        with pytest.raises(FileExistsError):
            os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))                          # o O_EXCL antigo falha: ele espera
    assert state.with_suffix(".lock").read_bytes() == b""                                           # ao sair, o PID e limpo (nao fica um PID vivo enganando ninguem)


def test_a_dead_legacy_owner_or_a_legacy_file_older_than_60_seconds_does_not_block_the_new_protocol(path):
    import os
    import subprocess
    import sys
    import time
    lock = path.with_suffix(".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    lock.write_text(str(dead.pid), encoding="ascii")                                                 # dono antigo MORTO no meio da secao
    with es.locked(path, wait_s=1):
        pass
    lock.write_text(str(os.getppid()), encoding="ascii")                                             # PID vivo (o processo pai)...
    old = time.time() - (es.LEGACY_STALE_S + 5)
    os.utime(lock, (old, old))                                                                       # ...mas arquivo mais velho que 60 s: a regra antiga o quebraria
    with es.locked(path, wait_s=1):
        pass


def test_our_own_pid_in_the_file_never_blocks_us(path):
    import os
    lock = path.with_suffix(".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(str(os.getpid()), encoding="ascii")
    with es.locked(path, wait_s=1):
        pass


def test_two_processes_one_on_each_protocol_never_lose_an_update(path):
    import json
    state = path
    state.parent.mkdir(parents=True, exist_ok=True)
    legacy, new = _child(LEGACY_COUNTER, state, 40), _child(NEW_COUNTER, state, 40)
    out_legacy, err_legacy = legacy.communicate(timeout=120)
    out_new, err_new = new.communicate(timeout=120)
    assert legacy.returncode == 0 and new.returncode == 0, (err_legacy[-300:], err_new[-300:])
    total = json.loads(state.read_text())["n"]
    assert total == int(out_legacy.strip()) + int(out_new.strip())                                  # nenhuma atualizacao perdida: exclusao mutua entre as DUAS versoes
    assert int(out_new.strip()) > 0                                                                  # e o novo protocolo de fato trabalhou


def test_a_legacy_owner_that_appears_between_the_peek_and_the_open_is_still_seen_after_the_os_lock(path, monkeypatch):
    """Corrida: a espiada nao viu ninguem, o dono antigo criou o arquivo logo depois. A checagem depois do lock do SO (pelo proprio handle) o ve e o novo espera."""
    import time
    path.parent.mkdir(parents=True, exist_ok=True)
    holder = _child(LEGACY_HOLD, path, 1.2)
    try:
        assert holder.stdout.readline().strip() == "held"
        monkeypatch.setattr(es, "_peek_holder", lambda p: None)                                    # a espiada "perdeu" o dono antigo
        with pytest.raises(TimeoutError, match="processo antigo"):
            with es.locked(path, wait_s=0.4):
                pytest.fail("entrou junto com o dono antigo")
    finally:
        holder.kill()
        holder.wait(timeout=10)


def test_our_pid_replaces_a_longer_previous_content_exactly(path):
    import os
    lock = path.with_suffix(".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("9" * 40 + ":restos-de-outro-formato", encoding="ascii")
    old = time.time() - (es.LEGACY_STALE_S + 5)
    os.utime(lock, (old, old))                                                                       # velho: nao bloqueia
    with es.locked(path, wait_s=1):
        assert lock.read_text(encoding="ascii") == f"{os.getpid()}{es.NEW_PROTOCOL_MARK}"                                  # sem sobras do conteudo anterior


# -- 10a revisao do Codex (#643): PID de dono NOVO morto e reusado por outro processo nao pode bloquear -------------------------------------------------
def test_a_lock_file_left_by_a_dead_new_protocol_owner_whose_pid_is_now_a_live_stranger_does_not_block(tmp_path):
    import subprocess
    import sys
    import time
    stranger = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        path = tmp_path / "state.json"
        lock_file = path.with_suffix(".lock")
        lock_file.write_text(f"{stranger.pid}{es.NEW_PROTOCOL_MARK}", encoding="ascii")          # o dono novo morreu; o SO soltou o lock; o PID agora e de OUTRO processo vivo
        t0 = time.monotonic()
        with es.locked(path, wait_s=3.0):
            pass
        assert time.monotonic() - t0 < 2.0                                                        # imediato: o lock do SO e a verdade
    finally:
        stranger.kill()
        stranger.wait(timeout=10)


def test_a_plain_pid_of_a_live_process_is_still_treated_as_a_legacy_owner(tmp_path):
    import subprocess
    import sys
    stranger = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        path = tmp_path / "state.json"
        path.with_suffix(".lock").write_text(str(stranger.pid), encoding="ascii")                 # formato ANTIGO (so o PID): continua protegendo a janela de migracao
        with pytest.raises(TimeoutError):
            with es.locked(path, wait_s=0.5):
                pass
    finally:
        stranger.kill()
        stranger.wait(timeout=10)


def test_the_new_owner_writes_its_pid_with_the_protocol_mark_that_the_old_reader_still_parses(tmp_path):
    path = tmp_path / "state.json"
    with es.locked(path):
        text = path.with_suffix(".lock").read_text(encoding="ascii")
        assert text == f"{os.getpid()}{es.NEW_PROTOCOL_MARK}" and text.split(":")[0].isdigit()
