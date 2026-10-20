"""Gates da migração P1: AST dos módulos novos e negativos de dependência."""
import json
import subprocess
import sys

import pytest

from tools.rooms.ownership_audit import (
    LEGACY_ROOM_MODULES,
    ROOT,
    collect_imports,
    ownership_violations,
    scan,
)


def test_existing_room_packages_have_no_cross_room_dependency():
    result = scan()
    assert result["result"] == "PASS", result["violations"]


def test_detects_direct_cross_room_import():
    files = {"tools/rooms/kitchen/planner.py":
             "from tools.rooms.bedroom import builder\n"}
    assert ownership_violations(files)[0]["reason"] == "CROSS_ROOM_DEPENDENCY"


def test_detects_shared_importing_legacy_room():
    # alias legado que continua existindo (as fachadas de comodo em tools/ sairam na FP-044/F6)
    files = {"tools/rooms/shared/parts.py": "import interior.planners.living_room_planner\n"}
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


def test_from_package_import_room_alias_is_blocked_in_shared():
    # `from <pacote> import <modulo>` e expandido para o modulo (o caminho que pegava `from tools import <fachada>`)
    assert "tools.some_module" in collect_imports("from tools import some_module\n")
    code = "from tools.rooms import kitchen\n"
    violations = ownership_violations({"tools/rooms/shared/geometry_ext.py": code})
    assert any(r["imported"] == "tools.rooms.kitchen" for r in violations)


def test_relative_local_import_remains_allowed():
    code = "from . import validation\n"
    assert ownership_violations({"tools/rooms/kitchen/layout.py": code}) == []
    assert "tools.rooms.kitchen.validation" in collect_imports(
        code, module_name="tools.rooms.kitchen.layout")


# Os casos das fachadas de quarto (bedroom_layout, bedroom_designer, bed_class) viraram import direto do dono (as fachadas sairam na FP-044/F6);
# o desvio por alias legado que ainda existe segue coberto por interior.planners.living_room_planner.
@pytest.mark.parametrize('source', [
    'import tools.rooms.bedroom.layout\n',
    'from tools.rooms.bedroom.bed_class import derive_spec\n',
])
def test_room_cannot_bypass_boundary_through_legacy_facade(source):
    violations = ownership_violations({'tools/rooms/kitchen/planner.py': source})
    assert any(v['reason'] == 'CROSS_ROOM_DEPENDENCY' for v in violations)


def test_shared_cannot_import_room_class_through_legacy_facade():
    violations = ownership_violations({
        'tools/rooms/shared/parts.py': 'from tools import sofa_class\n',
    })
    assert any(v['reason'] == 'SHARED_IMPORTS_ROOM' for v in violations)


@pytest.mark.parametrize('source', [
    'from tools.furnish_apartment import collect_boxes\n',
    'from tools import furnish_apartment\n',
])
def test_room_cannot_import_its_orchestrator(source):
    violations = ownership_violations({'tools/rooms/kitchen/planner.py': source})
    assert any(v['reason'] == 'ROOM_IMPORTS_ORCHESTRATOR' for v in violations)


def test_same_room_legacy_facade_remains_compatible():
    assert ownership_violations({
        'tools/rooms/kitchen/validation.py': 'from tools import kitchen_validation\n',
    }) == []


def test_nested_legacy_module_cannot_bypass_boundary():
    violations = ownership_violations({
        'tools/rooms/shared/parts.py':
            'from interior.planners import living_room_planner\n',
    })
    assert any(v['reason'] == 'SHARED_IMPORTS_ROOM' for v in violations)


@pytest.mark.parametrize('reverse', [False, True])
def test_room_packages_and_facades_import_in_a_fresh_process(reverse):
    # Cold imports catch partial-initialization failures hidden by pytest's
    # collection cache. No CLI entrypoints or SketchUp jobs are executed.
    modules = set(LEGACY_ROOM_MODULES) | {
        'tools.furnish_apartment', 'tools.variant_sweep', 'tools.geometry_sanity',
        'tools.furniture_overlap_gate', 'tools.circulation_gate',
    }
    modules.update('.'.join(p.relative_to(ROOT).with_suffix('').parts)
                   for p in (ROOT / 'tools/rooms').rglob('*.py'))
    code = 'import importlib, json, sys; ' + (
        '[importlib.import_module(name) for name in json.loads(sys.argv[1])]'
    )
    result = subprocess.run(
        [sys.executable, '-c', code, json.dumps(sorted(modules, reverse=reverse))],
        cwd=ROOT, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
