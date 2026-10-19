"""Regressão P3: nenhuma CLI migrada encerra SketchUp.exe por /IM.

A restrição é comportamental: módulos de teste podem citar a string; os
entrypoints reais abaixo não podem chamar taskkill pelo nome. Novas CLIs
SketchUp também devem usar tools.sketchup.batch/legacy_process.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

MIGRATED_PY = (
    "tools/sketchup/furnish/place_layout_skp.py",
    "tools/place_bedroom_skp.py",
    "tools/furnish_plan.py",
    "tools/furnish_apartment.py",
    "tools/render_banho_vray.py",
    "tools/kitchen_vray.py",
    "tools/bake_theme_skp.py",
    "interior/renderers/sketchup_basic_provider.py",
    "interior/renderers/vray_final_provider.py",
)


@pytest.mark.parametrize("relative", MIGRATED_PY)
def test_cli_has_no_global_sketchup_kill(relative):
    path = ROOT / relative
    content = path.read_text("utf-8")
    # Prove syntax before analyzing code; no Windows/SketchUp required.
    tree = ast.parse(content, filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        # Detect command-wide kill even when called through another wrapper.
        if not node.args or not isinstance(node.args[0], (ast.List, ast.Tuple)):
            continue
        args = [x.value for x in node.args[0].elts if isinstance(x, ast.Constant)]
        if args and str(args[0]).lower() == "taskkill":
            assert "/IM" not in args, f"global SketchUp kill in {relative}"
    assert not re.search(r'taskkill\\s+/F\\s+/IM\\s+SketchUp', content, re.I), relative


def test_ps1_closes_only_created_pid():
    script = (ROOT / "tools/render_room.ps1").read_text("utf-8")
    assert "$p=Start-Process" in script and "-PassThru" in script
    assert "$p.CloseMainWindow()" in script
    assert not re.search(r"taskkill[^\\n]*/IM", script, re.I)
