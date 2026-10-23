"""FP-054 F1-01 (#380): o gate de circulacao nao aprova o que nao mediu.

Contraprova da F0 (`docs/reports/fp054/f0/gate_probes.json` P1/P2): comodo sem portal, ou com 1 portal e partido ao meio por
movel, saia PASS. Agora: sem portal (ou portal sem ponto interno) = BLOCKED_MISSING_INPUT; portal unico = NOT_APPLICABLE
explicito; o resultado do gate so e PASS se alguma regra mediu e nenhuma falhou/ficou bloqueada."""
from __future__ import annotations

import json
import random

import pytest
from shapely.geometry import Polygon

from core.constraint_result import ConstraintResult, combine
from tools.navigation.baseline_probes import synthetic_room
from tools.validation import circulation_gate as cg


def _strip(con, x_frac=0.5, half_in=10.0):
    """Estante de parede a parede no meio do comodo (parte o comodo em dois)."""
    from core.scale import PT_TO_IN
    (ax, ay), (bx, by) = con["rooms"][0]["polygon_pts"][0], con["rooms"][0]["polygon_pts"][2]
    x0, y0, x1, y1 = ax * PT_TO_IN, ay * PT_TO_IN, bx * PT_TO_IN, by * PT_TO_IN
    cx = x0 + (x1 - x0) * x_frac
    return [{"module": "Estante", "kind": "body", "z0_in": 0.0, "h_in": 80.0,
             "corners": [[cx - half_in, y0 - 5], [cx + half_in, y0 - 5], [cx + half_in, y1 + 5], [cx - half_in, y1 + 5]]}]


# ------------------------------------------------------------------------------------------------ contrato
def test_measured_status_requires_measure_threshold_and_units():
    with pytest.raises(ValueError):
        ConstraintResult("r", "PASS", "OK")
    with pytest.raises(ValueError):
        ConstraintResult("r", "FAIL", "X", measured=0.5, threshold=0.9)          # sem unidade


def test_unmeasured_status_requires_a_why():
    with pytest.raises(ValueError):
        ConstraintResult("r", "BLOCKED_MISSING_INPUT", "NO_PORTAL")
    with pytest.raises(ValueError):
        ConstraintResult("r", "NOT_APPLICABLE", "")
    ok = ConstraintResult("r", "NOT_APPLICABLE", "SINGLE_PORTAL", evidence={"why": "1 portal"})
    assert ok.to_dict()["status"] == "NOT_APPLICABLE"


def test_unknown_status_is_refused():
    with pytest.raises(ValueError):
        ConstraintResult("r", "OK", "X", evidence={"why": "x"})
    with pytest.raises(ValueError):
        combine(["PASS", "MAYBE"])


@pytest.mark.parametrize("statuses,expected", [
    ([], "NOT_APPLICABLE"),
    (["NOT_APPLICABLE", "NOT_APPLICABLE"], "NOT_APPLICABLE"),
    (["PASS", "NOT_APPLICABLE"], "PASS"),
    (["WARN"], "PASS"),
    (["PASS", "BLOCKED_MISSING_INPUT"], "BLOCKED_MISSING_INPUT"),
    (["BLOCKED_MISSING_INPUT", "FAIL", "PASS"], "FAIL"),
])
def test_combine_precedence(statuses, expected):
    assert combine(statuses) == expected


# --------------------------------------------------------------------------------- gate: contraprovas da F0
def test_zero_portals_blocks_instead_of_passing():
    con = synthetic_room(4.0, doors=())
    res = cg.gate(con, _strip(con), "r_syn")
    corr = res["checks"]["corredor_principal"]
    assert corr["result"] == "BLOCKED_MISSING_INPUT"
    assert corr["reason_code"] == "NO_PORTAL"
    assert res["result"] == "BLOCKED_MISSING_INPUT"


def test_single_portal_is_not_applicable_never_pass():
    con = synthetic_room(4.0, doors=("w_left",))
    res = cg.gate(con, _strip(con), "r_syn")
    corr = res["checks"]["corredor_principal"]
    assert corr["result"] == "NOT_APPLICABLE"
    assert corr["reason_code"] == "SINGLE_PORTAL"
    assert res["result"] == "NOT_APPLICABLE"          # nada medido: nem PASS nem FAIL


def test_portal_without_inner_point_blocks(monkeypatch):
    """Portal que existe na planta mas nao cai dentro do comodo nao pode sumir em silencio (era descartado)."""
    con = synthetic_room(4.0)
    real = cg._portal_points

    def drop_one(sm, cell_in):
        pts, dropped = real(sm, cell_in)
        return pts[:1], dropped + [{"zone": 1, "why": "forcado pelo teste"}]
    monkeypatch.setattr(cg, "_portal_points", drop_one)
    res = cg.gate(con, [], "r_syn")
    assert res["checks"]["corredor_principal"]["result"] == "BLOCKED_MISSING_INPUT"
    assert res["checks"]["corredor_principal"]["reason_code"] == "PORTAL_WITHOUT_INNER_POINT"
    assert res["result"] == "BLOCKED_MISSING_INPUT"


def test_portal_points_reports_zone_whose_inner_step_leaves_the_room():
    """O portal e projetado na borda e empurrado 0,25 m para dentro; num comodo mais estreito que isso o ponto sai do outro
    lado — antes sumia sem aviso, agora volta como descartado."""
    from core.scale import PT_TO_IN
    cell = Polygon([(0, 0), (100, 0), (100, 5), (0, 5)])                 # 5 in de largura < passo de 0,25 m (~9,8 in)
    zone_in = Polygon([(40, -12), (60, -12), (60, -2), (40, -2)])          # zona da porta logo abaixo da parede sul
    zone_pt = Polygon([(x / PT_TO_IN, y / PT_TO_IN) for x, y in zone_in.exterior.coords])   # o modelo guarda em pt
    pts, dropped = cg._portal_points({"_geom": {"circ": [zone_pt]}}, cell)
    assert pts == [] and len(dropped) == 1 and dropped[0]["zone"] == 0


def test_two_portals_connected_pass_and_split_fails():
    con = synthetic_room(4.0)
    ok = cg.gate(con, [], "r_syn")
    assert ok["result"] == "PASS"
    assert ok["checks"]["corredor_principal"]["result"] == "PASS"
    bad = cg.gate(con, _strip(con), "r_syn")
    assert bad["result"] == "FAIL"


def test_room_without_dining_set_marks_chair_checks_not_applicable():
    res = cg.gate(synthetic_room(4.0), [], "r_syn")
    assert res["checks"]["atras_das_cadeiras"]["result"] == "NOT_APPLICABLE"
    assert res["checks"]["cadeira_puxada"]["result"] == "NOT_APPLICABLE"


def test_every_check_carries_a_typed_constraint():
    res = cg.gate(synthetic_room(4.0, doors=("w_left",)), [], "r_syn")
    rows = res["constraints"]
    assert {r["rule_id"] for r in rows} >= {"circulation.corridor", "circulation.behind_chairs", "circulation.chair_pull"}
    for r in rows:                                    # o construtor ja valida; aqui so garante que veio serializado
        ConstraintResult(**r)


# ----------------------------------------------------------------------------------------------- metamorficos
def test_box_order_does_not_change_the_verdict():
    con = synthetic_room(4.0)
    rng = random.Random(11)
    boxes = _strip(con, 0.3, 4.0) + _strip(con, 0.7, 4.0)
    for b in boxes:                                   # estreita as faixas para deixar passagem em cima/embaixo
        b["corners"][2][1] -= 60
        b["corners"][3][1] -= 60
    ref = json.dumps(cg.gate(con, boxes, "r_syn"), sort_keys=True)
    for _ in range(3):
        shuffled = boxes[:]
        rng.shuffle(shuffled)
        assert json.dumps(cg.gate(con, shuffled, "r_syn"), sort_keys=True) == ref


def test_adding_a_blocker_never_turns_fail_into_pass():
    con = synthetic_room(4.0)
    base = _strip(con)
    assert cg.gate(con, base, "r_syn")["result"] == "FAIL"
    extra = _strip(con, 0.25, 6.0)
    assert cg.gate(con, base + extra, "r_syn")["result"] == "FAIL"


@pytest.mark.planta74_scale
def test_planta74_single_portal_rooms_are_not_applicable_and_others_keep_their_verdict():
    import contextlib
    import io

    from tools.furnish_apartment import CONSENSUS, collect_boxes
    con = json.loads(CONSENSUS.read_text("utf-8"))
    with contextlib.redirect_stdout(io.StringIO()):
        boxes, _ = collect_boxes(con)
    got = {rid: cg.gate(con, boxes, rid)["result"] for rid in ("r000", "r001", "r002", "r003", "r004", "r005", "r006", "r007")}
    assert got == {"r000": "PASS",                     # #381: Suite 01 corrigida pela decisao do Felipe (layout_decisions)
                   "r001": "PASS", "r002": "PASS", "r003": "PASS",
                   "r004": "NOT_APPLICABLE", "r005": "NOT_APPLICABLE", "r006": "NOT_APPLICABLE", "r007": "NOT_APPLICABLE"}


# ------------------------------------------------------------------- consumidores: plano do gabinete da cozinha
def _kitchen_plan():
    from pathlib import Path

    from tools.furnish_apartment import CONSENSUS
    from tools.rooms.kitchen.capabilities.cabinet import plan_kitchen_cabinet
    from tools.rooms.kitchen.capabilities.cabinet_flow import inputs_to_cabinet_request
    req = json.loads(Path("artifacts/review/fp043/p7_kitchen_cabinet/request.json").read_text("utf-8"))
    con = json.loads(CONSENSUS.read_text("utf-8"))
    return plan_kitchen_cabinet(con, "r004", inputs_to_cabinet_request("f1-01", req["inputs"], req["materials"], req.get("grain")))


@pytest.mark.planta74_scale
def test_kitchen_cabinet_plan_records_circulation_as_not_applicable_not_pass():
    plan = _kitchen_plan()
    assert plan["status"] == "OK"
    circ = next(g for g in plan["gates"] if g["gate"] == "circulation")
    assert "circulation_gate NOT_APPLICABLE" in circ["detail"] and "SINGLE_PORTAL" in circ["detail"]
    assert "circulation_gate PASS" not in circ["detail"]


@pytest.mark.planta74_scale
def test_kitchen_cabinet_plan_refuses_when_circulation_is_blocked(monkeypatch):
    real = cg._portal_points
    monkeypatch.setattr(cg, "_portal_points", lambda sm, cell: (real(sm, cell)[0], [{"zone": 0, "why": "teste"}]))
    plan = _kitchen_plan()
    assert plan["status"] == "REFUSED" and plan["stage"] == "kitchen_gate:circulation"
    assert "BLOCKED_MISSING_INPUT" in plan["gates"][-1]["detail"]
