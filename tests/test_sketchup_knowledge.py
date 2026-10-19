"""Prova L1 do estudo consultivo; não simula competência no SketchUp."""
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.sketchup.knowledge import CATALOG, cabinet_plan, load_catalog, recipe, search

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "tests/data/sketchup_knowledge/cabinet_case.v1.json"


@pytest.fixture
def case():
    return json.loads(CASE.read_text(encoding="utf-8"))


def test_golden_selects_sources_and_keeps_execution_blocked(case):
    plan = cabinet_plan(case)
    assert plan["plan_state"] == "BLOCKED_CAPABILITY_MISSING"
    assert plan["execution_authorized"] is False
    assert plan["validation"] == {
        "L1": "PASS_SYNTHETIC_CALCULATIONS_ONLY",
        "L2": "PENDING_SKETCHUP", "L3": "PENDING_HUMAN",
    }
    assert len(plan["recipes"]) == 3
    assert all(r["sources"][0]["url"].startswith("https://www.youtube.com/")
               and r["sources"][0]["locator"] for r in plan["recipes"])
    assert len(plan["catalog_sha256"]) == 64
    assert len(plan["case_sha256"]) == 64
    assert plan["missing_info"]  # não inventa ferragens
    assert plan["drawer_boxes"] == "NOT_DIMENSIONED_HARDWARE_REQUIRED"


def test_panel_math_has_measured_bays_and_real_front_gaps(case):
    p = cabinet_plan(case)
    assert p["calculations_mm"]["bay_clear_width"] == 573
    assert p["calculations_mm"]["bay_clear_height"] == 684
    parts = {x["id"]: x for x in p["proposed_parts"]}
    door = parts["door_left"]["bbox_mm"]
    drawer = parts["drawer_front_1"]["bbox_mm"]
    assert drawer[0] - door[3] == 3
    assert parts["drawer_front_2"]["bbox_mm"][2] - drawer[5] == 3
    assert door[1:3] == [-18, 3]
    assert parts["back"]["bbox_mm"] == [0, 554, 0, 1200, 560, 720]
    assert len(parts) == 10  # seis painéis, uma porta, três frentes
    assert p["L1_checks"]["no_positive_volume_overlaps"] is True


@pytest.mark.parametrize("key,value", [
    ("width", 54), ("height", 36), ("carcass_depth", 6),
    ("front_gap", 0), ("front_gap", 200), ("panel_thickness", -1),
    ("height", float("nan")), ("width", float("inf")),
    ("width", True), ("front_gap", "3"),
])
def test_infeasible_or_nonfinite_dimensions_are_refused(case, key, value):
    case["dimensions"][key] = value
    with pytest.raises(ValueError):
        cabinet_plan(case)


@pytest.mark.parametrize("patch", [
    {"dimension_grounding": "FROM_COURSE"}, {"units": "m"},
    {"output_skp": "artifacts/planta_74/planta_74.skp"},
    {"drawer_count": True}, {"drawer_count": 0}, {"drawer_count": 2.5},
    {"hardware": {"model": "invented", "clearance": 0}},
])
def test_cannot_smuggle_project_dimensions_or_execution_fields(case, patch):
    case.update(patch)
    with pytest.raises(ValueError):
        cabinet_plan(case)


def test_unknown_dimensions_and_missing_input_fail_closed(case):
    case["dimensions"]["door_hinge"] = 110
    with pytest.raises(ValueError):
        cabinet_plan(case)
    del case["dimensions"]
    with pytest.raises(ValueError):
        cabinet_plan(case)


def test_catalog_overclaim_and_missing_provenance_are_refused(tmp_path):
    original = json.loads(CATALOG.read_text(encoding="utf-8"))
    variants = []
    data = copy.deepcopy(original)
    data["recipes"][0]["proof_state"] = "PROVEN_REAL_SU"
    variants.append(data)
    data = copy.deepcopy(original)
    data["recipes"][0]["sources"][0]["id"] = "unknown"
    variants.append(data)
    data = copy.deepcopy(original)
    data["sources"].append(data["sources"][0])
    variants.append(data)
    data = copy.deepcopy(original)
    data["recipes"][0]["sources"][0]["locator"] = ""
    variants.append(data)
    data = copy.deepcopy(original)
    data["recipes"][0]["api_candidates"][0]["status"] = "PROVEN_REAL_SU"
    variants.append(data)
    for data in variants:
        path = tmp_path / "catalog.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(ValueError):
            load_catalog(path)


def test_search_is_accent_insensitive_and_unknown_recipe_fails():
    assert "gaveta" in search("GAVETAS")[0]["title"].lower()
    assert search("componentes")
    assert search("REPETIÇÃO") == search("repeticao")
    assert search("nonsense_unique_token") == []
    assert len(search("")) == 8
    with pytest.raises(ValueError, match="RECIPE_UNKNOWN"):
        recipe("missing")
    assert recipe("cabinet.front-gaps-and-profiles")["api_candidates"][2]["status"] == "ABSENT_METHOD_COMPUTE_PROFILE"


def test_cli_runs_from_other_cwd_without_writing_files(tmp_path):
    env = {"PYTHONPATH": str(ROOT)}
    import os
    env = {**os.environ, **env, "PYTHONDONTWRITEBYTECODE": "1"}
    before = list(tmp_path.iterdir())
    result = subprocess.run(
        [sys.executable, "-B", "-m", "tools.sketchup.knowledge", "cabinet-plan", "--case", str(CASE)],
        cwd=tmp_path, env=env, capture_output=True, text=True, check=True,
    )
    assert json.loads(result.stdout)["execution_authorized"] is False
    assert list(tmp_path.iterdir()) == before
    bad = tmp_path / "bad.json"
    bad.write_text('{"schema_version": "wrong"}', encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-B", "-m", "tools.sketchup.knowledge", "cabinet-plan", "--case", str(bad)],
        cwd=tmp_path, env=env, capture_output=True, text=True,
    )
    assert result.returncode == 2
    assert json.loads(result.stdout)["status"] == "INVALID_INPUT"
