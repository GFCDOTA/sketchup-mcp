"""FP-056 P2: UsablePlacementRegion (laje - parede - barreira) e completude do programa no gate de nao regressao."""
from __future__ import annotations

import json

import pytest

from tools.validation import defect_baseline as db

BASE = [{"key": "r1|WALL|Armario", "room_id": "r1", "check": "WALL", "measure": 0.0046, "unit": "m", "cause": "R1",
         "finding": {"check": "WALL", "module": "Armario"}}]
PROGRAM = {"r1": ["Armario", "Cama", "Tapete"]}


def test_emptied_room_is_a_regression_and_its_defects_are_not_counted_as_resolved():
    r = db.regression({"r1": {"findings": [], "modules": []}}, BASE, PROGRAM)
    assert r["status"] == "FAIL" and set(r["missing_program"]) == {"r1|PROGRAM|Armario", "r1|PROGRAM|Cama", "r1|PROGRAM|Tapete"}
    assert r["resolved"] == [] and r["vanished_with_piece"] == ["r1|WALL|Armario"]


def test_real_fix_counts_as_resolved_and_an_omission_needs_a_recorded_decision():
    fixed = {"r1": {"findings": [], "modules": ["Armario", "Cama", "Tapete"]}}
    r = db.regression(fixed, BASE, PROGRAM)
    assert r["status"] == "PASS" and r["resolved"] == ["r1|WALL|Armario"]
    omitted = {"r1": {"findings": [], "modules": ["Armario", "Cama"]}}
    assert db.regression(omitted, BASE, PROGRAM)["status"] == "FAIL"
    ok = db.regression(omitted, BASE, PROGRAM, accepted_omissions={"r1|PROGRAM|Tapete": "decisao registrada X"})
    assert ok["status"] == "PASS" and ok["accepted_omissions"] == ["r1|PROGRAM|Tapete"]


@pytest.mark.planta74_scale
def test_usable_region_has_no_area_inside_walls_or_barriers_in_any_room():
    from core.scale import PT_TO_M
    from tools.rooms.shared.placement_region import barrier_mass_pt, usable_placement_region
    from tools.rooms.shared.project_paths import PLANTA_74_CONSENSUS
    con = json.loads(PLANTA_74_CONSENSUS.read_text("utf-8"))
    mass = barrier_mass_pt(con)
    for r in con["rooms"]:
        region, rep = usable_placement_region(con, r["id"])
        assert region.intersection(mass).area * PT_TO_M ** 2 < 1e-6, r["id"]
        assert 0 < rep["usable_m2"] < rep["slab_m2"] and rep["under_walls_m2"] > 0
