"""Como o SketchUp é lançado — regressão do L2 de 2026-10-19.

Via servidor MCP stdio o stdin do processo é o pipe do JSON-RPC, com uma leitura
síncrona sempre pendente. O SketchUp herdava esse handle e travava na carga:
todo su_* via MCP dava TIMEOUT (repro: filho com leitura pendente no stdin →
TIMEOUT; mesmo filho com stdin=DEVNULL → OK em 9 s). Aqui não há SketchUp:
o contrato é o que vai para o subprocess.Popen.
"""
from __future__ import annotations

import subprocess

import pytest

from tools.sketchup import process


class _Rec:
    def __init__(self, fail_breakaway=False):
        self.calls = []
        self.fail_breakaway = fail_breakaway

    def __call__(self, cmd, **kw):
        self.calls.append(kw)
        brk = getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0)
        if self.fail_breakaway and brk and kw.get("creationflags", 0) & brk:
            raise PermissionError(5, "Acesso negado")  # job sem BREAKAWAY_OK
        return object()


def test_sketchup_nunca_herda_o_stdin_de_quem_chama(monkeypatch):
    rec = _Rec()
    monkeypatch.setattr(subprocess, "Popen", rec)
    process.System().popen(["SketchUp.exe", "x.skp"], {"A": "1"})
    kw = rec.calls[-1]
    assert kw["stdin"] is subprocess.DEVNULL
    assert kw["stdout"] is subprocess.DEVNULL and kw["stderr"] is subprocess.DEVNULL
    assert kw["env"] == {"A": "1"}


@pytest.mark.skipif(not hasattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB"), reason="flag só no Windows")
def test_tenta_sair_do_job_e_cai_para_sem_breakaway_quando_o_job_recusa(monkeypatch):
    rec = _Rec(fail_breakaway=True)
    monkeypatch.setattr(subprocess, "Popen", rec)
    process.spawn_detached(["SketchUp.exe"])
    brk = subprocess.CREATE_BREAKAWAY_FROM_JOB
    assert len(rec.calls) == 2
    assert rec.calls[0]["creationflags"] & brk
    assert not rec.calls[1]["creationflags"] & brk
    assert all(c["stdin"] is subprocess.DEVNULL for c in rec.calls)


def test_build_shell_usa_o_mesmo_lancamento():
    """su_build_shell sobe o SketchUp por build_plan_shell_skp.run — mesmo travamento."""
    src = open("tools/build_plan_shell_skp.py", encoding="utf-8").read()
    run_src = src[src.index("def run("):src.index("def _infer_plant(")]
    assert "spawn_detached(cmd, env)" in run_src
    assert "subprocess.Popen(" not in run_src


def test_servidor_mcp_carrega_extensoes_c_antes_de_ler_o_stdin_sem_fixar_escala():
    """L2 2026-10-19: su_furnish via MCP travava para sempre importando numpy (via
    shapely) DENTRO da tool, com a leitura do pipe do JSON-RPC pendente. O servidor
    pré-carrega as extensões C no import — só as bibliotecas: importar o
    furnish_apartment ali arrastaria os brains inteiros para o boot do servidor."""
    import os
    import sys

    pytest.importorskip("mcp")  # o job pytest do CI não instala o extra [mcp]
    env = {k: v for k, v in os.environ.items() if k != "PT_TO_M"}
    code = ("import os, sys, tools.mcp_server.server; "
            "missing = [m for m in ('numpy', 'shapely.geometry', 'shapely.ops', 'PIL.Image') if m not in sys.modules]; "
            "assert not missing, missing; "
            "assert 'tools.furnish_apartment' not in sys.modules")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr[-2000:]
