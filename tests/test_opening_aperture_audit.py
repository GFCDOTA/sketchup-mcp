"""opening_aperture_audit — BANHO-2 class: opening that did not render as an
aperture (blind pocket). Synthetic micro-fixture locks the contract: a real gap
passes, a blind pocket (solid wall at the opening) is flagged. Calibration-
independent (affine + ratios passed in)."""
from __future__ import annotations

import numpy as np

from tools.opening_aperture_audit import detect_blind_pockets, wall_solidity_ratio
from tools.overlay_diff import Affine, dark_mask

# project(x, y) = (x, 100 - y): pdf-point -> pixel, y flipped (like ortho-top).
AFF = Affine(a=1.0, b=0.0, c=-1.0, d=100.0)


def _render(good_gap=True, bad_gap=False):
    """200x100 white bg with a horizontal dark wall band (rows 45..55).
    A 'gap' punches the wall white (through-aperture) at that opening's x."""
    rgb = np.full((100, 200, 3), 255, np.uint8)
    rgb[45:56, :, :] = 30  # dark wall band across all x
    if good_gap:
        rgb[45:56, 45:56, :] = 255   # real aperture at x~50
    if bad_gap:
        rgb[45:56, 145:156, :] = 255  # aperture at x~150
    return rgb


_CONSENSUS = {
    "wall_thickness_pts": 10,
    "walls": [{"id": "wH", "start": [0, 50], "end": [200, 50]}],
    "openings": [
        {"id": "good", "center": [50, 50], "wall_id": "wH", "opening_width_pts": 10},
        {"id": "bad", "center": [150, 50], "wall_id": "wH", "opening_width_pts": 10},
    ],
}


def test_flags_blind_pocket_passes_real_aperture():
    res = detect_blind_pockets(_CONSENSUS, _render(good_gap=True, bad_gap=False), AFF)
    flagged = {f["id"] for f in res["findings"]}
    assert "bad" in flagged          # blind pocket caught
    assert "good" not in flagged     # real aperture passes
    assert res["overall"] == "FAIL"
    assert res["n_fail"] == 1


def test_all_apertures_present_passes():
    res = detect_blind_pockets(_CONSENSUS, _render(good_gap=True, bad_gap=True), AFF)
    assert res["overall"] == "PASS"
    assert res["n_fail"] == 0


def test_ratio_separates_gap_from_pocket():
    mask = dark_mask(_render(good_gap=True, bad_gap=False), 120)
    wall = _CONSENSUS["walls"][0]
    r_good = wall_solidity_ratio(mask, AFF, _CONSENSUS["openings"][0], wall, 10)
    r_bad = wall_solidity_ratio(mask, AFF, _CONSENSUS["openings"][1], wall, 10)
    assert r_good < 0.3   # real gap: far less solid than its wall
    assert r_bad > 0.8    # blind pocket: as solid as its wall


def test_flag_ratio_is_tunable():
    rgb = _render(good_gap=True, bad_gap=False)
    # a very lenient ratio (>1) flags nothing (nothing is MORE solid than wall)
    res = detect_blind_pockets(_CONSENSUS, rgb, AFF, flag_ratio=1.5)
    assert res["overall"] == "PASS"


def test_no_host_wall_flagged_with_reason():
    con = {"wall_thickness_pts": 10, "walls": [],
           "openings": [{"id": "orphan", "center": [50, 50], "wall_id": "x"}]}
    res = detect_blind_pockets(con, _render(), AFF)
    assert res["findings"][0]["reason"] == "no_host_wall"
    assert res["overall"] == "FAIL"
