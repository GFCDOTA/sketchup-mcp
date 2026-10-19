"""Fachada FP-043/P4: implementacao unica em `tools.rooms.shared.spatial_model`.

Preserva `import tools.spatial_model`, `python -m tools.spatial_model` e `python tools/spatial_model.py`; nada de logica aqui.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_TARGET = "tools.rooms.shared.spatial_model"
if __name__ == "__main__":
    import runpy

    runpy.run_module(_TARGET, run_name="__main__", alter_sys=True)
else:
    import importlib

    sys.modules[__name__] = importlib.import_module(_TARGET)
