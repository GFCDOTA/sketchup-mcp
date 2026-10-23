"""FP-054 F1-03 (R-04 / #381): layout reprovado nao e materializado.

Antes, `jobs.furnish` mandava ao SketchUp o que `collect_boxes` devolvesse, sem rodar circulacao nem sobreposicao: a Suite 01
(corredor 0,00 m) era materializada como OK. Agora um pre-voo obrigatorio roda os gates por comodo e so PASS/NOT_APPLICABLE
seguem; FAIL e BLOCKED_MISSING_INPUT recusam ANTES de subir o SketchUp, dizendo comodo, gate e motivo."""
from __future__ import annotations

import pytest

from tools.navigation.baseline_probes import synthetic_room
from tools.validation import layout_preflight as lp


def _strip(con):
    from core.scale import PT_TO_IN
    (ax, ay), (bx, by) = con["rooms"][0]["polygon_pts"][0], con["rooms"][0]["polygon_pts"][2]
    x0, y0, x1, y1 = ax * PT_TO_IN, ay * PT_TO_IN, bx * PT_TO_IN, by * PT_TO_IN
    cx = (x0 + x1) / 2
    return [{"module": "Estante", "kind": "body", "room": "SINTETICO", "z0_in": 0.0, "h_in": 80.0,
             "corners": [[cx - 10, y0 - 5], [cx + 10, y0 - 5], [cx + 10, y1 + 5], [cx - 10, y1 + 5]]}]


ROOMS = [("r_syn", "SINTETICO", "LIVING", "OK", 1)]


def test_blocked_corridor_fails_the_preflight_with_room_and_gate():
    con = synthetic_room(4.0)
    pre = lp.preflight(con, _strip(con), ROOMS)
    assert pre["status"] == "FAIL"
    assert pre["blocking"] == [{"room_id": "r_syn", "gate": "circulation", "status": "FAIL",
                                "reasons": {"corredor_principal": "CORRIDOR_BLOCKED"}}]


def test_clear_room_passes():
    pre = lp.preflight(synthetic_room(4.0), [], ROOMS)
    assert pre["status"] == "PASS" and pre["blocking"] == []


def test_single_portal_room_is_not_applicable_and_does_not_block():
    pre = lp.preflight(synthetic_room(4.0, doors=("w_left",)), [], ROOMS)
    assert pre["status"] == "NOT_APPLICABLE" and pre["blocking"] == []


def test_overlapping_furniture_fails():
    con = synthetic_room(4.0)
    a = {"module": "Armario A", "kind": "body", "room": "SINTETICO", "z0_in": 0.0, "h_in": 80.0,
         "corners": [[200, 200], [240, 200], [240, 230], [200, 230]]}
    b = {**a, "module": "Armario B"}
    pre = lp.preflight(con, [a, b], ROOMS)
    assert pre["status"] == "FAIL"
    assert any(x["gate"] == "furniture_overlap" for x in pre["blocking"])


def test_a_gate_that_crashes_blocks_instead_of_being_skipped():
    pre = lp.preflight({}, [{"module": "X", "room": "Q", "corners": [[0, 0], [1, 0], [1, 1]]}], [("r1", "Q", "BEDROOM", "OK", 1)])
    assert pre["status"] == "BLOCKED_MISSING_INPUT"
    assert pre["blocking"][0]["gate"] == "circulation" and pre["blocking"][0]["reasons"]["error"].startswith(("KeyError", "TypeError"))


def test_rooms_without_furniture_are_not_checked():
    pre = lp.preflight(synthetic_room(4.0), [], [("r_syn", "SINTETICO", "LIVING", "skip(sem brain)", 0)])
    assert pre["status"] == "NOT_APPLICABLE" and pre["rooms"] == []


@pytest.mark.planta74_scale
def test_furnish_refuses_the_real_apartment_while_suite01_blocks_its_corridor(tmp_path, monkeypatch):
    """Layout ORIGINAL da Suite 01 (sem a decisao #381): a cadeira da escrivaninha fecha a passagem. Nada pode subir o
    SketchUp. (Com a decisao do Felipe aplicada o apartamento passa — tests/test_fp054_suite01_decision.py.)"""
    from tests.test_sketchup_specialist import FakeSystem, su_with
    from tools.rooms.bedroom import layout_decisions
    from tools.sketchup import jobs
    monkeypatch.setattr(layout_decisions, "DECISIONS", ())

    def never(cmd, env, handle):
        raise AssertionError("SketchUp subiu com layout reprovado")
    r = jobs.furnish(out_dir=str(tmp_path / "out"), mode="interactive", su=su_with(FakeSystem(job=never)))
    assert r["status"] == "BLOCKED_LAYOUT_GATE", r.get("status")
    assert {"room_id": "r000", "gate": "circulation"} in [{k: b[k] for k in ("room_id", "gate")} for b in r["preflight"]["blocking"]]
    assert not (tmp_path / "out").exists()


@pytest.mark.planta74_scale
def test_preflight_refuses_furniture_inside_a_wall():
    """Contraprova real (#381): subir o conjunto da cama 2 in na Suite 01 punha o criado-mudo de cima 1,3-1,8 dm2 dentro da
    parede norte e o pre-voo deixava passar (so media corredor e sobreposicao)."""
    import contextlib
    import copy
    import io
    import json

    from tools.furnish_apartment import CONSENSUS, collect_boxes
    from tools.rooms.bedroom import layout_decisions as ld
    con = json.loads(CONSENSUS.read_text("utf-8"))
    bad = copy.deepcopy(ld.DECISIONS[0])
    bad["shift"] = {"names": ["cama_queen", "cabeceira", "criado_mudo_dir", "criado_mudo_esq"],
                    "dy": {"value": -2.0, "unit": "in", "origin": "user_request"}}
    saved, ld.DECISIONS = ld.DECISIONS, (bad,)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            boxes, summary = collect_boxes(con)
    finally:
        ld.DECISIONS = saved
    pre = lp.preflight(con, boxes, summary)
    assert not lp.allows_materialization(pre)
    hit = [b for b in pre["blocking"] if b["room_id"] == "r000" and b["gate"] == "room_collisions"]
    assert hit and any("Criado-mudo 2" in w for w in hit[0]["reasons"]["wall_penetration"])
