"""Fachada FP-043/P4: implementacao unica em `tools.knowledge.pdf.export_claude_context`.

Preserva `import tools.pdf_knowledge.export_claude_context`, `python -m tools.pdf_knowledge.export_claude_context` e `python tools/pdf_knowledge/export_claude_context.py`; nada de logica aqui.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_TARGET = "tools.knowledge.pdf.export_claude_context"
if __name__ == "__main__":
    import runpy

    runpy.run_module(_TARGET, run_name="__main__", alter_sys=True)
else:
    import importlib

    sys.modules[__name__] = importlib.import_module(_TARGET)
