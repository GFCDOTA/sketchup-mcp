"""P3: seven furniture classes have canonical owners and identity-preserving facades."""
import ast
from importlib import import_module
from pathlib import Path
import pytest

CASES = [["tools.armchair_builder","tools.rooms.shared.armchair_builder","build_armchair"],["tools.armchair_class","tools.rooms.living.armchair_class","derive_armchair_spec"],["tools.bed_class","tools.rooms.bedroom.bed_class","derive_bed_spec"],["tools.coffee_table_class","tools.rooms.living.coffee_table_class","build_coffee_table_v2"],["tools.dining_table_class","tools.rooms.living.dining_table_class","build_dining_table"],["tools.rack_class","tools.rooms.living.rack_class","build_rack"],["tools.sofa_class","tools.rooms.living.sofa_class","derive_living_sofa"]]


@pytest.mark.parametrize("old,canonical,symbol", CASES)
def test_reexport_and_no_duplicate_implementation(old, canonical, symbol):
    old_mod, owner_mod = import_module(old), import_module(canonical)
    assert getattr(old_mod, symbol) is getattr(owner_mod, symbol)
    src = Path(old_mod.__file__).read_text("utf-8")
    declarations = [n.name for n in ast.parse(src).body if isinstance(n, (ast.ClassDef, ast.FunctionDef))]
    assert set(declarations) <= {"__getattr__", "__dir__"}
    assert "from tools.rooms." in src
    assert "from tools.furnish_apartment import" not in Path(owner_mod.__file__).read_text("utf-8")


@pytest.mark.parametrize("old,canonical,symbol", CASES)
def test_old_public_modules_keep_access_to_owner_constants(old, canonical, symbol):
    old_mod, new_mod = import_module(old), import_module(canonical)
    names = [n for n in dir(new_mod) if n.isupper() and not n.startswith("_")]
    for n in names:
        assert getattr(old_mod, n) is getattr(new_mod, n)
