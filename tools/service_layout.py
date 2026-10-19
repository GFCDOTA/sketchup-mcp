"""Public legacy module; the SERVICE brain now belongs to tools.rooms.service.layout.

This compatibility facade preserves existing imports and both CLI launch modes.
Do not duplicate room-specific logic here.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Preserve `python tools/service_layout.py` when launched outside a package.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.rooms.service import layout as _service  # noqa: E402

build_boxes = _service.build_boxes
main = _service.main


def __getattr__(name: str):
    """Compatibility for imported old helpers and constants."""
    if name.startswith("__"):
        raise AttributeError(name)
    return getattr(_service, name)


def __dir__():
    return sorted(set(globals()) | set(dir(_service)))


if __name__ == "__main__":
    main()
