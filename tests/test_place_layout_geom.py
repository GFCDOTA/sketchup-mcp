"""Geometria pura do place_layout_skp.rb — inset da pegada da peça macia.

Regressão do L2 (SketchUp real, 2026-10-19): almofada/braço/colchão girados 30°
ganhavam topo inset a partir do AABB do topo e vazavam da pegada planejada
(raytest vertical acertava a peça fora do polígono). Sem `ruby` no PATH pula —
o CI Linux do GitHub tem ruby.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

RUBY = shutil.which("ruby")
pytestmark = pytest.mark.skipif(RUBY is None, reason="ruby não instalado")
TOOLS = Path("tools")


def test_place_layout_e_geom_compilam():
    for rb in (TOOLS / "sketchup" / "furnish" / "place_layout_skp.rb", TOOLS / "sketchup" / "furnish" / "place_layout_geom.rb"):
        r = subprocess.run([RUBY, "-c", str(rb)], capture_output=True, text=True)
        assert r.returncode == 0, f"{rb}: {r.stderr}"


def test_inset_da_pegada_girada():
    r = subprocess.run([RUBY, "tests/ruby/test_place_layout_geom.rb"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_chanfro_nao_usa_mais_o_bounds_do_topo():
    """O topo inset sai do polígono da peça; `top.bounds` (AABB) era a causa do vazamento."""
    src = (TOOLS / "sketchup" / "furnish" / "place_layout_skp.rb").read_text(encoding="utf-8")
    assert "require_relative 'place_layout_geom'" in src
    assert "PlaceLayoutGeom.inset_convex" in src
    assert "bb = top.bounds" not in src
