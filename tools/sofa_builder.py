"""Legacy public API for the shared parametric sofa builder.

Implementation and geometry are owned by tools.rooms.shared.sofa.
Keep all historical names and python -m CLI behavior.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.rooms.shared import sofa as _impl  # noqa: E402

build_sofa = _impl.build_sofa
place_sofa_boxes = _impl.place_sofa_boxes
parts_to_boxes = _impl.parts_to_boxes
_p = _impl._p
_darker = _impl._darker


def __getattr__(name: str):
    if name.startswith("__"):
        raise AttributeError(name)
    return getattr(_impl, name)


def __dir__():
    return sorted(set(globals()) | set(dir(_impl)))


if __name__ == "__main__":
    import runpy
    runpy.run_module("tools.rooms.shared.sofa", run_name="__main__")
