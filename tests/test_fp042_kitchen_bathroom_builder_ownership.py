"""Regressão P3: layouts cozinha/banheiros têm owner único e entradas legadas estáveis."""
from pathlib import Path

import pytest

from tools.rooms.kitchen import layout as kitchen
from tools.rooms.bathroom import layout as bathroom
from tools import kitchen_layout as legacy_kitchen
from tools.rooms.shared import geometry


@pytest.mark.parametrize("legacy,implementation,helpers", [
    (legacy_kitchen, kitchen, ("_fbox", "_wall_setup", "_window_zones")),
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


def test_bathroom_builder_is_owned_by_the_room_and_reuses_shared_geometry():
    """A fachada bathroom_layout saiu na FP-044/F6; o contrato do dono continua: builder unico + helpers do shared."""
    assert bathroom.build_boxes.__module__ == bathroom.__name__
    assert bathroom._to_box.__module__ == bathroom.__name__
    for sym in ("_fbox", "_wall_setup", "_window_zones", "_door_zones"):
        assert getattr(bathroom, sym) is getattr(geometry, sym)


@pytest.mark.parametrize("legacy,room", [(legacy_kitchen, "kitchen")])
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
    for helper in (bathroom._skin_parts, bathroom._enxoval_parts, bathroom.theme_of):
        assert helper.__module__ == bathroom.__name__
