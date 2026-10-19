"""Fachada pública para o layout de bathroom; implementation única em tools.rooms.bathroom.layout.

Preserva import histórico, API de helpers e execução CLI standalone.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.rooms.shared.geometry import _door_zones, _fbox, _wall_setup, _window_zones  # noqa: E402,F401
from tools.rooms.bathroom import layout as _impl  # noqa: E402

build_boxes = _impl.build_boxes


def __getattr__(name: str):
    if name.startswith("__"):
        raise AttributeError(name)
    return getattr(_impl, name)


def __dir__():
    return sorted(set(globals()) | set(dir(_impl)))


def main():
    # Preserve standalone legacy output while executing canonical room provider.
    import json
    con = json.loads((ROOT / "fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json").read_text("utf-8"))
    for room in ("r005", "r006", "r007"):
        boxes, out = build_boxes(con, room)
        print(room, out.get("room_name"), out["result"], out.get("pecas"))


if __name__ == "__main__":
    main()
