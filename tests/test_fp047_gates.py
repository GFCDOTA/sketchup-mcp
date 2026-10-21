"""FP-047/F3: gates L1 de parede, giro e circulacao comparados antes x depois (R-07..R-13; CA-09..CA-12, CA-16).

Parte unitaria (escala padrao): logica de `delta` e fiacao em `compare`. Parte real (`planta74_scale`, processo isolado em
PT_TO_M=0.0259): negativos montados SOBRE o consenso real — mover mobilia para dentro da parede, cadeira no arco da porta,
excecoes de hospedagem/estrutural/piso — sem tocar fixture, canonico ou builder.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tools.validation import room_regression as rr
from tools.validation import room_regression_diff as rd
from tools.validation import room_regression_gates as gates

ROOT = Path(__file__).resolve().parents[1]
PT_TO_M = 0.0259
# Achado REAL e preexistente em develop@23939d9 (medido nesta fatia, nao introduzido por ela): a circulacao da SUITE 01 reprova
# o corredor principal (portal 2 sem passagem com a mobilia). Fica listado; mudar isto exige olhar o gate, nao editar o teste.
KNOWN_PREEXISTING = {"CIRC|r000|corredor_principal"}


def _f(gate, room, metric, key=None):
    return {"gate": gate, "room": room, "metric": metric, "detail": {}}


def _g(**findings):
    return {"findings": findings, "rooms_checked": ["r000"]}


# --- delta (sem escala, sem consenso) ------------------------------------------------------------------------------------

def test_new_finding_is_introduced_and_fails():
    d = gates.delta(_g(), _g(**{"WALL|SUITE 02|Cama|bed": _f("wall_penetration", "SUITE 02", 12.0)}))
    assert d["state"] == "FAIL" and [x["why"] for x in d["introduced"]] == ["NEW"]


def test_same_finding_in_base_is_preexisting_and_does_not_fail_the_change():
    f = {"CIRC|r000|corredor_principal": _f("circulation", "SUITE 01", 1.0)}
    d = gates.delta(_g(**f), _g(**f))
    assert d["state"] == "PASS" and d["introduced"] == [] and [x["key"] for x in d["preexisting"]] == list(f)


def test_worse_finding_counts_as_introduced_but_float_noise_does_not():
    key = "WALL|SUITE 02|Cama|bed"
    worse = gates.delta(_g(**{key: _f("wall_penetration", "SUITE 02", 5.0)}), _g(**{key: _f("wall_penetration", "SUITE 02", 9.0)}))
    assert worse["state"] == "FAIL" and worse["introduced"][0]["why"] == "WORSE"
    noise = gates.delta(_g(**{key: _f("wall_penetration", "SUITE 02", 5.0)}), _g(**{key: _f("wall_penetration", "SUITE 02", 5.05)}))
    assert noise["state"] == "PASS"


def test_resolved_findings_are_reported_and_never_fail():
    d = gates.delta(_g(**{"DOOR|COZINHA|d1|Mesa|m": _f("door_swing", "COZINHA", 30.0)}), _g())
    assert d["state"] == "PASS" and [x["key"] for x in d["resolved"]] == ["DOOR|COZINHA|d1|Mesa|m"]


# --- fiacao em compare ---------------------------------------------------------------------------------------------------

def _snap(boxes):
    return rd.snapshot(boxes, fixture="synthetic", pt_to_m=PT_TO_M)


def _boxes():
    base = {"corners": [[0, 0], [1, 0], [1, 1], [0, 1]], "x0": 0, "y0": 0, "x1": 1, "y1": 1, "h_in": 30, "z0_in": 0.0, "kind": "k",
            "geometry_intent": "FURNITURE"}
    return [{**base, "room": "SUITE 02", "module": "Cama", "label": "bed"}, {**base, "room": "COZINHA", "module": "Pia", "label": "sink"}]


def _contract():
    return {"schema_version": "room_regression_request.v1", "change_id": "fp047-gates-001", "fixture": "synthetic",
            "change_mode": "strict_identity", "control_rooms": ["COZINHA"], "protect_canonicals": True, "require_l2": False,
            "require_l3_if_visual_changed": True}


def _compare(gb, ga, **kw):
    s = _snap(_boxes())
    canon = {"a.skp": "x"}
    return rd.compare(s, s, _contract(), canonical_before=canon, canonical_after=canon, gates_before=gb, gates_after=ga, **kw)


def test_compare_passes_when_gates_show_only_preexisting_and_lists_them_in_evidence():
    f = {"CIRC|r000|corredor_principal": _f("circulation", "SUITE 02", 1.0)}
    report = _compare(_g(**f), _g(**f))
    assert report["state"] == "PASS" and report["tests"]["l1"] == "PASS" and rr.validate_report(report) == []
    assert report["evidence"]["preexisting_gate_findings"] == list(f) and report["evidence"]["introduced_gate_findings"] == []
    suite = next(r for r in report["room_results"] if r["room_key"] == "SUITE 02")
    assert [x["key"] for x in suite["gate_findings"]["preexisting"]] == list(f)


def test_compare_fails_the_room_where_a_gate_finding_was_introduced_even_with_zero_box_delta_authorization_issue():
    report = _compare(_g(), _g(**{"WALL|SUITE 02|Cama|bed": _f("wall_penetration", "SUITE 02", 12.0)}))
    assert report["state"] == "FAIL" and report["tests"]["l1"] == "FAIL"
    assert next(r for r in report["room_results"] if r["room_key"] == "SUITE 02")["state"] == "FAIL"
    assert next(r for r in report["room_results"] if r["room_key"] == "COZINHA")["state"] == "PASS"


def test_only_one_side_of_the_gates_is_blocked_never_compared_against_nothing():
    for gb, ga in ((_g(), None), (None, _g())):
        report = _compare(gb, ga)
        assert report["state"] == "BLOCKED" and report["blocked"] == ["GATES_INCOMPLETE"]


def test_without_gates_l1_stays_not_run_and_state_never_passes():
    report = _compare(None, None)
    assert report["tests"]["l1"] == "NOT_RUN" and report["state"] == "BLOCKED"


def test_a_crashing_gate_is_a_finding_not_an_omission(monkeypatch):
    from tools.validation import circulation_gate, room_collisions

    monkeypatch.setattr(room_collisions, "audit", lambda con, boxes: {})
    monkeypatch.setattr(circulation_gate, "gate", lambda con, boxes, rid: (_ for _ in ()).throw(RuntimeError("boom")))
    boxes = _boxes()
    before = copy.deepcopy(boxes)
    out = gates.run({"rooms": [{"id": "r000", "name": "SUITE 01"}]}, boxes)
    assert list(out["findings"]) == ["GATE_ERROR|r000|circulation"] and boxes == before


# --- real: planta_74, escala isolada ------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def real():
    from core.scale import PT_TO_IN
    from core.scale import PT_TO_M as SCALE
    if abs(SCALE - PT_TO_M) > 1e-12:
        pytest.skip("escala da planta_74 (PT_TO_M=0.0259) nao ativa")
    from tools.orchestration.furnish_apartment import CONSENSUS, collect_boxes
    from tools.rooms.shared.clearance import door_swings_pt, wall_mass_pt
    con = json.loads(Path(CONSENSUS).read_text("utf-8"))
    boxes, _ = collect_boxes(con)
    return {"con": con, "boxes": boxes, "walls": wall_mass_pt(con), "swings": door_swings_pt(con), "to_in": PT_TO_IN}


def _square(point, to_in, *, side_in=8.0, **over):
    cx, cy = point.x * to_in, point.y * to_in
    h = side_in / 2
    corners = [[cx - h, cy - h], [cx + h, cy - h], [cx + h, cy + h], [cx - h, cy + h]]
    box = {"kind": "chair", "x0": cx - h, "y0": cy - h, "x1": cx + h, "y1": cy + h, "corners": corners, "h_in": 30.0, "z0_in": 0.0,
           "rgb": [1, 2, 3], "label": "cadeira-teste", "ambiguous": False, "decorative": False, "room": "SUITE 02",
           "module": "Cadeira-teste", "geometry_intent": "FURNITURE",
           "interaction_policy": {"circulation": "BLOCKING", "furniture_overlap": "EXCLUSIVE"}, "host": {"relationship": "NONE"}}
    box.update(over)
    return box


def _keys(real, extra):
    return set(gates.run(real["con"], real["boxes"] + extra)["findings"])


@pytest.mark.planta74_scale
def test_real_baseline_has_no_wall_or_door_finding_and_only_the_known_circulation_one(real):
    keys = _keys(real, [])
    assert not [k for k in keys if k.startswith(("WALL|", "DOOR|", "GATE_ERROR|"))], keys
    assert keys == KNOWN_PREEXISTING


@pytest.mark.planta74_scale
def test_furniture_inside_a_wall_is_a_wall_finding_and_fails_the_regression(real):
    chair = _square(real["walls"].representative_point(), real["to_in"])
    before, after = gates.run(real["con"], real["boxes"]), gates.run(real["con"], real["boxes"] + [chair])
    d = gates.delta(before, after)
    assert d["state"] == "FAIL" and any(x["key"].startswith("WALL|SUITE 02|Cadeira-teste") for x in d["introduced"])
    assert {x["key"] for x in d["preexisting"]} == KNOWN_PREEXISTING            # a preexistente continua separada da nova


@pytest.mark.planta74_scale
def test_chair_in_a_door_swing_is_a_door_finding(real):
    door_id, swing = sorted(real["swings"].items())[0]
    chair = _square(swing.representative_point(), real["to_in"])
    found = [k for k in _keys(real, [chair]) if k.startswith("DOOR|")]
    assert any(door_id in k and "Cadeira-teste" in k for k in found), found


@pytest.mark.planta74_scale
def test_decorative_in_the_swing_blocks_but_decorative_in_the_wall_is_not_a_wall_finding(real):
    _, swing = sorted(real["swings"].items())[0]
    deco_swing = _square(swing.representative_point(), real["to_in"], geometry_intent="DECORATIVE")
    assert any(k.startswith("DOOR|") and "Cadeira-teste" in k for k in _keys(real, [deco_swing]))
    deco_wall = _square(real["walls"].representative_point(), real["to_in"], geometry_intent="DECORATIVE")
    assert not any("Cadeira-teste" in k and k.startswith("WALL|") for k in _keys(real, [deco_wall]))


@pytest.mark.planta74_scale
def test_hosted_structural_and_walkable_pieces_use_the_existing_exceptions_without_disabling_the_gate(real):
    wall_pt, swing_pt = real["walls"].representative_point(), sorted(real["swings"].items())[0][1].representative_point()
    hosted = _square(wall_pt, real["to_in"], host={"relationship": "WALL"}, interaction_policy={"circulation": "BLOCKING", "furniture_overlap": "ALLOW"})
    structural = _square(wall_pt, real["to_in"], geometry_intent="STRUCTURAL")
    walkable = _square(swing_pt, real["to_in"], h_in=0.5, interaction_policy={"circulation": "WALKABLE", "furniture_overlap": "ALLOW"})
    for piece in (hosted, structural, walkable):
        assert not any("Cadeira-teste" in k for k in _keys(real, [piece])), piece["geometry_intent"]
    assert any("Cadeira-teste" in k for k in _keys(real, [_square(wall_pt, real["to_in"])]))     # o gate continua ligado


@pytest.mark.planta74_scale
def test_gate_run_does_not_mutate_the_boxes(real):
    before = copy.deepcopy(real["boxes"])
    gates.run(real["con"], real["boxes"])
    assert real["boxes"] == before


@pytest.mark.planta74_scale
def test_end_to_end_strict_identity_on_real_snapshot_passes_with_the_known_finding_listed(real):
    snap = rd.capture()
    g = gates.run(real["con"], [p["box"] for p in snap["parts"]])
    contract = {**_contract(), "fixture": "planta_74", "control_rooms": ["r004"]}
    report = rd.compare(snap, snap, contract, canonical_before=snap["source_digests"], canonical_after=snap["source_digests"],
                        gates_before=g, gates_after=g)
    assert report["state"] == "PASS" and set(report["evidence"]["preexisting_gate_findings"]) == KNOWN_PREEXISTING
    assert rr.validate_report(report) == []
