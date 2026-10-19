"""stdin/stdout do servidor MCP são do PROTOCOLO — nada mais usa (FP-043 §8).

No transporte stdio, cada linha de stdout é um frame JSON-RPC e o stdin é o pipe de entrada, com uma leitura
síncrona SEMPRE pendente. Dois defeitos reais saem disso (L2 de 2026-10-19, SketchUp 26.0.429, Windows):

- um `print` perdido (os jobs imprimem `[py] …`, os gates imprimem relatórios) ou um processo filho que herda o
  stdout corrompe o stream; o cliente Python do SDK tolera linhas inválidas, clientes estritos não;
- um processo filho que herda o stdin TRAVA: no Windows, consultar um handle síncrono (o Python faz isso ao
  iniciar) bloqueia enquanto outra thread tem um `ReadFile` pendente no mesmo arquivo. Foi o motivo de todo
  `su_*` dar TIMEOUT via MCP; `stdin=DEVNULL` no lançamento do SketchUp resolveu aquele caminho, aqui o resto.

Duas camadas:

1. `isolate_stdio()` (uma vez, antes de servir): guarda CÓPIAS de stdin/stdout reais para o transporte e aponta
   os handles padrão do processo — descritores do CRT e, no Windows, os handles do SO que o `subprocess` herda —
   stdin → NUL, stdout → stderr. Filho que escreve em stdout cai em stderr; filho que lê stdin vê EOF.
2. `quiet(fn)` (por tool): redireciona `sys.stdout` para o stderr durante a chamada, cobrindo `print` e `sys.stdout.write`.

O que sai em stderr é diagnóstico humano (log do cliente). Nada aqui interpreta ou filtra o protocolo.
"""
from __future__ import annotations

import contextlib
import functools
import io
import os
import sys
from typing import Any, Callable

_ISOLATED = False


def _set_std_handle(which: int, fd: int) -> None:
    """Windows: o `subprocess` herda o handle padrão do SO, não o descritor do CRT — alinha os dois."""
    import ctypes
    import msvcrt

    kernel32 = ctypes.windll.kernel32
    kernel32.SetStdHandle.argtypes = [ctypes.c_ulong, ctypes.c_void_p]
    kernel32.SetStdHandle(ctypes.c_ulong(which).value, msvcrt.get_osfhandle(fd))


def isolate_stdio() -> None:
    """Desvia stdin/stdout do PROCESSO e deixa em `sys.stdin`/`sys.stdout` cópias para o transporte.

    Idempotente. `stdio_server()` lê `sys.stdin.buffer`/`sys.stdout.buffer` ao iniciar: por isso, ao sair daqui,
    esses dois apontam para as cópias do protocolo. Depois que o transporte sobe, as tools usam `quiet()`.
    """
    global _ISOLATED
    if _ISOLATED:
        return
    sys.stdout.flush()
    protocol_in, protocol_out = os.dup(0), os.dup(1)
    nul = os.open(os.devnull, os.O_RDONLY)
    os.dup2(nul, 0)
    os.close(nul)
    os.dup2(2, 1)
    if sys.platform == "win32":
        _set_std_handle(-10, 0)   # STD_INPUT_HANDLE  → NUL
        _set_std_handle(-11, 2)   # STD_OUTPUT_HANDLE → stderr
    sys.stdin = io.TextIOWrapper(os.fdopen(protocol_in, "rb"), encoding="utf-8")
    sys.stdout = io.TextIOWrapper(os.fdopen(protocol_out, "wb", buffering=0), encoding="utf-8",
                                  newline="\n", write_through=True)
    _ISOLATED = True


def quiet(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Executa `fn` com `sys.stdout` → `sys.stderr`; preserva assinatura e docstring (o FastMCP deriva o schema delas)."""

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        with contextlib.redirect_stdout(sys.stderr):
            return fn(*args, **kwargs)

    return wrapper


def quiet_tools(app: Any) -> None:
    """Faz toda tool registrada daqui em diante em `app.tool(...)` rodar com stdout desviado."""
    original = app.tool

    def tool(*args: Any, **kwargs: Any):
        register = original(*args, **kwargs)
        return lambda fn: register(quiet(fn))

    app.tool = tool
