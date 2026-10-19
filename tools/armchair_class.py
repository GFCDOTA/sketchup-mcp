"""Legacy facade. Canonical owner: tools.rooms.living.armchair_class; exported API kept stable."""
from __future__ import annotations
from tools.rooms.living import armchair_class as _impl

derive_armchair_spec = _impl.derive_armchair_spec
armchair_class_gate = _impl.armchair_class_gate
_raw = _impl._raw
_sabotages = _impl._sabotages
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
    runpy.run_module("tools.rooms.living.armchair_class", run_name="__main__")
