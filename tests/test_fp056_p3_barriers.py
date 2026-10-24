"""FP-056 P3 (#434): guarda-corpo, peitoril e mureta limitam o espaco utilizavel — o pre-voo recusa movel sobre a barreira."""
from __future__ import annotations

import json

import pytest

from tools.validation import room_collisions
from tools.validation.layout_preflight import preflight

IN_PER_M = 39.3700787402


def _con():
    from tools.rooms.shared.project_paths import PLANTA_74_CONSENSUS
    return json.loads(PLANTA_74_CONSENSUS.read_text("utf-8"))


def _box_on(point_pt, z0_m=0.0, h_m=0.9, room="A.S."):
    """Caixa de 20 x 20 cm de MOBILIARIO centrada em um ponto (pontos do PDF) da barreira."""
    from core.scale import PT_TO_IN
    cx, cy = point_pt[0] * PT_TO_IN, point_pt[1] * PT_TO_IN
    d = 0.10 * IN_PER_M
    return {"room": room, "module": "Peca teste", "kind": "teste", "label": "teste", "geometry_intent": "FURNITURE",
            "corners": [[cx - d, cy - d], [cx + d, cy - d], [cx + d, cy + d], [cx - d, cy + d]],
            "z0_in": z0_m * IN_PER_M, "h_in": h_m * IN_PER_M, "interaction_policy": {"furniture_overlap": "EXCLUSIVE"}}


def _barrier_point(con, sb_id="h_sb000"):
    sb = next(s for s in con["soft_barriers"] if s["id"] == sb_id)
    a, b = sb["polyline_pts"][0], sb["polyline_pts"][1]
    return ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0), sb.get("height_m")


@pytest.mark.planta74_scale
def test_furniture_standing_on_a_peitoril_is_a_barrier_penetration():
    con = _con()
    pt, height = _barrier_point(con)
    assert height == 1.1
    audit = room_collisions.audit(con, [_box_on(pt)])
    hits = audit["A.S."]["barrier_penetration"]
    assert len(hits) == 1 and hits[0]["barrier"] == "h_sb000" and hits[0]["area_cm2"] > 0
    assert any("barreira h_sb000" in f for f in room_collisions.findings(con, [_box_on(pt)]))


@pytest.mark.planta74_scale
def test_a_piece_whose_base_is_above_the_barrier_top_is_not_blocked():
    con = _con()
    pt, _ = _barrier_point(con)
    audit = room_collisions.audit(con, [_box_on(pt, z0_m=1.5, h_m=0.4)])
    assert audit["A.S."]["barrier_penetration"] == []


@pytest.mark.planta74_scale
def test_a_sourced_barrier_without_a_declared_height_blocks_every_height_fail_closed():
    con = _con()
    pt, _ = _barrier_point(con)
    next(s for s in con["soft_barriers"] if s["id"] == "h_sb000").pop("height_m")
    audit = room_collisions.audit(con, [_box_on(pt, z0_m=1.5, h_m=0.4)])
    assert len(audit["A.S."]["barrier_penetration"]) == 1


@pytest.mark.planta74_scale
def test_preflight_refuses_materialization_when_a_piece_crosses_a_barrier():
    con = _con()
    pt, _ = _barrier_point(con)
    boxes = [_box_on(pt)]
    rooms = [("r001", "A.S.", "service", "OK", 1)]
    report = preflight(con, boxes, rooms)
    col = next(r for r in report["rooms"] if r["gate"] == "room_collisions")
    assert col["status"] == "FAIL" and col["reasons"]["barrier_penetration"]
    assert report["status"] == "FAIL"


@pytest.mark.planta74_scale
def test_an_unsourced_stroke_is_not_a_built_barrier_and_is_not_judged_here():
    # sb000-sb007 nao sao renderizados pelo shell (Hard Rule 1); ja recortam a laje, entao a contencao os cobre
    con = _con()
    pt, _ = _barrier_point(con, "sb007")
    assert room_collisions.audit(con, [_box_on(pt)])["A.S."]["barrier_penetration"] == []


@pytest.mark.planta74_scale
def test_the_generated_apartment_has_no_piece_on_any_barrier():
    import contextlib
    import io

    from tools.furnish_apartment import collect_boxes
    con = _con()
    with contextlib.redirect_stdout(io.StringIO()):
        boxes, _ = collect_boxes(con)
    got = {room: d["barrier_penetration"] for room, d in room_collisions.audit(con, boxes).items() if d["barrier_penetration"]}
    assert got == {}, got


def test_python_barrier_thickness_matches_the_shell_ruby_constant():
    import re
    from pathlib import Path

    from tools.rooms.shared.clearance import SOFT_BARRIER_THICKNESS_IN
    rb = Path(__file__).resolve().parents[1] / "tools/sketchup/shell/build_plan_shell_skp.rb"
    m = re.search(r"^SOFT_BARRIER_THICKNESS_IN\s*=\s*([0-9.]+)", rb.read_text("utf-8"), re.M)
    assert m and float(m.group(1)) == SOFT_BARRIER_THICKNESS_IN


@pytest.mark.planta74_scale
def test_service_planner_does_not_cross_a_built_barrier_through_the_zone_slit(monkeypatch):
    # Variante verificada na decisao AS-1 (churrasqueira 0,85/0,70 m): a Jardineira caia sobre a mureta h_sb001 (437 cm2)
    # porque a fenda de 3,8 cm da barreira no cell sumia sob a tolerancia de 2 cm de `contains`.
    import contextlib
    import io

    from tools.rooms.service import layout as svc
    con = _con()
    orig = svc._programa

    def wider(zones):
        prog = orig(zones)
        for p in prog:
            if p["kind"] in ("churrasqueira", "coifa"):
                p["widths"] = [0.85, 0.70]
        return prog
    monkeypatch.setattr(svc, "_programa", wider)
    with contextlib.redirect_stdout(io.StringIO()):
        boxes, _out = svc.build_boxes(con, "r001")
    for b in boxes:
        b["room"] = "A.S."
    audit = room_collisions.audit(con, boxes)
    assert audit["A.S."]["barrier_penetration"] == []
    assert {"Bancada gourmet", "Banqueta"} <= {b["module"] for b in boxes}        # a variante tambem devolve o programa
