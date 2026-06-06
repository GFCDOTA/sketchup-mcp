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


# ---- --render given but sidecar MISSING -> INCOMPLETE (not silent green) ----


def _write_consensus(tmp_path, walls):
    import json
    con = {"wall_thickness_pts": 5.4, "walls": walls, "openings": []}
    p = tmp_path / "c.json"
    p.write_text(json.dumps(con), encoding="utf-8")
    return p


def _good_render(path):
    """A valid PNG with content well inside the frame (passes render_bbox), so
    these tests isolate the sidecar/INCOMPLETE behavior, not framing."""
    import numpy as np
    from PIL import Image
    img = np.full((200, 200, 3), 200, np.uint8)
    img[60:140, 60:140] = 20  # centered content, margins ~60 >= 32
    Image.fromarray(img).save(path)
    return path


def test_render_without_sidecar_is_incomplete(tmp_path):
    cpath = _write_consensus(
        tmp_path, [{"id": "a", "start": [0, 0], "end": [100, 0]}])
    render = tmp_path / "top.png"
    _good_render(render)  # no sibling .proj.json -> wall_presence can't run
    res = run_all(consensus_path=str(cpath), render_path=str(render))
    assert res["overall"] == "INCOMPLETE"
    wp = res["gates"]["wall_presence"]
    assert wp["verdict"] == "SKIPPED_NO_SIDECAR"
    assert "sidecar" in wp


def test_fail_beats_incomplete(tmp_path):
    # duplicate walls -> wall_overlap FAIL; render w/o sidecar would be
    # INCOMPLETE. FAIL must win (a real defect outranks a coverage gap).
    cpath = _write_consensus(tmp_path, [
        {"id": "a", "start": [0, 0], "end": [100, 0]},
        {"id": "b", "start": [0, 0], "end": [100, 0]}])
    render = tmp_path / "top.png"
    _good_render(render)
    res = run_all(consensus_path=str(cpath), render_path=str(render))
    if res["gates"]["wall_overlap"]["overall"] == "FAIL":
        assert res["overall"] == "FAIL"


def test_cli_exit_code_3_on_incomplete(tmp_path):
    # The crux (oracle :8765): CI gates on the EXIT CODE, not on stdout. A
    # missing sidecar must produce a non-zero, non-FAIL exit so green can't ship
    # sidecar-less. 3 (not argparse's usage-error 2).
    import subprocess
    import sys
    cpath = _write_consensus(
        tmp_path, [{"id": "a", "start": [0, 0], "end": [100, 0]}])
    render = tmp_path / "top.png"
    _good_render(render)
    r = subprocess.run(
        [sys.executable, "-m", "tools.run_deterministic_gates",
         "--consensus", str(cpath), "--render", str(render)],
        cwd=REPO, capture_output=True, text=True)
    assert r.returncode == 3, (r.returncode, r.stdout, r.stderr)
    assert "INCOMPLETE" in r.stdout
    assert "SKIPPED_NO_SIDECAR" in r.stdout
