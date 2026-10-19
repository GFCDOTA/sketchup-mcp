"""stdout do servidor MCP é só do protocolo (FP-043 §8) — provado com um cliente ESTRITO.

O cliente abaixo fala JSON-RPC cru por pipes: cada linha de stdout tem de ser um frame JSON-RPC válido. Uma tool
barulhenta (print, sys.stdout.write, processo filho, escrita direta no fd 1) não pode vazar para ele; o ruído tem
de aparecer no stderr. O cliente Python do SDK tolera linhas inválidas — este não.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

pytestmark = pytest.mark.usefixtures("require_mcp")  # pula local sem o extra; falha no job mcp-server (REQUIRE_EXTRAS=1)

ROOT = Path(__file__).resolve().parents[1]
NOISE = ("RUIDO-PRINT", "RUIDO-WRITE", "RUIDO-FILHO", "RUIDO-FD1")

SERVER = r'''
import os, subprocess, sys
from tools.mcp_server import server

@server.mcp.tool()
def noisy() -> dict:
    """Escreve em todo canal possível."""
    print("RUIDO-PRINT")
    sys.stdout.write("RUIDO-WRITE\n")
    subprocess.run([sys.executable, "-c", "print('RUIDO-FILHO')"], check=True)
    os.write(1, b"RUIDO-FD1\n")
    return {"ok": True}

server.main()
'''


def _talk(frames: list[dict], expect_ids: set[int]) -> tuple[list[str], list[dict], str]:
    env = {**os.environ, "PYTHONPATH": str(ROOT), "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.Popen([sys.executable, "-c", SERVER], cwd=ROOT, stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    timer = threading.Timer(60, proc.kill)
    timer.start()
    raw_lines: list[str] = []
    answers: dict[int, dict] = {}
    try:
        for frame in frames:
            proc.stdin.write((json.dumps(frame) + "\n").encode())
            proc.stdin.flush()
            if "id" in frame:
                while frame["id"] not in answers:
                    line = proc.stdout.readline().decode("utf-8")
                    assert line, "servidor fechou o stdout antes de responder"
                    raw_lines.append(line)
                    msg = json.loads(line)                       # JSON estrito: qualquer ruído quebra aqui
                    assert msg.get("jsonrpc") == "2.0", line
                    if "id" in msg:
                        answers[msg["id"]] = msg
        proc.stdin.close()
        proc.wait(timeout=30)
        rest = proc.stdout.read().decode("utf-8")
        raw_lines += rest.splitlines(keepends=True)
    finally:
        timer.cancel()
        if proc.poll() is None:
            proc.kill()
        stderr = proc.stderr.read().decode("utf-8", "replace")
    assert set(answers) >= expect_ids
    return raw_lines, [answers[i] for i in sorted(expect_ids)], stderr


INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "strict", "version": "1"}}}
INITIALIZED = {"jsonrpc": "2.0", "method": "notifications/initialized"}


def test_cliente_estrito_nao_ve_ruido_de_tool_nem_de_processo_filho():
    call = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "noisy", "arguments": {}}}
    lines, (init, result), stderr = _talk([INIT, INITIALIZED, call], {1, 2})
    assert init["result"]["serverInfo"]["name"] == "sketchup-mcp"
    assert not result["result"].get("isError"), result
    # todo byte de stdout foi um frame JSON-RPC...
    for line in lines:
        assert json.loads(line)["jsonrpc"] == "2.0"
    assert not any(token in "".join(lines) for token in NOISE)
    # ...e o ruído existiu e foi parar no stderr
    for token in NOISE:
        assert token in stderr, f"{token} sumiu: deveria estar no stderr"


def test_lista_de_tools_continua_completa_e_responde_pelo_protocolo():
    lst = {"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}}
    _, (_, listing), _ = _talk([INIT, INITIALIZED, lst], {1, 3})
    names = {t["name"] for t in listing["result"]["tools"]}
    assert {"su_status", "su_apply_edits", "su_build_shell", "list_capabilities", "noisy"} <= names
    assert len(names - {"noisy"}) == 18


def test_quiet_preserva_assinatura_para_o_schema_do_fastmcp():
    import inspect

    from tools.mcp_server.stdio_isolation import quiet

    def tool(a: int, b: str = "x") -> dict:
        """doc da tool"""
        return {"a": a, "b": b}

    wrapped = quiet(tool)
    assert inspect.signature(wrapped) == inspect.signature(tool)
    assert wrapped.__doc__ == "doc da tool" and wrapped(1) == {"a": 1, "b": "x"}


def test_quiet_desvia_print_para_o_stderr(capsys):
    from tools.mcp_server.stdio_isolation import quiet

    quiet(lambda: print("DENTRO"))()
    print("FORA")
    out, err = capsys.readouterr()
    assert "DENTRO" in err and "DENTRO" not in out and "FORA" in out
