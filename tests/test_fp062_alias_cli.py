"""FP-062: `python -m <caminho antigo>` tem que executar o CLI real.

O alias de compatibilidade (`sys.modules[__name__] = impl`) não roda o bloco `__main__` do módulo
movido. Sem o encaminhamento, `python -m tools.orchestration.promote_canonical` sai com código 0 e
não faz nada: o pipeline parece ter rodado e não rodou.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# caminhos antigos documentados como entrypoint (.claude/memory/artifact_policy.md, FP-034)
CLI_OLD_PATHS = [
    "tools.orchestration.promote_canonical",
    "tools.orchestration.variant_sweep",
]


@pytest.mark.parametrize("old_path", CLI_OLD_PATHS)
def test_running_an_old_path_as_module_runs_the_real_cli(old_path):
    proc = subprocess.run(
        [sys.executable, "-m", old_path, "--help"],
        cwd=ROOT, capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    assert "usage:" in proc.stdout, (
        f"`python -m {old_path} --help` não executou o CLI real (saída: {proc.stdout!r})"
    )
