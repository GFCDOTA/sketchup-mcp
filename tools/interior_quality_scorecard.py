"""Fachada FP-043/P4: implementacao unica em `tools.interior_studio.interior_quality_scorecard`.

Preserva `import tools.interior_quality_scorecard`, `python -m tools.interior_quality_scorecard` e `python tools/interior_quality_scorecard.py`; nada de logica aqui.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_TARGET = "tools.interior_studio.interior_quality_scorecard"
if __name__ == "__main__":
    import runpy

    runpy.run_module(_TARGET, run_name="__main__", alter_sys=True)
else:
    import importlib

    sys.modules[__name__] = importlib.import_module(_TARGET)
