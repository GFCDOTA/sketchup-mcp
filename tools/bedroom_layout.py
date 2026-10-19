"""Legacy CLI and public API for the bedroom layout brain.

The implementation lives in tools.rooms.bedroom.layout.
"""
from __future__ import annotations

from tools.rooms.bedroom import layout as _impl
from tools.rooms.shared.geometry import (  # noqa: F401 — old imports remain
    _fbox, _wall_setup, _perp_depth, _window_zones, _door_zones,
)

run = _impl.run
plot = _impl.plot
main = _impl.main


def __getattr__(name):
    if name.startswith("__"):
        raise AttributeError(name)
    return getattr(_impl, name)


def __dir__():
    return sorted(set(globals()) | set(dir(_impl)))


if __name__ == "__main__":
    main()
