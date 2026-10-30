"""FP-043 P3b (#457): launchers do PR #296 nao apontam para raizes que nao existem mais (`E:\\Claude\\sketchup-mcp[-mobiliar]`).

O repo mora em `E:\\Claude\\apps\\sketchup-mcp` desde a revisao do workspace (2026-09-19). Um launcher com a raiz antiga morre ao ler a primeira
entrada (FileNotFoundError / Copy-Item) — o smoke "dos launchers" nunca teria como passar.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
LAUNCHERS = (
    "tools/sketchup/furnish/place_layout_skp.py",
    "tools/rooms/bedroom/capabilities/place_bedroom_skp.py",
    "tools/furnish_plan.py",
    "tools/furnish_apartment.py",
    "tools/rooms/bathroom/capabilities/render_banho_vray.py",
    "tools/rooms/kitchen/capabilities/vray.py",
    "tools/rooms/kitchen/capabilities/bake_theme.py",
    "tools/rendering/render_room.ps1",
)
DEAD_ROOT = re.compile(r"E:[\\/]+Claude[\\/]+sketchup-mcp(?:-mobiliar)?(?![\w-])", re.IGNORECASE)


def _code_lines(text: str):
    for n, line in enumerate(text.splitlines(), 1):
        code = line.split("#", 1)[0]                       # comentario pode citar o caminho antigo (historia), codigo nao
        yield n, code


@pytest.mark.parametrize("relative", LAUNCHERS)
def test_launcher_code_has_no_absolute_path_to_a_root_that_no_longer_exists(relative):
    text = (REPO / relative).read_text("utf-8")
    dead = [(n, code.strip()[:100]) for n, code in _code_lines(text) if DEAD_ROOT.search(code)]
    assert dead == [], f"{relative} aponta para raiz morta: {dead}"


def test_furnish_plan_root_is_this_repository_and_its_inputs_exist():
    from tools import furnish_plan
    assert furnish_plan.ROOT == REPO
    assert furnish_plan.CONSENSUS.exists() and furnish_plan.BASE_SKP.exists()


def test_render_room_script_resolves_everything_from_its_own_location_and_never_writes_to_the_canonical_folder():
    ps1 = (REPO / "tools/rendering/render_room.ps1").read_text("utf-8")
    assert "$PSScriptRoot" in ps1
    assert re.search(r"\$fdir\s*=.*runs", ps1), "o PNG nao pode ser gravado em artifacts/planta_74/furnished (canonico)"
    for rel in ("tools/sketchup/vray/vray_export.rb", "tools/rendering/tweak_vrscene.py", "assets/textures/procedural",
                "artifacts/planta_74/furnished/planta_74_furnished.skp"):
        assert (REPO / rel).exists(), rel
        assert rel.replace("/", "\\") in ps1 or rel in ps1, f"render_room.ps1 deveria referenciar {rel}"


def test_render_room_script_does_not_leave_its_own_sketchup_open_and_kills_nothing_by_name():
    ps1 = (REPO / "tools/rendering/render_room.ps1").read_text("utf-8")
    assert "Stop-Process -Id $p.Id" in ps1                              # smoke de 2026-10-25: o SketchUp do proprio script ficava aberto
    assert not re.search(r"Stop-Process\s+-Name|taskkill[^\n]*/IM", ps1, re.I)
