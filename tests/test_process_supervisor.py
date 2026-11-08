"""Real Windows Job Object process-tree tests; no agents or listeners are started."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tools.orchestration import process_supervisor
from tools.orchestration.process_supervisor import ProcessSupervisorError, WindowsJob

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
