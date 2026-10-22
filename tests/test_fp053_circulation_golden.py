"""FP-053 golden spatial demo: chair-use envelope can block corridor without solid collision."""
import copy
import json
from pathlib import Path

import pytest
from shapely.geometry import LineString, box

from tools.rooms.shared.circulation_oracle import check_protected_route

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "fixtures/components/circulation_table_chair/case_001_golden.json"


def load_golden():
    return json.loads(GOLDEN.read_text("utf-8"))


def check(data):
    furniture = data["furniture"]
    return check_protected_route(
        room=box(*data["room_bounds"]),
        route=LineString(data["route"]),
        required_width_m=data["required_width_m"],
        footprints={f["id"]: box(*f["footprint"]) for f in furniture},
        use_envelopes={f["id"]: box(*f["use_envelope"]) for f in furniture if f.get("use_envelope")},
        required_use_ids={f["id"] for f in furniture if f["requires_use_envelope"]},
    )


def test_golden_chair_use_blocks_route_even_when_solid_footprint_does_not():
    data = load_golden()
    r = check(data)
    assert r["state"] == data["expected_state"]
    assert r["execution_authorized"] is False
    assert r["obstructions"] == [{"id": "chair", "kind": "functional_use_envelope"}]
    assert "SketchUp" not in r


def test_same_room_table_and_chair_shifted_out_of_corridor_is_valid_l1():
    data = load_golden()
    data["furniture"][1]["footprint"] = [2.05, 1.65, 2.45, 2.15]
    data["furniture"][1]["use_envelope"] = [1.75, 1.4, 2.65, 2.4]
    r = check(data)
    assert r["state"] == "L1_ROUTE_CLEAR"
    assert r["execution_authorized"] is False


def test_chair_without_use_envelope_is_blocked_instead_of_ignored():
    data = load_golden()
    data["furniture"][1]["use_envelope"] = None
    r = check(data)
    assert r["state"] == "BLOCKED_USE_ENVELOPE_MISSING"
    assert r["missing_ids"] == ["chair"]


def test_table_itself_in_corridor_is_blocked():
    data = load_golden()
    data["furniture"][0]["footprint"] = [0.9, 1.3, 1.1, 2.5]
    r = check(data)
    assert any(x == {"id": "table", "kind": "solid_footprint"} for x in r["obstructions"])


def test_corridor_near_wall_rejected_before_furniture():
    data = load_golden()
    data["route"] = [[0.05, 0.5], [0.05, 3.5]]
    assert check(data)["state"] == "BLOCKED_ROUTE_OUTSIDE_ROOM"


@pytest.mark.parametrize("width", [0, -0.1, float("nan"), float("inf")])
def test_missing_or_invalid_width_is_not_guessed(width):
    data = load_golden()
    data["required_width_m"] = width
    assert check(data)["state"] == "BLOCKED_INVALID_CLEARANCE"


def test_golden_is_synthetic_not_apartment_approval():
    data = load_golden()
    assert data["origin"] == "fixture_synthetic" and data["case_id"]
    assert not any(k in data for k in ("planta_74", "l2", "approved_target"))
