"""core.observability — a camada de eventos do AI Pipeline Inspector.

Superfície pública mínima, de propósito. Um call-site instrumentado deve
precisar de UMA linha e de nenhum objeto de contexto na assinatura:

    from core import observability as obs

    with obs.stage("rag.retrieval.started", "rag.retrieval.finished",
                   component="qdrant.rag_chunks",
                   meta={"collection": COLLECTION, "topK": top_k}) as st:
        hits = _http(...)
        st.meta["nRetrieved"] = len(hits)

DESLIGADO POR PADRÃO. Sem `INSPECTOR=1` no ambiente e sem `configure()`
explícito, `emit()` retorna na primeira linha e `stage()` só mede um
`perf_counter`. Nenhum arquivo é aberto, nada é serializado, `redact` nem é
importado. É essa a resposta ao risco "instrumentação vira carroça".
"""
from __future__ import annotations

import datetime as _dt
import os
import time as _time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator

from core.observability.context import (
    RunContext,
    attach,
    current_run,
    current_span_id,
    new_run_id,
    reset_for_tests,
    run_scope,
    span_scope,
)
from core.observability.events import (
    EVENT_NAMES,
    SCHEMA_VERSION,
    Event,
    Status,
    UnknownEventName,
    default_category,
    is_well_formed,
)
from core.observability.sink import (
    JsonlSink,
    MemorySink,
    NullSink,
    Sink,
    default_traces_dir,
    get_sink,
    set_sink,
)
from core.observability.taxonomy import (
    Category,
    DecisionEvidence,
    HarnessKind,
    IndexKind,
    RetrievalKind,
    classify_retrieval,
    is_rag,
)

__all__ = [
    "Category", "DecisionEvidence", "Event", "HarnessKind", "IndexKind", "attach",
    "JsonlSink", "MemorySink", "NullSink", "RetrievalKind", "RunContext",
    "SCHEMA_VERSION", "Sink", "Status", "UnknownEventName",
    "classify_retrieval", "configure", "current_run", "current_span_id",
    "default_traces_dir", "emit", "is_enabled", "is_rag", "is_well_formed",
    "new_run_id", "reset_for_tests", "run", "stage", "span_scope",
]

_ENV_FLAG = "INSPECTOR"
_ENV_DIR = "INSPECTOR_TRACES_DIR"

_clock: Callable[[], float] = _time.time


def _iso(ts: float) -> str:
    return _dt.datetime.fromtimestamp(ts, _dt.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.") + f"{int((ts % 1) * 1000):03d}Z"


# ---------------------------------------------------------------------------
# configuração
# ---------------------------------------------------------------------------


def configure(*, sink: Sink | None = None, traces_dir: Path | str | None = None,
              clock: Callable[[], float] | None = None) -> Sink | None:
    """Liga a instrumentação. Devolve o sink anterior (restaure-o no teardown).

    `configure(sink=None, traces_dir=None)` com `INSPECTOR` desligado no
    ambiente é um no-op explícito — desligar é o default, e chamar configure
    sem argumentos não deve ligar nada por acidente.
    """
    global _clock
    if clock is not None:
        _clock = clock
    if sink is not None:
        return set_sink(sink)
    if traces_dir is not None:
        return set_sink(JsonlSink(traces_dir))
    if os.environ.get(_ENV_FLAG, "0") not in ("0", "", "false", "off"):
        return set_sink(JsonlSink(Path(os.environ.get(_ENV_DIR) or default_traces_dir())))
    return get_sink()


def is_enabled() -> bool:
    sink = get_sink()
    return sink is not None and not isinstance(sink, NullSink)


def shutdown() -> None:
    sink = set_sink(None)
    if sink is not None:
        sink.close()


# ---------------------------------------------------------------------------
# emissão
# ---------------------------------------------------------------------------


def emit(name: str, *, component: str, status: Status | str = Status.OK,
         category: Category | None = None, meta: dict[str, Any] | None = None,
         duration_ms: float | None = None,
         span_id: str | None = None, parent_span_id: str | None = None) -> Event | None:
    """Emite um evento. Devolve o `Event` escrito, ou None se desligado.

    Fora de um `run(...)` também devolve None: um evento sem `runId` não é
    correlacionável, e escrevê-lo criaria um trace órfão que o replay não sabe
    posicionar. Silêncio honesto é melhor que linha inútil.
    """
    sink = get_sink()
    if sink is None or isinstance(sink, NullSink):
        return None
    ctx = current_run()
    if ctx is None:
        return None
    if name not in EVENT_NAMES:
        raise UnknownEventName(f"{name!r} não está no catálogo de events.py")

    from core.observability.redact import redact_meta  # lazy: só no caminho ligado

    ev = Event(
        name=name,
        run_id=ctx.run_id,
        trace_id=ctx.trace_id,
        seq=ctx.next_seq(),
        ts=_iso(_clock()),
        category=category or default_category(name),
        status=Status(status) if not isinstance(status, Status) else status,
        component=component,
        span_id=span_id if span_id is not None else current_span_id(),
        parent_span_id=parent_span_id,
        duration_ms=round(duration_ms, 3) if duration_ms is not None else None,
        meta=redact_meta(meta),
    )
    sink.write(ev)
    return ev


@dataclass
class Stage:
    """Handle de um span aberto. `meta` é mutável até o `finished`."""

    component: str
    meta: dict[str, Any] = field(default_factory=dict)
    span_id: str | None = None
    status: Status = Status.OK

    def degraded(self, note: str) -> None:
        """Marca degradação honesta (infra off, fallback) sem levantar erro."""
        self.status = Status.DEGRADED
        self.meta["note"] = note


@contextmanager
def stage(started: str, finished: str, *, component: str,
          failed: str | None = None, category: Category | None = None,
          meta: dict[str, Any] | None = None) -> Iterator[Stage]:
    """Abre um span cronometrado: emite `started`, mede, emite `finished`.

    Exceção dentro do bloco emite `failed` (ou `finished` com status `failed`,
    quando o catálogo não tem um nome de falha) e RE-LEVANTA — o observador
    nunca engole o erro do observado.

    O `perf_counter` roda mesmo desligado; é ~40 ns e mantém o código do
    call-site idêntico nos dois modos.
    """
    st = Stage(component=component, meta=dict(meta or {}))
    # o pai é lido ANTES de empilhar o novo span — depois de `span_scope`,
    # `current_span_id()` já é o filho.
    parent = current_span_id()
    with span_scope() as sid:
        st.span_id = sid
        emit(started, component=component, status=Status.STARTED,
             category=category, meta=st.meta, span_id=sid, parent_span_id=parent)
        t0 = _time.perf_counter()
        try:
            yield st
        except Exception as exc:
            dt = (_time.perf_counter() - t0) * 1000.0
            fail_meta = dict(st.meta)
            fail_meta.setdefault("errorType", type(exc).__name__)
            fail_meta.setdefault("error", str(exc))
            emit(failed or finished, component=component, status=Status.FAILED,
                 category=category, meta=fail_meta, duration_ms=dt,
                 span_id=sid, parent_span_id=parent)
            raise
        dt = (_time.perf_counter() - t0) * 1000.0
        emit(finished, component=component, status=st.status, category=category,
             meta=st.meta, duration_ms=dt, span_id=sid, parent_span_id=parent)


@contextmanager
def run(*, run_id: str | None = None, trace_id: str | None = None,
        component: str = "run", meta: dict[str, Any] | None = None) -> Iterator[RunContext]:
    """Abre uma execução: emite `run.started` e, ao sair, `run.finished`/`.failed`.

    `KeyboardInterrupt` e `SystemExit` viram `run.canceled` — cancelamento não é
    falha, e a UI precisa distinguir "eu apertei Ctrl-C" de "quebrou".
    """
    with run_scope(run_id=run_id, trace_id=trace_id) as ctx:
        t0 = _time.perf_counter()
        emit("run.started", component=component, status=Status.STARTED, meta=meta)
        try:
            yield ctx
        except (KeyboardInterrupt, SystemExit):
            emit("run.canceled", component=component, status=Status.SKIPPED,
                 duration_ms=(_time.perf_counter() - t0) * 1000.0)
            raise
        except Exception as exc:
            emit("run.failed", component=component, status=Status.FAILED,
                 meta={"errorType": type(exc).__name__, "error": str(exc)},
                 duration_ms=(_time.perf_counter() - t0) * 1000.0)
            raise
        emit("run.finished", component=component, status=Status.OK,
             duration_ms=(_time.perf_counter() - t0) * 1000.0)
