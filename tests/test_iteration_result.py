import pytest

from core.domain.iteration_result import Evaluation, IterationResult, IterationStatus


def _make(**overrides) -> IterationResult:
    base = dict(
        iteration_id="planta_74.r005.001",
        project_id="planta_74",
        room_id="r005",
        timestamp="2026-08-11T12:00:00Z",
        request="trocar material do box",
    )
    base.update(overrides)
    return IterationResult(**base)


def test_defaults():
    it = _make()
    assert it.status == IterationStatus.PENDING
    assert it.evaluation == Evaluation()
    assert it.design_changes == []
    assert it.gate_results == []


def test_to_json_roundtrip_preserves_all_fields():
    it = _make(
        design_changes=[{"field": "material", "from": "nero", "to": "oak"}],
        gate_results=[{"gate": "wall_overlap", "verdict": "PASS"}],
        render_artifacts=["artifacts/planta_74/r005/iterations/render_001.png"],
        evaluation=Evaluation(score=8.1, verdict="APROVADO_DESIGN", strengths=["luz"], problems=[], recommendations=["nada"]),
        status=IterationStatus.APPROVED,
    )
    restored = IterationResult.from_json(it.to_json())
    assert restored == it


def test_from_dict_defaults_status_to_pending_when_absent():
    it = _make()
    d = it.to_dict()
    del d["status"]
    restored = IterationResult.from_dict(d)
    assert restored.status == IterationStatus.PENDING


def test_status_only_accepts_enum_values():
    it = _make()
    d = it.to_dict()
    d["status"] = "NOT_A_REAL_STATUS"
    with pytest.raises(ValueError):
        IterationResult.from_dict(d)


def test_two_iterations_of_same_room_are_independent_objects():
    a = _make(iteration_id="planta_74.r005.001")
    b = _make(iteration_id="planta_74.r005.002", request="mudou luz")
    assert a.iteration_id != b.iteration_id
    assert a.request != b.request
