"""Fachada FP-043/P4: implementacao unica em `tools.rendering.gen_textures`.

Preserva `import tools.gen_textures`, `python -m tools.gen_textures` e `python tools/gen_textures.py`; nada de logica aqui.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_TARGET = "tools.rendering.gen_textures"
if __name__ == "__main__":
    import runpy

    runpy.run_module(_TARGET, run_name="__main__", alter_sys=True)
else:
    import importlib

    sys.modules[__name__] = importlib.import_module(_TARGET)
