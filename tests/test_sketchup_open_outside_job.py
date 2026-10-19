"""FP-043/P3b — `su_open` abre a janela do humano FORA do Job Object do cliente (L2: o cliente Python do mcp a matava).

So a logica (comando WMI, fallback, handle por PID); a prova real e o L2 em artifacts/review/fp043/p3b_windows_l2/.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.test_sketchup_specialist import EXE, FakeSystem, su_with
from tools.sketchup import process
from tools.sketchup.process import PidHandle, spawn_outside_job


class OutsideSystem(FakeSystem):
    def __init__(self, handle, **kw):
        super().__init__(**kw)
        self._h = handle
        self.outside_calls = []

    def popen_outside_job(self, cmd):
        self.outside_calls.append(cmd)
        return self._h


@pytest.fixture
def skp(tmp_path):
    p = tmp_path / "m.skp"
    p.write_bytes(b"SKP")
    return p


def test_open_usa_o_lancamento_fora_do_job_quando_disponivel(skp):
    sys_ = OutsideSystem(PidHandle(4321))
    r = su_with(sys_).open(skp)
    assert r == {"status": "OPENED", "pid": 4321, "skp": str(skp), "outside_job": True}
    assert sys_.outside_calls == [[str(EXE), str(skp)]] and sys_.launched == []


def test_open_cai_no_filho_desanexado_quando_wmi_nao_serve(skp):
    sys_ = OutsideSystem(None)
    r = su_with(sys_).open(skp)
    assert r["status"] == "OPENED" and r["outside_job"] is False and len(sys_.launched) == 1


def test_open_com_dubles_sem_wmi_segue_o_caminho_antigo(skp):
    sys_ = FakeSystem()
    r = su_with(sys_).open(skp)
    assert r["outside_job"] is False and sys_.launched[0][0] == [str(EXE), str(skp)]


def _fake_run(monkeypatch, *, rc=0, out="", seen=None):
    def run(cmd, **kw):
        if seen is not None:
            seen.append(cmd)
        return subprocess.CompletedProcess(cmd, rc, stdout=out, stderr="")
    monkeypatch.setattr(process.subprocess, "run", run)


def test_spawn_outside_job_monta_o_comando_wmi_com_aspas_escapadas(monkeypatch):
    monkeypatch.setattr(process.sys, "platform", "win32")
    seen = []
    _fake_run(monkeypatch, out="1234\r\n", seen=seen)
    h = spawn_outside_job(["C:/Program Files/SketchUp/SketchUp.exe", "C:/o'brien/m.skp"])
    assert isinstance(h, PidHandle) and h.pid == 1234
    script = seen[0][-1]
    assert "Win32_Process" in script and "Invoke-CimMethod" in script and "o''brien" in script
    assert "-ExecutionPolicy" not in seen[0] and "Bypass" not in " ".join(seen[0])


@pytest.mark.parametrize("rc,out", [(2, ""), (0, ""), (0, "nao-e-pid"), (1, "99")])
def test_spawn_outside_job_devolve_none_quando_o_wmi_falha_ou_nao_traz_pid(monkeypatch, rc, out):
    monkeypatch.setattr(process.sys, "platform", "win32")
    _fake_run(monkeypatch, rc=rc, out=out)
    assert spawn_outside_job(["x.exe"]) is None


def test_spawn_outside_job_so_no_windows(monkeypatch):
    monkeypatch.setattr(process.sys, "platform", "linux")
    assert spawn_outside_job(["x.exe"]) is None


def test_pid_handle_poll_e_terminate_so_do_proprio_pid(monkeypatch):
    calls = []

    def run(cmd, **kw):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout='"SketchUp.exe","77","Console","1","1 K"\n' if "tasklist" in cmd[0] else "", stderr="")
    monkeypatch.setattr(process.subprocess, "run", run)
    h = PidHandle(77)
    assert h.poll() is None
    h.terminate()
    assert calls[-1] == ["taskkill", "/PID", "77"]                  # nunca por nome de imagem
    monkeypatch.setattr(process.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, stdout="INFO: none", stderr=""))
    assert PidHandle(77).poll() == 0
