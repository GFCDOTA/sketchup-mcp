"""Real Windows Job Object process-tree tests; no agents or listeners are started."""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from tools.orchestration import process_supervisor
from tools.orchestration.event_store import EventStore, LeaseLost
from tools.orchestration.process_supervisor import ProcessSupervisorError, WindowsJob, run_claimed

pytestmark = pytest.mark.skipif(os.name != "nt", reason="requires real Windows Job Objects")
ROOT = Path(__file__).resolve().parents[1]


def _env():
    return {"SystemRoot": os.environ["SystemRoot"], "TEMP": os.environ["TEMP"], "TMP": os.environ["TEMP"]}


def _wait_file(path: Path, process=None):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if path.exists():
            return
        if process is not None and process.poll() is not None:
            raise AssertionError(f"supervisor exited early: {process.returncode}")
        time.sleep(0.05)
    raise AssertionError(f"file was not created: {path}")


def _tree_script(tmp_path):
    # Root starts a child which signals readiness then tries a delayed side effect.
    ready, effect = tmp_path / "ready", tmp_path / "effect"
    child = f"from pathlib import Path; import time; Path({str(ready)!r}).write_text('ready'); time.sleep(3); Path({str(effect)!r}).write_text('escaped')"
    root = tmp_path / "root.py"
    root.write_text("import subprocess, sys, time\n" +
                    f"subprocess.Popen([sys.executable, '-c', {child!r}]); time.sleep(60)\n", encoding="utf-8")
    return root, ready, effect


def test_exit_code_and_timeout(tmp_path):
    with WindowsJob([sys.executable, "-c", "import time; time.sleep(.5); raise SystemExit(7)"],
                    cwd=tmp_path, env=_env()) as job:
        assert job.wait(0.01) is None
        assert job.wait(10) == 7


def test_terminate_kills_child_tree(tmp_path):
    root, ready, effect = _tree_script(tmp_path)
    with WindowsJob([sys.executable, str(root)], cwd=tmp_path, env=_env()) as job:
        _wait_file(ready)
        job.terminate()
        assert job.wait(10) is not None
    time.sleep(3.5)
    assert not effect.exists()


def test_supervisor_death_kills_child_tree(tmp_path):
    root, ready, effect = _tree_script(tmp_path)
    wrapper = tmp_path / "wrapper.py"
    wrapper.write_text(
        "import json, sys, time\n"
        "from tools.orchestration.process_supervisor import WindowsJob\n"
        "job = WindowsJob([sys.executable, sys.argv[1]], cwd=sys.argv[2], env=json.loads(sys.argv[3]))\n"
        "time.sleep(60)\n", encoding="utf-8")
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT)
    supervisor = subprocess.Popen([sys.executable, str(wrapper), str(root), str(tmp_path), json.dumps(_env())],
                                  cwd=tmp_path, env=environment, creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        _wait_file(ready, supervisor)
        supervisor.kill()
        supervisor.wait(timeout=10)
        time.sleep(3.5)
        assert not effect.exists()
    finally:
        if supervisor.poll() is None:
            supervisor.kill()
            supervisor.wait(timeout=10)


def test_closing_after_root_exit_still_kills_descendant(tmp_path):
    root, ready, effect = _tree_script(tmp_path)
    source = root.read_text(encoding="utf-8").replace("; time.sleep(60)", "; time.sleep(1)")
    root.write_text(source, encoding="utf-8")
    with WindowsJob([sys.executable, str(root)], cwd=tmp_path, env=_env()) as job:
        _wait_file(ready)
        assert job.wait(10) == 0
    time.sleep(3.5)
    assert not effect.exists()


def test_job_assignment_failure_never_launches_process(tmp_path, monkeypatch):
    marker = tmp_path / "launched"
    script = f"from pathlib import Path; Path({str(marker)!r}).write_text('launched')"
    monkeypatch.setattr(process_supervisor, "_update_attrs", lambda *args: 0)
    with pytest.raises(ProcessSupervisorError, match="JOB_LIST"):
        WindowsJob([sys.executable, "-c", script], cwd=tmp_path, env=_env())
    assert not marker.exists()


def test_rejects_invalid_command_and_never_falls_back(tmp_path):
    with pytest.raises(ValueError):
        WindowsJob(["python"], cwd=tmp_path, env=_env())
    with pytest.raises((ValueError, ProcessSupervisorError)):
        WindowsJob([str(tmp_path / "missing.exe")], cwd=tmp_path, env=_env())


def test_claimed_process_finishes_and_result_is_fenced(tmp_path):
    store = EventStore(tmp_path / "events.db")
    store.publish("IMPLEMENT_REQUESTED", "key", "pr:7", {})
    event = store.claim("IMPLEMENT_REQUESTED", "worker", 3)
    result = run_claimed(store, event, [sys.executable, "-c", "raise SystemExit(7)"],
                         cwd=tmp_path, env=_env(), lease_seconds=3, timeout=10, interval=.1)
    assert result == ("finished", 7)
    store.complete(event, {"exit_code": result[1]})
    with pytest.raises(LeaseLost):
        store.complete(event, {})


def test_lease_loss_terminates_tree_and_rejects_old_result(tmp_path):
    root, ready, effect = _tree_script(tmp_path)
    store = EventStore(tmp_path / "events.db")
    store.publish("IMPLEMENT_REQUESTED", "key", "pr:7", {})
    event = store.claim("IMPLEMENT_REQUESTED", "worker", 2)
    results = []
    thread = threading.Thread(target=lambda: results.append(
        run_claimed(store, event, [sys.executable, str(root)], cwd=tmp_path, env=_env(),
                    lease_seconds=2, timeout=10, interval=.1)))
    thread.start()
    try:
        _wait_file(ready)
        with store._tx() as db:
            db.execute("UPDATE events SET lease_until=0 WHERE id=?", (event["id"],))
        thread.join(timeout=10)
        assert not thread.is_alive()
        assert results == [("lease_lost", None)]
        replacement = store.claim("IMPLEMENT_REQUESTED", "replacement", 10)
        assert replacement["id"] == event["id"] and replacement["lease_token"] != event["lease_token"]
        with pytest.raises(LeaseLost):
            store.complete(event, {})
        store.complete(replacement, {})
        time.sleep(3.5)
        assert not effect.exists()
    finally:
        thread.join(timeout=10)


def test_watchdog_terminates_tree_while_sqlite_lock_blocks_renewal(tmp_path):
    root, ready, effect = _tree_script(tmp_path)
    store = EventStore(tmp_path / "events.db", busy_timeout_ms=8000)
    store.publish("IMPLEMENT_REQUESTED", "key", "pr:7", {})
    event = store.claim("IMPLEMENT_REQUESTED", "worker", 1.5)
    lock_held, renewal_started = threading.Event(), threading.Event()
    original_renew = store.renew

    def signalled_renew(*args):
        if lock_held.is_set():
            renewal_started.set()
        return original_renew(*args)

    store.renew = signalled_renew
    results = []
    thread = threading.Thread(target=lambda: results.append(
        run_claimed(store, event, [sys.executable, str(root)], cwd=tmp_path, env=_env(),
                    lease_seconds=1.5, timeout=10, interval=.1)))
    thread.start()
    lock = None
    try:
        _wait_file(ready)
        lock = sqlite3.connect(store.path, isolation_level=None)
        lock.execute("BEGIN IMMEDIATE")
        lock_held.set()
        assert renewal_started.wait(3)
        time.sleep(3.5)
        assert not effect.exists()
        lock.execute("ROLLBACK")
        lock.close()
        lock = None
        thread.join(timeout=10)
        assert not thread.is_alive()
        assert results == [("lease_lost", None)]
        with pytest.raises(LeaseLost):
            store.complete(event, {})
    finally:
        if lock is not None:
            lock.close()
        thread.join(timeout=10)


def test_claimed_timeout_terminates_descendants(tmp_path):
    root, ready, effect = _tree_script(tmp_path)
    store = EventStore(tmp_path / "events.db")
    store.publish("IMPLEMENT_REQUESTED", "key", "pr:7", {})
    event = store.claim("IMPLEMENT_REQUESTED", "worker", 3)
    result = run_claimed(store, event, [sys.executable, str(root)], cwd=tmp_path, env=_env(),
                         lease_seconds=3, timeout=1.5, interval=.1)
    assert ready.exists()
    assert result == ("timeout", None)
    time.sleep(3)
    assert not effect.exists()


def test_lost_lease_refuses_to_start_process(tmp_path):
    store = EventStore(tmp_path / "events.db")
    store.publish("IMPLEMENT_REQUESTED", "key", "pr:7", {})
    event = store.claim("IMPLEMENT_REQUESTED", "worker", 2)
    with store._tx() as db:
        db.execute("UPDATE events SET lease_until=0 WHERE id=?", (event["id"],))
    marker = tmp_path / "must-not-start"
    script = f"from pathlib import Path; Path({str(marker)!r}).write_text('started')"
    assert run_claimed(store, event, [sys.executable, "-c", script], cwd=tmp_path, env=_env(),
                       lease_seconds=2, timeout=5, interval=.1) == ("lease_lost", None)
    assert not marker.exists()


def test_renewal_error_kills_tree_and_never_returns_success(tmp_path):
    root, ready, effect = _tree_script(tmp_path)
    store = EventStore(tmp_path / "events.db")
    store.publish("IMPLEMENT_REQUESTED", "key", "pr:7", {})
    event = store.claim("IMPLEMENT_REQUESTED", "worker", 3)
    original = store.renew

    def broken_after_start(*args):
        if ready.exists():
            raise RuntimeError("database unavailable")
        return original(*args)

    store.renew = broken_after_start
    with pytest.raises(RuntimeError, match="database unavailable"):
        run_claimed(store, event, [sys.executable, str(root)], cwd=tmp_path, env=_env(),
                    lease_seconds=3, timeout=10, interval=.1)
    time.sleep(3.5)
    assert not effect.exists()


def test_unsignalled_root_is_an_error_not_a_success(tmp_path, monkeypatch):
    store = EventStore(tmp_path / "events.db")
    store.publish("IMPLEMENT_REQUESTED", "key", "pr:7", {})
    event = store.claim("IMPLEMENT_REQUESTED", "worker", 2)
    monkeypatch.setattr(process_supervisor, "_wait", lambda *_: 0x102)
    with pytest.raises(ProcessSupervisorError, match="did not signal termination"):
        run_claimed(store, event, [sys.executable, "-c", "import time; time.sleep(60)"],
                    cwd=tmp_path, env=_env(), lease_seconds=2, timeout=.4, interval=.1)
