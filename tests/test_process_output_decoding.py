"""#496: a saida de tasklist/powershell em pagina OEM nao pode virar stdout vazio ("nenhum SketchUp rodando")."""
from __future__ import annotations

import subprocess
import sys

from tools.sketchup import process


def test_run_text_survives_bytes_that_are_not_utf8_and_keeps_the_digits():
    code = "import sys; sys.stdout.buffer.write(bytes([0x53, 0x55, 0x20, 0x34, 0x32, 0x34, 0x32, 0x20, 0x80, 0x74]))"
    out = process.run_text([sys.executable, "-c", code])
    assert out.returncode == 0 and "4242" in out.stdout and out.stdout.startswith("SU 4242")


def test_run_text_never_returns_none_even_with_empty_output():
    out = process.run_text([sys.executable, "-c", "pass"])
    assert out.stdout == "" and out.stderr == ""


def test_run_text_propagates_the_exit_code_and_passes_timeout():
    out = process.run_text([sys.executable, "-c", "import sys; sys.exit(3)"], timeout=30)
    assert out.returncode == 3


def test_system_tasklist_and_pid_handle_use_the_safe_reader(monkeypatch):
    calls = []

    def fake(cmd, **kw):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, '"SketchUp.exe","777","\ufffdx"', "")
    monkeypatch.setattr(process, "run_text", fake)
    assert '"777"' in process.System().tasklist()
    assert process.PidHandle(777).poll() is None                      # "777" ainda esta na lista: processo vivo
    assert calls and all(c[0] == "tasklist" for c in calls)
