"""Fachada FP-042/R6: implementacao unica em `tools.orchestration.scene_composer`.

Preserva `import interior.composer.scene_composer`, `python -m interior.composer.scene_composer` e `python interior/composer/scene_composer.py`; nada de logica aqui.
Consumidor da fachada: testes de compatibilidade (tests/test_intent_to_scene.py, tests/test_living_sofa_is_approved_premium.py). Remover quando nenhum restar.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_TARGET = "tools.orchestration.scene_composer"
if __name__ == "__main__":
    import runpy

    runpy.run_module(_TARGET, run_name="__main__", alter_sys=True)
else:
    import importlib

    sys.modules[__name__] = importlib.import_module(_TARGET)
