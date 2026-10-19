"""Fachada FP-043/P4: implementacao unica em `tools.rendering.compose_side_by_side`.

Preserva `import tools.compose_side_by_side`, `python -m tools.compose_side_by_side` e `python tools/compose_side_by_side.py`; nada de logica aqui.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_TARGET = "tools.rendering.compose_side_by_side"
if __name__ == "__main__":
    import runpy

    runpy.run_module(_TARGET, run_name="__main__", alter_sys=True)
else:
    import importlib

    sys.modules[__name__] = importlib.import_module(_TARGET)
