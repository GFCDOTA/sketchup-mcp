"""FP-042 P2/P3: componentes compartilhados vs. componentes exclusivos da sala.

Sem inicializar SketchUp, nem modificar arquivos SKP, fixtures ou dimensões.
"""
from unittest.mock import Mock

import pytest

from tools.rooms.living import components
from tools.rooms.shared import decor, furniture


def test_legacy_symbols_are_exact_reexports_and_brains_use_them():
    from tools import furnish_apartment as legacy

    assert legacy._oct_in is components._oct_in
    assert legacy._dining_table_rect is components._dining_table_rect
    assert legacy._dining_table_square is components._dining_table_square
    assert legacy._bwg_recolor is components._bwg_recolor
    assert legacy._chair_parts is furniture._chair_parts
    assert legacy.place_decor_boxes is decor.place_decor_boxes
    assert legacy.living_room_boxes.__globals__["_chair_parts"] is furniture._chair_parts
    assert legacy.bedroom_designer_boxes.__globals__["_chair_parts"] is furniture._chair_parts


@pytest.mark.parametrize("factory,length,span", [
    (components._dining_table_rect, 6, (1.60, 0.90)),
    (components._dining_table_square, 6, (0.92, 0.92)),
])
def test_dining_tables_preserve_solid_top_apron_and_four_legs(factory, length, span):
    parts = factory()
    assert len(parts) == length
    assert [part["kind"] for part in parts] == ["top", "saia", "foot", "foot", "foot", "foot"]
    assert (parts[0]["x1"], parts[0]["y1"]) == span
    assert all(p["z1"] > p["z0"] for p in parts)
    assert all(p["x1"] > p["x0"] and p["y1"] > p["y0"] for p in parts)


def test_same_chair_geometry_works_for_living_and_bedroom():
    parts = furniture._chair_parts()
    assert len(parts) == 8
    assert [p["kind"] for p in parts].count("foot") == 4
    assert {p["kind"] for p in parts} == {"foot", "frame", "seat", "back"}
    assert parts[-1]["z1"] == 0.90


def test_pendant_octagon_preserves_nonrectangular_intent():
    box = components._oct_in("pend_cupula", 100, 200, 0.2, 1.85, 0.25, [30, 31, 32], "Pendente")
    assert box["kind"] == "pend_cupula"
    assert box["module"] == "Pendente"
    assert box["decorative"] is True
    assert box["ambiguous"] is False
    assert len(box["corners"]) == 8
    assert box["h_in"] == round(0.25 * 39.3700787402, 2)
    assert box["z0_in"] == round(1.85 * 39.3700787402, 2)


def test_living_palette_does_not_mutate_protected_accents():
    boxes = [
        {"kind": "seat", "module": "Sofa", "rgb": [1, 1, 1]},
        {"kind": "top", "module": "Mesa", "rgb": [1, 1, 1]},
        {"kind": "spot", "module": "Luz", "rgb": [1, 1, 1]},
        {"kind": "rug_custom", "module": "Tapete", "rgb": [9, 8, 7]},
    ]
    assert components._bwg_recolor(boxes) is boxes
    assert [b["rgb"] for b in boxes] == [
        [74, 72, 78], [108, 80, 58], [255, 240, 212], [9, 8, 7],
    ]


def test_shared_decor_adapter_preserves_lift_position_and_module(monkeypatch):
    from tools import decor_builders, sofa_builder

    original = [{"z0": 0.20, "z1": 0.80}]
    build = Mock(return_value=(original, {"result": "OK"}))
    placed = Mock(return_value=[{"kind": "wall_art"}])
    monkeypatch.setattr(decor_builders, "build_decor", build)
    monkeypatch.setattr(sofa_builder, "place_sofa_boxes", placed)
    result = decor.place_decor_boxes(
        "wall_art", (30, 40), (0, 1), z_lift=1.15, module="Quadro", frame="bronze",
    )
    build.assert_called_once_with("wall_art", frame="bronze")
    placed.assert_called_once_with(original, (30, 40), (0, 1))
    assert original[0]["z0"] == pytest.approx(1.35)
    assert original[0]["z1"] == pytest.approx(1.95)
    assert result[0]["module"] == "Quadro"
