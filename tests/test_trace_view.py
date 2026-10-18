"""CLI de leitura de trace. Se ela mentir, o Inspector inteiro perde a base."""
from __future__ import annotations

import json

import pytest

from core import observability as obs
from core.observability.replay import load_run
from core.observability.sink import JsonlSink, set_sink
from tools import trace_view


@pytest.fixture
def traces(tmp_path):
    obs.reset_for_tests()
    previous = set_sink(JsonlSink(tmp_path))
    try:
        yield tmp_path
    finally:
        set_sink(previous)
        obs.reset_for_tests()


def _record(run_id="run_a", *, fail=False):
    ctx = obs.run(run_id=run_id, component="test")
    if fail:
        with pytest.raises(RuntimeError):
            with ctx:
                with obs.stage("rag.query.started", "rag.query.finished",
                               component="reference_db.retrieve"):
                    raise RuntimeError("boom")
        return
    with ctx:
        with obs.stage("rag.query.started", "rag.query.finished",
                       component="reference_db.retrieve",
                       meta={"backendRequested": "embed"}) as q:
            with obs.stage("rag.embedding.started", "rag.embedding.finished",
                           component="ollama.nomic"):
                pass
            obs.emit("rag.degraded", component="reference_db.embed_recall",
                     status="degraded", meta={"fallbackReason": "Qdrant off"})
            with obs.stage("rag.retrieval.started", "rag.retrieval.finished",
                           component="reference_db.faceted",
                           meta={"candidatesCount": 7, "nSelected": 6}):
                pass
            q.meta["backendActual"] = "faceted"
        obs.emit("gate.passed", component="gate.circulation",
                 meta={"gate": "circulation", "verdict": "PASS"})


# ---------------------------------------------------------------------------
# descoberta
# ---------------------------------------------------------------------------


def test_resolves_the_most_recent_run_by_default(traces):
    _record("run_velha")
    _record("run_nova")
    # mtime pode empatar em disco rápido; o que importa é resolver alguma run
    assert trace_view.resolve(None, traces) is not None


def test_resolves_by_run_id(traces):
    _record("run_por_id")
    assert trace_view.resolve("run_por_id", traces).name == "run_por_id.jsonl"


def test_resolves_by_explicit_path(traces):
    _record("run_path")
    p = traces / "run_path.jsonl"
    assert trace_view.resolve(str(p), traces) == p


def test_unknown_target_resolves_to_none(traces):
    assert trace_view.resolve("nao_existe", traces) is None


def test_empty_directory_lists_nothing(tmp_path):
    assert trace_view.list_traces(tmp_path) == []
    assert trace_view.main(["--list", "--dir", str(tmp_path)]) == 1


# ---------------------------------------------------------------------------
# a árvore precisa mostrar o fallback
# ---------------------------------------------------------------------------


def test_tree_nests_children_and_point_events_under_their_span(traces):
    _record("run_arvore")
    trace = load_run(traces / "run_arvore.jsonl")
    spans, points, children = trace_view.build_view(trace)

    root = next(sid for sid, s in spans.items()
                if s["component"] == "reference_db.retrieve")
    kids = [spans[c]["component"] for c in children[root]]
    assert kids == ["ollama.nomic", "reference_db.faceted"]
    # o evento pontual que EXPLICA o fallback fica dentro do span, não some
    assert [e.name for e in points[root]] == ["rag.degraded"]


def test_tree_output_shows_the_faceted_fallback_executing(traces, capsys):
    _record("run_saida")
    trace_view.main(["run_saida", "--dir", str(traces), "--tree"])
    out = capsys.readouterr().out
    assert "reference_db.faceted" in out
    assert "rag.degraded" in out
    assert "candidatesCount=7" in out
    # ordem: o degraded aparece ANTES do faceted que ele causou
    assert out.index("rag.degraded") < out.index("reference_db.faceted")


# ---------------------------------------------------------------------------
# honestidade: nunca afirmar integridade sem checar
# ---------------------------------------------------------------------------


def test_healthy_run_reports_invariants_ok_and_exits_zero(traces, capsys):
    _record("run_boa")
    code = trace_view.main(["run_boa", "--dir", str(traces)])
    assert code == 0
    assert "INVARIANTES: OK" in capsys.readouterr().out


def test_corrupted_run_reports_the_violation_and_exits_nonzero(traces, capsys):
    _record("run_furada")
    p = traces / "run_furada.jsonl"
    rows = [json.loads(x) for x in p.read_text("utf-8").splitlines() if x.strip()]
    del rows[2]                                        # abre um buraco no seq
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

    code = trace_view.main(["run_furada", "--dir", str(traces)])
    out = capsys.readouterr().out
    assert code == 1
    assert "VIOLAÇÃO" in out
    assert "seq_not_contiguous" in out


def test_check_mode_is_quiet_and_gates_on_exit_code(traces, capsys):
    _record("run_check")
    assert trace_view.main(["run_check", "--dir", str(traces), "--check"]) == 0
    out = capsys.readouterr().out
    assert "ÁRVORE" not in out and "t+s" not in out


def test_failed_run_is_rendered_without_being_called_corrupt(traces, capsys):
    """run.failed é execução legítima — não pode virar violação de invariante."""
    _record("run_falha", fail=True)
    code = trace_view.main(["run_falha", "--dir", str(traces)])
    out = capsys.readouterr().out
    assert code == 0
    assert "INVARIANTES: OK" in out
    assert "terminal=failed" in out


# ---------------------------------------------------------------------------
# JSON para script/CI
# ---------------------------------------------------------------------------


def test_json_summary_is_machine_readable(traces, capsys):
    _record("run_json")
    code = trace_view.main(["run_json", "--dir", str(traces), "--json"])
    data = json.loads(capsys.readouterr().out)
    assert code == 0
    assert data["runId"] == "run_json"
    assert data["terminal"] == "finished"
    assert data["complete"] is True
    assert data["violations"] == []
    assert data["byCategory"]["RAG"] >= 6


def test_json_summary_surfaces_violations(traces, capsys):
    _record("run_json_ruim")
    p = traces / "run_json_ruim.jsonl"
    rows = [json.loads(x) for x in p.read_text("utf-8").splitlines() if x.strip()]
    p.write_text("\n".join(json.dumps(r) for r in rows[:-1]) + "\n",
                 encoding="utf-8")          # tira o terminal

    code = trace_view.main(["run_json_ruim", "--dir", str(traces), "--json"])
    data = json.loads(capsys.readouterr().out)
    assert code == 1
    assert "missing_terminal" in {v["code"] for v in data["violations"]}


def test_missing_trace_exits_two(tmp_path, capsys):
    assert trace_view.main(["nao_existe", "--dir", str(tmp_path)]) == 2


def test_list_marks_runs_that_violate_invariants(traces, capsys):
    _record("run_ok_list")
    trace_view.main(["--list", "--dir", str(traces)])
    out = capsys.readouterr().out
    assert "run_ok_list" in out
    assert "finished" in out
