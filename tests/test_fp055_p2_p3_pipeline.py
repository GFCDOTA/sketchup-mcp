"""FP-055 P2 (contratos) e P3 (orquestrador): a decisao do especialista muda a proposta, com rastro ate o resultado."""
from __future__ import annotations

import types

import pytest

from core.pipeline_contracts import (
    BuildResult,
    CapabilityLedger,
    ContractError,
    GenerationRequest,
    LayoutProposal,
)
from tests.test_fp054_f2c_candidates import ROOM, _scene
from tools.orchestration import intelligent_pipeline as ip
from tools.rooms.shared.spatial_solver.contracts import DegreesOfFreedom

BATH_BUILDER = "tools.rooms.bathroom.layout.build_boxes"


def _req(**kw):
    base = dict(project_id="planta_74", source_document="fixtures/x.json", source_revision="ab", repository_commit="c",
                generation_profile="INTELLIGENT_DRY_RUN", output_directory="runs/fp055/t")
    return GenerationRequest(**{**base, **kw})


# ---------------------------------------------------------------------------------------------- P2 contratos
def test_request_rejects_missing_field_unknown_profile_and_unauthorised_official_write():
    with pytest.raises(ContractError, match="source_revision"):
        _req(source_revision="")
    with pytest.raises(ContractError, match="perfil"):
        _req(generation_profile="YOLO")
    with pytest.raises(ContractError, match="allow_official_write"):
        _req(output_directory="artifacts/planta_74/furnished")


def test_feasible_proposal_cannot_carry_a_hard_violation():
    with pytest.raises(ContractError):
        LayoutProposal("p", "r", "FEASIBLE", "c", (), ({"code": "X"},), {}, 1, 1, "", "a", "p")


def test_build_result_must_explain_every_missing_object():
    with pytest.raises(ContractError, match="sem motivo"):
        BuildResult(("A · x", "A · y"), ("A · x",), {}, (), "26.0.429")
    BuildResult(("A · x", "A · y"), ("A · x",), {"A · y": "omitido pela circulacao"}, (), "26.0.429")


def test_ledger_enforces_order_and_evidence():
    led = CapabilityLedger()
    with pytest.raises(ContractError):
        led.consume("x", "efeito")                          # CONSUMED sem INVOKED
    led.available("x")
    led.invoke("x")
    with pytest.raises(ContractError, match="evidencia"):
        led.consume("x", "")
    led.consume("x", "alimentou o solver")
    with pytest.raises(ContractError):
        led.validate("x", "gate")                           # VALIDATED sem REFLECTED_IN_MODEL
    assert led.state("x") == "CONSUMED"


# ---------------------------------------------------------------------------------------------- P3 orquestrador
def _plan(con, boxes, ifaces, policy=None, builder=BATH_BUILDER):
    led = CapabilityLedger()
    out = ip.plan_room(con, boxes, ifaces, "r_syn", "BATHROOM", ROOM, builder, led, policy=policy)
    return out, led


def _zero_dof_policy():
    return types.SimpleNamespace(POLICY_VERSION="test.zero-dof", ANCHOR_AND_DOF={
        "toilet": ("WALL_BACKED", DegreesOfFreedom((0.0, 0.0), 0.02, False, "PROJECT_POLICY", "teste: vaso fixo"))})


def test_specialist_constraint_changes_the_proposal_with_trace():
    con, boxes, ifaces = _scene()                            # vaso com armario na frente; deslizar para o norte resolve
    free, led_free = _plan(con, boxes, ifaces)
    fixed, led_fixed = _plan(con, boxes, ifaces, policy=_zero_dof_policy())
    assert free["status"] == "FEASIBLE" and free["proposal"].candidate_id.startswith("r_syn:Vaso:+")
    assert fixed["status"] == "INFEASIBLE" and fixed["proposal"].candidate_id == "ORIGINAL"
    assert fixed["proposal"].policy_version == "test.zero-dof"                     # rastro: politica -> proposta
    trail = led_fixed.to_dict()["specialist.bathroom"]["trail"]
    assert "test.zero-dof" in next(e["evidence"] for e in trail if e["state"] == "INVOKED")
    assert led_free.state("specialist.bathroom") == "CONSUMED" and led_free.state("f2.spatial_solver") == "CONSUMED"
    assert free["proposal"].boxes and all(b["room"] == ROOM for b in free["proposal"].boxes)


def test_missing_semantic_interface_is_invalid_input_and_is_not_consumed():
    con, boxes, _ifaces = _scene(obstacle=False)
    out, led = _plan(con, boxes, {})
    # o contrato do solver recusa a entrada antes de enumerar: sem interface semantica nao ha proposta
    assert out["status"] == "INVALID_INPUT" and not out["proposal"].buildable_as_valid
    assert any(v["code"] == "MISSING_SEMANTIC_INTERFACE" for v in out["proposal"].hard_violations)
    assert led.state("f1c.functional_interfaces") == "INVOKED"                    # chamado, nao consumido


def test_builder_outside_the_specialist_allowlist_is_blocked():
    con, boxes, ifaces = _scene()
    out, _led = _plan(con, boxes, ifaces, builder="tools.rooms.kitchen.layout.build_boxes")
    assert out["status"] == "BLOCKED" and "allowlist" in out["reason"]


def test_run_fails_closed_on_runtime_and_source_revision():
    blocked = ip.run(_req(), runtime_check=lambda p: {"status": "BLOCKED", "reasons": ["velho"]})
    assert blocked["status"] == "BLOCKED_RUNTIME" and blocked["valid"] is False
    bad_src = ip.run(_req(source_document="fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json"),
                     runtime_check=lambda p: {"status": "OK", "reasons": []})
    assert bad_src["status"] == "BLOCKED_SOURCE_REVISION" and bad_src["valid"] is False


def test_only_the_jobs_own_pid_is_collected_never_inspection_persistent_ids():
    # achado real da P4: a varredura recursiva pegava persistent_id dos nos da inspecao e tentava fechar esses numeros
    res = {"pid": 4242, "result": {"nodes": [{"name": "A · x", "pid": 49758}, {"name": "B · y", "pid": 23652}]},
           "build": {"pid": 777}}
    assert ip._pids(res) == {4242, 777}
    assert ip._pids({"pid": True}) == set() and ip._pids({}) == set()


def test_furniture_outside_the_built_floor_is_caught_even_when_proposal_matches_build():
    # achado real da P4: shell em outra escala; proposta x construido batia (0 mm) e a mobilia estava fora do comodo
    vaso = {"room": "R", "module": "Vaso", "z0_in": 0.0, "h_in": 16, "corners": [[100, 100], [125, 100], [125, 114], [100, 114]]}
    espelho = {"room": "R", "module": "Espelho", "z0_in": 60.0, "h_in": 30, "corners": [[0, 0], [1, 0], [1, 1], [0, 1]]}
    floor_ok = {"name": "Floor_Group_r", "bbox_world_m": {"min": [2.0, 2.0, 0.0], "max": [4.0, 4.0, 0.0]}}
    assert ip.inside_built_shell([floor_ok], [vaso, espelho], {"r": "R"}) == []        # espelho alto nao conta no piso
    floor_far = {"name": "Floor_Group_r", "bbox_world_m": {"min": [3.5, 3.5, 0.0], "max": [6.9, 6.9, 0.0]}}
    probs = ip.inside_built_shell([floor_far], [vaso], {"r": "R"})
    assert probs and probs[0]["group"] == "R · Vaso"
    assert "ausente" in ip.inside_built_shell([], [vaso], {"r": "R"})[0]["problem"]
