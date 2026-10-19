"""Regressão P3: layouts cozinha/banheiros têm owner único e entradas legadas estáveis."""
from pathlib import Path

import pytest

from tools.rooms.kitchen import layout as kitchen
from tools.rooms.bathroom import layout as bathroom
from tools import kitchen_layout as legacy_kitchen
from tools import bathroom_layout as legacy_bathroom
from tools.rooms.shared import geometry


@pytest.mark.parametrize("legacy,implementation,helpers", [
    (legacy_kitchen, kitchen, ("_fbox", "_wall_setup", "_window_zones")),
    (legacy_bathroom, bathroom, ("_fbox", "_wall_setup", "_window_zones", "_door_zones")),
])
def test_builder_ownership_and_compatibility(legacy, implementation, helpers):
    assert legacy.build_boxes is implementation.build_boxes
    assert legacy._to_box is implementation._to_box
    assert legacy.PT_TO_M == implementation.PT_TO_M
    assert legacy.PT_TO_IN == implementation.PT_TO_IN
    assert implementation.build_boxes.__module__ == implementation.__name__
    assert Path(implementation.__file__).resolve().parents[3] == Path(legacy.__file__).resolve().parents[1]
    for sym in helpers:
        assert getattr(legacy, sym) is getattr(geometry, sym)
        assert getattr(implementation, sym) is getattr(geometry, sym)


@pytest.mark.parametrize("legacy,room", [(legacy_kitchen, "kitchen"), (legacy_bathroom, "bathroom")])
def test_legacy_module_is_thin_facade_without_duplicate_builder(legacy, room):
    text = Path(legacy.__file__).read_text(encoding="utf-8")
    assert "def build_boxes(" not in text
    assert f"from tools.rooms.{room} import layout as _impl" in text
    assert 'if __name__ == "__main__":' in text
    assert callable(legacy.main)


def test_kitchen_anchor_validator_uses_same_canonical_builder():
    from tools.rooms.kitchen import anchor_rules
    from tools import kitchen_validation
    assert kitchen_validation.validate is anchor_rules.validate


def test_bathroom_skin_and_sink_helpers_stay_in_bathroom():
    assert legacy_bathroom._skin_parts is bathroom._skin_parts
    assert legacy_bathroom._enxoval_parts is bathroom._enxoval_parts
    assert legacy_bathroom.theme_of is bathroom.theme_of
