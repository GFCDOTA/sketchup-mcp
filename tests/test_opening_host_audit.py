"""FP-031 #3 — opening<->host-wall positional detector (deterministic, no SU/PDF).

Synthetic cases lock the contract; the real fixtures pin the motivating signal:
quadrado (clean) passes, planta_74 flags its mis-hosted windows.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.opening_host_audit import audit_opening_hosts

REPO = Path(__file__).resolve().parents[1]


def _con(walls, openings, thick=5.4):
    return {"wall_thickness_pts": thick, "walls": walls, "openings": openings}


WLONG = {"id": "wlong", "start": [0, 0], "end": [100, 0], "orientation": "h"}
WFAR = {"id": "wfar", "start": [0, 50], "end": [100, 50], "orientation": "h"}


def test_clean_opening_on_host_passes():
    con = _con([WLONG, WFAR],
               [{"id": "ok", "center": [50, 0], "wall_id": "wlong",
                 "opening_width_pts": 20}])
    rep = audit_opening_hosts(con)
    assert rep["overall"] == "PASS"
    assert rep["n_fail"] == 0


def test_wrong_host_is_flagged_as_mismatch():
    # centre sits on wlong but is assigned wfar (50pt away); wlong is closer.
    con = _con([WLONG, WFAR],
               [{"id": "bad", "center": [50, 0], "wall_id": "wfar",
                 "opening_width_pts": 20}])
    rep = audit_opening_hosts(con)
    assert rep["overall"] == "FAIL"
    f = rep["openings"][0]
    assert f["verdict"] == "FAIL"
    assert any("host_mismatch" in r for r in f["reasons"])
    assert f["nearest_wall"] == "wlong"


def test_opening_wider_than_host_is_flagged():
    con = _con([WLONG, WFAR],
               [{"id": "wide", "center": [50, 0], "wall_id": "wlong",
                 "opening_width_pts": 150}])
    rep = audit_opening_hosts(con)
    assert rep["overall"] == "FAIL"
    assert any("width_exceeds_host" in r for r in rep["openings"][0]["reasons"])


def test_missing_host_or_center_fails_safe():
    con = _con([WLONG], [{"id": "nohost", "center": [50, 0],
                          "wall_id": "ghost", "opening_width_pts": 10}])
    rep = audit_opening_hosts(con)
    assert rep["openings"][0]["verdict"] == "FAIL"


# ---- real fixtures ----
def _load(fixture, name):
    p = REPO / "fixtures" / fixture / name
    return json.loads(p.read_text("utf-8")) if p.exists() else None


@pytest.mark.skipif(
    _load("quadrado", "consensus_with_window.json") is None,
    reason="quadrado fixture absent")
def test_quadrado_clean_passes():
    con = _load("quadrado", "consensus_with_window.json")
    rep = audit_opening_hosts(con)
    assert rep["overall"] == "PASS", [
        f for f in rep["openings"] if f["verdict"] == "FAIL"]


@pytest.mark.skipif(
    _load("planta_74", "consensus_with_human_walls_and_soft_barriers.json") is None,
    reason="planta_74 fixture absent")
def test_planta74_openings_well_hosted_after_regen():
    # FP-031 #28: the regenerated canonical consensus (merged collinear walls +
    # re-hosted openings) now hosts every opening correctly. The catch-behaviour
    # is covered by the synthetic tests above.
    con = _load("planta_74", "consensus_with_human_walls_and_soft_barriers.json")
    rep = audit_opening_hosts(con)
    assert rep["overall"] == "PASS", [
        f for f in rep["openings"] if f["verdict"] == "FAIL"]
