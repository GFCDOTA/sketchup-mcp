"""Tests for ``cockpit.proposed_actions`` (Slice 4).

Cycle 13 shipped the producer (``tools.propose_skp_actions``); this
Slice consumes the resulting ``proposed_actions.json`` from the
cockpit Review tab. These tests cover loading, schema-stale
handling, the promotion mapping for each known action type, and
the apply convenience wrapper that wires the audit-trail link
through.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from cockpit import overrides as overrides_mod
from cockpit.proposed_actions import (
    PROPOSED_ACTION_TYPES,
    PROPOSED_ACTIONS_FILENAME,
    action_already_applied,
    actions_for_target,
    apply_proposed_action,
    load_proposed_actions,
    proposed_action_to_override_payload,
    proposed_actions_path,
)

# ---- Fixtures -------------------------------------------------------

def _toy_consensus() -> dict:
    return {
        "schema_version": "1.0.0",
        "wall_thickness_pts": 5.4,
        "walls": [
            {"id": "w0", "start": [0, 0], "end": [100, 0],
             "thickness": 5.4, "orientation": "h"},
        ],
        "rooms": [
            {"id": "r0", "name": "SALA", "polygon_pts": [
                [0, 0], [50, 0], [50, 100], [0, 100],
            ], "area_pts2": 5000},
            {"id": "r2", "name": "TERRACO TECNICO", "polygon_pts": [
                [0, 100], [50, 100], [50, 130], [0, 130],
            ], "area_pts2": 1500},
        ],
        "openings": [
            {"id": "o0", "kind_v5": "interior_door",
             "decision": "clean", "confidence": 0.95,
             "evidence": {"room_left": "SALA"}},
            {"id": "o1", "kind_v5": "window",
             "decision": "clean", "confidence": 0.55},
            {"id": "o3", "kind_v5": "unknown",
             "decision": "clean", "confidence": 0.9},
        ],
    }


def _toy_proposed_actions_doc() -> dict:
    return {
        "schema_version": "proposed_actions_v1",
        "run_id": "fake_run",
        "consensus_sha256": "abc123",
        "generated_at": "2026-05-09T00:00:00Z",
        "generator": "tools/propose_skp_actions.py@v0.1",
        "actions": [
            {
                "id": "act-1",
                "type": "classify_opening",
                "target": {"kind": "opening", "id": "o3"},
                "payload": {"suggested_kind": "interior_passage",
                            "evidence": ["room_left", "room_right"]},
                "confidence": 0.4,
                "rationale": "kind_unknown_default",
                "generator": "tools/propose_skp_actions.py@v0.1",
                "created_at": "2026-05-09T00:00:00Z",
            },
            {
                "id": "act-2",
                "type": "mark_low_confidence",
                "target": {"kind": "opening", "id": "o1"},
                "payload": {"current_confidence": 0.55},
                "confidence": 1.0,
                "rationale": "below threshold",
                "generator": "tools/propose_skp_actions.py@v0.1",
                "created_at": "2026-05-09T00:00:00Z",
            },
            {
                "id": "act-3",
                "type": "request_human_review",
                "target": {"kind": "room", "id": "r2"},
                "payload": {"reason_codes": ["fidelity_warning"],
                            "warning_count": 1},
                "confidence": 0.85,
                "rationale": "room TERRACO TECNICO matched warning",
                "generator": "tools/propose_skp_actions.py@v0.1",
                "created_at": "2026-05-09T00:00:00Z",
            },
        ],
    }


def _write_consensus(tmp_path: Path) -> Path:
    p = tmp_path / "consensus.json"
    p.write_text(json.dumps(_toy_consensus()), encoding="utf-8")
    return p


def _write_proposed_actions(tmp_path: Path, doc: dict | None = None) -> Path:
    out = proposed_actions_path(tmp_path)
    out.write_text(
        json.dumps(doc if doc is not None else _toy_proposed_actions_doc(),
                    indent=2),
        encoding="utf-8",
    )
    return out


# ---- Sanity ---------------------------------------------------------

def test_proposed_action_types_mirror_producer():
    """Cockpit's tuple must list the same 6 v1 types as the producer
    so a stale install of one side doesn't drift silently."""
    from tools.propose_skp_actions import (
        ACTION_TYPES as PRODUCER_TYPES,
    )
    assert set(PROPOSED_ACTION_TYPES) == set(PRODUCER_TYPES)


def test_proposed_actions_filename_is_conventional():
    assert PROPOSED_ACTIONS_FILENAME == "proposed_actions.json"


# ---- load_proposed_actions ------------------------------------------

def test_load_proposed_actions_missing_file_returns_empty(tmp_path):
    doc = load_proposed_actions(tmp_path)
    assert doc["actions"] == []
    assert doc["schema_version"] == "proposed_actions_v1"
    # No load_error when file is simply missing
    assert "_load_error" not in doc


def test_load_proposed_actions_round_trip(tmp_path):
    _write_proposed_actions(tmp_path)
    doc = load_proposed_actions(tmp_path)
    assert len(doc["actions"]) == 3
    assert doc["consensus_sha256"] == "abc123"
    assert doc["_consensus_sha256_match"] is True  # no expected supplied


def test_load_proposed_actions_sha_match(tmp_path):
    _write_proposed_actions(tmp_path)
    doc = load_proposed_actions(tmp_path, expected_consensus_sha="abc123")
    assert doc["_consensus_sha256_match"] is True


def test_load_proposed_actions_sha_mismatch_flags_stale(tmp_path):
    _write_proposed_actions(tmp_path)
    doc = load_proposed_actions(tmp_path, expected_consensus_sha="DIFFERENT")
    assert doc["_consensus_sha256_match"] is False


def test_load_proposed_actions_handles_corrupt_json(tmp_path):
    proposed_actions_path(tmp_path).write_text("{ not json", encoding="utf-8")
    doc = load_proposed_actions(tmp_path)
    assert doc["actions"] == []
    assert "_load_error" in doc


# ---- proposed_action_to_override_payload (promotion mapping) -------

def test_promote_classify_opening_to_kind_override():
    action = _toy_proposed_actions_doc()["actions"][0]  # classify_opening on o3
    payload = proposed_action_to_override_payload(action)
    assert payload is not None
    assert payload["type"] == "opening_kind_override"
    assert payload["target"] == {"kind": "opening", "id": "o3"}
    assert payload["payload"]["new_kind_v5"] == "interior_passage"
    assert "act-1" in payload["reason"]


def test_promote_mark_low_confidence_to_mark_suspect_low():
    action = _toy_proposed_actions_doc()["actions"][1]  # mark_low_confidence
    payload = proposed_action_to_override_payload(action)
    assert payload is not None
    assert payload["type"] == "mark_suspect"
    assert payload["target"] == {"kind": "opening", "id": "o1"}
    assert payload["payload"] == {"severity": "low",
                                    "tag": "low_confidence"}


def test_promote_request_human_review_room_to_mark_suspect_medium():
    action = _toy_proposed_actions_doc()["actions"][2]  # request_human_review on room
    payload = proposed_action_to_override_payload(action)
    assert payload is not None
    assert payload["type"] == "mark_suspect"
    assert payload["target"] == {"kind": "room", "id": "r2"}
    assert payload["payload"]["severity"] == "medium"
    assert payload["payload"]["tag"] == "fidelity_warning"


def test_promote_request_human_review_opening_to_mark_suspect_medium():
    action = {
        "id": "act-x",
        "type": "request_human_review",
        "target": {"kind": "opening", "id": "o2"},
        "payload": {"reason_codes": ["decision_not_clean"]},
        "rationale": "decision was debug",
    }
    payload = proposed_action_to_override_payload(action)
    assert payload is not None
    assert payload["type"] == "mark_suspect"
    assert payload["target"] == {"kind": "opening", "id": "o2"}
    assert payload["payload"]["severity"] == "medium"
    assert payload["payload"]["tag"] == "decision_not_clean"


def test_promote_unknown_action_type_returns_none():
    action = {
        "id": "act-x",
        "type": "expand_room_polygon",  # not promotable in Slice 4
        "target": {"kind": "room", "id": "r0"},
        "payload": {"delta_pts": [], "delta_area_pts2": 100.0},
    }
    assert proposed_action_to_override_payload(action) is None


def test_promote_returns_none_on_invalid_input():
    assert proposed_action_to_override_payload({}) is None
    assert proposed_action_to_override_payload({"type": "classify_opening"}) is None
    assert proposed_action_to_override_payload(None) is None  # type: ignore[arg-type]
    # classify_opening missing suggested_kind
    assert proposed_action_to_override_payload({
        "id": "x", "type": "classify_opening",
        "target": {"kind": "opening", "id": "o3"},
        "payload": {},
    }) is None


# ---- apply_proposed_action (audit-link wired through) ---------------

def test_apply_classify_opening_creates_kind_override_with_audit_link(tmp_path):
    _write_consensus(tmp_path)
    action = _toy_proposed_actions_doc()["actions"][0]
    consensus = _toy_consensus()
    data = apply_proposed_action(
        run_dir=tmp_path,
        action=action,
        audit_actor="human:test",
        consensus_path=tmp_path / "consensus.json",
        consensus=consensus,
    )
    assert len(data["overrides"]) == 1
    ov = data["overrides"][0]
    assert ov["type"] == "opening_kind_override"
    assert ov["payload"]["new_kind_v5"] == "interior_passage"
    # Audit trail's create entry carries the source link
    creates = [a for a in data["audit_trail"] if a["event"] == "create"]
    assert len(creates) == 1
    assert creates[0]["source_proposed_action_id"] == "act-1"
    assert creates[0]["actor"] == "human:test"


def test_apply_mark_low_confidence_creates_suspect_low(tmp_path):
    _write_consensus(tmp_path)
    action = _toy_proposed_actions_doc()["actions"][1]
    consensus = _toy_consensus()
    data = apply_proposed_action(
        run_dir=tmp_path,
        action=action,
        audit_actor="human",
        consensus_path=tmp_path / "consensus.json",
        consensus=consensus,
    )
    ov = data["overrides"][-1]
    assert ov["type"] == "mark_suspect"
    assert ov["payload"]["severity"] == "low"
    # Audit-link present
    create = [a for a in data["audit_trail"] if a["event"] == "create"][-1]
    assert create["source_proposed_action_id"] == "act-2"


def test_apply_unknown_action_type_raises(tmp_path):
    _write_consensus(tmp_path)
    with pytest.raises(ValueError, match="not promotable"):
        apply_proposed_action(
            run_dir=tmp_path,
            action={
                "id": "x", "type": "expand_room_polygon",
                "target": {"kind": "room", "id": "r0"},
                "payload": {"delta_pts": [], "delta_area_pts2": 0},
            },
            audit_actor="human",
            consensus=_toy_consensus(),
        )


def test_apply_action_without_id_raises(tmp_path):
    _write_consensus(tmp_path)
    with pytest.raises(ValueError, match="missing required field: id"):
        apply_proposed_action(
            run_dir=tmp_path,
            action={
                "type": "classify_opening",
                "target": {"kind": "opening", "id": "o3"},
                "payload": {"suggested_kind": "window"},
            },
            audit_actor="human",
            consensus=_toy_consensus(),
        )


def test_save_override_omits_source_link_when_not_provided(tmp_path):
    """Back-compat: existing call sites that don't pass the new
    kwarg produce identical output to before."""
    _write_consensus(tmp_path)
    consensus = _toy_consensus()
    data = overrides_mod.save_override(
        run_dir=tmp_path,
        override_payload={
            "type": "mark_suspect",
            "target": {"kind": "opening", "id": "o0"},
            "payload": {"severity": "low", "tag": "manual"},
        },
        audit_actor="human",
        consensus=consensus,
    )
    create = data["audit_trail"][-1]
    assert "source_proposed_action_id" not in create


# ---- View helpers (UI side) -----------------------------------------

def test_actions_for_target_filters_by_kind_and_id():
    actions = _toy_proposed_actions_doc()["actions"]
    o1 = actions_for_target(actions, "opening", "o1")
    assert len(o1) == 1 and o1[0]["id"] == "act-2"
    r2 = actions_for_target(actions, "room", "r2")
    assert len(r2) == 1 and r2[0]["id"] == "act-3"
    none = actions_for_target(actions, "opening", "DOES_NOT_EXIST")
    assert none == []


def test_actions_for_target_handles_int_vs_str_ids():
    actions = [{
        "id": "x",
        "type": "classify_opening",
        "target": {"kind": "opening", "id": 7},
        "payload": {"suggested_kind": "window"},
    }]
    # Caller passes str; helper should match int target.id
    assert len(actions_for_target(actions, "opening", "7")) == 1


def test_action_already_applied_via_audit_link():
    audit = [
        {"event": "create", "source_proposed_action_id": "act-1"},
        {"event": "create"},  # no link
    ]
    assert action_already_applied({"id": "act-1"}, audit) is True
    assert action_already_applied({"id": "act-2"}, audit) is False
    assert action_already_applied({}, audit) is False


# ---- End-to-end round-trip with Cycle 13 producer (smoke) -----------

def test_end_to_end_produce_then_consume(tmp_path):
    """Produce a proposed_actions.json via the real Cycle 13 producer,
    load it via the Slice 4 consumer, promote one action, verify the
    override + audit-link land on disk."""
    from tools.propose_skp_actions import (
        propose_actions,
        write_proposed_actions,
    )

    consensus_path = _write_consensus(tmp_path)
    consensus = _toy_consensus()
    doc = propose_actions(
        consensus=consensus,
        consensus_sha256="dummy_sha",
        run_id="e2e_run",
    )
    write_proposed_actions(doc, proposed_actions_path(tmp_path))

    loaded = load_proposed_actions(tmp_path)
    assert loaded["actions"], "producer should have emitted at least one action"

    # Pick the classify_opening for o3
    chosen = next(
        a for a in loaded["actions"]
        if a["type"] == "classify_opening"
    )
    out = apply_proposed_action(
        run_dir=tmp_path,
        action=chosen,
        audit_actor="human:e2e",
        consensus_path=consensus_path,
        consensus=consensus,
    )
    assert any(
        ov["type"] == "opening_kind_override"
        and ov["payload"]["new_kind_v5"] == "interior_passage"
        for ov in out["overrides"]
    )
    assert any(
        a.get("source_proposed_action_id") == chosen["id"]
        for a in out["audit_trail"]
    )

    # Re-load proposed_actions and verify "already applied" detection
    re_loaded = load_proposed_actions(tmp_path)
    assert action_already_applied(chosen, out["audit_trail"]) is True
    # Other actions remain un-applied
    other = next(
        a for a in re_loaded["actions"]
        if a["type"] != "classify_opening"
    )
    assert action_already_applied(other, out["audit_trail"]) is False
