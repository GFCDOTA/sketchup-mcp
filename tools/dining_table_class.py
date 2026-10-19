"""Legacy facade. Canonical owner: tools.rooms.living.dining_table_class; exported API kept stable."""
from __future__ import annotations
from tools.rooms.living import dining_table_class as _impl

DiningTableSpec = _impl.DiningTableSpec
_rot_box = _impl._rot_box
_disc_bands = _impl._disc_bands
_oval_end_bands = _impl._oval_end_bands
build_dining_table = _impl.build_dining_table
_seat_anchors = _impl._seat_anchors
_chair_proxy_parts = _impl._chair_proxy_parts
dining_class_gate = _impl.dining_class_gate
chair_satellite_gate = _impl.chair_satellite_gate
circulation_gate = _impl.circulation_gate
derive_dining_spec = _impl.derive_dining_spec
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
    runpy.run_module("tools.rooms.living.dining_table_class", run_name="__main__")
