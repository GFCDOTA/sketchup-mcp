"""Fachada FP-042/R6: implementacao unica em `tools.rendering.providers.render_provider`.

Preserva `import interior.renderers.render_provider`, `python -m interior.renderers.render_provider` e `python interior/renderers/render_provider.py`; nada de logica aqui.
Consumidor da fachada: compatibilidade de caminho antigo. Remover quando nenhum restar.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_TARGET = "tools.rendering.providers.render_provider"
if __name__ == "__main__":
    import runpy

    runpy.run_module(_TARGET, run_name="__main__", alter_sys=True)
else:
    import importlib

    sys.modules[__name__] = importlib.import_module(_TARGET)
