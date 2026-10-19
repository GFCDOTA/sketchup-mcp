"""Legacy facade. Canonical owner: tools.rooms.living.sofa_class; exported API kept stable."""
from __future__ import annotations
from tools.rooms.living import sofa_class as _impl

derive_spec = _impl.derive_spec
derive_living_sofa = _impl.derive_living_sofa
sofa_class_gate = _impl.sofa_class_gate
_sabotages = _impl._sabotages
_raw = _impl._raw

__all__ = [n for n in dir(_impl) if not n.startswith("_")]

def __getattr__(name):
    if name.startswith("__"):
        raise AttributeError(name)
    return getattr(_impl, name)

def __dir__():
    return sorted(set(globals()) | set(dir(_impl)))

if __name__ == "__main__":
    import runpy
    runpy.run_module("tools.rooms.living.sofa_class", run_name="__main__")
