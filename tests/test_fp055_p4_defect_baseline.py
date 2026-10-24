"""FP-055 P4: gate de nao regressao contra o registro de defeitos do apartamento original."""
from __future__ import annotations

import json
from pathlib import Path

from tools.validation import defect_baseline as db

ROOT = Path(__file__).resolve().parents[1]
BASE = [{"key": "r1|WALL|Armario", "room_id": "r1", "check": "WALL", "measure": 0.0046, "unit": "m", "cause": "R1"},
        {"key": "r1|DOOR|d1", "room_id": "r1", "check": "DOOR", "measure": 41.0, "unit": "deg", "cause": "R5"},
        {"key": "r2|OBJECTS|A+B", "room_id": "r2", "check": "OBJECTS", "measure": 0.03, "unit": "m", "cause": "R3"}]


def _rep(*findings):
    return {"findings": list(findings)}


def test_same_defects_pass_new_or_deeper_fail_and_gone_is_resolved():
    same = {"r1": _rep({"check": "WALL", "module": "Armario", "depth_m": 0.0046},
                       {"check": "DOOR", "door": "d1", "max_open_deg": 49.0, "required_deg": 90.0})}
    r = db.regression(same, BASE)
    assert r["status"] == "PASS" and r["resolved"] == [] and r["compared_rooms"] == ["r1"]
    deeper = {"r1": _rep({"check": "WALL", "module": "Armario", "depth_m": 0.0060})}
    r = db.regression(deeper, BASE)
    assert r["status"] == "FAIL" and r["worse"][0]["key"] == "r1|WALL|Armario" and "r1|DOOR|d1" in r["resolved"]
    new = {"r1": _rep({"check": "CONTAINMENT", "module": "Vaso", "outside_depth_m": 0.002})}
    assert db.regression(new, BASE)["new"][0]["key"] == "r1|CONTAINMENT|Vaso"
    door_worse = {"r1": _rep({"check": "DOOR", "door": "d1", "max_open_deg": 30.0, "required_deg": 90.0})}
    assert db.regression(door_worse, BASE)["worse"][0]["measure"] == 60.0


def test_rooms_outside_the_generation_are_not_reported_as_resolved():
    r = db.regression({"r1": _rep()}, BASE)
    assert "r2|OBJECTS|A+B" not in r["resolved"]


def test_committed_baseline_is_the_original_apartment_and_keeps_every_known_defect():
    doc = json.loads((ROOT / "artifacts/review/fp055/p4/defect_baseline.json").read_text("utf-8"))
    keys = {d["key"] for d in doc["defects"]}
    assert "5426c0087bdfcdc6" in doc["source_geometry"] and len(doc["source_sha256"]) == 64
    for k in ("r000|DOOR|h_o003", "r003|DOOR|h_o004", "r004|WALL|base_cabinet_01", "r001|CONTAINMENT|Maquina de lavar",
              "r001|CONTAINMENT|Bancada gourmet", "r005|OBJECTS|Enxoval+Vaso"):
        assert k in keys, k
    assert {d["cause"] for d in doc["defects"]} <= {"R1", "R2", "R2a", "R2b", "R3", "R5"}
