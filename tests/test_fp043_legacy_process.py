"""P3: um launcher legado NUNCA pode fechar um SketchUp humano por nome."""
from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest

from tools.sketchup.legacy_process import _ps_literal, launch_owned, close_owned


def test_start_process_captures_only_pid_created(monkeypatch):
    seen = []
    def fake_run(cmd, **kwargs):
        seen.append((cmd, kwargs))
        return SimpleNamespace(stdout="9021", returncode=0)
    monkeypatch.setattr(subprocess, "run", fake_run)
    pid = launch_owned("SketchUp.exe", "base.skp", "job.rb", env={"RUN": "1"})
    assert pid == 9021
    cmd, kwargs = seen[0]
    assert "-PassThru" in cmd[-1]
    assert 'WriteLine($p.Id)' in cmd[-1]
    assert kwargs["check"] and kwargs["env"] == {"RUN": "1"}


def test_launcher_fails_closed_if_pid_not_returned(monkeypatch):
    monkeypatch.setattr(subprocess, "run",
                        lambda *a, **k: SimpleNamespace(stdout="warning", returncode=0))
    with pytest.raises(RuntimeError, match="PID"):
        launch_owned("SketchUp.exe", "base.skp", "job.rb", env={})


def test_close_owned_uses_only_pid_and_no_force(monkeypatch):
    called = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw:
                        (called.append(cmd) or SimpleNamespace(returncode=0)))
    assert close_owned(9021)
    assert called == [["taskkill", "/PID", "9021"]]


@pytest.mark.parametrize("bad", [0, -1, None, "9021", True])
def test_unknown_pid_cannot_trigger_close(bad):
    with pytest.raises(ValueError):
        close_owned(bad)


def test_powershell_escaped_quotes():
    assert _ps_literal("Bob's Job") == "'Bob''s Job'"
