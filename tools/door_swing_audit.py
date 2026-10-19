"""Fachada FP-043/P4: implementacao unica em `tools.validation.door_swing_audit`.

Preserva `import tools.door_swing_audit`, `python -m tools.door_swing_audit` e `python tools/door_swing_audit.py`; nada de logica aqui.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_TARGET = "tools.validation.door_swing_audit"
if __name__ == "__main__":
    import runpy

    runpy.run_module(_TARGET, run_name="__main__", alter_sys=True)
else:
    import importlib

    sys.modules[__name__] = importlib.import_module(_TARGET)
