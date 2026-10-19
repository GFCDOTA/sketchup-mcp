"""FP-043/P3b — NENHUM codigo rastreado encerra processo por NOME (varredura do repo inteiro, nao so os 10 migrados).

O L2 da P3b achou 4 chamadas `taskkill /F /IM SketchUp.exe` fora da lista do PR #296 (material_review, designer de quarto,
sofa_premium_harness). Depois da P4 os arquivos "migrados" viraram fachadas e `test_fp043_no_global_taskkill` passava no
vazio. Aqui: toda CHAMADA (subprocess/os.system/...) em qualquer .py rastreado, e toda linha de codigo em .ps1/.cmd/.sh/.rb.
Docstring e mensagem que citam `taskkill /IM` para PROIBIR nao contam.
"""
from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = ("tests/", "docs/archive/", "artifacts/", "runs/", ".claude/")
NON_PY = re.compile(r"taskkill[^\n]*?/IM|Stop-Process\s+-Name|Get-Process[^\n|]*\|\s*Stop-Process|\bpkill\b|\bkillall\b", re.I)
IM = re.compile(r"/IM\b", re.I)


def tracked_code() -> list[str]:
    out = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode("utf-8").split("\0")
    return [f for f in out if f.endswith((".py", ".ps1", ".cmd", ".bat", ".sh", ".rb")) and not f.startswith(EXCLUDED)]


def _strings(call: ast.Call) -> list[str]:
    found: list[str] = []
    for arg in list(call.args) + [k.value for k in call.keywords]:
        for sub in ast.walk(arg):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                found.append(sub.value)
    return found


def py_offenders(rel: str, text: str) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(text)):
        if not isinstance(node, ast.Call):
            continue
        strings = _strings(node)
        joined = " ".join(strings)
        if any(s.lower().startswith("taskkill") for s in strings) and IM.search(joined):
            found.append(f"{rel}:{node.lineno}: taskkill /IM")
        if re.search(r"Stop-Process\s+-Name|\bpkill\b|\bkillall\b", joined, re.I):
            found.append(f"{rel}:{node.lineno}: kill por nome")
    return found


def test_nenhum_codigo_rastreado_encerra_processo_por_nome():
    offenders: list[str] = []
    for rel in tracked_code():
        text = (ROOT / rel).read_text("utf-8", errors="replace")
        if rel.endswith(".py"):
            offenders += py_offenders(rel, text)
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if NON_PY.search(line) and not line.lstrip().startswith(("#", "//", "REM", "::")):
                offenders.append(f"{rel}:{n}: {line.strip()[:90]}")
    assert offenders == [], "\n".join(offenders)


def test_detector_pega_chamada_real_e_ignora_texto():
    bad = "import subprocess\nsubprocess.run(['taskkill', '/F', '/IM', 'SketchUp.exe'])\n"
    sys_call = "import os\nos.system('taskkill /F /IM SketchUp.exe')\n"
    text_only = 'def f():\n    """nunca taskkill /IM SketchUp.exe"""\n    print("nao use taskkill /IM")\n'
    by_pid = "import subprocess\nsubprocess.run(['taskkill', '/PID', '12', '/F'])\n"
    assert py_offenders("a.py", bad) and py_offenders("b.py", sys_call)
    assert not py_offenders("c.py", text_only) and not py_offenders("d.py", by_pid)
    assert NON_PY.search("taskkill /F /IM SketchUp.exe") and not NON_PY.search("taskkill /PID 12 /F")
