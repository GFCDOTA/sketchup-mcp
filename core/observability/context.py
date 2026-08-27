"""context — identidade e ordenação de uma execução (run / trace / span).

Carrega o `runId`, o `traceId` e a pilha de spans pelo call-stack via
`contextvars`, pra que um `emit()` lá no fundo do `rag_embed_backend` saia
correlacionado sem que ninguém precise passar um objeto de contexto por seis
assinaturas de função (que é como instrumentação vira acoplamento).

Duas garantias que o replay depende:

1. `seq` é MONOTÔNICO POR RUN e vem de um contador com lock — não do relógio.
   Dois eventos emitidos no mesmo microssegundo, ou em threads diferentes do
   `ThreadingHTTPServer`, precisam de ordem total estável. Wall-clock não dá
   isso; contador dá.
2. `spanId` é SEQUENCIAL e determinístico dentro da run (`s001`, `s002`, ...).
   Sem isso o trace de uma run gravada não é comparável com o de outra, e o
   teste de replay vira teste de uuid.

`traceId` usa `core.domain.ids.make_trace_id()` (uuid4) — é identidade, não
precisa ser reproduzível, e reusa o que já existe em vez de criar um segundo
gerador de id no repo.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Callable, Iterator

from core.domain.ids import make_trace_id

# ---------------------------------------------------------------------------


@dataclass
class RunContext:
    """Estado de UMA execução. Compartilhado entre threads da mesma run."""

    run_id: str
    trace_id: str
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _seq: int = field(default=0, repr=False)
    _span_no: int = field(default=0, repr=False)

    def next_seq(self) -> int:
        """Próximo número de sequência da run. Thread-safe, monotônico, 1-based."""
        with self._lock:
            self._seq += 1
            return self._seq

    def next_span_id(self) -> str:
        with self._lock:
            self._span_no += 1
            return f"s{self._span_no:03d}"

    @property
    def emitted(self) -> int:
        """Quantos eventos esta run já numerou (só leitura, p/ diagnóstico)."""
        return self._seq


_run: ContextVar[RunContext | None] = ContextVar("obs_run", default=None)
_span: ContextVar[str | None] = ContextVar("obs_span", default=None)


def current_run() -> RunContext | None:
    return _run.get()


def current_span_id() -> str | None:
    return _span.get()


def new_run_id(clock: Callable[[], float] | None = None,
               suffix: str | None = None) -> str:
    """`run_<UTC compacto>_<sufixo>` — ordenável lexicograficamente por design.

    `clock` e `suffix` são injetáveis: os testes fixam ambos e ganham um id
    determinístico; a borda real passa `time.time` e um pedaço do trace_id.
    """
    import datetime as _dt
    import time as _time

    ts = (clock or _time.time)()
    stamp = _dt.datetime.fromtimestamp(ts, _dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    tail = suffix if suffix is not None else make_trace_id()[:6]
    return f"run_{stamp}_{tail}"


@contextmanager
def run_scope(*, run_id: str | None = None, trace_id: str | None = None,
              clock: Callable[[], float] | None = None) -> Iterator[RunContext]:
    """Abre uma run. Reentrante: uma run aninhada NÃO substitui a de fora.

    O aninhamento acontece de verdade — `run_deterministic_gates` pode ser
    chamado dentro de um ciclo do `correction_loop` que já abriu a run. Trocar o
    runId no meio quebraria a correlação, então a de dentro é ignorada.
    """
    existing = _run.get()
    if existing is not None:
        yield existing
        return
    tid = trace_id or make_trace_id()
    ctx = RunContext(run_id=run_id or new_run_id(clock, suffix=tid[:6]), trace_id=tid)
    token: Token = _run.set(ctx)
    try:
        yield ctx
    finally:
        _run.reset(token)


@contextmanager
def attach(ctx: RunContext, *, span_id: str | None = None) -> Iterator[RunContext]:
    """Reata uma run existente NESTA thread.

    `contextvars` não atravessa `threading.Thread`: uma thread nova nasce com
    contexto vazio, então um `emit()` lá dentro não acha a run e é descartado em
    silêncio. Isso não é teórico: o BFF (`ops/estudio-front/server.py`) é
    `ThreadingHTTPServer`, uma thread por requisição. É o ÚNICO boundary de
    thread do repo hoje — não há `ThreadPoolExecutor` nem `Thread()` em
    `tools/` (verificado por grep). Lá a run nasce dentro do handler, na
    própria thread, então não precisa reatar; `attach` existe para o dia em
    que uma requisição delegar trabalho a outra thread.

    Quem cria a thread reata explicitamente:

        ctx = obs.current_run()
        def worker():
            with obs.attach(ctx):
                ...   # agora emite correlacionado

    `seq` continua vindo do MESMO `RunContext` (com lock), então a numeração
    permanece total e sem colisão entre threads.
    """
    token: Token = _run.set(ctx)
    span_token: Token | None = _span.set(span_id) if span_id is not None else None
    try:
        yield ctx
    finally:
        if span_token is not None:
            _span.reset(span_token)
        _run.reset(token)


@contextmanager
def span_scope(span_id: str | None = None) -> Iterator[str | None]:
    """Empilha um span. Fora de uma run é no-op honesto (devolve None)."""
    ctx = _run.get()
    if ctx is None:
        yield None
        return
    sid = span_id or ctx.next_span_id()
    token: Token = _span.set(sid)
    try:
        yield sid
    finally:
        _span.reset(token)


def reset_for_tests() -> None:
    """Limpa os contextvars entre testes (o pytest reusa a mesma thread)."""
    _run.set(None)
    _span.set(None)
