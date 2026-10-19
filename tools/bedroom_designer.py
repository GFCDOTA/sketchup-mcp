"""Legacy public adapter for the bedroom design pipeline.

All layout/render behavior belongs to tools.rooms.bedroom.designer.
"""
from __future__ import annotations

from tools.rooms.bedroom import designer as _impl
from tools.rooms.shared.geometry import (  # noqa: F401 — old re-exports
    _fbox, _wall_setup, _window_zones, _door_zones,
)

run = _impl.run
_items_to_boxes = _impl._items_to_boxes
build_layout = _impl.build_layout
build_skp = _impl.build_skp
main = _impl.main


def __getattr__(name):
    if name.startswith("__"):
        raise AttributeError(name)
    return getattr(_impl, name)


def __dir__():
    return sorted(set(globals()) | set(dir(_impl)))


if __name__ == "__main__":
    main()
