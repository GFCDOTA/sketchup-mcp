"""FP-052: truth target preflight; historical room style is never permission to build a part."""
import copy
import json
from pathlib import Path

from tools.rooms.reference_targets import inspect_reference_target

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "artifacts/reference_lab/targets/planta_74/r004/kitchen_base_001.target.v1.json"


def _target():
    return json.loads(TARGET.read_text("utf-8"))


def test_sample_target_is_valid_but_not_approved():
    result = inspect_reference_target(_target(), root=ROOT)
    assert result["schema_valid"] is True
    assert result["ready"] is False
    assert "BLOCKED_TARGET_UNDEFINED" in result["codes"]
    assert "BLOCKED_TARGET_CONFLICT" in result["codes"]
    assert result["execution_authorized"] is False


def test_room_golden_does_not_approve_cabinet():
    t = _target()
    assert t["style"]["status"] == "HISTORICALLY_APPROVED"
    assert t["approval"]["decision"] == "PENDING"
    t["state"] = "APPROVED_TARGET"
    result = inspect_reference_target(t, root=ROOT)
    assert result["ready"] is False and "BLOCKED_TARGET_UNDEFINED" in result["codes"]


def test_missing_file_blocks():
    t = _target()
    t["source_refs"][0]["path"] = "projects/planta_74/source/nao_existe.pdf"
    r = inspect_reference_target(t, root=ROOT)
    assert "BLOCKED_TARGET_EVIDENCE" in r["codes"]


def test_hash_mismatch_blocks():
    t = _target()
    t["source_refs"][0]["sha256"] = "0" * 64
    r = inspect_reference_target(t, root=ROOT)
    assert "BLOCKED_TARGET_EVIDENCE" in r["codes"]


def test_traversal_is_not_allowed():
    t = _target()
    t["source_refs"][0]["path"] = "../outside.pdf"
    r = inspect_reference_target(t, root=ROOT)
    assert "BLOCKED_TARGET_EVIDENCE" in r["codes"]


def test_approval_without_component_reference_refused():
    t = _target()
    t["state"] = "APPROVED_TARGET"
    t["conflicts"] = []
    t["approval"] = {
        "decision": "APPROVED", "scope": "FURNITURE_TARGET",
        "reviewer": "example", "review_record_path": "artifacts/reference_lab/DECISIONS.md",
    }
    r = inspect_reference_target(t, root=ROOT)
    assert not r["ready"] and "BLOCKED_TARGET_UNDEFINED" in r["codes"]


def test_unknown_component_source_fails():
    t = _target()
    t["parts"][0]["required_source_ids"] = ["inventado"]
    r = inspect_reference_target(t, root=ROOT)
    assert "BLOCKED_TARGET_EVIDENCE" in r["codes"]
