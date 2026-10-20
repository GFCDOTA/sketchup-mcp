"""Regressão P3: layouts cozinha/banheiros têm owner único e entradas legadas estáveis."""
from pathlib import Path

import pytest

from tools.rooms.kitchen import layout as kitchen
from tools.rooms.bathroom import layout as bathroom
from tools.rooms.shared import geometry


@pytest.mark.parametrize("implementation,helpers", [
    (kitchen, ("_fbox", "_wall_setup", "_window_zones")),
    (bathroom, ("_fbox", "_wall_setup", "_window_zones", "_door_zones")),
])
def test_builder_is_owned_by_the_room_and_reuses_shared_geometry(implementation, helpers):
    """As fachadas kitchen_layout/bathroom_layout sairam na FP-044/F6; o contrato do dono continua."""
    assert implementation.build_boxes.__module__ == implementation.__name__
    assert implementation._to_box.__module__ == implementation.__name__
    for sym in helpers:
        assert getattr(implementation, sym) is getattr(geometry, sym)


@pytest.mark.parametrize("implementation", [kitchen, bathroom])
def test_owner_keeps_the_cli_and_a_single_builder(implementation):
    text = Path(implementation.__file__).read_text(encoding="utf-8")
    assert text.count("def build_boxes(") == 1
    assert 'if __name__ == "__main__":' in text


def test_kitchen_anchor_validator_and_its_cli_live_in_the_owner():
    # a fachada kitchen_validation saiu na FP-044/F6; o main() foi movido para o dono sem mudanca
    from tools.rooms.kitchen import anchor_rules
    assert anchor_rules.validate.__module__ == anchor_rules.__name__
    assert anchor_rules.main.__module__ == anchor_rules.__name__


def test_bathroom_skin_and_sink_helpers_stay_in_bathroom():
    for helper in (bathroom._skin_parts, bathroom._enxoval_parts, bathroom.theme_of):
        assert helper.__module__ == bathroom.__name__
