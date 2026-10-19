"""Job Object do servidor MCP no Windows — o diagnóstico `server_job` do `su_status` (FP-043 §8).

Cliente MCP no Windows põe o servidor num job KILL_ON_JOB_CLOSE: sem breakaway, fechar o cliente mata o SketchUp
aberto por uma tool. `job_info()` mede isso; aqui contra jobs reais criados no teste. O comportamento do cliente
Claude Code (Node) não é inferido: roda-se `su_status` no servidor dele e lê-se o campo.
"""
from __future__ import annotations

import json
import subprocess
import sys

import pytest

from tools.sketchup import jobs, process

PROBE = "import json; from tools.sketchup.process import job_info; print(json.dumps(job_info()))"


def test_fora_do_windows_o_diagnostico_diz_que_nao_sabe(monkeypatch):
    monkeypatch.setattr(process.sys, "platform", "linux")
    assert process.job_info() == {"supported": False, "sketchup_survives_server_exit": None}


def test_su_status_expoe_server_job():
    out = jobs.status()
    assert "server_job" in out and "sketchup_survives_server_exit" in out["server_job"]


def _probe_in_job(limit_flags: int) -> dict:
    win32job = pytest.importorskip("win32job")
    baseline = subprocess.run([sys.executable, "-c", PROBE], capture_output=True, text=True)
    if json.loads(baseline.stdout.strip().splitlines()[-1]).get("in_job"):
        pytest.skip("este shell já roda dentro de um Job Object (aninhado: a consulta devolve o externo); "
                    "meça com `su_status.server_job` no servidor real")
    win32api = pytest.importorskip("win32api")
    win32con = pytest.importorskip("win32con")
    job = win32job.CreateJobObject(None, "")
    info = win32job.QueryInformationJobObject(job, win32job.JobObjectExtendedLimitInformation)
    info["BasicLimitInformation"]["LimitFlags"] |= limit_flags
    win32job.SetInformationJobObject(job, win32job.JobObjectExtendedLimitInformation, info)
    child = subprocess.Popen([sys.executable, "-c", "import sys; sys.stdin.readline(); " + PROBE],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
                             )
    handle = win32api.OpenProcess(win32con.PROCESS_SET_QUOTA | win32con.PROCESS_TERMINATE, False, child.pid)
    try:
        win32job.AssignProcessToJobObject(job, handle)
    except Exception as exc:  # job pai sem aninhamento: não dá para montar o cenário aqui
        child.kill()
        pytest.skip(f"não foi possível atribuir ao job: {exc}")
    out, _ = child.communicate("go\n", timeout=60)
    return json.loads(out.strip().splitlines()[-1])


@pytest.mark.skipif(sys.platform != "win32", reason="Job Object é do Windows")
@pytest.mark.parametrize("flags,survives", [
    ("KILL", False),
    ("KILL|BREAKAWAY", True),
    ("KILL|SILENT", True),
    ("NONE", True),
])
def test_job_info_le_os_flags_do_job_real(flags, survives):
    win32job = pytest.importorskip("win32job")
    bits = {"KILL": win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE, "BREAKAWAY": win32job.JOB_OBJECT_LIMIT_BREAKAWAY_OK,
            "SILENT": win32job.JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK, "NONE": 0}
    value = 0
    for part in flags.split("|"):
        value |= bits[part]
    got = _probe_in_job(value)
    assert got["in_job"] is True
    assert got["kill_on_job_close"] is bool(value & bits["KILL"])
    assert got["breakaway_ok"] is bool(value & bits["BREAKAWAY"])
    assert got["silent_breakaway_ok"] is bool(value & bits["SILENT"])
    assert got["sketchup_survives_server_exit"] is survives


@pytest.mark.skipif(sys.platform != "win32", reason="Job Object é do Windows")
def test_job_info_e_coerente_no_ambiente_atual():
    got = process.job_info()
    assert got["supported"] is True
    if got["in_job"]:
        assert got["sketchup_survives_server_exit"] == (
            (not got["kill_on_job_close"]) or got["breakaway_ok"] or got["silent_breakaway_ok"])
    elif got["in_job"] is False:
        assert got["sketchup_survives_server_exit"] is True
