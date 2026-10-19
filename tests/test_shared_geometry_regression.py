"""Gates sintéticos da geometria cross-room. Não dependem de SketchUp."""
import math

import pytest
from shapely.geometry import box

from core.scale import M
from tools.rooms.shared.geometry import _fbox, _front_strip, _oriented_box


@pytest.mark.parametrize("orientation,expected", [
    ("h", (5.0, 8.0, 9.0, 11.0)),
    ("v", (8.0, 5.0, 11.0, 9.0)),
])
def test_fbox_orientation_has_stable_coordinates(orientation, expected):
    rect = _fbox(orientation, 8, 1, 7, 0, 4, 3)
    # 'h': face Y=8, along X=7 -> x5..9, y8..11
    # 'v': face X=8, along Y=7 -> x8..11, y5..9
    assert rect.bounds == expected


@pytest.mark.parametrize("facing", [(0, -1), (0, 1), (1, 0), (-1, 0)])
def test_oriented_box_has_nonzero_footprint_and_expected_height(facing):
    box_ = _oriented_box("sample", (100, 200), facing, 1.0, 0.5,
                         0.2, 0.8, [10, 20, 30], module="fixture")
    assert len(box_["corners"]) == 4
    assert box_["x0"] < box_["x1"] and box_["y0"] < box_["y1"]
    assert box_["module"] == "fixture"
    assert box_["z0_in"] == pytest.approx(0.2 * 39.3700787402, abs=0.01)
    assert box_["h_in"] == pytest.approx(0.8 * 39.3700787402, abs=0.01)


def test_legacy_exports_are_same_function_object():
    from tools import bedroom_layout, furnish_apartment
    from tools.rooms.shared import geometry
    for name in ("_fbox", "_wall_setup", "_door_zones", "_window_zones", "_perp_depth"):
        assert getattr(bedroom_layout, name) is getattr(geometry, name)
    assert furnish_apartment._oriented_box is geometry._oriented_box
