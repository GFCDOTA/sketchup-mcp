"""FP-031 #3b — duplicate/overlapping wall detector (deterministic, no SU/PDF)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.wall_overlap_audit import audit_wall_overlaps

REPO = Path(__file__).resolve().parents[1]


def _con(walls, thick=5.4):
    return {"wall_thickness_pts": thick, "walls": walls}


def test_no_overlap_passes():
    con = _con([
        {"id": "a", "start": [0, 0], "end": [100, 0]},      # h
        {"id": "b", "start": [0, 50], "end": [100, 50]},    # parallel, far
        {"id": "c", "start": [0, 0], "end": [0, 50]},       # v, perpendicular
    ])
    assert audit_wall_overlaps(con)["overall"] == "PASS"


def test_duplicate_wall_is_flagged():
    con = _con([
        {"id": "w", "start": [10, 20], "end": [10, 120]},     # v, x=10
        {"id": "dup", "start": [11, 21], "end": [11, 119]},   # v, x=11 (~dup)
    ])
    rep = audit_wall_overlaps(con)
    assert rep["overall"] == "FAIL"
    assert rep["n_overlaps"] == 1
    ids = {rep["overlaps"][0]["wall_a"], rep["overlaps"][0]["wall_b"]}
    assert ids == {"w", "dup"}


def test_collinear_but_disjoint_does_not_flag():
    # same line, but spans do not overlap (end-to-end) -> not a duplicate
    con = _con([
        {"id": "p", "start": [0, 0], "end": [40, 0]},
        {"id": "q", "start": [60, 0], "end": [100, 0]},
    ])
    assert audit_wall_overlaps(con)["overall"] == "PASS"


def test_parallel_partition_not_flagged():
    # two walls a real partition-width apart (>= thickness) are NOT duplicates
    con = _con([
        {"id": "a", "start": [0, 0], "end": [0, 100]},
        {"id": "b", "start": [20, 0], "end": [20, 100]},
    ])
    assert audit_wall_overlaps(con)["overall"] == "PASS"


def _load(fixture, name):
    p = REPO / "fixtures" / fixture / name
    return json.loads(p.read_text("utf-8")) if p.exists() else None


@pytest.mark.skipif(_load("quadrado", "consensus_with_window.json") is None,
                    reason="quadrado fixture absent")
def test_quadrado_no_overlaps():
    assert audit_wall_overlaps(_load("quadrado", "consensus_with_window.json"))["overall"] == "PASS"


@pytest.mark.skipif(
    _load("planta_74", "consensus_with_human_walls_and_soft_barriers.json") is None,
    reason="planta_74 fixture absent")
def test_planta74_flags_duplicate_wall():
    rep = audit_wall_overlaps(
        _load("planta_74", "consensus_with_human_walls_and_soft_barriers.json"))
    assert rep["overall"] == "FAIL"
    pairs = [{f["wall_a"], f["wall_b"]} for f in rep["overlaps"]]
    assert {"w020", "h_w001"} in pairs
