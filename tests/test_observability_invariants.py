"""Invariantes de uma run finalizada — a defesa contra relatório escrito à mão.

Nesta sessão eu afirmei "25 eventos, zero lacunas" e depois transcrevi uma
tabela que pulava o `seq=20`. O dado estava correto; a apresentação, não. A
correção não é "ter mais cuidado" — é um invariante que qualquer renderizador
execute antes de afirmar integridade.
"""
from __future__ import annotations

import itertools

import pytest

from core import observability as obs
from core.observability.replay import load_run, parse_rows, validate
from core.observability.sink import JsonlSink, MemorySink, set_sink


def _row(seq, name="rag.chunk.retrieved", *, run_id="run_x", ts=None,
         span=None, parent=None, status="ok", category="RAG", trace="t" * 32):
    return {"v": 1, "runId": run_id, "traceId": trace, "spanId": span,
            "parentSpanId": parent, "seq": seq,
            "ts": ts or f"2026-08-27T01:49:{seq % 60:02d}.000Z",
            "durationMs": None, "component": "c", "category": category,
            "status": status, "name": name, "meta": {}}


def _run_rows(n_middle=2, **kw):
    rows = [_row(1, "run.started", status="started", category="OBSERVABILITY", **kw)]
    rows += [_row(i + 2, **kw) for i in range(n_middle)]
    rows.append(_row(n_middle + 2, "run.finished", category="OBSERVABILITY", **kw))
    return rows


def _codes(rows, **kw):
    return {v.code for v in validate(parse_rows(rows, **kw))}


# ---------------------------------------------------------------------------
# trace íntegro
# ---------------------------------------------------------------------------


def test_a_healthy_trace_has_no_violations():
    assert validate(parse_rows(_run_rows())) == ()


def test_empty_trace_is_reported_not_silently_ok():
    assert _codes([]) == {"empty_trace"}


# ---------------------------------------------------------------------------
# seq == 1..N sem buracos  (o invariante que este episódio motivou)
# ---------------------------------------------------------------------------


def test_gap_in_seq_is_a_violation():
    rows = _run_rows(n_middle=3)
    del rows[2]                                   # remove o seq=3
    codes = _codes(rows)
    assert "seq_not_contiguous" in codes


def test_gap_message_names_the_missing_seq():
    rows = _run_rows(n_middle=3)
    del rows[2]
    v = next(x for x in validate(parse_rows(rows)) if x.code == "seq_not_contiguous")
    assert "3" in v.detail


def test_seq_not_starting_at_one_is_a_violation():
    rows = [_row(s, "run.started" if s == 5 else "rag.chunk.retrieved",
                 status="started" if s == 5 else "ok",
                 category="OBSERVABILITY" if s == 5 else "RAG") for s in (5, 6)]
    rows.append(_row(7, "run.finished", category="OBSERVABILITY"))
    assert "seq_not_contiguous" in _codes(rows)


def test_duplicate_seq_is_a_violation():
    rows = _run_rows(n_middle=2)
    rows.append(dict(rows[1]))                    # reenvia o seq=2
    assert "duplicate_seq" in _codes(rows)


# ---------------------------------------------------------------------------
# exatamente um run.started e um terminal
# ---------------------------------------------------------------------------


def test_missing_run_started_is_a_violation():
    rows = [_row(1), _row(2, "run.finished", category="OBSERVABILITY")]
    assert "run_started_count" in _codes(rows)


def test_two_run_started_is_a_violation():
    rows = [_row(1, "run.started", status="started", category="OBSERVABILITY"),
            _row(2, "run.started", status="started", category="OBSERVABILITY"),
            _row(3, "run.finished", category="OBSERVABILITY")]
    assert "run_started_count" in _codes(rows)


def test_missing_terminal_is_a_violation():
    """Processo morto no meio: o trace fica aberto, e isso tem que aparecer."""
    rows = [_row(1, "run.started", status="started", category="OBSERVABILITY"),
            _row(2)]
    assert "missing_terminal" in _codes(rows)


def test_two_terminals_is_a_violation():
    rows = _run_rows(n_middle=1)
    rows.append(_row(4, "run.failed", status="failed", category="OBSERVABILITY"))
    assert "multiple_terminals" in _codes(rows)


@pytest.mark.parametrize("terminal", ["run.finished", "run.failed", "run.canceled"])
def test_each_terminal_kind_satisfies_the_invariant(terminal):
    status = {"run.finished": "ok", "run.failed": "failed",
              "run.canceled": "skipped"}[terminal]
    rows = [_row(1, "run.started", status="started", category="OBSERVABILITY"),
            _row(2, terminal, status=status, category="OBSERVABILITY")]
    assert validate(parse_rows(rows)) == ()


def test_terminal_must_be_the_last_event():
    rows = [_row(1, "run.started", status="started", category="OBSERVABILITY"),
            _row(2, "run.finished", category="OBSERVABILITY"),
            _row(3)]
    assert "terminal_not_last" in _codes(rows)


# ---------------------------------------------------------------------------
# timestamps monotônicos
# ---------------------------------------------------------------------------


def test_timestamp_going_backwards_is_a_violation():
    rows = [_row(1, "run.started", status="started", category="OBSERVABILITY",
                 ts="2026-08-27T01:49:10.000Z"),
            _row(2, ts="2026-08-27T01:49:02.000Z"),
            _row(3, "run.finished", category="OBSERVABILITY",
                 ts="2026-08-27T01:49:11.000Z")]
    assert "ts_not_monotonic" in _codes(rows)


def test_equal_timestamps_are_fine():
    """Dois eventos no mesmo milissegundo é normal — `seq` é quem ordena."""
    rows = [_row(1, "run.started", status="started", category="OBSERVABILITY",
                 ts="2026-08-27T01:49:10.000Z"),
            _row(2, ts="2026-08-27T01:49:10.000Z"),
            _row(3, "run.finished", category="OBSERVABILITY",
                 ts="2026-08-27T01:49:10.000Z")]
    assert validate(parse_rows(rows)) == ()


# ---------------------------------------------------------------------------
# spans
# ---------------------------------------------------------------------------


def test_parent_span_that_does_not_exist_is_a_violation():
    rows = [_row(1, "run.started", status="started", category="OBSERVABILITY"),
            _row(2, span="s002", parent="s001"),          # s001 nunca apareceu
            _row(3, "run.finished", category="OBSERVABILITY")]
    assert "orphan_parent" in _codes(rows)


def test_well_formed_span_hierarchy_passes():
    rows = [_row(1, "run.started", status="started", category="OBSERVABILITY"),
            _row(2, "rag.query.started", span="s001", status="started"),
            _row(3, "rag.embedding.started", span="s002", parent="s001",
                 status="started"),
            _row(4, "rag.embedding.finished", span="s002", parent="s001"),
            _row(5, "rag.query.finished", span="s001"),
            _row(6, "run.finished", category="OBSERVABILITY")]
    assert validate(parse_rows(rows)) == ()


def test_mixed_trace_ids_under_one_run_is_a_violation():
    rows = _run_rows(n_middle=1)
    rows[1]["traceId"] = "z" * 32
    assert "mixed_trace_ids" in _codes(rows)


def test_malformed_row_is_counted_as_a_violation():
    rows = _run_rows(n_middle=2)
    del rows[1]["status"]
    assert {"malformed_rows", "seq_not_contiguous"} <= _codes(rows)


# ---------------------------------------------------------------------------
# runs REAIS gravadas em disco — o que o relatório afirma
# ---------------------------------------------------------------------------


@pytest.fixture
def traces(tmp_path):
    obs.reset_for_tests()
    previous = set_sink(JsonlSink(tmp_path))
    try:
        yield tmp_path
    finally:
        set_sink(previous)
        obs.reset_for_tests()


def test_a_real_recorded_run_satisfies_every_invariant(traces):
    from tools.reference_db import retrieve
    from tools.run_deterministic_gates import run_all

    with obs.run(run_id="run_real", component="test"):
        retrieve("kitchen", "black_wood_gold", backend="faceted")
        run_all(fixture="quadrado")

    trace = load_run(traces / "run_real.jsonl")
    assert validate(trace) == (), [v.detail for v in validate(trace)]
    assert [e.seq for e in trace.events] == list(range(1, len(trace.events) + 1))
    assert trace.complete


def test_a_failed_real_run_still_satisfies_the_invariants(traces):
    with pytest.raises(ValueError):
        with obs.run(run_id="run_boom", component="test"):
            obs.emit("llm.started", component="x", status="started")
            raise ValueError("estourou")

    trace = load_run(traces / "run_boom.jsonl")
    assert validate(trace) == ()
    assert trace.terminal_status == "failed"


def test_concurrent_runs_each_satisfy_the_invariants(traces):
    import threading

    def _work(i):
        with obs.run(run_id=f"run_par_{i}", component="test"):
            for _ in range(5):
                obs.emit("rag.chunk.retrieved", component="x", meta={"chunkId": "c"})

    threads = [threading.Thread(target=_work, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    for i in range(4):
        trace = load_run(traces / f"run_par_{i}.jsonl")
        assert validate(trace) == (), f"run_par_{i}: {[v.code for v in validate(trace)]}"


def test_truncated_run_is_reported_not_silently_valid():
    """Trace cortado no teto perde eventos — o invariante tem que acusar.

    E o caso é traiçoeiro: o sink reusa o `seq` do evento que estourou o teto
    para escrever o marcador terminal, então o trace truncado fica com `seq`
    contíguo, um `run.started` e um terminal. Estruturalmente impecável, e ainda
    assim faltando 40 eventos.
    """
    obs.reset_for_tests()
    import tempfile
    from pathlib import Path

    tmp = Path(tempfile.mkdtemp())
    previous = set_sink(JsonlSink(tmp, max_bytes=800))
    try:
        with obs.run(run_id="run_cortada", component="test"):
            for _ in range(60):
                obs.emit("rag.chunk.retrieved", component="x",
                         meta={"chunkId": "c" * 20, "score": 0.5})
    finally:
        set_sink(previous)
        obs.reset_for_tests()

    trace = load_run(tmp / "run_cortada.jsonl")
    assert trace.truncated
    codes = {v.code for v in validate(trace)}
    assert "truncated_trace" in codes
    # justamente o ponto: nenhum invariante ESTRUTURAL acusa
    assert not (codes - {"truncated_trace"})


# ---------------------------------------------------------------------------
# o fallback como EXECUÇÃO, não como conclusão
# ---------------------------------------------------------------------------


@pytest.fixture
def sink():
    obs.reset_for_tests()
    mem = MemorySink()
    ticks = itertools.count(1_800_000_000.0, 0.001)
    previous = obs.configure(sink=mem, clock=lambda: next(ticks))
    try:
        yield mem
    finally:
        set_sink(previous)
        obs.reset_for_tests()


def test_faceted_retrieval_has_its_own_executed_span(sink):
    """`backendActual=faceted` tem que ser CONSEQUÊNCIA de um span observável."""
    from tools.reference_db import retrieve

    with obs.run(run_id="run_fb"):
        retrieve("kitchen", "black_wood_gold", backend="faceted")

    faceted = [e for e in sink.events
               if e.component == "reference_db.faceted"
               and e.name == "rag.retrieval.finished"]
    assert len(faceted) == 1, "o retrieval faceted não apareceu como execução"
    ev = faceted[0]
    assert ev.duration_ms is not None
    assert ev.meta["candidatesCount"] >= 0
    assert ev.meta["nRetrieved"] >= 0
    assert ev.meta["nSelected"] >= 0
    assert ev.meta["indexKind"] == "STRUCTURED"


def test_faceted_span_is_nested_under_the_query_span(sink):
    from core.observability.replay import build_span_tree, parse_rows
    from tools.reference_db import retrieve

    with obs.run(run_id="run_nest_fb"):
        retrieve("kitchen", "black_wood_gold", backend="faceted")

    roots = build_span_tree(parse_rows(sink.rows(), run_id="run_nest_fb"))
    query = next(r for r in roots if r.component == "reference_db.retrieve")
    assert "reference_db.faceted" in {c.component for c in query.children}


def test_degraded_run_shows_the_faceted_execution_that_produced_the_result(sink):
    """Sem Qdrant: a trace mostra a busca vetorial FALHANDO e o faceted RODANDO.

    Antes, `backendActual=faceted` era a única evidência de que o faceted tinha
    executado — uma conclusão, não uma observação.
    """
    from tools.reference_db import retrieve

    with obs.run(run_id="run_degraded"):
        retrieve("kitchen", "black_wood_gold", backend="embed")

    faceted = next(e for e in sink.events
                   if e.component == "reference_db.faceted"
                   and e.name == "rag.retrieval.finished")
    query = next(e for e in sink.events if e.name == "rag.query.finished")

    if query.meta["fallbackTriggered"]:
        # o span do faceted SABE que é o caminho de fallback
        assert faceted.meta["fallbackTriggered"] is True
        # e a ordem conta a história: vetorial falha ANTES do faceted rodar
        degraded = next(e for e in sink.events if e.name == "rag.degraded")
        assert degraded.seq < faceted.seq
        assert faceted.seq < query.seq
