"""FP-054 F1B: folga funcional e alcance por peca (REPORT_ONLY). Cenas sinteticas deterministicas + registro + planta real."""
from __future__ import annotations

import copy
import json
import random

import pytest

from core.functional_constraints import (
    FUNCTIONAL_CONSTRAINTS,
    FunctionalConstraint,
    FunctionalEvaluation,
    Threshold,
    registry_errors,
)
from core.scale import PT_TO_IN
from tests.test_fp054_f1_circulation_properties import _transform_scene
from tools.navigation.baseline_probes import synthetic_room
from tools.validation import functional_clearance as fc

M = 39.3700787402


# ------------------------------------------------------------------------------------------------- contratos
LAV = FUNCTIONAL_CONSTRAINTS["lavatory.front_clearance"]          # 0,55 / 0,60 / 0,80


@pytest.mark.parametrize("measured,verdict", [
    (0.50, "INVALID"),                 # abaixo do minimo
    (0.55, "VALID_BELOW_TARGET"),      # exatamente no minimo
    (0.58, "VALID_BELOW_TARGET"),      # entre minimo e alvo
    (0.60, "VALID"),                   # exatamente no alvo
    (0.79, "VALID"),
    (0.80, "PREFERRED"),               # preferido
])
def test_three_levels_are_classified_separately(measured, verdict):
    assert LAV.classify(measured) == verdict


def test_registry_is_consistent_and_never_claims_normative():
    assert registry_errors() == []
    for c in FUNCTIONAL_CONSTRAINTS.values():
        for lvl in (c.reference_minimum, c.project_target, c.preferred):
            assert lvl.provenance != "NORMATIVE" and lvl.source
        assert c.project_target.provenance == "PROJECT_POLICY"


def test_threshold_rejects_bad_unit_provenance_and_order():
    with pytest.raises(ValueError):
        Threshold(0.6, "cm", "COMFORT_GUIDE", "x")
    with pytest.raises(ValueError):
        Threshold(0.6, "m", "FOLK_WISDOM", "x")
    with pytest.raises(ValueError):
        Threshold(0.6, "m", "COMFORT_GUIDE", "")
    t = Threshold(0.6, "m", "COMFORT_GUIDE", "x")
    with pytest.raises(ValueError):
        FunctionalConstraint("x", "toilet", "front_depth", t, Threshold(0.5, "m", "PROJECT_POLICY", "x"), t)


def test_evaluation_requires_measure_or_missing_input():
    with pytest.raises(ValueError):
        FunctionalEvaluation("r", "o", "toilet", "c", "VALID", "X")
    with pytest.raises(ValueError):
        FunctionalEvaluation("r", "o", "toilet", "c", "BLOCKED_MISSING_INPUT", "X")


# ---------------------------------------------------------------------------------------- cenas sinteticas
def _room(doors=("w_left",), side=2.5):
    con = synthetic_room(side, doors=doors)
    (ax, ay), (bx, by) = con["rooms"][0]["polygon_pts"][0], con["rooms"][0]["polygon_pts"][2]
    return con, (ax * PT_TO_IN, ay * PT_TO_IN, bx * PT_TO_IN, by * PT_TO_IN)


def _rect(module, kind, x0, y0, x1, y1, h=16.0):
    return {"module": module, "kind": kind, "z0_in": 0.0, "h_in": h,
            "corners": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]}


def _toilet_on_east_wall(b):
    x0, y0, x1, y1 = b
    cy = (y0 + y1) / 2
    return _rect("Vaso", "vaso", x1 - 0.65 * M, cy - 0.18 * M, x1, cy + 0.18 * M)


def _eval(con, boxes):
    rows = [e.to_dict() for e in fc.evaluate_room(con, boxes, "r_syn", "BATHROOM", "SINTETICO")]
    return {r["constraint"]: r for r in rows}


def test_single_portal_room_is_evaluated_not_not_applicable():
    con, b = _room(doors=("w_left",))
    r = _eval(con, [_toilet_on_east_wall(b)])
    assert r["toilet.reach_path"]["verdict"] in ("VALID", "PREFERRED")
    assert r["toilet.front_clearance"]["verdict"] == "PREFERRED"        # sala vazia de 2,5 m: muito espaco na frente


def test_missing_portal_blocks_reach_but_still_measures_the_front():
    con, b = _room(doors=())
    r = _eval(con, [_toilet_on_east_wall(b)])
    assert r["toilet.reach_path"]["verdict"] == "BLOCKED_MISSING_INPUT"
    assert r["toilet.reach_path"]["missing_input"] == ["portal"]
    assert r["toilet.front_clearance"]["verdict"] == "PREFERRED"


def test_unresolvable_use_face_blocks_instead_of_guessing():
    con, b = _room()
    x0, y0, x1, y1 = b
    mid = ((x0 + x1) / 2, (y0 + y1) / 2)
    floating = _rect("Vaso", "vaso", mid[0], mid[1], mid[0] + 0.65 * M, mid[1] + 0.36 * M)   # solta: nenhuma parede
    r = {k: v for k, v in _eval(con, [floating]).items() if k.startswith("toilet.")}
    assert len(r) == 2 and {v["verdict"] for v in r.values()} == {"BLOCKED_MISSING_INPUT"}
    assert all(v["missing_input"] == ["use_face"] for v in r.values())


def test_absent_object_is_not_applicable():
    con, b = _room()
    r = _eval(con, [_toilet_on_east_wall(b)])
    assert r["shower.reach_path"]["verdict"] == "NOT_APPLICABLE"
    assert r["shower.reach_path"]["reason_code"] == "OBJECT_ABSENT"


def test_front_obstacle_measures_the_gap():
    con, b = _room()
    x0, y0, x1, y1 = b
    t = _toilet_on_east_wall(b)
    face_x = x1 - 0.65 * M
    cab = _rect("Armario", "body", face_x - 0.50 * M - 10, y0, face_x - 0.50 * M, y1, h=80)   # parede de armario a 0,50 m
    r = _eval(con, [t, cab])
    assert r["toilet.front_clearance"]["verdict"] == "INVALID"
    assert abs(r["toilet.front_clearance"]["measured"] - 0.487) < 0.02          # 0,50 m - folga de 0,5 in do bloqueio


def test_disconnected_path_is_invalid_with_zero_width():
    con, b = _room()
    x0, y0, x1, y1 = b
    wall = _rect("Estante", "body", (x0 + x1) / 2 - 5, y0 - 5, (x0 + x1) / 2 + 5, y1 + 5, h=80)  # parte o comodo
    r = _eval(con, [_toilet_on_east_wall(b), wall])
    assert r["toilet.reach_path"]["verdict"] == "INVALID"
    assert r["toilet.reach_path"]["measured"] == 0.0 and r["toilet.reach_path"]["reason_code"] == "PATH_DISCONNECTED"


def test_bottleneck_sets_the_reach_width():
    con, b = _room()
    toilet = _toilet_on_east_wall(b)
    cell = fc._room_context(con, [toilet], "r_syn")[0]               # a celula do modelo espacial (nao o poligono do comodo)
    cx0, cy0, cx1, cy1 = cell.bounds
    xm = (cx0 + cx1) / 2
    gap = 0.50 * M                                                   # passagem de 0,50 m junto a parede sul da celula
    wall = _rect("Estante", "body", xm - 5, cy0 + gap, xm + 5, cy1 + 5, h=80)
    r = _eval(con, [toilet, wall])
    w = r["toilet.reach_path"]["measured"]
    assert abs(w - (0.50 - 0.5 / M)) <= 0.011 and r["toilet.reach_path"]["verdict"] == "INVALID"   # 0,50 - folga 0,5 in


def _scene():
    con, b = _room()
    x0, y0, x1, y1 = b
    xm = (x0 + x1) / 2
    return con, [_toilet_on_east_wall(b), _rect("Estante", "body", xm - 5, y0 - 5 + 0.70 * M, xm + 5, y1 + 5, h=80)]


def _verdicts(con, boxes):
    return {k: (v["verdict"], v["measured"]) for k, v in _eval(con, boxes).items()}


def test_translation_invariance():
    con, boxes = _scene()
    base = _verdicts(con, boxes)
    con2, boxes2 = _transform_scene(con, boxes, lambda x, y: (x + 137.0, y - 61.0),
                                    lambda x, y: (x + 137.0 * PT_TO_IN, y - 61.0 * PT_TO_IN), swap=False)
    moved = _verdicts(con2, boxes2)
    for k, (v, m) in base.items():
        assert moved[k][0] == v and (m is None or abs(moved[k][1] - m) <= 0.011), k


def test_quarter_turn_invariance():
    con, boxes = _scene()
    base = _verdicts(con, boxes)
    (ax, ay), (bx, by) = con["rooms"][0]["polygon_pts"][0], con["rooms"][0]["polygon_pts"][2]
    cx, cy = (ax + bx) / 2, (ay + by) / 2
    con2, boxes2 = _transform_scene(con, boxes, lambda x, y: (cx - (y - cy), cy + (x - cx)),
                                    lambda x, y: (cx * PT_TO_IN - (y - cy * PT_TO_IN), cy * PT_TO_IN + (x - cx * PT_TO_IN)),
                                    swap=True)
    turned = _verdicts(con2, boxes2)
    for k, (v, m) in base.items():
        assert turned[k][0] == v and (m is None or abs(turned[k][1] - m) <= 0.011), k


def test_object_order_invariance_and_determinism():
    con, boxes = _scene()
    ref = json.dumps(_eval(con, boxes), sort_keys=True)
    rnd = random.Random(7)
    for _ in range(3):
        b2 = copy.deepcopy(boxes)
        rnd.shuffle(b2)
        assert json.dumps(_eval(con, b2), sort_keys=True) == ref


def test_adding_an_obstacle_never_improves_reach_or_front():
    con, boxes = _scene()
    before = _verdicts(con, boxes)
    x0, y0, x1, y1 = _room()[1]
    extra = _rect("Cesto", "body", x0 + 0.2 * M, y0 + 0.2 * M, x0 + 0.5 * M, y0 + 0.4 * M, h=30)
    after = _verdicts(con, boxes + [extra])
    for k in before:
        if before[k][1] is not None:
            assert after[k][1] <= before[k][1] + 1e-9, k


# ------------------------------------------------------------------------------------------------ planta real
@pytest.mark.planta74_scale
def test_planta74_dry_run_is_complete_deterministic_and_report_only():
    import contextlib
    import io

    from tools.furnish_apartment import CONSENSUS, collect_boxes
    con = json.loads(CONSENSUS.read_text("utf-8"))
    with contextlib.redirect_stdout(io.StringIO()):
        boxes, _ = collect_boxes(con)
    snapshot = json.dumps(boxes, sort_keys=True)
    a, b = fc.evaluate(con, boxes), fc.evaluate(con, copy.deepcopy(boxes))
    assert a == b and a["mode"] == "REPORT_ONLY" and a["registry_errors"] == []
    assert json.dumps(boxes, sort_keys=True) == snapshot                       # avaliar nao muda nenhuma caixa
    assert a["evaluations"] == 20 and sum(a["summary"].values()) == 20
    assert a["summary"]["BLOCKED_MISSING_INPUT"] == 0                          # toda peca registrada resolveu a face
    rows = {(r["room_id"], r["constraint"]): r for r in a["rows"]}
    assert rows[("r004", "kitchen_counter.reach_path")]["verdict"] in ("VALID", "PREFERRED")
