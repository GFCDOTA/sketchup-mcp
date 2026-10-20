"""Contratos da divisão do runtime em cômodos + shared (sem editar SKP)."""
import ast
from pathlib import Path

import pytest

from tools.rooms.registry import load_manifest, resolve_module, resolve_project_room

ROOT = Path(__file__).resolve().parents[1]
ROOMS = ROOT / "tools" / "rooms"
TYPES = ("living", "bedroom", "kitchen", "bathroom", "service",
         "balcony", "closet", "home_office", "circulation")


def test_room_module_manifest_is_safe_and_complete():
    data = load_manifest()
    assert set(data["rooms"]) == set(TYPES)
    assert "tools.rooms.shared.geometry" in data["shared"]["code"]
    assert all(not r["execution_authorized"] for r in data["rooms"].values())
    for name in TYPES:
        assert (ROOMS / name / "__init__.py").is_file()
        assert resolve_module(name)["room"] == name


def test_project_ids_unchanged_and_service_is_composite():
    assert resolve_project_room("r004")["module"]["room"] == "kitchen"
    assert resolve_project_room("r001")["module"]["room"] == "service"
    assert resolve_project_room("r000")["module"]["room"] == "bedroom"
    assert resolve_project_room("r002")["module"]["room"] == "living"
    assert resolve_module("varanda")["state"] == "NO_INDEPENDENT_BRAIN_COMPOSITE_SERVICE"


def test_fail_closed_for_unknown_room():
    with pytest.raises(KeyError):
        resolve_module("garagem")
    with pytest.raises(TypeError):
        resolve_module(None)


@pytest.mark.parametrize("name", TYPES)
def test_room_package_does_not_import_another_room_implementation(name):
    source = (ROOMS / name / "__init__.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert not any(isinstance(node, (ast.Import, ast.ImportFrom))
                   for node in ast.walk(tree))


def test_cross_room_geometry_is_in_shared_and_legacy_aliases_match():
    from tools import furnish_apartment as f
    from tools.rooms.bedroom import layout as b
    from tools.rooms.shared import geometry as shared

    for name in ("_fbox", "_wall_setup", "_perp_depth",
                 "_window_zones", "_door_zones"):
        assert getattr(b, name) is getattr(shared, name)
    assert f._oriented_box is shared._oriented_box


def test_no_direct_bedroom_helpers_in_other_room_modules():
    for path in [
        ROOT / "tools/rooms/kitchen/layout.py",
        ROOT / "tools/rooms/bathroom/layout.py",
        ROOMS / "living" / "planner.py",
    ]:
        ast.parse(path.read_text(encoding="utf-8"))
        text = path.read_text(encoding="utf-8")
        assert "from tools.rooms.bedroom.layout import" not in text
        assert "from tools.rooms.shared.geometry import" in text
    legacy = (ROOT / "interior/planners/living_room_planner.py").read_text(encoding="utf-8")
    assert "from tools.rooms.living import planner as _impl" in legacy
    assert "def plan_living(" not in legacy


def test_service_no_longer_imports_orchestrator_for_geometry():
    # A fachada service_layout saiu na FP-044/F6; a geometria compartilhada continua no dono do comodo.
    implementation = (ROOMS / "service" / "layout.py").read_text(encoding="utf-8")
    assert "from tools.furnish_apartment import _oriented_box" not in implementation
    assert "from tools.rooms.shared.geometry import _oriented_box" in implementation


def test_room_modules_do_not_turn_consultative_knowledge_into_execution():
    for name in TYPES:
        assert resolve_module(name)["execution_authorized"] is False


def test_runtime_room_providers_are_owned_by_room_packages():
    # as fachadas de comodo em tools/ sairam na FP-044/F6: o consumidor importa o dono.
    from tools.rooms.bathroom import layout as bathroom
    from tools.rooms.bedroom import designer, layout as bedroom
    from tools.rooms.kitchen import layout as kitchen
    from tools.rooms.service import layout as service
    for mod, fn in ((bathroom, "build_boxes"), (kitchen, "build_boxes"), (service, "build_boxes"),
                    (bedroom, "run"), (designer, "run")):
        assert getattr(mod, fn).__module__ == mod.__name__


def test_legacy_entrypoints_preserve_cli_without_owning_room_builder_source():
    # Fachada aposentada (FP-044/F6): a CLI passa a ser o __main__ do dono.
    for owner in ("kitchen/layout.py", "kitchen/anchor_rules.py", "bathroom/layout.py", "bedroom/layout.py",
                  "bedroom/designer.py", "service/layout.py"):
        assert 'if __name__ == "__main__":' in (ROOMS / owner).read_text("utf-8")
    for name in ("kitchen", "bathroom", "service", "bedroom"):
        path = ROOMS / name / "layout.py"
        assert path.is_file()
        assert (path.read_text("utf-8").count("def build_boxes(") == 1
                if name in ("kitchen", "bathroom", "service") else
                "def run(" in path.read_text("utf-8"))
