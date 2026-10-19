"""FP-043 P4d — a migração por responsabilidade é verificável, não só documentada.

Para cada item do mapa P0 marcado `status: done`:
- o destino existe e está rastreado; o caminho antigo é fachada que SÓ delega (sem def/class/lógica) ou, quando o
  mapa diz `path_resolver_unico`, está ausente e nenhum código ainda o cita;
- import frio em duas ordens (antigo→novo e novo→antigo) devolve o MESMO módulo (um dono por comportamento).
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MAP = json.loads((ROOT / "docs/specs/fp043_p0_map.v1.json").read_text("utf-8"))
DONE = [r for r in MAP["items"] if r.get("status") == "done" and r["disposition"] == "move"]
PY_FACADES = [r for r in DONE if r["item"].endswith(".py") and r.get("compat") == "facade_at_old_path"]
RESOLVED = [r for r in DONE if r.get("compat") == "path_resolver_unico"]


def _mod(path: str) -> str:
    return ".".join(Path(path).with_suffix("").parts)


def _tracked() -> set[str]:
    return set(subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0"))


@pytest.mark.parametrize("row", PY_FACADES, ids=lambda r: r["item"])
def test_origem_e_fachada_que_so_delega(row):
    tree = ast.parse((ROOT / row["item"]).read_text("utf-8"))
    logic = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef))]
    assert logic == [], f"{row['item']} tem logica propria: {[n.name for n in logic]}"
    text = (ROOT / row["item"]).read_text("utf-8")
    assert f'_TARGET = "{_mod(row["destination"])}"' in text
    assert row["destination"] in _tracked()


@pytest.mark.parametrize("row", RESOLVED, ids=lambda r: r["item"])
def test_caminho_unico_resolvido_sem_origem_nem_referencia_de_codigo(row):
    assert not (ROOT / row["item"]).exists()
    assert row["destination"] in _tracked()
    hits = subprocess.run(["git", "grep", "-l", "-F", row["item"], "--", "*.py", "*.rb", "*.ps1", "*.cmd", "*.yml"],
                          cwd=ROOT, capture_output=True, text=True).stdout.split()
    assert hits == [], hits


_PROBE = """
import importlib, sys
pairs = {pairs!r}
order = {order!r}
for old, new in pairs:
    a, b = (old, new) if order == "old_first" else (new, old)
    ma = importlib.import_module(a)
    mb = importlib.import_module(b)
    assert importlib.import_module(old) is importlib.import_module(new), (old, new)
print("OK", len(pairs))
"""


@pytest.mark.parametrize("order", ["old_first", "new_first"])
def test_import_frio_nas_duas_ordens_devolve_o_mesmo_modulo(order):
    pairs = [(_mod(r["item"]), _mod(r["destination"])) for r in PY_FACADES]
    code = "import sys;sys.path.insert(0, sys.argv[1]);" + _PROBE.format(pairs=pairs, order=order)
    done = subprocess.run([sys.executable, "-c", code, str(ROOT)], cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=300)
    assert done.returncode == 0 and "OK" in done.stdout, done.stderr[-1500:]
