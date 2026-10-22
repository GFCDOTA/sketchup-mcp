"""Primitivas de peca em `shared/parts.py` (SOLID: dependencia na direcao certa).

Cama, guarda-roupa, criado-mudo, mesas, rack e decor importavam o modulo do SOFA para criar caixa ou girar movel. Agora todos
dependem de `parts`; `sofa.py` so reexporta os nomes antigos (mesmos objetos) para compatibilidade.
"""
from __future__ import annotations

import ast
import math
from pathlib import Path

import pytest

from tools.rooms.shared import parts, sofa

ROOT = Path(__file__).resolve().parents[1]
GENERIC = {"_p", "_darker", "parts_to_boxes", "place_sofa_boxes", "PT_TO_IN"}


def test_sofa_reexports_are_the_same_objects():
    assert sofa._p is parts.part and sofa._darker is parts.darker
    assert sofa.place_sofa_boxes is parts.place_parts and sofa.parts_to_boxes is parts.parts_to_boxes


def test_no_builder_takes_generic_helpers_from_the_sofa_module():
    """So o proprio sofa (e testes do sofa) podem pegar primitiva via `shared.sofa`; o resto usa `shared.parts`."""
    offenders = []
    for path in list((ROOT / "tools").rglob("*.py")) + list((ROOT / "interior").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "tools.rooms.shared.sofa":
                bad = {a.name for a in node.names} & GENERIC
                if bad:
                    offenders.append(f"{path.relative_to(ROOT).as_posix()}:{node.lineno} {sorted(bad)}")
    assert offenders == [], offenders


def test_part_normalizes_corners_and_rounds():
    p = parts.part("t", "top", 1.0, 0.5, 0.0, 0.0, 0.7, 0.74, (1, 2, 3))
    assert (p["x0"], p["x1"], p["y0"], p["y1"]) == (0.0, 1.0, 0.0, 0.5) and p["rgb"] == [1, 2, 3]
    assert parts.darker((100, 200, 10), 0.5) == [50, 100, 5]


@pytest.mark.parametrize("facing", [(0, -1), (0, 1), (1, 0), (-1, 0), (0.6, 0.8)])
def test_place_parts_keeps_size_and_turns_the_front_to_facing(facing):
    box = parts.part("b", "base", 0.0, 0.0, 2.0, 1.0, 0.0, 0.4, (0, 0, 0))
    placed = parts.place_parts([box], (100.0, 50.0), facing)[0]
    xs, ys = [c[0] for c in placed["corners"]], [c[1] for c in placed["corners"]]
    assert sum(xs) / 4 == pytest.approx(100.0, abs=0.02) and sum(ys) / 4 == pytest.approx(50.0, abs=0.02)
    edges = sorted(math.dist(placed["corners"][i], placed["corners"][(i + 1) % 4]) for i in range(4))
    assert edges[0] == pytest.approx(1.0 * parts.PT_TO_IN, abs=0.05) and edges[-1] == pytest.approx(2.0 * parts.PT_TO_IN, abs=0.05)
    assert placed["h_in"] == pytest.approx(0.4 * parts.PT_TO_IN, abs=0.01)
