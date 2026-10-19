"""Legacy facade. Canonical owner: tools.rooms.shared.armchair_builder; exported API kept stable."""
from __future__ import annotations
from tools.rooms.shared import armchair_builder as _impl

_lighter = _impl._lighter
ArmchairSpec = _impl.ArmchairSpec
build_armchair = _impl.build_armchair

__all__ = [n for n in dir(_impl) if not n.startswith("_")]

def __getattr__(name):
    if name.startswith("__"):
        raise AttributeError(name)
    return getattr(_impl, name)

def __dir__():
    return sorted(set(globals()) | set(dir(_impl)))
