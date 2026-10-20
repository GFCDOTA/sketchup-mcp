"""Limites entre módulos por cômodo; inspeção AST estática e reprodutível."""
import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT / "tools" / "rooms" / "shared"
ROOM_FILES = (
    ROOT / "tools/rooms/kitchen/layout.py",
    ROOT / "tools/rooms/bathroom/layout.py",
    ROOT / "tools/service_layout.py",
    ROOT / "interior/planners/living_room_planner.py",
)
FORBIDDEN = {"tools.rooms.bedroom.layout", "tools.rooms.bedroom.designer",
             "tools.furnish_apartment"}


def _imports(path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
        elif isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
    return imports


@pytest.mark.parametrize("path", ROOM_FILES, ids=lambda p: p.name)
def test_room_modules_do_not_import_bedroom_or_orchestrator(path):
    assert not (_imports(path) & FORBIDDEN), (
        str(path) + ": dependência transversal de cômodo; extrair em shared"
    )


def test_shared_geometry_has_no_room_specific_dependencies():
    imports = _imports(SHARED / "geometry.py")
    assert not (imports & FORBIDDEN)
    assert not any(i.startswith("tools.rooms.kitchen") or
                   i.startswith("tools.rooms.bathroom") or
                   i.startswith("tools.rooms.bedroom")
                   for i in imports)


def test_room_dispatch_stays_pure_and_no_sketchup_side_effects():
    path = ROOT / "tools/rooms/dispatch.py"
    imports = _imports(path)
    assert not any(i.startswith("tools.furnish_apartment") or
                   i.startswith("tools.sketchup.jobs") for i in imports)
    assert "subprocess" not in imports
    assert "os" not in imports


def test_runtime_modules_are_not_replaced_by_catalog_recipes():
    import json
    manifest = json.loads((ROOT / "tools/rooms/manifest.v1.json").read_text("utf-8"))
    assert all(room["execution_authorized"] is False
               for room in manifest["rooms"].values())
