"""FP-031 — combined deterministic gate suite runner."""
from __future__ import annotations

from pathlib import Path

import pytest

from tools.run_deterministic_gates import run_all

REPO = Path(__file__).resolve().parents[1]
_PLANTA = (REPO / "fixtures" / "planta_74"
           / "consensus_with_human_walls_and_soft_barriers.json")
_QUAD = REPO / "fixtures" / "quadrado" / "consensus_with_window.json"
_RENDER = REPO / "tests" / "data" / "overlay_gate" / "planta74_top.png"


def test_clean_consensus_passes_consensus_gates():
    con = {"wall_thickness_pts": 5.4,
           "walls": [{"id": "a", "start": [0, 0], "end": [100, 0]},
                     {"id": "b", "start": [0, 0], "end": [0, 100]}],
           "openings": [{"id": "d", "center": [50, 0], "wall_id": "a",
                         "opening_width_pts": 20}]}
    # write the in-memory consensus to a temp file and run the suite on it
    import json
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(con, f)
        path = f.name
    res = run_all(consensus_path=path)
    assert res["overall"] == "PASS"
    assert set(res["gates"]) == {"opening_host", "wall_overlap"}


@pytest.mark.skipif(not _PLANTA.exists(), reason="planta_74 fixture absent")
def test_planta74_consensus_gates_pass_after_regen():
    # FP-031 #28: regenerated canonical consensus passes both consensus gates.
    res = run_all(fixture="planta_74")
    assert res["overall"] == "PASS"
    assert res["gates"]["opening_host"]["overall"] == "PASS"
    assert res["gates"]["wall_overlap"]["overall"] == "PASS"
    assert "wall_presence" not in res["gates"]  # no render passed


@pytest.mark.skipif(not (_PLANTA.exists() and _RENDER.exists()),
                    reason="planta_74 render/data absent")
def test_planta74_with_render_includes_wall_presence_pass():
    pytest.importorskip("PIL.Image")
    pytest.importorskip("numpy")
    res = run_all(fixture="planta_74", render_path=str(_RENDER))
    assert "wall_presence" in res["gates"]
    # walls are all present in the clean render -> that sub-gate PASSes
    assert res["gates"]["wall_presence"]["verdict"] == "PASS"


@pytest.mark.skipif(not _QUAD.exists(), reason="quadrado fixture absent")
def test_quadrado_consensus_gates_pass():
    res = run_all(consensus_path=str(_QUAD))
    assert res["overall"] == "PASS"
