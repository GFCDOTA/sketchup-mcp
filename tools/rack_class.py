"""Legacy facade. Canonical owner: tools.rooms.living.rack_class; exported API kept stable."""
from __future__ import annotations
from tools.rooms.living import rack_class as _impl

RackSpec = _impl.RackSpec
build_rack = _impl.build_rack
tv_satellite_gate = _impl.tv_satellite_gate
sofa_satellite_gate = _impl.sofa_satellite_gate
derive_rack_spec = _impl.derive_rack_spec
rack_class_gate = _impl.rack_class_gate
_sabotages = _impl._sabotages
_apply_sab = _impl._apply_sab
_tv_proxy_parts = _impl._tv_proxy_parts
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
    runpy.run_module("tools.rooms.living.rack_class", run_name="__main__")
