"""FP-033 — correction_finding normalization + schema contract tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from tools import correction_finding as cf
from tools import finding_router as fr

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "schemas" / "correction_finding.schema.json"


@pytest.fixture(scope="module")
def validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _assert_all_valid(validator, findings):
    assert findings, "expected at least one normalized finding"
    for f in findings:
        errs = list(validator.iter_errors(f))
        assert not errs, f"{f} -> {errs[0].message if errs else ''}"


# --- schema ----------------------------------------------------------------


def test_schema_is_valid_and_accepts_minimal(validator):
    validator.validate({
        "type": "furniture_overlap", "severity": "FAIL",
        "source": "deterministic", "evidence": "x",
    })


def test_schema_rejects_bad_severity(validator):
    errs = list(validator.iter_errors({
        "type": "x", "severity": "PASS", "source": "deterministic", "evidence": "y",
    }))
    assert errs, "severity must be WARN|FAIL"


def test_schema_rejects_bad_route(validator):
    errs = list(validator.iter_errors({
        "type": "x", "severity": "FAIL", "source": "deterministic",
        "evidence": "y", "route": "AUTO_MAGIC",
    }))
    assert errs


# --- normalize: visual_findings.v1 (the FP-032 contract) -------------------


def _v1_blob():
    return {
        "schema_version": "visual_findings.v1",
        "top_level_verdict": "FAIL",
        "source": "claude_bridge",
        "axes": {"global_visual": {"verdict": "FAIL", "evidence": "gap"}},
        "findings": [
            {"id": "vf_001", "severity": "FAIL", "axis": "wall_fidelity",
             "type": "missing_wall_continuation", "location": "top/center",
             "evidence_image": "corrupted_top.png", "evidence": "wall gap"},
            {"id": "vf_002", "severity": "WARN", "axis": "global_visual",
             "type": "global_visual", "location": "", "evidence_image": "",
             "evidence": "slightly off"},
        ],
    }


def test_normalizes_visual_findings_v1(validator):
    out = cf.from_visual_findings_v1(_v1_blob())
    _assert_all_valid(validator, out)
    assert len(out) == 2
    # provenance + routing carried honestly
    assert out[0]["type"] == "missing_wall_continuation"
    assert out[0]["source"] == "claude_bridge"
    assert out[0]["route"] == fr.NEEDS_FELIPE          # oracle-seen wall gap -> human
    # anti-ping-pong: o output do OLHO (source_check=visual_oracle) nunca
    # re-roteia pro próprio olho — o resíduo qualitativo é do Felipe
    assert out[1]["route"] == fr.NEEDS_FELIPE


def test_visual_findings_empty_is_empty():
    assert cf.from_visual_findings_v1({"findings": []}) == []
    assert cf.from_visual_findings_v1({}) == []


# --- normalize: geometry_sanity.audit() ------------------------------------


def test_normalizes_geometry_audit(validator):
    audit = {"overall": "FAIL", "findings": [
        {"severity": "FAIL", "check": "outside_room", "label": "sofa",
         "kind": "sofa", "detail": "centro fora"},
        {"severity": "FAIL", "check": "off_axis", "label": "rack",
         "kind": "rack", "detail": "eixo torto"},
    ]}
    out = cf.from_geometry_audit(audit, room="living")
    _assert_all_valid(validator, out)
    assert {f["type"] for f in out} == {"outside_room", "off_axis"}
    assert all(f["route"] == fr.DETERMINISTIC_AUTOFIX for f in out)
    assert all(f["room"] == "living" for f in out)


# --- normalize: furniture_overlap_gate -------------------------------------


def test_normalizes_overlap_gate(validator):
    gate = {"result": "FAIL", "room": "kitchen", "room_name": "COZINHA",
            "n_modules": 5, "fails": ["a × b: 900 cm² (35%)"],
            "warns": ["c × d: 200 cm² (15%)"]}
    out = cf.from_overlap_gate(gate)
    _assert_all_valid(validator, out)
    assert len(out) == 2
    sev = {f["severity"] for f in out}
    assert sev == {"FAIL", "WARN"}
    assert all(f["type"] == "furniture_overlap" for f in out)
    assert all(f["route"] == fr.DETERMINISTIC_AUTOFIX for f in out)


def test_overlap_gate_pass_yields_nothing():
    assert cf.from_overlap_gate(
        {"result": "PASS", "room": "x", "fails": [], "warns": []}) == []


# --- normalize: run_deterministic_gates ------------------------------------


def test_normalizes_deterministic_gates(validator):
    gates = {
        "opening_host": {"verdict": "FAIL"},
        "wall_overlap": {"overall": "WARN"},
        "position_fidelity": {"verdict": "FAIL"},
        "wall_presence": {"verdict": "PASS"},        # -> no finding
        "render_bbox": {"verdict": "SKIPPED_NO_SIDECAR"},  # -> no finding
    }
    out = cf.from_deterministic_gates(gates)
    _assert_all_valid(validator, out)
    by_type = {f["type"]: f for f in out}
    assert set(by_type) == {"opening_host_mismatch", "wall_overlap", "position_fidelity"}
    assert by_type["opening_host_mismatch"]["route"] == fr.DETERMINISTIC_AUTOFIX
    assert by_type["wall_overlap"]["route"] == fr.DETERMINISTIC_AUTOFIX
    assert by_type["position_fidelity"]["route"] == fr.NEEDS_FELIPE   # vs PDF = aparência


def test_make_finding_drops_none_optionals_and_routes():
    f = cf.make_finding(type="furniture_overlap", severity="FAIL",
                        source="deterministic", evidence="e")
    assert "location" not in f and "axis" not in f
    assert f["route"] == fr.DETERMINISTIC_AUTOFIX
