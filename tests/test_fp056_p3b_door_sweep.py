"""FP-056 P3b (#500): o pre-voo ve a VARREDURA REAL da folha (R5), com baseline conhecido e sem aprovar nada."""
from __future__ import annotations

import contextlib
import io
import json

import pytest

pytestmark = pytest.mark.planta74_scale


def _real():
    from tools.furnish_apartment import collect_boxes
    from tools.rooms.shared.project_paths import PLANTA_74_CONSENSUS
    con = json.loads(PLANTA_74_CONSENSUS.read_text("utf-8"))
    with contextlib.redirect_stdout(io.StringIO()):
        boxes, summary = collect_boxes(con)
    return con, boxes, summary


def test_true_sweep_matches_the_leaf_motion_the_built_validator_measures():
    from core.scale import PT_TO_M
    from tools.rooms.shared.clearance import door_sweeps_pt, door_swings_pt
    from tools.rooms.shared.project_paths import PLANTA_74_CONSENSUS
    con = json.loads(PLANTA_74_CONSENSUS.read_text("utf-8"))
    sweeps, quarter = door_sweeps_pt(con), door_swings_pt(con)
    for did in ("h_o003", "h_o004"):
        sw_m2 = sweeps[did].area * PT_TO_M ** 2
        assert 0.42 < sw_m2 < 0.43                                          # 0,427 m2 medido no validador do construido
        assert sw_m2 > quarter[did].area * PT_TO_M ** 2 * 1.05             # o quarto de circulo antigo era menor


def test_audit_finds_exactly_the_two_registered_rug_sweeps_and_nothing_else():
    from tools.validation import room_collisions
    con, boxes, _ = _real()
    hits = {(d["door"], d["module"]) for r in room_collisions.audit(con, boxes).values() for d in r["door_sweep_hits"]}
    assert hits == {("h_o003", "rug"), ("h_o004", "rug")}


def test_preflight_passes_only_because_the_two_hits_are_registered_known_gaps(monkeypatch):
    from tools.validation import known_gaps
    from tools.validation.layout_preflight import preflight
    con, boxes, summary = _real()
    assert preflight(con, boxes, summary)["status"] == "PASS"
    monkeypatch.setattr(known_gaps, "load", lambda *a, **k: {})            # sem o registro: o conflito reprova
    rep = preflight(con, boxes, summary)
    assert rep["status"] == "FAIL"
    reasons = {b["room_id"]: b["reasons"]["door_sweep_hits"] for b in rep["blocking"] if b["gate"] == "room_collisions"}
    assert set(reasons) == {"r000", "r003"} and reasons["r000"][0].startswith("h_o003:rug/tapete")


def test_a_new_piece_in_the_sweep_is_blocked_even_when_the_rug_is_registered():
    from tools.validation import room_collisions
    from tools.validation.layout_preflight import preflight
    con, boxes, summary = _real()
    rug = next(b for b in boxes if b["room"] == "SUITE 01" and b["kind"] == "rug")
    # uma peca nova (mobiliario, 30 cm de altura) sobre o mesmo ponto do giro
    piece = {**rug, "kind": "novo", "module": "Pufe", "label": "pufe", "geometry_intent": "FURNITURE", "z0_in": 0.0, "h_in": 11.8,
             "interaction_policy": {"furniture_overlap": "EXCLUSIVE", "circulation": "BLOCKING"}}
    hits = {(d["door"], d["module"]) for r in room_collisions.audit(con, boxes + [piece]).values() for d in r["door_sweep_hits"]}
    assert ("h_o003", "Pufe") in hits
    rep = preflight(con, boxes + [piece], summary)
    assert rep["status"] == "FAIL"


def test_moving_the_rug_out_of_the_sweep_clears_the_hit_in_the_audit():
    from tools.validation import room_collisions
    con, boxes, _ = _real()
    moved = [dict(b) for b in boxes]
    for b in moved:
        if b["room"] == "SUITE 01" and b["kind"] == "rug":
            b["corners"] = [[x + 200.0, y + 200.0] for x, y in b["corners"]]      # bem fora do giro (5 m)
    hits = {(d["door"]) for r in room_collisions.audit(con, moved).values() for d in r["door_sweep_hits"]}
    assert "h_o003" not in hits
