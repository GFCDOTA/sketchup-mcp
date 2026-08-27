"""replay — ler um trace gravado e reconstruir a execução, honestamente.

O replay não re-executa nada: ele reproduz os eventos que ficaram no `.jsonl`.
Por isso o leitor precisa ser mais rigoroso que o escritor. Três coisas que ele
NÃO pode fazer:

- **completar evento torto.** Linha sem `seq` ou com `status` desconhecido é
  descartada e CONTADA, nunca preenchida com default. Um `status:"ok"` inventado
  vira um nó verde de uma etapa que talvez nem tenha rodado.
- **esconder buraco.** Se a run numerou até 42 e faltam o 17 e o 18, o leitor
  reporta `missing_seq`. A UI mostra a lacuna; não finge continuidade.
- **contar evento duplicado duas vezes.** Reconnect de SSE reenvia a partir do
  `Last-Event-ID` e sobreposição é normal. Dedup é por `(runId, seq)`, primeira
  ocorrência vence — o campo `seq` existe justamente pra isso.

Ordenação é por `seq`, nunca por `ts`: dois eventos no mesmo milissegundo (ou de
threads diferentes do BFF) não têm ordem confiável no relógio.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from core.observability.events import Event, is_well_formed


@dataclass(frozen=True)
class SpanNode:
    """Nó do trace tree. `children` já vem ordenado por `seq` de abertura."""

    span_id: str
    name: str
    component: str
    category: str
    status: str
    start_seq: int
    duration_ms: float | None
    parent_span_id: str | None
    children: tuple["SpanNode", ...] = ()


@dataclass(frozen=True)
class RunTrace:
    run_id: str
    trace_id: str | None
    events: tuple[Event, ...]
    dropped_malformed: int = 0
    duplicates_dropped: int = 0
    missing_seq: tuple[int, ...] = ()
    foreign_run_ids: tuple[str, ...] = ()
    truncated: bool = False

    @property
    def complete(self) -> bool:
        """Sem buraco, sem linha torta e com um evento terminal de run."""
        terminal = {"run.finished", "run.failed", "run.canceled"}
        return (not self.missing_seq
                and self.dropped_malformed == 0
                and any(e.name in terminal for e in self.events))

    @property
    def terminal_status(self) -> str | None:
        for e in reversed(self.events):
            if e.name in ("run.finished", "run.failed", "run.canceled"):
                return e.name.split(".", 1)[1]
        return None

    @property
    def total_duration_ms(self) -> float | None:
        for e in reversed(self.events):
            if e.name.startswith("run.") and e.duration_ms is not None:
                return e.duration_ms
        return None


def parse_rows(rows: Iterable[dict], *, run_id: str | None = None) -> RunTrace:
    """Normaliza linhas cruas num RunTrace. Não toca disco (testável puro)."""
    kept: dict[int, Event] = {}
    dropped = 0
    dupes = 0
    foreign: set[str] = set()
    truncated = False
    resolved_run = run_id

    for row in rows:
        if not is_well_formed(row):
            dropped += 1
            continue
        rid = row["runId"]
        if resolved_run is None:
            resolved_run = rid
        if rid != resolved_run:
            foreign.add(rid)
            continue
        if (row.get("meta") or {}).get("truncated"):
            truncated = True
        seq = int(row["seq"])
        if seq in kept:
            dupes += 1
            continue
        try:
            kept[seq] = Event.from_dict(row)
        except (KeyError, ValueError):
            dropped += 1

    ordered = tuple(kept[s] for s in sorted(kept))
    missing: tuple[int, ...] = ()
    if ordered:
        present = set(kept)
        missing = tuple(s for s in range(1, max(present) + 1) if s not in present)

    return RunTrace(
        run_id=resolved_run or "",
        trace_id=ordered[0].trace_id if ordered else None,
        events=ordered,
        dropped_malformed=dropped,
        duplicates_dropped=dupes,
        missing_seq=missing,
        foreign_run_ids=tuple(sorted(foreign)),
        truncated=truncated,
    )


def load_run(path: Path | str, *, run_id: str | None = None) -> RunTrace:
    """Lê um `<runId>.jsonl`. Arquivo ausente devolve um RunTrace vazio."""
    from tools.jsonl_io import read_jsonl  # lazy: core não importa tools no topo

    p = Path(path)
    return parse_rows(read_jsonl(p), run_id=run_id or p.stem)


def timeline(trace: RunTrace) -> list[tuple[float, Event]]:
    """[(offset_ms desde o 1º evento, Event)] — o eixo do scrubber.

    Offset vem do `ts`, que é o único sinal de tempo real que temos. Se um `ts`
    for ilegível, o offset do anterior é repetido (nunca extrapolado): melhor
    dois eventos empilhados no mesmo instante do que uma linha do tempo
    inventada.
    """
    if not trace.events:
        return []
    base = _epoch_ms(trace.events[0].ts)
    out: list[tuple[float, Event]] = []
    last = 0.0
    for ev in trace.events:
        ms = _epoch_ms(ev.ts)
        offset = last if (ms is None or base is None) else max(0.0, ms - base)
        last = offset
        out.append((round(offset, 3), ev))
    return out


def build_span_tree(trace: RunTrace) -> tuple[SpanNode, ...]:
    """Monta a árvore de spans. Span órfão (pai ausente) sobe pra raiz."""
    opened: dict[str, dict] = {}
    order: list[str] = []
    for ev in trace.events:
        sid = ev.span_id
        if not sid:
            continue
        if sid not in opened:
            opened[sid] = {"span_id": sid, "name": ev.name, "component": ev.component,
                           "category": ev.category.value, "status": ev.status.value,
                           "start_seq": ev.seq, "duration_ms": ev.duration_ms,
                           "parent_span_id": ev.parent_span_id}
            order.append(sid)
        else:
            node = opened[sid]
            if ev.duration_ms is not None:
                node["duration_ms"] = ev.duration_ms
                node["status"] = ev.status.value
                node["name"] = ev.name

    children: dict[str | None, list[str]] = {}
    for sid in order:
        parent = opened[sid]["parent_span_id"]
        if parent is not None and parent not in opened:
            parent = None            # órfão: sobe pra raiz em vez de sumir
        children.setdefault(parent, []).append(sid)

    def _build(sid: str) -> SpanNode:
        d = opened[sid]
        return SpanNode(
            span_id=d["span_id"], name=d["name"], component=d["component"],
            category=d["category"], status=d["status"], start_seq=d["start_seq"],
            duration_ms=d["duration_ms"], parent_span_id=d["parent_span_id"],
            children=tuple(_build(c) for c in
                           sorted(children.get(sid, []), key=lambda s: opened[s]["start_seq"])),
        )

    roots = sorted(children.get(None, []), key=lambda s: opened[s]["start_seq"])
    return tuple(_build(s) for s in roots)


def _epoch_ms(ts: str) -> float | None:
    import datetime as _dt

    try:
        return _dt.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
            tzinfo=_dt.timezone.utc).timestamp() * 1000.0
    except (ValueError, TypeError):
        return None
