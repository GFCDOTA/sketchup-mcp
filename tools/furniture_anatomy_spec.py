"""Legacy public API for the shared parametric anatomy builder.

Implementation and geometry are owned by tools.rooms.shared.anatomy.
Keep all historical names and python -m CLI behavior.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.rooms.shared import anatomy as _impl  # noqa: E402

SofaSpec = _impl.SofaSpec
BedSpec = _impl.BedSpec
WardrobeSpec = _impl.WardrobeSpec
NightstandSpec = _impl.NightstandSpec
sofa_spec = _impl.sofa_spec
bed_spec = _impl.bed_spec
wardrobe_spec = _impl.wardrobe_spec
nightstand_spec = _impl.nightstand_spec


def __getattr__(name: str):
    if name.startswith("__"):
        raise AttributeError(name)
    return getattr(_impl, name)


def __dir__():
    return sorted(set(globals()) | set(dir(_impl)))


if __name__ == "__main__":
    import runpy
    runpy.run_module("tools.rooms.shared.anatomy", run_name="__main__")
