"""FP-030 overlay/diff — wall-presence detection core (calibration-independent).

Synthetic masks with a known (identity) transform lock the detection contract:
a present wall passes; an erased wall is flagged with exactly one finding. The
real planta_74 affine calibration is validated separately (needs the render).
"""
from __future__ import annotations

import numpy as np

from tools.overlay_diff import (
    Affine,
    dark_mask,
    detect_missing_walls,
    wall_segment_coverage,
)

# Identity transform: consensus coords == pixel coords (no flip) for the synthetic.
IDENT = Affine(a=1.0, b=0.0, c=1.0, d=0.0)


def _blank(h=150, w=200):
    # bright background (like a render's empty space)
    return np.full((h, w, 3), 230, dtype=np.uint8)


def _draw_hwall(img, x0, x1, y, half=2, val=90):
    img[y - half:y + half + 1, x0:x1 + 1, :] = val


# three horizontal walls
WALLS = [
    {"id": "wA", "start": [20, 30], "end": [180, 30], "orientation": "h"},
    {"id": "wB", "start": [20, 75], "end": [180, 75], "orientation": "h"},
    {"id": "wC", "start": [20, 120], "end": [180, 120], "orientation": "h"},
]


def _scene_all_present():
    img = _blank()
    for w in WALLS:
        _draw_hwall(img, w["start"][0], w["end"][0], w["start"][1])
    return img


def test_all_walls_present_no_findings():
    mask = dark_mask(_scene_all_present())
    findings = detect_missing_walls(mask, IDENT, WALLS)
    assert findings == []


def test_present_wall_full_coverage():
    mask = dark_mask(_scene_all_present())
    cov = wall_segment_coverage(mask, IDENT, (20, 75), (180, 75))
    assert cov > 0.95


def test_erased_wall_is_flagged_exactly_once():
    img = _scene_all_present()
    # erase wall B: paint its band back to background
    img[75 - 4:75 + 5, 20:181, :] = 230
    mask = dark_mask(img)
    findings = detect_missing_walls(mask, IDENT, WALLS)
    assert len(findings) == 1
    assert findings[0]["wall_id"] == "wB"
    assert findings[0]["type"] == "missing_wall_continuation"
    assert findings[0]["coverage"] < 0.6


def test_partial_gap_opening_does_not_flag():
    """A small opening (door/window) along a wall must NOT flag the wall as
    missing — coverage stays above threshold."""
    img = _scene_all_present()
    # knock a small ~24px gap (opening) in wall B out of its 160px span
    img[75 - 4:75 + 5, 90:114, :] = 230
    mask = dark_mask(img)
    findings = detect_missing_walls(mask, IDENT, WALLS)
    assert all(f["wall_id"] != "wB" for f in findings)


def test_dark_mask_threshold():
    img = _blank()
    img[0:5, 0:5, :] = 90  # dark patch
    m = dark_mask(img)
    assert m[0, 0] and not m[100, 100]


# ---- real planta_74 render: exact sidecar calibration (FP-031 #2) ----
import json
from pathlib import Path

import pytest

from tools.overlay_diff import affine_from_sidecar, run_gate, wall_inframe_fraction

REPO = Path(__file__).resolve().parents[1]
RENDER = REPO / "tests" / "data" / "overlay_gate" / "planta74_top.png"
PROJ = REPO / "tests" / "data" / "overlay_gate" / "planta74_top.png.proj.json"
CONSENSUS = (REPO / "fixtures" / "planta_74"
             / "consensus_with_human_walls_and_soft_barriers.json")
_HAVE_DATA = RENDER.exists() and PROJ.exists() and CONSENSUS.exists()
pytestmark_data = pytest.mark.skipif(not _HAVE_DATA, reason="gate test data absent")


def _load_render():
    Image = pytest.importorskip("PIL.Image")
    return np.asarray(Image.open(RENDER).convert("RGB")).copy()


@pytestmark_data
def test_affine_from_sidecar_centers_target():
    proj = json.loads(PROJ.read_text("utf-8"))
    aff = affine_from_sidecar(proj)
    tx, ty = proj["cam_target_in"]
    px, py = aff.project(tx / proj["pt_to_in"], ty / proj["pt_to_in"])
    assert abs(px - proj["img_w"] / 2) < 1.0
    assert abs(py - proj["img_h"] / 2) < 1.0


@pytestmark_data
def test_real_planta74_clean_passes_with_sidecar():
    res = run_gate(str(RENDER), str(CONSENSUS))
    assert res["calibration"] == "sidecar_exact"
    assert res["verdict"] == "PASS", [f["wall_id"] for f in res["findings"]]
    assert res["n_walls"] >= 15   # 19 after the FP-031 collinear merge


@pytestmark_data
def test_real_planta74_erased_wall_is_flagged():
    pytest.importorskip("PIL.Image")
    rgb = _load_render()
    con = json.loads(CONSENSUS.read_text("utf-8"))
    proj = json.loads(PROJ.read_text("utf-8"))
    aff = affine_from_sidecar(proj)
    walls = con["walls"]
    mask = dark_mask(rgb, 160)
    # pick a fully in-frame, currently-present wall to erase
    target = None
    for w in walls:
        s, e = tuple(w["start"]), tuple(w["end"])
        if (wall_inframe_fraction(aff, s, e, mask.shape) > 0.95
                and wall_segment_coverage(mask, aff, s, e, radius=8) > 0.9):
            target = w
            break
    assert target is not None, "no clean in-frame wall found to erase"
    # erase: paint a fat corridor along its projected segment to background grey
    s, e = target["start"], target["end"]
    H, W = mask.shape
    for i in range(41):
        t = i / 40.0
        px, py = aff.project(s[0] + (e[0] - s[0]) * t, s[1] + (e[1] - s[1]) * t)
        px, py = int(round(px)), int(round(py))
        y0, y1 = max(0, py - 12), min(H, py + 13)
        x0, x1 = max(0, px - 12), min(W, px + 13)
        rgb[y0:y1, x0:x1, :] = (191, 191, 198)  # background grey
    findings = detect_missing_walls(
        dark_mask(rgb, 160), aff, walls, coverage_threshold=0.6, radius=8,
    )
    assert any(f["wall_id"] == target["id"] for f in findings), \
        f"erased wall {target['id']} not flagged"


@pytestmark_data
def test_real_planta74_no_wall_clipped_by_frame():
    # FP-031 #29: the deterministic top camera fits the whole plan in the 4:3
    # frame, so EVERY consensus wall is in-frame and the gate can verify it
    # (no perimeter clipping / silent skipping).
    con = json.loads(CONSENSUS.read_text("utf-8"))
    proj = json.loads(PROJ.read_text("utf-8"))
    aff = affine_from_sidecar(proj)
    shape = (proj["img_h"], proj["img_w"])
    clipped = [w["id"] for w in con["walls"]
               if wall_inframe_fraction(aff, tuple(w["start"]),
                                        tuple(w["end"]), shape) < 0.5]
    assert clipped == [], f"walls clipped by render frame: {clipped}"
