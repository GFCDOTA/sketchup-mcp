"""M3 — semantic_zones overlay (annotation-only) contract tests.

Locks the honest resolution of the planta_74 ``room_fidelity`` WARN: 8 geometric
cells carry 11 named semantic zones, the 2 open-plan cells are annotated (not
walled), and NO wall/opening/room geometry is created by the overlay. Synthetic
cases pin the fabrication guards; the real fixture pins the motivating 8->11.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tools.semantic_zones import (
    assess_room_fidelity,
    count_cells,
    count_zones,
    load_consensus,
    load_overlay,
    validate_overlay,
    zone_mapping,
)

REPO = Path(__file__).resolve().parents[1]
FIXTURE = "planta_74"


def _has_fixtures() -> bool:
    return (REPO / "fixtures" / FIXTURE / "semantic_zones.json").exists() and (
        REPO / "fixtures" / FIXTURE
        / "consensus_with_human_walls_and_soft_barriers.json").exists()


pytestmark = pytest.mark.skipif(not _has_fixtures(), reason="planta_74 fixtures absent")


# ---- real fixture: the motivating 8 cells -> 11 zones -------------------------
def test_planta74_maps_8_cells_to_11_zones():
    consensus = load_consensus(FIXTURE)
    overlay = load_overlay(FIXTURE)
    assert count_cells(consensus) == 8
    assert count_zones(overlay) == 11


def test_planta74_overlay_validates_against_consensus():
    consensus = load_consensus(FIXTURE)
    overlay = load_overlay(FIXTURE)
    res = validate_overlay(consensus, overlay)
    assert res["overall"] == "PASS", res["errors"]


def test_planta74_two_open_plan_cells_are_the_merged_ones():
    overlay = load_overlay(FIXTURE)
    merged = {c["cell_id"]: len(c["zones"])
              for c in overlay["cells"] if c["open_plan_merge"]}
    # r001 fuses 3 ambients, r002 fuses 2 — the documented open-plan cells.
    assert merged == {"r001": 3, "r002": 2}


def test_planta74_every_zone_name_comes_from_consensus():
    consensus = load_consensus(FIXTURE)
    overlay = load_overlay(FIXTURE)
    truth = {r["id"]: {p.strip() for p in r["name"].split("|")}
             for r in consensus["rooms"]}
    for cell in overlay["cells"]:
        for z in cell["zones"]:
            assert z["name"] in truth[cell["cell_id"]], (
                f"{cell['cell_id']} zone {z['name']!r} not authored in consensus")


def test_planta74_room_fidelity_becomes_explained():
    rep = assess_room_fidelity(FIXTURE)
    assert rep["verdict"] == "EXPLAINED"
    assert rep["geometric_cells"] == 8
    assert rep["semantic_zones"] == 11
    assert rep["overlay_valid"] is True
    assert sorted(rep["open_plan_cells"]) == ["r001", "r002"]


# ---- Hard Rule #1: the overlay creates NO geometry ---------------------------
def test_overlay_adds_no_walls_openings_or_rooms():
    """The overlay is annotation-only; loading/applying it must not touch the
    consensus geometry. Assert the overlay JSON carries no geometry keys and
    that the consensus is byte-identical before/after an assessment run."""
    overlay = load_overlay(FIXTURE)
    forbidden = {"walls", "openings", "rooms", "polygon_pts", "soft_barriers"}
    assert forbidden.isdisjoint(overlay.keys())
    for cell in overlay["cells"]:
        assert forbidden.isdisjoint(cell.keys())
        for z in cell["zones"]:
            assert forbidden.isdisjoint(z.keys())

    consensus_path = (REPO / "fixtures" / FIXTURE
                      / "consensus_with_human_walls_and_soft_barriers.json")
    before = consensus_path.read_bytes()
    assess_room_fidelity(FIXTURE)  # exercises load + validate + assess
    after = consensus_path.read_bytes()
    assert before == after, "consensus fixture mutated by overlay run"


def test_zone_mapping_shape():
    overlay = load_overlay(FIXTURE)
    mapping = zone_mapping(overlay)
    assert len(mapping) == 8
    assert mapping["r002"] == ["SALA DE JANTAR", "SALA DE ESTAR"]
    assert mapping["r000"] == ["SUITE 01"]


# ---- fabrication guards (synthetic) ------------------------------------------
def _mini_consensus():
    return {
        "rooms": [
            {"id": "r000", "name": "COZINHA"},
            {"id": "r001", "name": "SALA DE JANTAR | SALA DE ESTAR"},
        ]
    }


def _mini_overlay():
    return {
        "schema_version": "semantic_zones.v1",
        "cells": [
            {"cell_id": "r000", "open_plan_merge": False,
             "zones": [{"name": "COZINHA"}]},
            {"cell_id": "r001", "open_plan_merge": True,
             "zones": [{"name": "SALA DE JANTAR"}, {"name": "SALA DE ESTAR"}]},
        ],
    }


def test_synthetic_clean_overlay_passes():
    res = validate_overlay(_mini_consensus(), _mini_overlay())
    assert res["overall"] == "PASS", res["errors"]


def test_fabricated_zone_name_is_rejected():
    ov = _mini_overlay()
    ov["cells"][1]["zones"].append({"name": "PISCINA"})  # not in consensus
    res = validate_overlay(_mini_consensus(), ov)
    assert res["overall"] == "FAIL"
    assert any("PISCINA" in e for e in res["errors"])


def test_invented_cell_id_is_rejected():
    ov = _mini_overlay()
    ov["cells"].append({"cell_id": "r999", "open_plan_merge": False,
                        "zones": [{"name": "GHOST"}]})
    res = validate_overlay(_mini_consensus(), ov)
    assert res["overall"] == "FAIL"
    assert any("r999" in e for e in res["errors"])


def test_uncovered_consensus_room_is_rejected():
    ov = _mini_overlay()
    ov["cells"] = ov["cells"][:1]  # drop r001
    res = validate_overlay(_mini_consensus(), ov)
    assert res["overall"] == "FAIL"
    assert any("not covered" in e for e in res["errors"])


def test_wrong_merge_flag_is_rejected():
    ov = _mini_overlay()
    ov["cells"][1]["open_plan_merge"] = False  # but consensus names 2 ambients
    res = validate_overlay(_mini_consensus(), ov)
    assert res["overall"] == "FAIL"
    assert any("open_plan_merge" in e for e in res["errors"])


def test_invalid_overlay_degrades_verdict_not_upgrades(tmp_path, monkeypatch):
    """A broken overlay must fall back to the honest WARN, never fake EXPLAINED."""
    import tools.semantic_zones as sz

    con = _mini_consensus()
    bad = _mini_overlay()
    bad["cells"][1]["zones"].append({"name": "PISCINA"})  # fabricated

    monkeypatch.setattr(sz, "load_consensus", lambda fixture: copy.deepcopy(con))
    monkeypatch.setattr(sz, "load_overlay", lambda fixture: copy.deepcopy(bad))
    rep = sz.assess_room_fidelity("whatever")
    assert rep["verdict"] == "WARN"
    assert rep["overlay_valid"] is False
