"""Replay: reconstituir a execução do jsonl sem completar, esconder ou duplicar."""
from __future__ import annotations

import itertools

import pytest

from core import observability as obs
from core.observability.replay import build_span_tree, load_run, parse_rows, timeline
from core.observability.sink import JsonlSink, MemorySink, set_sink


def _row(seq: int, name: str = "rag.chunk.retrieved", *, run_id: str = "run_x",
         ts: str | None = None, span: str | None = None,
         parent: str | None = None, status: str = "ok",
         category: str = "RAG", duration: float | None = None,
         meta: dict | None = None) -> dict:
    return {
        "v": 1, "runId": run_id, "traceId": "t" * 32, "spanId": span,
        "parentSpanId": parent, "seq": seq,
        "ts": ts or f"2026-08-26T14:30:{seq % 60:02d}.000Z",
        "durationMs": duration, "component": "qdrant", "category": category,
        "status": status, "name": name, "meta": meta or {},
    }


@pytest.fixture
def sink():
    obs.reset_for_tests()
    mem = MemorySink()
    ticks = itertools.count(1_800_000_000.0, 0.25)
    previous = obs.configure(sink=mem, clock=lambda: next(ticks))
    try:
        yield mem
    finally:
        set_sink(previous)
        obs.reset_for_tests()


# ---------------------------------------------------------------------------
# ordenação e dedup
# ---------------------------------------------------------------------------


def test_events_are_ordered_by_seq_not_by_file_order():
    trace = parse_rows([_row(3), _row(1), _row(2)])
    assert [e.seq for e in trace.events] == [1, 2, 3]


def test_duplicate_events_collapse_first_wins():
    """Reconnect de SSE reenvia a partir do Last-Event-ID: sobreposição é normal."""
    trace = parse_rows([
        _row(1), _row(2), _row(3),
        _row(2), _row(3),                       # janela reenviada
        _row(4),
    ])
    assert [e.seq for e in trace.events] == [1, 2, 3, 4]
    assert trace.duplicates_dropped == 2


def test_duplicate_with_different_payload_keeps_the_first():
    trace = parse_rows([
        _row(1, meta={"score": 0.9}),
        _row(1, meta={"score": 0.1}),
    ])
    assert trace.events[0].meta["score"] == 0.9
    assert trace.duplicates_dropped == 1


def test_ts_out_of_order_does_not_reorder_the_trace():
    """Relógio pode andar pra trás (NTP). `seq` manda."""
    trace = parse_rows([
        _row(1, ts="2026-08-26T14:30:10.000Z"),
        _row(2, ts="2026-08-26T14:30:02.000Z"),
    ])
    assert [e.seq for e in trace.events] == [1, 2]


# ---------------------------------------------------------------------------
# eventos incompletos: descartar e contar, nunca completar
# ---------------------------------------------------------------------------


def test_torn_line_is_dropped_and_counted():
    bad = _row(2)
    del bad["status"]
    trace = parse_rows([_row(1), bad, _row(3)])
    assert [e.seq for e in trace.events] == [1, 3]
    assert trace.dropped_malformed == 1


def test_unknown_status_is_dropped_not_defaulted_to_ok():
    trace = parse_rows([_row(1), _row(2, status="quase_ok")])
    assert [e.seq for e in trace.events] == [1]
    assert trace.dropped_malformed == 1


def test_unknown_event_name_is_dropped():
    trace = parse_rows([_row(1), _row(2, name="rag.inventado")])
    assert trace.dropped_malformed == 1


def test_missing_seq_is_reported_not_hidden():
    trace = parse_rows([_row(1), _row(4)])
    assert trace.missing_seq == (2, 3)
    assert not trace.complete


def test_foreign_run_in_the_same_file_is_segregated():
    trace = parse_rows([_row(1), _row(2, run_id="run_outro")], run_id="run_x")
    assert [e.run_id for e in trace.events] == ["run_x"]
    assert trace.foreign_run_ids == ("run_outro",)


def test_empty_input_is_an_empty_trace_not_a_crash():
    trace = parse_rows([])
    assert trace.events == ()
    assert trace.terminal_status is None
    assert not trace.complete


# ---------------------------------------------------------------------------
# estado terminal
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name,expected", [
    ("run.finished", "finished"),
    ("run.failed", "failed"),
    ("run.canceled", "canceled"),
])
def test_terminal_status_is_recovered(name, expected):
    trace = parse_rows([
        _row(1, "run.started", status="started", category="OBSERVABILITY"),
        _row(2, name, status="ok", category="OBSERVABILITY", duration=1234.5),
    ])
    assert trace.terminal_status == expected
    assert trace.total_duration_ms == 1234.5


def test_run_without_terminal_event_is_incomplete():
    """Processo morto no meio: a UI precisa saber que o trace está aberto."""
    trace = parse_rows([_row(1, "run.started", status="started",
                             category="OBSERVABILITY"), _row(2)])
    assert trace.terminal_status is None
    assert not trace.complete


def test_truncated_marker_is_surfaced():
    trace = parse_rows([
        _row(1),
        _row(2, "run.finished", status="degraded", category="OBSERVABILITY",
             meta={"truncated": True}),
    ])
    assert trace.truncated


# ---------------------------------------------------------------------------
# timeline (o eixo do scrubber)
# ---------------------------------------------------------------------------


def test_timeline_offsets_start_at_zero():
    tl = timeline(parse_rows([
        _row(1, ts="2026-08-26T14:30:00.000Z"),
        _row(2, ts="2026-08-26T14:30:02.500Z"),
    ]))
    assert [round(off) for off, _ in tl] == [0, 2500]


def test_timeline_never_goes_backwards_on_a_bad_ts():
    """ts ilegível repete o offset anterior — não extrapola linha do tempo."""
    tl = timeline(parse_rows([
        _row(1, ts="2026-08-26T14:30:00.000Z"),
        _row(2, ts="lixo"),
        _row(3, ts="2026-08-26T14:30:01.000Z"),
    ]))
    offs = [off for off, _ in tl]
    assert offs == sorted(offs)


# ---------------------------------------------------------------------------
# árvore de spans
# ---------------------------------------------------------------------------


def test_span_tree_nests_children_under_parents():
    trace = parse_rows([
        _row(1, "rag.query.started", span="s001", status="started"),
        _row(2, "rag.embedding.started", span="s002", parent="s001", status="started"),
        _row(3, "rag.embedding.finished", span="s002", parent="s001", duration=120.0),
        _row(4, "rag.retrieval.started", span="s003", parent="s001", status="started"),
        _row(5, "rag.retrieval.finished", span="s003", parent="s001", duration=47.0),
        _row(6, "rag.query.finished", span="s001", duration=180.0),
    ])
    roots = build_span_tree(trace)
    assert len(roots) == 1
    root = roots[0]
    assert root.span_id == "s001"
    assert root.duration_ms == 180.0
    assert [c.span_id for c in root.children] == ["s002", "s003"]
    assert [c.duration_ms for c in root.children] == [120.0, 47.0]


def test_orphan_span_is_promoted_to_root_not_dropped():
    """Trace cortado pode perder o pai. O filho não pode sumir do trace tree."""
    trace = parse_rows([_row(1, "rag.retrieval.finished", span="s009",
                             parent="s001", duration=10.0)])
    roots = build_span_tree(trace)
    assert [r.span_id for r in roots] == ["s009"]


# ---------------------------------------------------------------------------
# ida e volta pelo disco
# ---------------------------------------------------------------------------


def test_recorded_run_round_trips_through_jsonl(tmp_path):
    obs.reset_for_tests()
    previous = set_sink(JsonlSink(tmp_path))
    try:
        with obs.run(run_id="run_disco"):
            with obs.stage("rag.retrieval.started", "rag.retrieval.finished",
                           component="qdrant", meta={"topK": 12}) as st:
                st.meta["nRetrieved"] = 9
            obs.emit("gate.failed", component="gate.circulation", status="failed",
                     meta={"measured": 0.54, "required": 0.60, "unit": "m"})
    finally:
        set_sink(previous)
        obs.reset_for_tests()

    trace = load_run(tmp_path / "run_disco.jsonl")
    assert trace.run_id == "run_disco"
    assert trace.complete
    assert trace.terminal_status == "finished"
    assert trace.missing_seq == ()
    names = [e.name for e in trace.events]
    assert names == ["run.started", "rag.retrieval.started", "rag.retrieval.finished",
                     "gate.failed", "run.finished"]
    finished = trace.events[2]
    assert finished.meta["nRetrieved"] == 9
    assert finished.duration_ms is not None


def test_two_runs_write_to_separate_files(tmp_path):
    obs.reset_for_tests()
    previous = set_sink(JsonlSink(tmp_path))
    try:
        for rid in ("run_um", "run_dois"):
            with obs.run(run_id=rid):
                obs.emit("llm.started", component="ollama")
    finally:
        set_sink(previous)
        obs.reset_for_tests()

    assert (tmp_path / "run_um.jsonl").exists()
    assert (tmp_path / "run_dois.jsonl").exists()
    assert load_run(tmp_path / "run_um.jsonl").run_id == "run_um"
    assert load_run(tmp_path / "run_dois.jsonl").run_id == "run_dois"


def test_missing_file_loads_as_empty_trace(tmp_path):
    trace = load_run(tmp_path / "nao_existe.jsonl")
    assert trace.events == ()
    assert not trace.complete


def test_sink_stops_writing_and_marks_truncated_past_the_ceiling(tmp_path):
    obs.reset_for_tests()
    previous = set_sink(JsonlSink(tmp_path, max_bytes=900))
    try:
        with obs.run(run_id="run_grande"):
            for _ in range(60):
                obs.emit("rag.chunk.retrieved", component="qdrant",
                         meta={"chunkId": "c" * 20, "score": 0.5, "rank": 1})
    finally:
        set_sink(previous)
        obs.reset_for_tests()

    trace = load_run(tmp_path / "run_grande.jsonl")
    assert trace.truncated
    assert len(trace.events) < 61        # parou antes do fim, e disse que parou
