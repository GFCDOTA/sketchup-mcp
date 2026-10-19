"""FP-043/P6a — adapter da cozinha: o gabinete so entra depois de ancora hidraulica, arquitetura, mobilia e circulacao.

Roda na escala da planta_74 (PT_TO_M=0.0259, processo proprio: marcador `planta74_scale`). L1: so planeja; consensus e
fixtures canonicos sao lidos e nunca alterados.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.planta74_scale

ROOT = Path(__file__).resolve().parents[1]
CON_PATH = ROOT / "fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json"
CAB = json.loads((ROOT / "fixtures/synthetic_cabinets/valid_a_base_600.json").read_text("utf-8"))
FREE_SPOT = (2.22, 15.88)       # ponto livre da cozinha da planta_74 (medido com o brain atual); nao e decisao de design


def _req(x=FREE_SPOT[0], y=FREE_SPOT[1], rot=0):
    r = copy.deepcopy(CAB)
    r["pose"]["x"]["value"], r["pose"]["y"]["value"], r["pose"]["rotation_deg"]["value"] = x, y, rot
    return r


def _con():
    return json.loads(CON_PATH.read_text("utf-8"))


def _plan(req, con=None):
    from tools.rooms.kitchen.capabilities.cabinet import plan_kitchen_cabinet
    return plan_kitchen_cabinet(con if con is not None else _con(), "r004", req)


def _gates(plan):
    return [(g["gate"], g["result"]) for g in plan["gates"]]


def test_ponto_livre_passa_os_quatro_gates_na_ordem():
    plan = _plan(_req())
    assert plan["status"] == "OK" and plan["execution_authorized"] is False
    assert _gates(plan) == [("hydraulic_anchor", "PASS"), ("architecture", "PASS"), ("furniture_overlap", "PASS"), ("circulation", "PASS")]
    from tools.rooms.shared.cabinet import require_valid
    require_valid(plan)


def test_gate_que_falha_para_os_seguintes_e_a_pose_nao_e_aceita():
    from tools.rooms.shared.cabinet import PlanRefused, require_valid
    plan = _plan(_req(0.5, 0.5))                                             # fora da cozinha
    assert plan["status"] == "REFUSED" and plan["stage"] == "kitchen_gate:architecture"
    assert _gates(plan) == [("hydraulic_anchor", "PASS"), ("architecture", "FAIL")]
    with pytest.raises(PlanRefused):
        require_valid(plan)


def test_sobreposicao_com_mobilia_planejada_da_cozinha_e_recusada():
    plan = _plan(_req(1.5, 15.2))
    assert plan["status"] == "REFUSED" and plan["stage"] == "kitchen_gate:furniture_overlap"
    assert _gates(plan)[-1] == ("furniture_overlap", "FAIL")


def test_invadir_zona_de_porta_e_recusado():
    from core.scale import PT_TO_M
    from tools.rooms.shared.spatial_model import build_spatial_model
    sm = build_spatial_model(_con(), "r004")
    circ = sm["_geom"]["circ"]
    assert circ, "a cozinha da planta_74 tem portal: o teste precisa de uma zona de porta"
    c = circ[0].centroid
    plan = _plan(_req(c.x * PT_TO_M - 0.3, c.y * PT_TO_M - 0.28))
    assert plan["status"] == "REFUSED" and plan["stage"] in ("kitchen_gate:circulation", "kitchen_gate:furniture_overlap",
                                                           "kitchen_gate:architecture"), plan["stage"]
    assert any(g["result"] == "FAIL" for g in plan["gates"])


def test_ancora_hidraulica_comprometida_recusa_antes_de_qualquer_outro_gate(monkeypatch):
    from tools.rooms.kitchen import anchor_rules
    monkeypatch.setattr(anchor_rules, "validate", lambda con, room_id="r004": {"result": "FAIL", "checks": {}, "lines": []})
    plan = _plan(_req())
    assert plan["status"] == "REFUSED" and plan["stage"] == "kitchen_gate:hydraulic_anchor"
    assert _gates(plan) == [("hydraulic_anchor", "FAIL")]                    # arquitetura/mobilia/circulacao nem rodaram


def test_circulation_gate_do_projeto_reprovando_recusa(monkeypatch):
    from tools.validation import circulation_gate
    monkeypatch.setattr(circulation_gate, "gate", lambda con, boxes, room_id: {"result": "FAIL", "checks": {}})
    plan = _plan(_req())
    assert plan["status"] == "REFUSED" and _gates(plan)[-1] == ("circulation", "FAIL")


def test_recusa_do_compartilhado_nao_chama_os_gates_da_cozinha(monkeypatch):
    from tools.rooms.kitchen import anchor_rules

    def boom(*a, **k):
        raise AssertionError("anchor nao deveria rodar")
    monkeypatch.setattr(anchor_rules, "validate", boom)
    bad = copy.deepcopy(CAB)
    bad["dimensions"]["width"]["value"] = 10
    plan = _plan(bad)
    assert plan["status"] == "REFUSED" and plan["gates"] == []


def test_entrada_incompleta_e_recusada_sem_tocar_a_cozinha():
    bad = copy.deepcopy(CAB)
    del bad["pose"]["x"]["unit"]
    plan = _plan(bad)
    assert plan["status"] == "REFUSED" and plan["stage"] == "input" and plan["gates"] == []


def test_consensus_e_fixture_canonico_nao_sao_alterados():
    before_file = hashlib.sha256(CON_PATH.read_bytes()).hexdigest()
    con = _con()
    snapshot = copy.deepcopy(con)
    _plan(_req(), con)
    _plan(_req(1.5, 15.2), con)
    assert con == snapshot                                                   # nenhuma mutacao em memoria
    assert hashlib.sha256(CON_PATH.read_bytes()).hexdigest() == before_file  # nem em disco


def test_escala_errada_falha_alto_em_vez_de_gerar_area_errada(monkeypatch):
    from core import scale
    monkeypatch.setattr(scale, "PT_TO_M", 0.19 / 5.4)
    monkeypatch.setattr(scale, "assert_pt_to_m_for_source", lambda src: (_ for _ in ()).throw(RuntimeError("escala")))
    with pytest.raises(RuntimeError):
        _plan(_req())


def test_pose_com_rotacao_nao_ortogonal_usa_a_pegada_real_e_nao_o_aabb():
    plan = _plan(_req(2.5, 17.0, 30))
    assert plan["status"] in ("OK", "REFUSED") and plan["gates"]
    from tools.rooms.shared.cabinet import footprint_world
    xs, ys = zip(*footprint_world(plan))
    aabb = (max(xs) - min(xs)) * (max(ys) - min(ys))
    W, D, _ = plan["envelope_m"]
    assert aabb > W * D * 1.1                                                # o AABB de 30 graus e bem maior que a pegada real
