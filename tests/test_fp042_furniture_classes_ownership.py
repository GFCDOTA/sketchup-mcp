"""P3: seven furniture classes have canonical owners and identity-preserving facades."""
from importlib import import_module
from pathlib import Path
import pytest

# fachadas aposentadas na FP-044/F6: o contrato que sobra e o do dono (simbolo definido nele, sem orquestrador)
RETIRED = [["tools.rooms.shared.armchair_builder", "build_armchair"],
           ["tools.rooms.bedroom.bed_class", "derive_bed_spec"],
           ["tools.rooms.living.armchair_class", "derive_armchair_spec"],
           ["tools.rooms.living.coffee_table_class", "build_coffee_table_v2"],
           ["tools.rooms.living.dining_table_class", "build_dining_table"],
           ["tools.rooms.living.rack_class", "build_rack"],
           ["tools.rooms.living.sofa_class", "derive_living_sofa"]]


@pytest.mark.parametrize("owner,symbol", RETIRED)
def test_owner_of_retired_facade_has_the_symbol_and_does_not_import_the_orchestrator(owner, symbol):
    mod = import_module(owner)
    assert callable(getattr(mod, symbol)) and getattr(mod, symbol).__module__ == owner
    assert "from tools.furnish_apartment import" not in Path(mod.__file__).read_text("utf-8")

