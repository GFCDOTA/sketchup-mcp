from core.domain.retrieval_trace import (
    EvaluationStage,
    ExecutionStage,
    LLMStage,
    RetrievalStage,
    RetrievedChunk,
    RetrievalTrace,
    ValidationStage,
)


def test_minimal_trace_defaults():
    t = RetrievalTrace(
        trace_id="a" * 32, project_id="planta_74", room_id="r004", query="qual madeira aprovada?",
    )
    assert t.retrieval.chunks == []
    assert t.llm.model is None
    assert t.estimated_cost is None  # opcional por design


def test_full_trace_json_roundtrip():
    t = RetrievalTrace(
        trace_id="b" * 32,
        project_id="planta_74",
        room_id="r005",
        query="qual madeira já foi aprovada no banheiro?",
        retrieval=RetrievalStage(
            chunks=[RetrievedChunk(chunk_id="c1", source="ITERATIONS.md", source_type="human_verdict", score=0.81, rank=1)],
            latency_ms=42.5,
        ),
        llm=LLMStage(model="llama3.1:8b", latency_ms=900.0, prompt_tokens=500, completion_tokens=120),
        execution=ExecutionStage(tool_calls=["knowledge_api.retrieve"]),
        validation=ValidationStage(gates=[{"gate": "wall_overlap", "verdict": "PASS"}], passed=True),
        evaluation=EvaluationStage(score=8.1, verdict="APROVADO_DESIGN"),
        total_latency_ms=950.0,
    )
    restored = RetrievalTrace.from_json(t.to_json())
    assert restored == t


def test_estimated_cost_stays_none_unless_explicitly_set():
    t = RetrievalTrace(trace_id="c" * 32, project_id="planta_74", room_id=None, query="x")
    assert t.to_dict()["estimated_cost"] is None
