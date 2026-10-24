"""FP-054 F2E: proposta somente-leitura — tipo certo, nada aplicado, antes/depois das mesmas linhas da avaliacao."""
from __future__ import annotations

import copy

from tests.test_fp054_f2c_candidates import ROOM, _r, _scene
from tools.rooms.shared.spatial_solver.proposal import propose


def _p(con, boxes, ifaces, **kw):
    return propose(con, boxes, ifaces, "r_syn", "BATHROOM", ROOM, **kw)


def test_clear_room_needs_no_change():
    con, boxes, ifaces = _scene(obstacle=False)
    p = _p(con, boxes, ifaces)
    assert p["kind"] == "NO_CHANGE_NEEDED" and p["original_rank"] == 1 and p["delta"] == []


def test_feasible_alternative_is_proposed_but_never_applied():
    con, boxes, ifaces = _scene()
    snap = copy.deepcopy(boxes)
    p = _p(con, boxes, ifaces)
    assert p["kind"] == "PROPOSAL_FEASIBLE" and p["applied"] is False
    # geometria da entrada (a "planta") nao mudou; core.spatial_semantics.annotate so acrescenta rotulos (idempotente)
    assert [b["corners"] for b in boxes] == [b["corners"] for b in snap]
    assert p["original"]["hard_violations"] and not p["best"]["hard_violations"]
    assert any(d["before"] == "INVALID" and d["after"] != "INVALID" for d in p["delta"])
    rows_after = {(r["object_id"], r["constraint"]): r for r in p["_rows"]["after"]}
    for d in p["delta"]:                                                   # delta vem das mesmas linhas que decidiram
        assert rows_after[(d["object_id"], d["constraint"])]["measured"] == d["after_m"]


def test_no_alternative_reports_closest_and_what_would_unblock():
    con, boxes, ifaces = _scene()
    x0 = min(c[0] for c in boxes[1]["corners"])
    ys = [c[1] for c in boxes[0]["corners"]]
    tall = _r("Armario", "body", x0, min(ys) - 0.9 * 39.37, min(c[0] for c in boxes[0]["corners"]) - 0.30 * 39.37,
              max(ys) + 0.9 * 39.37, h=80)
    p = _p(con, [boxes[0], tall], ifaces)
    assert p["kind"] == "CLOSEST_INFEASIBLE" and p["best"]["hard_violations"] and p["decisions_to_unblock"]


def test_budget_exhausted_is_not_solved():
    con, boxes, ifaces = _scene()
    assert _p(con, boxes, ifaces, max_candidates=1)["kind"] == "NOT_SOLVED"


def test_shallow_3d_interpenetration_is_a_hard_collision_for_solver_pieces():
    # achado real do F2E (Banho 02): vaso deslizado entra no gabinete suspenso — 29% da menor pegada, abaixo do FAIL de 30%
    # do gate do builder. Para peca do solver qualquer interpenetracao acima da tolerancia e rigida.
    from tests.test_fp054_f2b_geometry_engine import _ev
    con, boxes, ifaces = _scene(obstacle=False)
    xs = [c[0] for c in boxes[0]["corners"]]
    ys = [c[1] for c in boxes[0]["corners"]]
    y1 = max(ys)
    # faixa de 4 cm sobre o vaso de 0,65 m: 0,026 m2 — abaixo do AREA_MIN_M2 (0,04) do gate, que trataria como "rocar"
    cab = _r("Gabinete", "gabinete", min(xs), y1 - 0.04 * 39.37, max(xs), y1 + 0.5 * 39.37, h=8)
    cab["z0_in"] = 10.0                                       # suspenso, mas abaixo do topo do vaso (16 in)
    ev = _ev(con, [boxes[0], cab], list(ifaces.values()))
    assert any(v.code == "COLLISION" for v in ev.hard_violations)
