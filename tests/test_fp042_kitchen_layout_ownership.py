"""FP-042/P3/P4 kitchen builder migrated without changing geometry or public CLI."""
from pathlib import Path

from shapely.geometry import box

from tools import kitchen_layout as legacy
from tools.rooms.kitchen import layout
from tools.rooms.shared import geometry

ROOT = Path(__file__).resolve().parents[1]


def test_public_symbols_and_parametric_builder_are_identical():
    assert legacy.build_boxes is layout.build_boxes
    assert legacy.main is layout.main
    assert legacy._kmod is layout._kmod
    assert legacy._koct is layout._koct
    assert legacy._wall_setup is geometry._wall_setup
    assert legacy.KITCHEN_SINK_ANCHOR == layout.KITCHEN_SINK_ANCHOR
    assert legacy.KITCHEN_SINK_SIDE == "W"


def test_cli_remains_in_legacy_location_and_only_one_implementation_exists():
    shim = (ROOT / "tools/kitchen_layout.py").read_text("utf-8")
    source = (ROOT / "tools/rooms/kitchen/layout.py").read_text("utf-8")
    assert "def build_boxes(" not in shim
    assert "def build_boxes(" in source
    assert "from tools.rooms.shared.geometry import" in source
    assert "from tools.furnish_apartment import" not in source
    assert "if __name__ == \"__main__\":" in shim
    assert "def main():" in source


def test_legacy_helper_retains_same_geometry_contract():
    shp = box(0, 0, layout.M(1), layout.M(0.4))
    same = legacy._to_box("bancada", shp, 0.90, [30, 29, 32])
    direct = layout._to_box("bancada", shp, 0.90, [30, 29, 32])
    assert same == direct
