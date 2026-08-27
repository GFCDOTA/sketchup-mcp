"""Fase 3 nos call-sites REAIS.

Duas famílias de teste, e a primeira é a que importa mais:

1. **Não mudou o comportamento.** Cada caminho instrumentado produz saída
   byte-idêntica com a observabilidade ligada e desligada. É a tradução
   executável de *observability must describe execution, not change execution*.
2. **Descreveu a execução.** Os eventos certos, com intenção vs execução
   separadas, no boundary de thread real do sistema.
"""
from __future__ import annotations

import itertools
import json
import sys
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from core import observability as obs
from core.observability.sink import MemorySink, set_sink
from tools import correction_finding as cfind
from tools import correction_fixes as cfx
from tools import correction_loop as loop

REPO = Path(__file__).resolve().parents[1]
FRONT = REPO / "ops" / "estudio-front"


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


def _names(sink) -> list[str]:
    return [e.name for e in sink.events]


def _first(sink, name):
    hits = [e for e in sink.events if e.name == name]
    assert hits, f"nenhum evento {name!r} em {sorted(set(_names(sink)))}"
    return hits[0]


# ===========================================================================
# 1. NÃO MUDOU O COMPORTAMENTO
# ===========================================================================


@pytest.mark.parametrize("room,style,backend", [
    ("kitchen", "black_wood_gold", "faceted"),
    ("kitchen", "black_wood_gold", "embed"),
    ("bathroom", None, "faceted"),
    ("living", "industrial", "embed"),
])
def test_retrieve_bundle_is_identical_on_and_off(room, style, backend):
    from tools.reference_db import retrieve

    obs.reset_for_tests()
    previous = set_sink(None)
    try:
        off = json.dumps(retrieve(room, style, backend=backend), sort_keys=True)
        set_sink(MemorySink())
        with obs.run(run_id="cmp"):
            on = json.dumps(retrieve(room, style, backend=backend), sort_keys=True)
    finally:
        set_sink(previous)
        obs.reset_for_tests()
    assert off == on


def test_gate_run_all_result_is_identical_on_and_off():
    from tools.run_deterministic_gates import run_all

    obs.reset_for_tests()
    previous = set_sink(None)
    try:
        off = json.dumps(run_all(fixture="quadrado"), sort_keys=True)
        set_sink(MemorySink())
        with obs.run(run_id="cmp"):
            on = json.dumps(run_all(fixture="quadrado"), sort_keys=True)
    finally:
        set_sink(previous)
        obs.reset_for_tests()
    assert off == on


def _boxes_detector(ctx: cfx.FixContext):
    pairs = cfx._overlapping_module_pairs(ctx.boxes or [])
    return [cfind.make_finding(type="furniture_overlap", severity="FAIL",
                               source="deterministic",
                               source_check="furniture_overlap_gate",
                               evidence=f"{a} × {b}: {frac:.0%}")
            for a, b, frac in pairs]


def _box(module, x0, y0, w, d):
    return {"module": module, "kind": module, "z0_in": 0.0, "h_in": 30.0,
            "corners": [[x0, y0], [x0 + w, y0], [x0 + w, y0 + d], [x0, y0 + d]]}


_ROOM = [(-100.0, -100.0), (300.0, -100.0), (300.0, 300.0), (-100.0, 300.0)]


def test_correction_loop_result_is_identical_on_and_off(tmp_path):
    def _run(out):
        return loop.run_loop(
            fixture="synthetic", detect=_boxes_detector,
            boxes=[_box("sofa", 0, 0, 40, 20), _box("mesa", 20, 0, 24, 24)],
            room_poly=_ROOM, out_dir=out, heartbeat=None, log=lambda m: None)

    obs.reset_for_tests()
    previous = set_sink(None)
    try:
        off = _run(tmp_path / "off")
        set_sink(MemorySink())
        with obs.run(run_id="cmp"):
            on = _run(tmp_path / "on")
    finally:
        set_sink(previous)
        obs.reset_for_tests()

    assert (off.state, off.cycles, off.fixes_applied) == \
           (on.state, on.cycles, on.fixes_applied)


# ===========================================================================
# 2. DESCREVEU A EXECUÇÃO
# ===========================================================================


def test_retrieve_records_intent_and_actual_separately(sink):
    """Qdrant fora: pediu embed, executou faceted — e a trace diz os dois."""
    from tools.reference_db import retrieve

    with obs.run(run_id="run_intent"):
        retrieve("kitchen", "black_wood_gold", backend="embed")

    ev = _first(sink, "rag.query.finished")
    assert ev.meta["backendRequested"] == "embed"
    # sem Qdrant no CI, o efetivo é faceted; com Qdrant, é embed. Nos DOIS casos
    # o rótulo tem que bater com o backend que de fato executou.
    if ev.meta["backendActual"] == "faceted":
        assert ev.meta["fallbackTriggered"] is True
        assert ev.meta["resultingTaxonomy"] == "FACETED_STRUCTURED_RAG"
        assert ev.meta["intentMatchedExecution"] is False
        assert _first(sink, "rag.degraded").meta["fallbackReason"]
    else:
        assert ev.meta["resultingTaxonomy"] in ("VECTOR_SEMANTIC_RAG", "HYBRID_RAG")


def test_empty_retrieval_is_still_rag_not_an_orphan(sink):
    """`bathroom` não tem token curado: o retrieval volta VAZIO.

    Isso NÃO o torna um recuperador órfão. Órfão é quem nunca é consumido por
    geração alguma (project_memory_db) — propriedade da FIAÇÃO, não do resultado
    de uma execução. Quem conta a história do vazio é `nSelected=0`.
    """
    from tools.reference_db import retrieve

    with obs.run(run_id="run_vazio"):
        bundle = retrieve("bathroom", None, backend="faceted")

    assert bundle["tokens"] == []
    ev = _first(sink, "rag.query.finished")
    assert ev.meta["resultingTaxonomy"] == "FACETED_STRUCTURED_RAG"
    assert ev.meta["isRag"] is True
    assert ev.meta["nSelected"] == 0


def test_retrieve_nests_embedding_and_search_under_the_query_span(sink):
    """A causalidade é real: retrieve() chama embed() e search().

    O trace tree tem que mostrar isso ANINHADO, não como irmãos soltos na raiz.
    """
    from core.observability.replay import build_span_tree, parse_rows
    from tools.reference_db import retrieve

    with obs.run(run_id="run_tree"):
        retrieve("kitchen", "black_wood_gold", backend="embed")

    roots = build_span_tree(parse_rows(sink.rows(), run_id="run_tree"))
    query = next(r for r in roots if r.component == "reference_db.retrieve")
    # com Ollama no ar há embedding; com Qdrant no ar há busca. Ao menos um dos
    # dois tem que estar sob o span de retrieve.
    assert query.children, "embedding/search ficaram fora do span de retrieve"
    assert not any(r.component.startswith(("ollama.nomic", "qdrant."))
                   for r in roots), "filho vazou pra raiz do trace"


def test_faceted_run_is_not_labelled_a_fallback(sink):
    from tools.reference_db import retrieve

    with obs.run(run_id="run_faceted"):
        retrieve("kitchen", "black_wood_gold", backend="faceted")

    ev = _first(sink, "rag.query.finished")
    assert ev.meta["backendRequested"] == "faceted"
    assert ev.meta["fallbackTriggered"] is False
    assert ev.meta["intentMatchedExecution"] is True
    assert "rag.degraded" not in _names(sink)


def test_gates_emit_only_the_normalized_contract(sink):
    """A UI futura nunca deve conhecer os cinco formatos legados."""
    from tools.run_deterministic_gates import run_all

    with obs.run(run_id="run_gates"):
        run_all(fixture="quadrado")

    gate_events = [e for e in sink.events if e.name.startswith("gate.")]
    assert gate_events
    for e in gate_events:
        if e.name == "gate.measurement":
            assert set(e.meta) <= {"metric", "measured", "required", "unit",
                                   "status", "entityRef"}
            continue
        assert "gate" in e.meta and "verdict" in e.meta
        # nenhuma chave dos formatos crus vazou
        assert not ({"overall", "result", "checks", "fails", "warns", "findings"}
                    & set(e.meta))
        assert e.meta["verdict"] in ("PASS", "WARN", "FAIL", "INCOMPLETE",
                                     "SKIPPED", "UNKNOWN")


def test_correction_loop_emits_the_harness_phases(sink, tmp_path):
    """DETECT / CLASSIFY / FIX / RE-CHECK / terminal — o application harness."""
    with obs.run(run_id="run_loop"):
        res = loop.run_loop(
            fixture="synthetic", detect=_boxes_detector,
            boxes=[_box("sofa", 0, 0, 40, 20), _box("mesa", 20, 0, 24, 24)],
            room_poly=_ROOM, out_dir=tmp_path, heartbeat=None, log=lambda m: None)

    names = _names(sink)
    for expected in ("harness.cycle.started", "harness.detect", "harness.classify",
                     "harness.recheck", "agent.correction", "harness.terminal"):
        assert expected in names, f"faltou {expected}: {sorted(set(names))}"

    terminal = _first(sink, "harness.terminal")
    assert terminal.meta["terminal"] == res.state
    assert terminal.meta["harnessKind"] == "APPLICATION_HARNESS"


def test_harness_terminal_carries_the_real_stop_reason(sink, tmp_path):
    """Sem findings -> CLEAN. O motivo da parada é o dado, não a ausência dele."""
    with obs.run(run_id="run_clean"):
        loop.run_loop(fixture="synthetic", detect=lambda ctx: [], boxes=[],
                      room_poly=_ROOM, out_dir=tmp_path, heartbeat=None,
                      log=lambda m: None)
    terminal = _first(sink, "harness.terminal")
    assert terminal.meta["terminal"] == loop.CLEAN
    assert terminal.meta["counts"]["fixes"] == 0


def test_stall_is_reported_as_its_own_terminal(sink, tmp_path):
    """Findings idênticos em dois ciclos = patinagem, e a trace nomeia isso."""
    stuck = [cfind.make_finding(type="wall_overlap", severity="FAIL",
                                source="deterministic", source_check="x",
                                evidence="sempre o mesmo")]

    def _never_fixes(ctx):
        return list(stuck)

    with obs.run(run_id="run_stall"):
        loop.run_loop(fixture="synthetic", detect=_never_fixes, boxes=[],
                      room_poly=_ROOM, out_dir=tmp_path, heartbeat=None,
                      log=lambda m: None)
    assert _first(sink, "harness.terminal").meta["terminal"] in (
        loop.STALL, loop.NEEDS_FELIPE, loop.PENDING_VISION)


def test_agent_correction_carries_only_observable_evidence(sink, tmp_path):
    with obs.run(run_id="run_ev"):
        loop.run_loop(
            fixture="synthetic", detect=_boxes_detector,
            boxes=[_box("sofa", 0, 0, 40, 20), _box("mesa", 20, 0, 24, 24)],
            room_poly=_ROOM, out_dir=tmp_path, heartbeat=None, log=lambda m: None)

    corr = _first(sink, "agent.correction")
    assert corr.meta["triggerEvent"] == "harness.classify"
    assert corr.meta["toolCalled"]
    for forbidden in ("reasoning", "rationale", "thought", "chainOfThought"):
        assert forbidden not in corr.meta


# ===========================================================================
# 3. BOUNDARY DE THREAD REAL — o ThreadingHTTPServer do BFF
# ===========================================================================


@pytest.fixture
def front_handler(monkeypatch):
    """Importa o Handler REAL do BFF, com só o turno de chat stubado."""
    if str(FRONT) not in sys.path:
        sys.path.insert(0, str(FRONT))
    import rag_chat
    import server

    def _fake_chat(message: str) -> dict:
        # emite de dentro da thread da requisição: é isso que precisa correlacionar
        obs.emit("llm.finished", component="ollama.stub",
                 meta={"model": "stub", "promptTokens": 10, "completionTokens": 3})
        return {"reply": f"eco: {message}", "context_used": []}

    monkeypatch.setattr(rag_chat, "chat", _fake_chat)
    return server.Handler


def test_each_http_request_gets_its_own_correlated_run(sink, front_handler):
    """contextvars não atravessa thread — por isso a run nasce DENTRO do handler.

    Quatro requisições concorrentes no ThreadingHTTPServer real: quatro runs
    distintas, cada uma com seq contíguo e sem eventos vazando entre threads.
    """
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), front_handler)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        def _post(i: int):
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/chat",
                data=json.dumps({"message": f"msg{i}"}).encode(),
                headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read())

        workers = [threading.Thread(target=_post, args=(i,)) for i in range(4)]
        for w in workers:
            w.start()
        for w in workers:
            w.join()
    finally:
        httpd.shutdown()
        httpd.server_close()

    by_run: dict[str, list] = {}
    for e in sink.events:
        by_run.setdefault(e.run_id, []).append(e)

    assert len(by_run) == 4, f"esperado 4 runs isoladas, veio {len(by_run)}"
    for run_id, events in by_run.items():
        seqs = sorted(e.seq for e in events)
        assert seqs == list(range(1, len(seqs) + 1)), f"{run_id}: seq com buraco"
        assert len({e.trace_id for e in events}) == 1
        names = [e.name for e in sorted(events, key=lambda x: x.seq)]
        assert names[0] == "run.started" and names[-1] == "run.finished"
        assert "llm.finished" in names


def test_front_opens_the_run_inside_the_request_thread():
    """Contrato de fiação: o ponto de propagação é explícito no server.py.

    Se alguém mover o `obs.run(...)` pra fora do handler, a correlação por
    requisição some em silêncio — e o teste acima ainda passaria com 1 run.
    """
    src = (FRONT / "server.py").read_text(encoding="utf-8")
    chat_route = src[src.index('if route == "/api/chat":'):]
    assert "with obs.run(" in chat_route.split("def ")[0]
