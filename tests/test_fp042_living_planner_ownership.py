"""P3: living planner has single canonical owner, no bedroom dependency."""
from pathlib import Path

from interior.planners import living_room_planner as legacy
from tools.rooms.living import planner
from interior.planners import placement_brain
from interior.validators import sofa_placement_gate


def test_legacy_plan_living_is_same_callable():
    assert legacy.plan_living is planner.plan_living
    assert legacy._slide_clear is planner._slide_clear
    assert planner.ROOT == Path(__file__).resolve().parents[1]
    assert legacy.ROOT == planner.ROOT


def test_legacy_planner_is_facade_and_keeps_standalone_cli():
    source = Path(legacy.__file__).read_text(encoding="utf-8")
    assert "def plan_living(" not in source
    assert "runpy.run_module" in source
    assert 'if __name__ == "__main__":' in source


def test_cross_room_validation_and_engine_use_shared_geometry():
    for module in (placement_brain, sofa_placement_gate):
        source = Path(module.__file__).read_text(encoding="utf-8")
        assert "from tools.bedroom_layout import" not in source
        assert "from tools.rooms.shared.geometry import" in source
        assert "from core.scale import M" in source
    assert placement_brain._wall_setup is planner._wall_setup
    assert sofa_placement_gate._door_zones is planner._door_zones
