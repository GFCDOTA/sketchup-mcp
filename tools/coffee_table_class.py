"""Legacy facade. Canonical owner: tools.rooms.living.coffee_table_class; exported API kept stable."""
from __future__ import annotations
from tools.rooms.living import coffee_table_class as _impl

sofa_satellite_gate = _impl.sofa_satellite_gate
CoffeeTableClassSpec = _impl.CoffeeTableClassSpec
build_coffee_table_v2 = _impl.build_coffee_table_v2
derive_coffee_spec = _impl.derive_coffee_spec
coffee_table_class_gate = _impl.coffee_table_class_gate
_sabotages = _impl._sabotages
_apply_sab = _impl._apply_sab
build_matrix = _impl.build_matrix

__all__ = [n for n in dir(_impl) if not n.startswith("_")]

def __getattr__(name):
    if name.startswith("__"):
        raise AttributeError(name)
    return getattr(_impl, name)

def __dir__():
    return sorted(set(globals()) | set(dir(_impl)))

if __name__ == "__main__":
    import runpy
    runpy.run_module("tools.rooms.living.coffee_table_class", run_name="__main__")
