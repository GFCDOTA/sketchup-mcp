"""Fachada FP-042/R6: implementacao unica em `tools.rooms.shared.placement.wall_affordance`.

Preserva `import interior.semantics.wall_affordance`, `python -m interior.semantics.wall_affordance` e `python interior/semantics/wall_affordance.py`; nada de logica aqui.
Consumidor da fachada: testes de compatibilidade (tests/test_fp042_living_planner_ownership.py). Remover quando nenhum restar.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_TARGET = "tools.rooms.shared.placement.wall_affordance"
if __name__ == "__main__":
    import runpy

    runpy.run_module(_TARGET, run_name="__main__", alter_sys=True)
else:
    import importlib

    sys.modules[__name__] = importlib.import_module(_TARGET)
