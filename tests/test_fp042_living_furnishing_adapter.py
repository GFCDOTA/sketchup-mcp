"""FP-042/P3: ownership do solver da sala, sem mudar geometria ou SKP."""
from unittest.mock import Mock

import pytest

from tools.room_type import LIVING
from tools.rooms.living import components, furnishing
from tools.rooms.shared import decor, furniture, geometry


def test_living_brain_is_same_callable_as_legacy_and_registry():
    from tools import furnish_apartment as orchestrator

    assert orchestrator.living_room_boxes is furnishing.living_room_boxes
    assert orchestrator.BRAINS[LIVING] is furnishing.living_room_boxes
    assert furnishing._oriented_box is geometry._oriented_box
    assert furnishing._chair_parts is furniture._chair_parts
    assert furnishing.place_decor_boxes is decor.place_decor_boxes
    assert furnishing._bwg_recolor is components._bwg_recolor
    assert furnishing._dining_table_rect is components._dining_table_rect
    assert furnishing._oct_in is components._oct_in


@pytest.mark.parametrize("plan", [None, {}, []])
def test_no_valid_plan_does_not_create_unanchored_furniture(monkeypatch, plan):
    from interior.planners import living_room_planner

    report = {"result": "NO_VALID_LAYOUT", "room_name": "Sala", "plan": plan}
    mocked = Mock(return_value=report)
    monkeypatch.setattr(living_room_planner, "plan_living", mocked)
    boxes, out = furnishing.living_room_boxes({"rooms": []}, "r002")
    assert boxes == []
    assert out == {
        "result": "NO_VALID_LAYOUT",
        "room_name": "Sala",
        "placement": "no_plan_skip",
    }
    mocked.assert_called_once_with({"rooms": []}, "r002")


def test_living_module_does_not_depend_on_bedroom_or_orchestrator():
    import ast
    from pathlib import Path

    path = Path(furnishing.__file__)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = [n.module for n in ast.walk(tree)
               if isinstance(n, ast.ImportFrom) and n.module]
    assert "tools.furnish_apartment" not in imports
    assert not any(name.startswith("tools.rooms.bedroom") for name in imports)
