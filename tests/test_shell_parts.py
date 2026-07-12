"""test_shell_parts.py — envelope do render iso (walls before contents).

Rails pinados: nunca inventa (consensus vazio → []); porta FURA a massa; janela
NÃO fura (Hard Rule #2 — vira cor); mesma transformação dos móveis (pts×PT_TO_IN,
sem flip); corte dollhouse ~1.1 m.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.shell_parts import M_TO_IN, RGB_WALL, RGB_WINDOW, WALL_CUT_M, shell_parts  # noqa: E402

PT_TO_IN = 0.0259 * M_TO_IN  # escala congelada da planta_74


def _wall(id="w1", start=(0.0, 100.0), end=(200.0, 100.0), ori="h", t=6.0):
    return {"id": id, "start": list(start), "end": list(end),
            "orientation": ori, "thickness": t}


def test_empty_consensus_never_invents():
    assert shell_parts({}) == []
    assert shell_parts({"walls": [], "openings": []}) == []


def test_wall_becomes_box_in_shell_inches_no_flip():
    parts = shell_parts({"walls": [_wall()]}, pt_to_in=PT_TO_IN)
    assert len(parts) == 1
    p = parts[0]
    assert p["kind"] == "shell_wall" and p["rgb"] == RGB_WALL
    assert p["x0"] == pytest.approx(0.0)
    assert p["x1"] == pytest.approx(200.0 * PT_TO_IN)
    assert p["y0"] == pytest.approx(97.0 * PT_TO_IN)      # centro 100 ± t/2, sem flip
    assert p["y1"] == pytest.approx(103.0 * PT_TO_IN)
    assert p["z1"] == pytest.approx(WALL_CUT_M * M_TO_IN)  # corte dollhouse


def test_door_carves_gap_window_does_not():
    con = {
        "walls": [_wall()],
        "openings": [
            {"id": "d1", "kind": "door", "wall_id": "w1",
             "center": [50.0, 100.0], "opening_width_pts": 20.0},
            {"id": "j1", "kind": "window", "wall_id": "w1",
             "center": [150.0, 100.0], "opening_width_pts": 30.0},
        ],
    }
    parts = shell_parts(con, pt_to_in=PT_TO_IN)
    walls = [p for p in parts if p["kind"] == "shell_wall"]
    wins = [p for p in parts if p["kind"] == "shell_window"]
    # porta em [40,60] parte a massa em 2 segmentos: [0,40] e [60,200]
    assert len(walls) == 2
    assert walls[0]["x1"] == pytest.approx(40.0 * PT_TO_IN)
    assert walls[1]["x0"] == pytest.approx(60.0 * PT_TO_IN)
    # janela [135,165]: massa CONTÍNUA por baixo (segmento [60,200] cobre) + faixa azulada
    assert walls[1]["x1"] == pytest.approx(200.0 * PT_TO_IN)  # não furou
    assert len(wins) == 1 and wins[0]["rgb"] == RGB_WINDOW
    assert wins[0]["x0"] == pytest.approx(135.0 * PT_TO_IN)


def test_vertical_wall_and_foreign_opening_ignored():
    con = {
        "walls": [_wall(id="v1", start=(50.0, 0.0), end=(50.0, 300.0), ori="v", t=8.0)],
        "openings": [{"id": "dx", "kind": "door", "wall_id": "OUTRA",
                      "center": [50.0, 150.0], "opening_width_pts": 40.0}],
    }
    parts = shell_parts(con, pt_to_in=PT_TO_IN)
    assert len(parts) == 1                                 # opening de outra wall não corta
    p = parts[0]
    assert p["y0"] == pytest.approx(0.0) and p["y1"] == pytest.approx(300.0 * PT_TO_IN)
    assert p["x0"] == pytest.approx(46.0 * PT_TO_IN) and p["x1"] == pytest.approx(54.0 * PT_TO_IN)


def test_real_consensus_planta_74_aligns_with_furniture_system():
    """Fixture real: 20 walls → massa no MESMO sistema dos móveis. bbox do shell
    deve conter área plausível (não-degenerada) e todas as portas devem ter furado
    pelo menos um segmento (mais partes que walls)."""
    import json
    con = json.loads((ROOT / "fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json")
                     .read_text("utf-8"))
    parts = shell_parts(con, pt_to_in=PT_TO_IN)
    walls = [p for p in parts if p["kind"] == "shell_wall"]
    assert len(walls) > len(con["walls"])                  # portas partiram massas
    xs = [p["x0"] for p in walls] + [p["x1"] for p in walls]
    ys = [p["y0"] for p in walls] + [p["y1"] for p in walls]
    w_m = (max(xs) - min(xs)) / M_TO_IN
    h_m = (max(ys) - min(ys)) / M_TO_IN
    assert 5.0 < w_m < 30.0 and 5.0 < h_m < 30.0          # apê ~74m² plausível
