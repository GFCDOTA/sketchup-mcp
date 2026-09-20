"""Fundação de instrumentação: correlação, ordenação, spans e estados de run."""
from __future__ import annotations

import itertools
import threading

import pytest

from core import observability as obs
from core.observability.events import Event, Status, UnknownEventName, default_category
from core.observability.sink import MemorySink, NullSink, set_sink
from core.observability.taxonomy import Category


def _named(sink, name):
    """O ÚLTIMO evento de uma run é sempre `run.finished` — buscar por nome."""
    hits = [e for e in sink.events if e.name == name]
    assert hits, f"nenhum evento {name!r} emitido"
    return hits[-1]


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


# ---------------------------------------------------------------------------
# desligado por padrão — a defesa contra "instrumentação vira carroça"
# ---------------------------------------------------------------------------


def test_emit_is_noop_without_a_sink():
    obs.reset_for_tests()
    previous = set_sink(None)
    try:
        with obs.run():
            assert obs.emit("llm.started", component="x") is None
        assert not obs.is_enabled()
    finally:
        set_sink(previous)


def test_null_sink_counts_as_disabled():
    previous = set_sink(NullSink())
    try:
        assert not obs.is_enabled()
    finally:
        set_sink(previous)


def test_emit_outside_a_run_is_dropped(sink):
    """Evento sem runId não é correlacionável — silêncio honesto, não linha órfã."""
    assert obs.emit("llm.started", component="ollama") is None
    assert sink.events == []


# ---------------------------------------------------------------------------
# correlação
# ---------------------------------------------------------------------------


def test_all_events_of_a_run_share_run_and_trace_id(sink):
    with obs.run(run_id="run_fixo_1", trace_id="t" * 32):
        obs.emit("llm.started", component="ollama")
        with obs.stage("rag.retrieval.started", "rag.retrieval.finished",
                       component="qdrant"):
            obs.emit("rag.chunk.retrieved", component="qdrant",
                     meta={"chunkId": "c1", "score": 0.91, "rank": 1})

    assert {e.run_id for e in sink.events} == {"run_fixo_1"}
    assert {e.trace_id for e in sink.events} == {"t" * 32}


def test_two_runs_never_share_identity(sink):
    with obs.run(run_id="run_a"):
        obs.emit("llm.started", component="ollama")
    with obs.run(run_id="run_b"):
        obs.emit("llm.started", component="ollama")

    by_run = {}
    for e in sink.events:
        by_run.setdefault(e.run_id, []).append(e)
    assert set(by_run) == {"run_a", "run_b"}
    assert by_run["run_a"][0].trace_id != by_run["run_b"][0].trace_id
    # cada run reinicia a própria numeração
    assert [e.seq for e in by_run["run_a"]] == [1, 2, 3]
    assert [e.seq for e in by_run["run_b"]] == [1, 2, 3]


def test_nested_run_does_not_hijack_the_outer_run_id(sink):
    """run_deterministic_gates pode ser chamado dentro de um ciclo que já abriu
    a run. Trocar o runId no meio quebraria a correlação."""
    with obs.run(run_id="run_externo"):
        with obs.run(run_id="run_interno"):
            obs.emit("gate.passed", component="gate.x")
    assert {e.run_id for e in sink.events} == {"run_externo"}


# ---------------------------------------------------------------------------
# ordenação
# ---------------------------------------------------------------------------


def test_seq_is_monotonic_and_gapless(sink):
    with obs.run(run_id="run_seq"):
        for _ in range(12):
            obs.emit("rag.chunk.retrieved", component="qdrant", meta={"chunkId": "c"})
    seqs = [e.seq for e in sink.events]
    assert seqs == list(range(1, len(seqs) + 1))


def test_emit_from_an_unattached_thread_is_dropped(sink):
    """contextvars NÃO atravessa threading.Thread: a thread nova nasce sem run.

    Isso é armadilha real (o BFF é ThreadingHTTPServer). O comportamento correto
    é DESCARTAR — evento sem runId não é correlacionável — e a saída é `attach`.
    """
    with obs.run(run_id="run_solto"):
        def worker():
            obs.emit("rag.chunk.retrieved", component="qdrant", meta={"chunkId": "c"})

        t = threading.Thread(target=worker)
        t.start()
        t.join()

    assert [e.name for e in sink.events] == ["run.started", "run.finished"]


def test_seq_is_unique_under_concurrency(sink):
    """O BFF é ThreadingHTTPServer: duas threads da mesma run não podem colidir."""
    with obs.run(run_id="run_threads") as ctx:
        def worker():
            with obs.attach(ctx):
                for _ in range(50):
                    obs.emit("rag.chunk.retrieved", component="qdrant",
                             meta={"chunkId": "c"})

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    emitted = ctx.emitted        # inclui o run.finished emitido na saída do with
    seqs = sorted(e.seq for e in sink.events if e.run_id == "run_threads")
    assert len(seqs) == len(set(seqs)), "seq duplicado sob concorrência"
    assert seqs == list(range(1, emitted + 1))


def test_ordering_does_not_depend_on_wall_clock(sink):
    """Relógio congelado: a ordem ainda tem que sair certa pelo seq."""
    obs.configure(clock=lambda: 1_800_000_000.0)
    with obs.run(run_id="run_congelado"):
        obs.emit("llm.started", component="a")
        obs.emit("llm.finished", component="a")
    assert len({e.ts for e in sink.events}) == 1
    assert [e.seq for e in sink.events] == [1, 2, 3, 4]
    assert [e.name for e in sink.events] == [
        "run.started", "llm.started", "llm.finished", "run.finished"]


# ---------------------------------------------------------------------------
# spans
# ---------------------------------------------------------------------------


def test_stage_emits_started_and_finished_with_the_same_span(sink):
    with obs.run(run_id="run_span"):
        with obs.stage("rag.embedding.started", "rag.embedding.finished",
                       component="ollama.nomic") as st:
            st.meta["embedDim"] = 768

    pair = [e for e in sink.events if e.name.startswith("rag.embedding")]
    assert [e.name for e in pair] == ["rag.embedding.started", "rag.embedding.finished"]
    assert pair[0].span_id == pair[1].span_id
    assert pair[0].duration_ms is None
    assert pair[1].duration_ms is not None and pair[1].duration_ms >= 0
    assert pair[1].meta["embedDim"] == 768


def test_nested_stages_link_parent_to_child(sink):
    with obs.run(run_id="run_nest"):
        with obs.stage("rag.query.started", "rag.query.finished",
                       component="reference_db") as outer:
            with obs.stage("rag.retrieval.started", "rag.retrieval.finished",
                           component="qdrant") as inner:
                pass
    outer_id, inner_id = outer.span_id, inner.span_id
    assert outer_id != inner_id

    finished = {e.name: e for e in sink.events if e.name.endswith(".finished")}
    assert finished["rag.retrieval.finished"].parent_span_id == outer_id
    assert finished["rag.query.finished"].parent_span_id is None


def test_stage_marks_degraded_without_raising(sink):
    """Qdrant off é degradação honesta, não falha."""
    with obs.run(run_id="run_degraded"):
        with obs.stage("rag.retrieval.started", "rag.retrieval.finished",
                       component="qdrant") as st:
            st.degraded("Qdrant off -> faceted; confidence NÃO inflada")

    ev = [e for e in sink.events if e.name == "rag.retrieval.finished"][0]
    assert ev.status is Status.DEGRADED
    assert "faceted" in ev.meta["note"]


def test_stage_reraises_and_records_failure(sink):
    with obs.run(run_id="run_boom"), pytest.raises(RuntimeError):
        with obs.stage("tool.started", "tool.finished", failed="tool.failed",
                       component="mcp.room_gates"):
            raise RuntimeError("subprocess morreu")

    failed = [e for e in sink.events if e.name == "tool.failed"]
    assert len(failed) == 1
    assert failed[0].status is Status.FAILED
    assert failed[0].meta["errorType"] == "RuntimeError"
    assert failed[0].duration_ms is not None


# ---------------------------------------------------------------------------
# estados terminais da run
# ---------------------------------------------------------------------------


def test_run_finished_on_success(sink):
    with obs.run(run_id="run_ok"):
        pass
    assert [e.name for e in sink.events] == ["run.started", "run.finished"]
    assert sink.events[-1].duration_ms is not None


def test_run_failed_on_exception(sink):
    with pytest.raises(ValueError):
        with obs.run(run_id="run_erro"):
            raise ValueError("consensus ausente")
    last = sink.events[-1]
    assert last.name == "run.failed"
    assert last.status is Status.FAILED
    assert last.meta["errorType"] == "ValueError"


def test_run_canceled_is_distinct_from_failed(sink):
    """Ctrl-C não é bug. A UI precisa distinguir os dois."""
    with pytest.raises(KeyboardInterrupt):
        with obs.run(run_id="run_cancel"):
            raise KeyboardInterrupt
    last = sink.events[-1]
    assert last.name == "run.canceled"
    assert last.status is Status.SKIPPED


# ---------------------------------------------------------------------------
# retry / correção do harness
# ---------------------------------------------------------------------------


def test_retry_cycle_is_observable_end_to_end(sink):
    """FAIL -> retry -> correção -> PASS: a história que o Inspector conta."""
    with obs.run(run_id="run_retry"):
        with obs.stage("harness.cycle.started", "harness.cycle.finished",
                       component="correction_loop", meta={"cycle": 1}):
            obs.emit("gate.failed", component="gate.circulation", status="failed",
                     meta={"gate": "circulation", "measured": 0.54, "required": 0.60,
                           "unit": "m"})
            obs.emit("agent.retry", component="correction_loop",
                     meta={"cycle": 1, "findingType": "clearance",
                           "triggerEvent": "gate.failed", "gateResult": "FAIL"})
        with obs.stage("harness.cycle.started", "harness.cycle.finished",
                       component="correction_loop", meta={"cycle": 2}):
            obs.emit("agent.correction", component="correction_fixes",
                     meta={"fix": "nudge_fixture", "reverted": False,
                           "effect": "entity#9821 deslocada 6 cm"})
            obs.emit("gate.passed", component="gate.circulation",
                     meta={"gate": "circulation", "measured": 0.61, "required": 0.60,
                           "unit": "m"})
        obs.emit("harness.terminal", component="correction_loop",
                 meta={"terminal": "CLEAN", "cycle": 2})

    names = [e.name for e in sink.events]
    assert names.index("gate.failed") < names.index("agent.retry")
    assert names.index("agent.retry") < names.index("agent.correction")
    assert names.index("agent.correction") < names.index("gate.passed")

    terminal = [e for e in sink.events if e.name == "harness.terminal"][0]
    assert terminal.meta["terminal"] == "CLEAN"
    assert terminal.category is Category.HARNESS


def test_retry_evidence_has_no_reasoning_field(sink):
    with obs.run(run_id="run_ev"):
        obs.emit("agent.retry", component="correction_loop",
                 meta={"triggerEvent": "gate.failed", "gateResult": "FAIL",
                       "reasoning": "achei que ficaria melhor assim"})
    meta = _named(sink, "agent.retry").meta
    assert "reasoning" not in meta, "chain-of-thought vazou pela allowlist"
    assert meta["gateResult"] == "FAIL"


# ---------------------------------------------------------------------------
# metadados de chunk
# ---------------------------------------------------------------------------


def test_chunk_metadata_is_reference_only(sink):
    """O evento carrega id/score/rank/origem. Texto do chunk fica fora (§6.4)."""
    with obs.run(run_id="run_chunk"):
        obs.emit("rag.chunk.selected", component="qdrant.rag_chunks",
                 meta={"chunkId": "a1b2c3", "score": 0.94, "rank": 1,
                       "source": "references/tokens/nicho_led.json",
                       "sourceType": "token", "chars": 1140, "selected": True,
                       "text": "conteúdo enorme que NÃO pode entrar no evento"})
    meta = _named(sink, "rag.chunk.selected").meta
    assert meta["chunkId"] == "a1b2c3"
    assert meta["score"] == 0.94
    assert meta["selected"] is True
    assert "text" not in meta


def test_rejected_chunk_records_why(sink):
    """search_preferences hoje descarta o rejeitado; o evento tem que guardar."""
    with obs.run(run_id="run_rej"):
        obs.emit("rag.chunk.rejected", component="qdrant.felipe_preferences",
                 meta={"chunkId": "z9", "score": 0.21, "rank": 9,
                       "threshold": 0.30, "selected": False,
                       "reason": "abaixo do threshold"})
    meta = _named(sink, "rag.chunk.rejected").meta
    assert meta["selected"] is False
    assert meta["threshold"] == 0.30
    assert meta["reason"] == "abaixo do threshold"


# ---------------------------------------------------------------------------
# catálogo e serialização
# ---------------------------------------------------------------------------


def test_unknown_event_name_raises_instead_of_becoming_an_orphan(sink):
    with obs.run(run_id="run_typo"):
        with pytest.raises(UnknownEventName):
            obs.emit("rag.retreival.finished", component="qdrant")  # typo proposital


def test_default_category_by_prefix():
    assert default_category("rag.chunk.selected") is Category.RAG
    assert default_category("llm.finished") is Category.LLM
    assert default_category("gate.failed") is Category.DETERMINISTIC
    assert default_category("context.build.finished") is Category.HARNESS
    assert default_category("agent.retry") is Category.HARNESS
    assert default_category("tool.started") is Category.TOOL


def test_envelope_roundtrips_through_json(sink):
    with obs.run(run_id="run_json"):
        obs.emit("llm.finished", component="ollama.deepseek",
                 meta={"model": "deepseek-r1:14b", "promptTokens": 3841})
    original = _named(sink, "llm.finished")
    restored = Event.from_dict(original.to_dict())
    assert restored == original


def test_envelope_uses_camel_case_for_the_ui(sink):
    with obs.run(run_id="run_camel"):
        obs.emit("llm.started", component="ollama")
    d = _named(sink, "llm.started").to_dict()
    for key in ("runId", "traceId", "spanId", "parentSpanId", "durationMs"):
        assert key in d
