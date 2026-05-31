"""FP-031 #28 — consensus regeneration (merge collinear walls + re-host openings).

Deterministic: the regenerated consensus must satisfy BOTH positional detectors
that the raw planta_74 consensus fails.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.opening_host_audit import audit_opening_hosts
from tools.regenerate_consensus import regenerate
from tools.wall_overlap_audit import audit_wall_overlaps

REPO = Path(__file__).resolve().parents[1]
_PLANTA = (REPO / "fixtures" / "planta_74"
           / "consensus_with_human_walls_and_soft_barriers.json")


def test_synthetic_merges_collinear_and_rehosts():
    con = {"wall_thickness_pts": 5.4,
           "walls": [{"id": "a", "start": [0, 0], "end": [40, 0]},
                     {"id": "b", "start": [60, 0], "end": [100, 0]}],
           "openings": [{"id": "o", "center": [50, 0], "wall_id": "a",
                         "opening_width_pts": 15}]}
    reg = regenerate(con, bridge_gap=100.0)
    assert len(reg["walls"]) == 1                      # a+b bridged into one
    assert reg["openings"][0]["wall_id"] == reg["walls"][0]["id"]  # re-hosted


def test_synthetic_keeps_real_gap_unmerged():
    # a gap far larger than bridge_gap stays as two separate walls
    con = {"wall_thickness_pts": 5.4,
           "walls": [{"id": "a", "start": [0, 0], "end": [40, 0]},
                     {"id": "b", "start": [400, 0], "end": [440, 0]}],
           "openings": []}
    reg = regenerate(con, bridge_gap=100.0)
    assert len(reg["walls"]) == 2


@pytest.mark.skipif(not _PLANTA.exists(), reason="planta_74 fixture absent")
def test_regenerate_planta74_passes_both_detectors():
    con = json.loads(_PLANTA.read_text("utf-8"))
    reg = regenerate(con)
    assert audit_opening_hosts(reg)["overall"] == "PASS"
    assert audit_wall_overlaps(reg)["overall"] == "PASS"
    assert len(reg["walls"]) < len(con["walls"])       # collinear merged
    # every opening now references an existing (merged) wall
    wids = {w["id"] for w in reg["walls"]}
    assert all(o["wall_id"] in wids for o in reg["openings"])
