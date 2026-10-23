"""FP-054 F2B: motor de restricoes rigidas com culpado e reproducao dos defeitos conhecidos (sinteticos + planta real)."""
from __future__ import annotations

import contextlib
import io
import json

import pytest

from core.functional_constraints import FunctionalInterface
from tests.test_fp054_f1b_functional_clearance import M, _rect, _room
from tools.rooms.shared.spatial_solver.engine import evaluate_layout


def _ev(con, boxes, ifaces, rtype="BATHROOM"):
    return evaluate_layout(con, boxes, "r_syn", rtype, {(i.room_id, i.module): i for i in ifaces})


def _codes(ev):
    return {(v.code, v.object_id.split(":")[1], v.culprit) for v in ev.hard_violations}


def _toilet(b, at_y=None):
    x0, y0, x1, y1 = b
    cy = at_y if at_y is not None else (y0 + y1) / 2
    fx = x1 - 0.65 * M
    box = _rect("Vaso", "vaso", fx, cy - 0.18 * M, x1, cy + 0.18 * M)
    iface = FunctionalInterface("r_syn", "Vaso", "toilet", "use_face", ((fx, cy - 0.18 * M), (fx, cy + 0.18 * M)), (-1.0, 0.0),
                                "SEMANTIC_DECLARED", "teste")
    return box, iface, fx


def _box(b, entry, front_side="north"):
    """Box 0,9 x 0,9 no canto sudoeste; entrada declarada (trecho em m ao longo da frente) no lado `front_side`."""
    x0, y0, _x1, _y1 = b
    box = _rect("Box", "box_vidro", x0, y0, x0 + 0.9 * M, y0 + 0.9 * M, h=80)
    if front_side == "north":
        seg, n = ((x0 + entry[0] * M, y0 + 0.9 * M), (x0 + entry[1] * M, y0 + 0.9 * M)), (0.0, 1.0)
    else:                                                    # "west": frente encostada na parede oeste
        seg, n = ((x0, y0 + entry[0] * M), (x0, y0 + entry[1] * M)), (-1.0, 0.0)
    return box, FunctionalInterface("r_syn", "Box", "shower", "shower_entry", seg, n, "SEMANTIC_DECLARED", "teste")


def test_clear_room_is_feasible():
    con, b = _room()
    box, iface, _ = _toilet(b)
    ev = _ev(con, [box], [iface])
    assert ev.feasible, [v.to_dict() for v in ev.hard_violations]


def test_shower_door_against_the_wall_is_infeasible_with_wall_as_culprit():
    con, b = _room()
    box, iface = _box(b, (0.2, 0.8), front_side="west")
    ev = _ev(con, [box], [iface])
    # a celula sintetica comeca ~3 in antes do poligono do comodo: a frente fica a 3 in da parede (vao livre, sem uso)
    assert ("FUNCTIONAL_SHOWER_ENTRY_FRONT_CLEARANCE", "Box", "WALL") in _codes(ev)
    assert ("FUNCTIONAL_SHOWER_REACH_PATH", "Box", "PATH_DISCONNECTED") in _codes(ev)
    assert not ev.feasible


def test_insufficient_entry_width_is_hard_even_with_ample_front_space():
    con, b = _room()
    box, iface = _box(b, (0.45, 0.90))                     # vao de 0,45 m; frente livre ate o fundo do comodo
    ev = _ev(con, [box], [iface])
    rows = {r["constraint"]: r for r in ev.rows}
    assert rows["shower.entry_front_clearance"]["verdict"] == "PREFERRED"       # profundidade sobra...
    assert ("FUNCTIONAL_SHOWER_ENTRY_WIDTH", "Box", "DECLARED_ENTRY") in _codes(ev)   # ...mas nao compensa o vao
    assert not ev.feasible


def test_blocked_room_portal_breaks_circulation_and_reach():
    con, b = _room(doors=("w_left", "w_right"))                 # 2 portais: o corredor entre eles e medido
    x0, y0, x1, y1 = b
    box, iface, _ = _toilet(b)
    xm = (x0 + x1) / 2
    wall = _rect("Estante", "body", xm - 5, y0 - 5, xm + 5, y1 + 5, h=80)
    ev = _ev(con, [box, wall], [iface])
    assert ("ROOM_CIRCULATION_FAIL", "*", "LAYOUT") in _codes(ev)            # as duas portas nao se ligam mais
    assert ("DOOR_SWING_OBSTRUCTED", "Vaso", "d_w_right") in _codes(ev)        # e o vaso ficou no giro da porta leste


def test_piece_with_space_in_front_but_no_way_in_is_infeasible():
    con, b = _room()
    _x0, y0, x1, y1 = b
    box, iface, fx = _toilet(b)
    cy = (y0 + y1) / 2
    gx = fx - 0.80 * M                                       # cercado: 0,80 m livres na frente, sem abertura
    cage = [_rect("Armario A", "body", gx, cy - 0.40 * M, x1, cy - 0.36 * M, h=80),
            _rect("Armario B", "body", gx, cy + 0.36 * M, x1, cy + 0.40 * M, h=80),
            _rect("Armario C", "body", gx - 4, cy - 0.40 * M, gx, cy + 0.40 * M, h=80)]
    ev = _ev(con, [box, *cage], [iface])
    rows = {r["constraint"]: r for r in ev.rows}
    assert rows["toilet.front_clearance"]["verdict"] in ("VALID", "PREFERRED")
    assert ("FUNCTIONAL_TOILET_REACH_PATH", "Vaso", "PATH_DISCONNECTED") in _codes(ev)


def test_two_pieces_without_collision_but_facing_usage_zones_blame_each_other():
    con, b = _room()
    x0, y0, x1, y1 = b
    box, iface, fx = _toilet(b)
    cy = (y0 + y1) / 2
    lx = fx - 0.30 * M                                       # lavatorio de costas para a parede oposta, a 0,30 m do vaso
    lav = _rect("Bancada", "bancada_banho", lx - 0.45 * M, cy - 0.30 * M, lx, cy + 0.30 * M, h=34)
    lav_if = FunctionalInterface("r_syn", "Bancada", "lavatory", "use_face", ((lx, cy - 0.30 * M), (lx, cy + 0.30 * M)),
                                 (1.0, 0.0), "SEMANTIC_DECLARED", "teste")
    ev = _ev(con, [box, lav], [iface, lav_if])
    codes = _codes(ev)
    assert ("FUNCTIONAL_TOILET_FRONT_CLEARANCE", "Vaso", "Bancada") in codes
    assert ("FUNCTIONAL_LAVATORY_FRONT_CLEARANCE", "Bancada", "Vaso") in codes
    assert not [v for v in ev.hard_violations if v.code == "COLLISION"]          # nao colidem: e a zona de uso que falha


def test_kitchen_entrance_bottleneck_is_located():
    con, b = _room(side=3.0)
    x0, y0, x1, y1 = b
    counter = _rect("countertop", "kc_tampo", x1 - 0.60 * M, y0, x1, y1, h=36)
    iface = FunctionalInterface("r_syn", "countertop", "kitchen_counter", "work_face",
                                ((x1 - 0.60 * M, y0), (x1 - 0.60 * M, y1)), (-1.0, 0.0), "SEMANTIC_DECLARED", "teste")
    ym = (y0 + y1) / 2
    jamb = [_rect("Armario A", "body", x0, y0 - 5, x0 + 0.5 * M, ym - 0.35 * M, h=80),     # entrada estreita: 0,70 m
            _rect("Armario B", "body", x0, ym + 0.35 * M, x0 + 0.5 * M, y1 + 5, h=80)]
    ev = _ev(con, [counter, *jamb], [iface], rtype="KITCHEN")
    reach = next(v for v in ev.hard_violations if v.code == "FUNCTIONAL_KITCHEN_COUNTER_REACH_PATH")
    assert reach.culprit == "BOTTLENECK" and reach.measured < 0.90 and "gargalo em" in reach.detail


def test_missing_semantic_interface_is_an_input_violation():
    con, b = _room()
    box, _iface, _ = _toilet(b)
    ev = _ev(con, [box], [])
    assert {v.code for v in ev.hard_violations} == {"INPUT_SEMANTIC_INTERFACE_MISSING"}


# ------------------------------------------------------------------------------------------------ planta real
EXPECTED_REAL = {
    ("r005", "FUNCTIONAL_SHOWER_ENTRY_WIDTH", "r005:Box", "WALL"),
    ("r006", "FUNCTIONAL_SHOWER_ENTRY_FRONT_CLEARANCE", "r006:Box", "WALL"),
    ("r006", "FUNCTIONAL_SHOWER_ENTRY_WIDTH", "r006:Box", "WALL"),
    ("r006", "FUNCTIONAL_SHOWER_REACH_PATH", "r006:Box", "INTERFACE_OBSTRUCTED"),
    ("r006", "FUNCTIONAL_TOILET_FRONT_CLEARANCE", "r006:Vaso", "WALL"),
    ("r007", "FUNCTIONAL_LAVATORY_FRONT_CLEARANCE", "r007:Bancada", "Vaso"),
    ("r007", "FUNCTIONAL_TOILET_FRONT_CLEARANCE", "r007:Vaso", "Bancada"),
    ("r007", "FUNCTIONAL_TOILET_REACH_PATH", "r007:Vaso", "PATH_DISCONNECTED"),
}


@pytest.mark.planta74_scale
def test_real_plant_reproduces_exactly_the_eight_known_findings_with_culprits():
    from tools.furnish_apartment import CONSENSUS, collect_boxes
    from tools.validation.functional_clearance import collect_interfaces
    con = json.loads(CONSENSUS.read_text("utf-8"))
    with contextlib.redirect_stdout(io.StringIO()):
        boxes, _ = collect_boxes(con)
        ifaces = collect_interfaces(con, boxes)
    got = set()
    for rid, rt in (("r004", "KITCHEN"), ("r005", "BATHROOM"), ("r006", "BATHROOM"), ("r007", "BATHROOM")):
        ev = evaluate_layout(con, boxes, rid, rt, ifaces)
        assert ev.to_dict() == evaluate_layout(con, boxes, rid, rt, ifaces).to_dict()      # deterministico
        got |= {(rid, v.code, v.object_id, v.culprit) for v in ev.hard_violations}
        if rid == "r004":
            assert ev.feasible and ev.metrics["min_margin_m"] > 0                          # cozinha: so diagnostico
    assert got == EXPECTED_REAL
