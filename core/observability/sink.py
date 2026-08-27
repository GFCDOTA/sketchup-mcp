"""sink — para onde o evento vai. Default: lugar nenhum.

O risco nº 1 desta feature é instrumentação virar acoplamento e peso. A defesa é
o `NullSink` ser o default do processo: sem `INSPECTOR=1` e sem `configure()`,
`emit()` custa uma comparação `is None` e retorna. Nenhum arquivo aberto, nenhum
json serializado, nenhum import de `redact` no caminho quente.

`JsonlSink` reusa `tools.jsonl_io.append_jsonl` — append-only, uma linha por
evento, o mesmo idioma das filas do FP-033. Import é LAZY: `core` não pode
depender de `tools` no topo do módulo (regra de direção de dependência), e o
caminho desligado nem chega a importar.

Rotação: ao passar de `max_bytes`, o sink PARA de escrever e marca `truncated`.
Deliberadamente não rotaciona em arquivos numerados — um trace partido em N
arquivos é um trace que o replay precisa remontar, e remontar errado é pior que
dizer "cortei aqui". Trace gigante é sintoma, não caso de uso.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Protocol

from core.observability.events import Event

DEFAULT_MAX_BYTES = 5 * 1024 * 1024  # 5 MB — teto da spec §6.4


class Sink(Protocol):
    def write(self, event: Event) -> None: ...
    def close(self) -> None: ...


class NullSink:
    """Descarta. É o default, e é o que mantém o custo em zero."""

    def write(self, event: Event) -> None:  # noqa: D102
        return None

    def close(self) -> None:  # noqa: D102
        return None


class MemorySink:
    """Guarda em lista. Para testes e para o modo `--dry-run` do Inspector."""

    def __init__(self) -> None:
        self.events: list[Event] = []
        self._lock = threading.Lock()

    def write(self, event: Event) -> None:
        with self._lock:
            self.events.append(event)

    def close(self) -> None:
        return None

    def rows(self) -> list[dict]:
        return [e.to_dict() for e in self.events]


class JsonlSink:
    """Um arquivo por run: `<dir>/<runId>.jsonl`.

    Thread-safe (o BFF é `ThreadingHTTPServer`). Falha de I/O NUNCA propaga: um
    disco cheio não pode derrubar um build de .skp por causa do observador.
    """

    def __init__(self, directory: Path | str, *,
                 max_bytes: int = DEFAULT_MAX_BYTES) -> None:
        self.directory = Path(directory)
        self.max_bytes = max_bytes
        self._lock = threading.Lock()
        self._written: dict[str, int] = {}
        self._truncated: set[str] = set()

    def path_for(self, run_id: str) -> Path:
        return self.directory / f"{run_id}.jsonl"

    def is_truncated(self, run_id: str) -> bool:
        return run_id in self._truncated

    def write(self, event: Event) -> None:
        from tools.jsonl_io import append_jsonl  # lazy: core não importa tools no topo

        run_id = event.run_id
        with self._lock:
            if run_id in self._truncated:
                return
            row = event.to_dict()
            size = len(str(row))
            if self._written.get(run_id, 0) + size > self.max_bytes:
                self._truncated.add(run_id)
                marker = dict(row)
                marker["meta"] = {"truncated": True,
                                  "note": f"trace cortado em {self.max_bytes} bytes"}
                marker["name"] = "run.finished"
                marker["status"] = "degraded"
                try:
                    append_jsonl(self.path_for(run_id), [marker])
                except OSError:
                    pass
                return
            self._written[run_id] = self._written.get(run_id, 0) + size
        try:
            append_jsonl(self.path_for(run_id), [row])
        except OSError:
            # Observabilidade nunca derruba o observado.
            return

    def close(self) -> None:
        return None


# ---------------------------------------------------------------------------
# sink do processo
# ---------------------------------------------------------------------------

_sink: Sink | None = None
_sink_lock = threading.Lock()


def get_sink() -> Sink | None:
    return _sink


def set_sink(sink: Sink | None) -> Sink | None:
    """Troca o sink do processo. Devolve o anterior (para restaurar em teste)."""
    global _sink
    with _sink_lock:
        previous = _sink
        _sink = sink
    return previous


def default_traces_dir() -> Path:
    return Path(__file__).resolve().parents[2] / ".ai_bridge" / "traces"
