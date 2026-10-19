"""Gates da migração P1: AST dos módulos novos e negativos de dependência."""
import pytest

from tools.rooms.ownership_audit import collect_imports, ownership_violations, scan


def test_existing_room_packages_have_no_cross_room_dependency():
    result = scan()
    assert result["result"] == "PASS", result["violations"]


def test_detects_direct_cross_room_import():
    files = {"tools/rooms/kitchen/planner.py":
             "from tools.rooms.bedroom import builder\n"}
    assert ownership_violations(files)[0]["reason"] == "CROSS_ROOM_DEPENDENCY"


def test_detects_shared_importing_legacy_room():
    files = {"tools/rooms/shared/parts.py": "import tools.kitchen_layout\n"}
    assert ownership_violations(files)[0]["reason"] == "SHARED_IMPORTS_ROOM"


def test_shared_can_import_core_and_other_shared():
    files = {"tools/rooms/shared/parts.py":
             "from core.scale import M\nfrom tools.rooms.shared.geometry import _fbox\n"}
    assert ownership_violations(files) == []


def test_imports_are_parsed_without_executing_modules():
    assert "tools.rooms.kitchen" in collect_imports(
        "if False:\n    import tools.rooms.kitchen\n"
    )


def test_relative_cross_room_import_is_blocked():
    code = "from ..bathroom import layout\n"
    result = ownership_violations({"tools/rooms/kitchen/planner.py": code})
    assert any(r["imported"] == "tools.rooms.bathroom" and
               r["reason"] == "CROSS_ROOM_DEPENDENCY" for r in result)


def test_relative_from_parent_import_room_alias_is_blocked():
    code = "from .. import bathroom\n"
    violations = ownership_violations({"tools/rooms/kitchen/planner.py": code})
    assert any(r["imported"] == "tools.rooms.bathroom" for r in violations)


def test_from_tools_import_legacy_builder_is_blocked_in_shared():
    code = "from tools import kitchen_layout\n"
    violations = ownership_violations({"tools/rooms/shared/geometry_ext.py": code})
    assert any(r["imported"] == "tools.kitchen_layout" and
               r["reason"] == "SHARED_IMPORTS_ROOM" for r in violations)


def test_relative_local_import_remains_allowed():
    code = "from . import validation\n"
    assert ownership_violations({"tools/rooms/kitchen/layout.py": code}) == []
    assert "tools.rooms.kitchen.validation" in collect_imports(
        code, module_name="tools.rooms.kitchen.layout")
