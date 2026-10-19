"""FP-042 P2: source of truth da validação hidráulica passa a kitchen."""
from unittest.mock import Mock

from shapely.geometry import box

from tools import kitchen_validation as legacy
from tools.rooms.kitchen import anchor_rules, validation


def test_legacy_cli_module_reexports_canonical_rules():
    assert legacy.validate is anchor_rules.validate
    assert legacy._modules is anchor_rules._modules
    assert legacy.TOUCH_TOL_IN == anchor_rules.TOUCH_TOL_IN == 6.0
    assert callable(legacy.main)


def test_room_boundary_still_calls_legacy_patchable_api(monkeypatch):
    expected = {"result": "PASS", "lines": [], "checks": {"sink_wall": "LEFT"}}
    mocked = Mock(return_value=expected)
    monkeypatch.setattr(legacy, "validate", mocked)
    assert validation.validate_kitchen_anchor({}, "r004") is expected
    mocked.assert_called_once_with({}, "r004")


def test_sink_modules_aggregate_polygons_without_shape_change():
    square = [[0, 0], [1, 0], [1, 1], [0, 1]]
    result = anchor_rules._modules([{"module": "sink_module", "corners": square}])
    assert set(result) == {"sink_module"}
    assert result["sink_module"].area == 1.0


def test_canonical_rules_fail_closed_when_builder_finds_no_layout(monkeypatch):
    from tools import kitchen_layout, room_type, spatial_model

    sm = {"_geom": {"cell": box(0, 0, 100, 100),
                    "con": {"wall_thickness_pts": 8.0}, "circ": []}}
    monkeypatch.setattr(spatial_model, "build_spatial_model", lambda *_: sm)
    monkeypatch.setattr(room_type, "classify_rooms", lambda *_: [])
    mocked = Mock(return_value=([], {"reason": "NO_VALID_LAYOUT"}))
    monkeypatch.setattr(kitchen_layout, "build_boxes", mocked)
    result = legacy.validate({}, "r004")
    assert result == {
        "result": "FAIL",
        "checks": {"build": "NO_VALID_LAYOUT"},
        "lines": [],
    }
    mocked.assert_called_once_with({}, "r004")
