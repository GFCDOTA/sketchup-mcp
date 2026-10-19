"""Public compatibility module: kitchen's layout brain lives in tools.rooms.kitchen.layout.

Existing direct imports and the CLI entrypoint remain valid. Never implement
kitchen geometry in this facade.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.rooms.kitchen import layout as _kitchen  # noqa: E402

build_boxes = _kitchen.build_boxes
main = _kitchen.main


def __getattr__(name: str):
    if name.startswith("__"):
        raise AttributeError(name)
    return getattr(_kitchen, name)


def __dir__():
    return sorted(set(globals()) | set(dir(_kitchen)))


if __name__ == "__main__":
    main()
