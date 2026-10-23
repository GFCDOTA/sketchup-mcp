"""FP-054 F1-02 (#382): mesa e cadeira de jantar vem de papel DECLARADO, nao de prefixo de texto.

Contraprova da F0 (`gate_probes.json` P5): a mesma cadeira sem folga, rotulada `Chair`/`Dining table`, nao era medida e o gate
passava; rotulada em portugues, reprovava. E `Cadeira escrivaninha` contava como cadeira de jantar por comecar com "Cadeira"."""
from __future__ import annotations

import pytest

from core.furniture_roles import MODULE_ROLE, ROLES, resolve_role
from tools.navigation.baseline_probes import synthetic_room
from tools.validation import circulation_gate as cg


def _rect(module, kind, x, y, w, d, **extra):
    return {"module": module, "kind": kind, "corners": [[x, y], [x + w, y], [x + w, y + d], [x, y + d]],
            "z0_in": 0.0, "h_in": 30.0, **extra}


@pytest.fixture()
def room():
    from core.scale import PT_TO_IN
    con = synthetic_room(4.0)
    ax, ay = con["rooms"][0]["polygon_pts"][0]
    return con, ax * PT_TO_IN, ay * PT_TO_IN


def _tight_set(x0, y0, table, chair, **chair_extra):
    """Mesa a 18 in da parede sul e a cadeira colada na parede: 0 m atras (tem que reprovar quando medida)."""
    return [_rect(table, "top", x0 + 60, y0 + 18, 40, 26), _rect(chair, "seat", x0 + 70, y0 + 1, 17, 17, **chair_extra)]


# ------------------------------------------------------------------------------------------------ resolucao
def test_role_comes_from_explicit_field_then_exact_module_never_prefix():
    assert resolve_role({"module": "X", "furniture_role": "dining_chair"}) == ("dining_chair", "explicit")
    assert resolve_role({"module": "Cadeira jantar"}) == ("dining_chair", "module_registry")
    assert resolve_role({"module": "  cadeira JANTAR "}) == ("dining_chair", "module_registry")
    assert resolve_role({"module": "Cadeira de balanco"}) == (None, "undeclared")       # prefixo "Cadeira" nao basta
    assert resolve_role({"module": "Chair"}) == (None, "undeclared")
    assert resolve_role({"module": "Chair", "furniture_role": "banqueta"}) == (None, "invalid_explicit")


def test_registry_only_maps_to_known_roles():
    assert set(MODULE_ROLE.values()) <= set(ROLES)


# ------------------------------------------------------------------------------------- gate: contraprova da F0
def test_undeclared_seat_blocks_instead_of_passing(room):
    con, x0, y0 = room
    res = cg.gate(con, _tight_set(x0, y0, "Dining table", "Chair"), "r_syn")
    assert res["checks"]["atras_das_cadeiras"]["result"] == "BLOCKED_MISSING_INPUT"
    assert res["checks"]["atras_das_cadeiras"]["reason_code"] == "SEAT_ROLE_UNDECLARED"
    assert res["result"] == "BLOCKED_MISSING_INPUT"


def test_declared_roles_are_measured_whatever_the_label(room):
    con, x0, y0 = room
    boxes = _tight_set(x0, y0, "Dining table", "Chair", furniture_role="dining_chair")
    boxes[0]["furniture_role"] = "dining_table"
    res = cg.gate(con, boxes, "r_syn")
    assert res["checks"]["atras_das_cadeiras"]["result"] == "FAIL"
    assert len(res["checks"]["atras_das_cadeiras"]["cadeiras"]) == 1
    assert res["result"] == "FAIL"


def test_portuguese_and_declared_labels_give_the_same_verdict(room):
    con, x0, y0 = room
    pt = cg.gate(con, _tight_set(x0, y0, "Mesa de jantar", "Cadeira jantar"), "r_syn")
    boxes = _tight_set(x0, y0, "Dining table", "Chair", furniture_role="dining_chair")
    boxes[0]["furniture_role"] = "dining_table"
    en = cg.gate(con, boxes, "r_syn")
    assert pt["result"] == en["result"] == "FAIL"
    assert pt["checks"]["atras_das_cadeiras"]["cadeiras"] == en["checks"]["atras_das_cadeiras"]["cadeiras"]


def test_desk_chair_is_not_a_dining_chair(room):
    con, x0, y0 = room
    boxes = _tight_set(x0, y0, "Mesa de jantar", "Cadeira escrivaninha")
    res = cg.gate(con, boxes, "r_syn")
    assert res["checks"]["atras_das_cadeiras"]["cadeiras"] == []
    assert res["checks"]["atras_das_cadeiras"]["result"] == "NOT_APPLICABLE"
    assert res["checks"]["atras_das_cadeiras"]["reason_code"] == "NO_DINING_CHAIRS"


def test_decide_only_agrees_with_full_gate_on_blocked(room):
    con, x0, y0 = room
    boxes = _tight_set(x0, y0, "Dining table", "Chair")
    full = cg.gate(con, boxes, "r_syn")
    fast = cg.gate(con, boxes, "r_syn", decide_only=True)
    assert fast["result"] == full["result"] == "BLOCKED_MISSING_INPUT"


@pytest.mark.planta74_scale
def test_planta74_every_seat_has_a_declared_role_and_verdicts_hold():
    import contextlib
    import io
    import json

    from tools.furnish_apartment import CONSENSUS, collect_boxes
    con = json.loads(CONSENSUS.read_text("utf-8"))
    with contextlib.redirect_stdout(io.StringIO()):
        boxes, _ = collect_boxes(con)
    seats = [b for b in boxes if b.get("kind") == "seat"]
    assert seats and all(resolve_role(b)[0] for b in seats), [b.get("module") for b in seats if not resolve_role(b)[0]]
    sala = cg.gate(con, boxes, "r002")
    assert sala["result"] == "PASS" and len(sala["checks"]["atras_das_cadeiras"]["cadeiras"]) == 2
