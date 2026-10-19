"""FP-043 P3: escala física independente do report do próprio SketchUp."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from core.scale import DEFAULT_PT_TO_M, expected_pt_to_m
from tools.validation.scale_anchor_gate import audit, audit_paths

ROOT = Path(__file__).resolve().parents[1]
QUADRADO = ROOT / "fixtures/quadrado/consensus_with_window.json"
QUAD_REPORT = ROOT / "docs/specs/_assets/quadrado_canonical_geometry_report.json"
PLANTA = ROOT / "fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json"
PLANT_REPORT = ROOT / "artifacts/planta_74/geometry_report.json"


@pytest.mark.parametrize("source,report", [(QUADRADO, QUAD_REPORT), (PLANTA, PLANT_REPORT)])
def test_canonical_absolute_bbox_matches_verified_anchor(source, report):
    result = audit_paths(source, report)
    assert result["overall"] == "PASS", result
    assert max(result["relative_error_xy"]) < 0.03


def test_expected_anchor_independent_of_inherited_env(monkeypatch):
    monkeypatch.setenv("PT_TO_M", "0.0259")
    assert expected_pt_to_m(consensus_path=QUADRADO) == pytest.approx(DEFAULT_PT_TO_M)
    assert expected_pt_to_m(consensus_path=PLANTA) == pytest.approx(0.0259)
    assert expected_pt_to_m(source="planta_74.pdf") == pytest.approx(0.0259)


@pytest.mark.parametrize("source,report,wrong_factor", [
    (QUADRADO, QUAD_REPORT, 0.0259 / DEFAULT_PT_TO_M),
    (PLANTA, PLANT_REPORT, DEFAULT_PT_TO_M / 0.0259),
])
def test_wrong_scale_fails_even_if_report_internally_consistent(source, report, wrong_factor):
    c = json.loads(source.read_text("utf-8"))
    r = copy.deepcopy(json.loads(report.read_text("utf-8")))
    shell = next(g for g in r["groups_diagnostic"] if g["name"] == "PlanShell_Group")
    for side in ("min", "max"):
        shell["bbox_m"][side][:2] = [v * wrong_factor for v in shell["bbox_m"][side][:2]]
    result = audit(c, r, consensus_path=source)
    assert result["overall"] == "FAIL"
    assert result["reason"] == "ABSOLUTE_SCALE_MISMATCH"


def test_missing_report_cannot_silently_pass(tmp_path):
    result = audit_paths(QUADRADO, tmp_path / "does-not-exist.json")
    assert result["overall"] == "INCOMPLETE"


def test_missing_shell_bbox_cannot_silently_pass():
    assert audit({"walls": [{"start": [0,0], "end": [1,0], "thickness": 1}]},
                 {"groups_diagnostic": []})["overall"] == "INCOMPLETE"


def test_inconsistent_dimensions_are_rejected():
    c = json.loads(QUADRADO.read_text("utf-8"))
    r = json.loads(QUAD_REPORT.read_text("utf-8"))
    assert audit(c, r, consensus_path=QUADRADO, tolerance=0.0000001)["overall"] == "FAIL"
