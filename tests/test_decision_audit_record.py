"""Semi-autonomous pipeline (commit 1) — decision_audit_record schema contract.

Locks the shape of the audit record the carteiro (auto_decider / gate mode B)
appends per objective decision, and PINS the RAIL: ``decided_by`` may only ever
be ``auto_decider`` or ``gate_mode_b`` — NEVER a human. A human literal
(``Felipe``, ``human``, ``user``, ...) must be rejected by the schema.

Also sanity-checks the two sibling schemas that ship now but are consumed in
commits 5-9 (curadoria_verdict, rag_writeback_record).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMAS = REPO_ROOT / "schemas"
DAR_PATH = SCHEMAS / "decision_audit_record.schema.json"
CV_PATH = SCHEMAS / "curadoria_verdict.schema.json"
RWB_PATH = SCHEMAS / "rag_writeback_record.schema.json"

ALLOWED_DECIDED_BY = ("auto_decider", "gate_mode_b")
# anything human-shaped that must NEVER be accepted as a decider
HUMAN_DECIDERS = ("Felipe", "felipe", "human", "user", "operator", "IMPROVED", "")


def _validator(path: Path) -> Draft202012Validator:
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


@pytest.fixture(scope="module")
def dar() -> Draft202012Validator:
    return _validator(DAR_PATH)


def _record(**over) -> dict:
    base = {
        "schema": "decision_audit_record/1.0.0",
        "decision_id": "furniture_program_r004",
        "decision_type": "furniture_program",
        "classification": "OBJECTIVE_STRONG_PASS",
        "action": "auto_approve",
        "confidence": 1.0,
        "evidence": ["interns=PASS", "geometry_sanity=PASS", "furniture_overlap=PASS"],
        "judge_verdicts": {"interns": "PASS", "geometry_sanity": "PASS",
                           "furniture_overlap": "PASS"},
        "gate": None,
        "decided_by": "auto_decider",
        "caps_snapshot": {"max_auto_decisions_per_drain": 20,
                          "max_gate_calls_per_drain": 5},
        "corpus_version": "unknown",
        "created_at": "2026-01-01T00:00:00Z",
        "dry_run": False,
    }
    base.update(over)
    return base


# ---- shape ---------------------------------------------------------------


def test_schema_is_valid_and_accepts_minimal(dar):
    dar.validate(_record())


def test_gate_mode_b_record_with_gate_object_is_valid(dar):
    dar.validate(_record(
        classification="BORDERLINE", action="auto_approve",
        decided_by="gate_mode_b", confidence=0.7,
        gate={"trigger": "objective_gate_borderline", "status": "ok",
              "verdict": "GO", "confidence": "high", "applied": "approve"},
    ))


def test_taste_refused_record_is_valid(dar):
    dar.validate(_record(
        decision_type="consistency_gap", decision_id="gap_estilo_r004",
        classification="TASTE_REFUSED", action="refused_taste",
        confidence=0.0, judge_verdicts={"objective": False},
    ))


# ---- rejections ----------------------------------------------------------


def test_schema_rejects_bad_classification(dar):
    assert list(dar.iter_errors(_record(classification="MAYBE")))


def test_schema_rejects_bad_action(dar):
    assert list(dar.iter_errors(_record(action="auto_magic")))


def test_schema_rejects_confidence_out_of_range(dar):
    assert list(dar.iter_errors(_record(confidence=1.5)))
    assert list(dar.iter_errors(_record(confidence=-0.1)))


def test_schema_rejects_missing_required(dar):
    rec = _record()
    del rec["decided_by"]
    assert list(dar.iter_errors(rec))


def test_dry_run_is_required_and_boolean(dar):
    # dry_run distinguishes a SIMULATED record from an APPLIED one — both are valid
    assert not list(dar.iter_errors(_record(dry_run=True)))
    assert not list(dar.iter_errors(_record(dry_run=False)))
    # required: a record missing it is rejected
    rec = _record()
    del rec["dry_run"]
    assert list(dar.iter_errors(rec))
    # boolean only: a string must not pass
    assert list(dar.iter_errors(_record(dry_run="true")))


# ---- THE RAIL: decided_by is never human --------------------------------


def test_decided_by_accepts_only_the_two_machine_deciders(dar):
    for who in ALLOWED_DECIDED_BY:
        assert not list(dar.iter_errors(_record(decided_by=who))), who


def test_decided_by_rejects_every_human_shaped_value(dar):
    # property: no human/other literal may pass as a decider
    for who in HUMAN_DECIDERS:
        assert list(dar.iter_errors(_record(decided_by=who))), (
            f"decided_by={who!r} must be rejected — the machine RAIL"
        )


def test_decided_by_enum_is_exactly_the_two_machine_deciders():
    schema = json.loads(DAR_PATH.read_text(encoding="utf-8"))
    assert set(schema["properties"]["decided_by"]["enum"]) == set(ALLOWED_DECIDED_BY)


# ---- sibling schemas (ship now, consumed in commits 5-9) -----------------


def test_curadoria_verdict_schema_is_valid_and_pins_human_verdict():
    v = _validator(CV_PATH)
    v.validate({"variant_id": "planta_74_v3", "human_verdict": "IMPROVED",
                "liked": True, "note": "melhor luz", "tags": ["industrial"],
                "batch_id": "b1", "t": "2026-01-01T00:00:00Z"})
    assert list(v.iter_errors({"variant_id": "x", "human_verdict": "GREAT",
                               "batch_id": "b1", "t": "t"}))
    schema = json.loads(CV_PATH.read_text(encoding="utf-8"))
    assert set(schema["properties"]["human_verdict"]["enum"]) == {
        "IMPROVED", "SAME", "WORSE"}


def test_rag_writeback_schema_is_valid_and_minimal():
    v = _validator(RWB_PATH)
    v.validate({
        "asset_id": "sofa_venezia", "run_id": "r1", "cycle_id": "c1",
        "room_id": "r002", "room_type": "living", "style_profile": "industrial",
        "image_path": "iso.png", "skp_path": "v.skp", "human_verdict": "SAME",
        "liked": None, "felipe_comment": "", "tags": [], "positive_patterns": [],
        "negative_patterns": [], "evidence": [], "corpus_version": "unknown",
        "created_at": "2026-01-01T00:00:00Z",
    })
    assert list(v.iter_errors({"asset_id": "x", "human_verdict": "WORSE"}))
