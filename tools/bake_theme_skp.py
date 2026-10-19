"""Fachada FP-043/P4: implementacao unica em `tools.rooms.kitchen.capabilities.bake_theme`.

Preserva `import tools.bake_theme_skp`, `python -m tools.bake_theme_skp` e `python tools/bake_theme_skp.py`; nada de logica aqui.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_TARGET = "tools.rooms.kitchen.capabilities.bake_theme"
if __name__ == "__main__":
    import runpy

    runpy.run_module(_TARGET, run_name="__main__", alter_sys=True)
else:
    import importlib

    sys.modules[__name__] = importlib.import_module(_TARGET)
