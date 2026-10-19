"""Compatibility surface for the canonical living-room placement planner.

The implementation lives in tools.rooms.living.planner. Preserve historical
imports and python interior/planners/living_room_planner.py CLI execution.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.rooms.living import planner as _impl  # noqa: E402

plan_living = _impl.plan_living


def __getattr__(name: str):
    if name.startswith("__"):
        raise AttributeError(name)
    return getattr(_impl, name)


def __dir__():
    return sorted(set(globals()) | set(dir(_impl)))


if __name__ == "__main__":
    import runpy
    runpy.run_module("tools.rooms.living.planner", run_name="__main__")
