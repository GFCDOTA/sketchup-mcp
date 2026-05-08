"""Unit tests for `cockpit/overrides.py` — Slice 2 mutation surface.

Covers:
- empty_overrides_file shape (review_overrides_v1)
- load_overrides on missing file (no throw)
- round-trip for each of the 6 override types + the global block toggle
- audit_trail append-only invariant
- validation rules per ADR §2.5
- consensus_sha256 binding (mismatch invalidates apply, file persists)
- precedence resolution per ADR §2.5
- signature stability + change detection
- overrides_apply_view annotates `source: manual` correctly

All tests build their own run dir under `tmp_path` so they do NOT
touch the gitignored `runs/` tree.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from cockpit.overrides import (
    OPENING_KIND_VALUES,
    OVERRIDE_TYPES,
    SCHEMA_VERSION,
    SUSPECT_SEVERITIES,
    compute_consensus_sha256,
    empty_overrides_file,
    load_overrides,
    overrides_apply_view,
    overrides_for_element,
    overrides_path,
    precedence_resolve,
    save_override,
    set_block_skp_export,
    validate_override_payload,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _toy_consensus() -> dict:
    """Minimal consensus matching the Cockpit render_overlay test
    fixture so override targets resolve."""
    return {
        "schema_version": "1.0.0",
        "wall_thickness_pts": 5.4,
        "walls": [
            {"id": "w0", "start": [0, 0], "end": [100, 0],
             "thickness": 5.4, "orientation": "h"},
            {"id": "w1", "start": [50, 0], "end": [50, 100],
             "thickness": 5.4, "orientation": "v"},
        ],
        "rooms": [
            {"id": "r0", "name": "SALA",
             "polygon_pts": [[0, 0], [50, 0], [50, 100], [0, 100]],
             "area_pts2": 5000},
            {"id": "r1", "name": "COZINHA",
             "polygon_pts": [[50, 0], [100, 0], [100, 100], [50, 100]],
             "area_pts2": 5000},
        ],
        "openings": [
            {"id": "o0", "wall_id": "w1",
             "kind_v5": "interior_door", "decision": "clean",
             "center": [50.0, 50.0],
             "evidence": {"room_left": "SALA", "room_right": "COZINHA",
                          "room_left_id": "r0", "room_right_id": "r1"}},
            {"id": "o1", "wall_id": "w0",
             "kind_v5": "window", "decision": "debug",
             "center": [25.0, 0.0],
             "evidence": {"room_left": "SALA",
                          "room_left_id": "r0", "room_right_id": None}},
        ],
        "soft_barriers": [],
    }


def _materialise_run(tmp_path: Path,
                     run_id: str = "test_run") -> tuple[Path, Path]:
    """Create `tmp_path/<run_id>/consensus.json` with toy consensus.
    Returns (run_dir, consensus_path)."""
    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    consensus_path = run_dir / "consensus.json"
    consensus_path.write_text(
        json.dumps(_toy_consensus()), encoding="utf-8"
    )
    return run_dir, consensus_path


# ---------------------------------------------------------------------------
# Empty-file shape
# ---------------------------------------------------------------------------

def test_empty_overrides_file_is_valid_v1():
    """Skeleton dict matches review_overrides_v1 contract (ADR §2.3)."""
    out = empty_overrides_file(
        run_id="some_run",
        consensus_path="runs/some_run/consensus.json",
        consensus_sha256="abcd" * 16,
    )
    assert out["schema_version"] == SCHEMA_VERSION == "review_overrides_v1"
    assert out["run_id"] == "some_run"
    assert out["consensus_sha256"] == "abcd" * 16
    assert out["overrides"] == []
    assert out["audit_trail"] == []
    assert out["global"] == {"block_skp_export": False, "block_reason": None}
    # ISO 8601 timestamps are present
    assert "T" in out["created_at"] and out["created_at"].endswith("Z")
    assert "T" in out["last_updated_at"]


# ---------------------------------------------------------------------------
# load_overrides: missing-file behaviour
# ---------------------------------------------------------------------------

def test_load_overrides_missing_file_returns_empty(tmp_path: Path):
    """When `review_overrides.json` does not exist, load_overrides
    returns a fresh empty dict — does NOT throw and does NOT write."""
    run_dir, consensus_path = _materialise_run(tmp_path)
    data = load_overrides(run_dir, consensus_path=consensus_path)
    assert data["schema_version"] == "review_overrides_v1"
    assert data["overrides"] == []
    assert data["audit_trail"] == []
    assert not overrides_path(run_dir).exists(), (
        "load_overrides on missing file must NOT create the file "
        "(only save_override should write)"
    )


def test_load_overrides_missing_file_no_consensus_does_not_throw(
        tmp_path: Path):
    run_dir = tmp_path / "no_consensus_run"
    run_dir.mkdir()
    data = load_overrides(run_dir, consensus_path=None)
    assert data["overrides"] == []


# ---------------------------------------------------------------------------
# Round-trip: opening_kind_override
# ---------------------------------------------------------------------------

def test_save_opening_kind_override_round_trip(tmp_path: Path):
    """Write an opening_kind_override, re-read, assert persistence."""
    run_dir, consensus_path = _materialise_run(tmp_path)
    payload = {
        "type": "opening_kind_override",
        "target": {"kind": "opening", "id": "o0"},
        "payload": {"new_kind_v5": "interior_passage"},
        "reason": "human says it's a passage, not a door",
    }
    saved = save_override(
        run_dir, payload, audit_actor="human:tester",
        consensus_path=consensus_path, consensus=_toy_consensus(),
    )
    assert len(saved["overrides"]) == 1
    rec = saved["overrides"][0]
    assert rec["type"] == "opening_kind_override"
    assert rec["payload"]["new_kind_v5"] == "interior_passage"
    assert rec["author"] == "human:tester"
    assert rec["target"] == {"kind": "opening", "id": "o0"}
    assert "id" in rec and rec["id"]
    assert "signature" in rec and len(rec["signature"]) == 64

    # Re-read from disk
    re = load_overrides(run_dir, consensus_path=consensus_path)
    assert re["overrides"] == saved["overrides"]
    assert re["_consensus_sha256_match"] is True


# ---------------------------------------------------------------------------
# Round-trip: room_label_override
# ---------------------------------------------------------------------------

def test_save_room_label_override_round_trip(tmp_path: Path):
    run_dir, consensus_path = _materialise_run(tmp_path)
    payload = {
        "type": "room_label_override",
        "target": {"kind": "room", "id": "r0"},
        "payload": {"new_name": "SUITE 01"},
        "reason": "rename via cockpit",
    }
    save_override(
        run_dir, payload, audit_actor="human",
        consensus_path=consensus_path, consensus=_toy_consensus(),
    )
    re = load_overrides(run_dir, consensus_path=consensus_path)
    assert re["overrides"][0]["payload"]["new_name"] == "SUITE 01"
    assert re["overrides"][0]["target"]["id"] == "r0"


# ---------------------------------------------------------------------------
# Round-trip: mark_suspect
# ---------------------------------------------------------------------------

def test_save_mark_suspect_round_trip(tmp_path: Path):
    run_dir, consensus_path = _materialise_run(tmp_path)
    payload = {
        "type": "mark_suspect",
        "target": {"kind": "opening", "id": "o1"},
        "payload": {"severity": "high", "tag": "shape_unclear"},
        "reason": "unclear arc",
    }
    save_override(
        run_dir, payload, audit_actor="agent:auditor",
        consensus_path=consensus_path, consensus=_toy_consensus(),
    )
    re = load_overrides(run_dir, consensus_path=consensus_path)
    assert re["overrides"][0]["payload"]["severity"] == "high"
    assert re["overrides"][0]["payload"]["tag"] == "shape_unclear"
    assert re["overrides"][0]["author"] == "agent:auditor"


# ---------------------------------------------------------------------------
# Round-trip: reject_element / approve_element
# ---------------------------------------------------------------------------

def test_save_reject_element_round_trip(tmp_path: Path):
    run_dir, consensus_path = _materialise_run(tmp_path)
    payload = {
        "type": "reject_element",
        "target": {"kind": "opening", "id": "o0"},
        "payload": {},
        "reason": "phantom door",
    }
    save_override(
        run_dir, payload, audit_actor="human",
        consensus_path=consensus_path, consensus=_toy_consensus(),
    )
    re = load_overrides(run_dir, consensus_path=consensus_path)
    assert re["overrides"][0]["type"] == "reject_element"
    # Empty payload is permitted
    assert re["overrides"][0]["payload"] == {}


def test_save_approve_element_round_trip(tmp_path: Path):
    run_dir, consensus_path = _materialise_run(tmp_path)
    payload = {
        "type": "approve_element",
        "target": {"kind": "room", "id": "r0"},
        "payload": {},
        "reason": "sala is correct",
    }
    save_override(
        run_dir, payload, audit_actor="human",
        consensus_path=consensus_path, consensus=_toy_consensus(),
    )
    re = load_overrides(run_dir, consensus_path=consensus_path)
    assert re["overrides"][0]["type"] == "approve_element"


# ---------------------------------------------------------------------------
# Round-trip: opening_connects_override
# ---------------------------------------------------------------------------

def test_save_opening_connects_override_round_trip(tmp_path: Path):
    run_dir, consensus_path = _materialise_run(tmp_path)
    payload = {
        "type": "opening_connects_override",
        "target": {"kind": "opening", "id": "o1"},
        "payload": {"room_left_id": "r0", "room_right_id": "r1"},
        "reason": "fix room linkage",
    }
    save_override(
        run_dir, payload, audit_actor="human",
        consensus_path=consensus_path, consensus=_toy_consensus(),
    )
    re = load_overrides(run_dir, consensus_path=consensus_path)
    rec = re["overrides"][0]
    assert rec["type"] == "opening_connects_override"
    assert rec["payload"]["room_left_id"] == "r0"
    assert rec["payload"]["room_right_id"] == "r1"


# ---------------------------------------------------------------------------
# Block SKP export toggle (global flag)
# ---------------------------------------------------------------------------

def test_set_block_skp_export_round_trip(tmp_path: Path):
    """`block_skp_export` is global, lives under `global.*`, audit-
    trailed like a normal override."""
    run_dir, consensus_path = _materialise_run(tmp_path)
    set_block_skp_export(
        run_dir, blocked=True,
        reason="fidelity insufficient", audit_actor="human",
        consensus_path=consensus_path,
    )
    re = load_overrides(run_dir, consensus_path=consensus_path)
    assert re["global"]["block_skp_export"] is True
    assert re["global"]["block_reason"] == "fidelity insufficient"
    # Audit trail recorded the toggle
    assert any(a.get("tag") == "block_skp_export"
               for a in re["audit_trail"])

    # Toggling back also audit-trailed
    set_block_skp_export(
        run_dir, blocked=False, reason=None, audit_actor="human",
        consensus_path=consensus_path,
    )
    re2 = load_overrides(run_dir, consensus_path=consensus_path)
    assert re2["global"]["block_skp_export"] is False
    assert re2["global"]["block_reason"] is None
    block_events = [a for a in re2["audit_trail"]
                    if a.get("tag") == "block_skp_export"]
    assert len(block_events) == 2  # one set, one unset


# ---------------------------------------------------------------------------
# Audit trail append-only invariant (ADR §2.10.3)
# ---------------------------------------------------------------------------

def test_audit_trail_is_append_only(tmp_path: Path):
    """Each save_override / set_block_skp_export call appends; never
    replaces or removes existing entries."""
    run_dir, consensus_path = _materialise_run(tmp_path)

    # Create two overrides + toggle block twice → 4 events
    payload_a = {
        "type": "opening_kind_override",
        "target": {"kind": "opening", "id": "o0"},
        "payload": {"new_kind_v5": "window"},
        "reason": "first",
    }
    payload_b = {
        "type": "room_label_override",
        "target": {"kind": "room", "id": "r1"},
        "payload": {"new_name": "KITCHEN"},
        "reason": "second",
    }
    save_override(run_dir, payload_a, audit_actor="h1",
                  consensus_path=consensus_path,
                  consensus=_toy_consensus())
    save_override(run_dir, payload_b, audit_actor="h1",
                  consensus_path=consensus_path,
                  consensus=_toy_consensus())
    set_block_skp_export(run_dir, blocked=True, reason="x",
                          audit_actor="h2",
                          consensus_path=consensus_path)
    set_block_skp_export(run_dir, blocked=False, reason=None,
                          audit_actor="h2",
                          consensus_path=consensus_path)

    final = load_overrides(run_dir, consensus_path=consensus_path)
    assert len(final["audit_trail"]) == 4
    # Order preserved (ts + ids assigned in append order)
    events = [a["event"] for a in final["audit_trail"]]
    assert events.count("create") + events.count("update") == 4
    # Every entry has a unique uuid id
    ids = [a["id"] for a in final["audit_trail"]]
    assert len(set(ids)) == len(ids)
    # Every entry has a diff_signature
    for a in final["audit_trail"]:
        assert "diff_signature" in a and len(a["diff_signature"]) == 64


# ---------------------------------------------------------------------------
# Validation rejection
# ---------------------------------------------------------------------------

def test_invalid_kind_override_rejected(tmp_path: Path):
    """opening_kind_override with new_kind_v5 outside the enumerated
    set must be rejected (ADR §2.5 validation rules)."""
    run_dir, consensus_path = _materialise_run(tmp_path)
    payload = {
        "type": "opening_kind_override",
        "target": {"kind": "opening", "id": "o0"},
        "payload": {"new_kind_v5": "garage_door"},  # not in enum
        "reason": "should fail",
    }
    with pytest.raises(ValueError, match="new_kind_v5"):
        save_override(
            run_dir, payload, audit_actor="human",
            consensus_path=consensus_path, consensus=_toy_consensus(),
        )
    # File never written
    assert not overrides_path(run_dir).exists()


def test_unknown_override_type_rejected(tmp_path: Path):
    run_dir, consensus_path = _materialise_run(tmp_path)
    payload = {
        "type": "demolish_wall",  # not a v1 override type
        "target": {"kind": "opening", "id": "o0"},
        "payload": {},
    }
    with pytest.raises(ValueError, match="type"):
        save_override(
            run_dir, payload, audit_actor="human",
            consensus_path=consensus_path, consensus=_toy_consensus(),
        )


def test_target_id_must_exist_in_consensus(tmp_path: Path):
    """target.id must resolve in consensus when consensus supplied
    (ADR §2.5 validation rules)."""
    run_dir, consensus_path = _materialise_run(tmp_path)
    payload = {
        "type": "opening_kind_override",
        "target": {"kind": "opening", "id": "o_phantom"},
        "payload": {"new_kind_v5": "window"},
    }
    with pytest.raises(ValueError, match="not found"):
        save_override(
            run_dir, payload, audit_actor="human",
            consensus_path=consensus_path, consensus=_toy_consensus(),
        )


def test_validate_payload_returns_errors_list_directly():
    """validate_override_payload returns the errors list — does NOT
    raise. (Used by the cockpit UI to surface error text inline.)"""
    errors = validate_override_payload(
        {"type": "opening_kind_override",
         "target": {"kind": "opening", "id": "o0"},
         "payload": {"new_kind_v5": "bogus"}},
        consensus=None,
    )
    assert any("new_kind_v5" in e for e in errors)


def test_mark_suspect_severity_validation():
    errors = validate_override_payload(
        {"type": "mark_suspect",
         "target": {"kind": "opening", "id": "o0"},
         "payload": {"severity": "extreme"}},
        consensus=None,
    )
    assert any("severity" in e for e in errors)
    # Valid severity — no error
    errors2 = validate_override_payload(
        {"type": "mark_suspect",
         "target": {"kind": "room", "id": "r0"},
         "payload": {"severity": "medium", "tag": "x"}},
        consensus=None,
    )
    assert not errors2


# ---------------------------------------------------------------------------
# consensus_sha256 binding (ADR §2.10.6)
# ---------------------------------------------------------------------------

def test_consensus_sha256_mismatch_invalidates_overrides(tmp_path: Path):
    """When the consensus on disk changes, load_overrides reports
    `_consensus_sha256_match=False` so the cockpit can warn the user.
    The override file remains on disk for re-confirmation."""
    run_dir, consensus_path = _materialise_run(tmp_path)
    payload = {
        "type": "opening_kind_override",
        "target": {"kind": "opening", "id": "o0"},
        "payload": {"new_kind_v5": "window"},
    }
    save_override(
        run_dir, payload, audit_actor="human",
        consensus_path=consensus_path, consensus=_toy_consensus(),
    )

    # Mutate consensus on disk → sha changes
    consensus_path.write_text(
        json.dumps({"schema_version": "1.0.0",
                     "rooms": [], "walls": [], "openings": []}),
        encoding="utf-8",
    )

    re = load_overrides(run_dir, consensus_path=consensus_path)
    assert re["_consensus_sha256_match"] is False
    # Override file STILL on disk — not auto-purged
    assert overrides_path(run_dir).exists()
    assert len(re["overrides"]) == 1


def test_consensus_sha256_match_when_unchanged(tmp_path: Path):
    run_dir, consensus_path = _materialise_run(tmp_path)
    save_override(
        run_dir,
        {"type": "approve_element",
         "target": {"kind": "room", "id": "r0"},
         "payload": {}, "reason": ""},
        audit_actor="human",
        consensus_path=consensus_path, consensus=_toy_consensus(),
    )
    re = load_overrides(run_dir, consensus_path=consensus_path)
    assert re["_consensus_sha256_match"] is True


def test_compute_consensus_sha256_stable(tmp_path: Path):
    p = tmp_path / "x.json"
    p.write_text("{}", encoding="utf-8")
    s1 = compute_consensus_sha256(p)
    s2 = compute_consensus_sha256(p)
    assert s1 == s2
    assert len(s1) == 64
    p.write_text("{ }", encoding="utf-8")
    s3 = compute_consensus_sha256(p)
    assert s3 != s1


# ---------------------------------------------------------------------------
# Precedence (ADR §2.5)
# ---------------------------------------------------------------------------

def test_precedence_reject_beats_mark_suspect():
    """reject_element > mark_suspect when both target the same
    element (ADR §2.5)."""
    overrides = [
        {"id": "1", "type": "mark_suspect",
         "target": {"kind": "opening", "id": "o0"},
         "payload": {"severity": "high"},
         "created_at": "2026-05-08T10:00:00Z"},
        {"id": "2", "type": "reject_element",
         "target": {"kind": "opening", "id": "o0"},
         "payload": {},
         "created_at": "2026-05-08T10:01:00Z"},
    ]
    chosen = precedence_resolve(overrides)
    assert chosen["opening:o0"]["type"] == "reject_element"


def test_precedence_kind_override_beats_approve():
    """opening_kind_override outranks approve_element."""
    overrides = [
        {"id": "1", "type": "approve_element",
         "target": {"kind": "opening", "id": "o0"},
         "payload": {}, "created_at": "2026-05-08T10:00:00Z"},
        {"id": "2", "type": "opening_kind_override",
         "target": {"kind": "opening", "id": "o0"},
         "payload": {"new_kind_v5": "window"},
         "created_at": "2026-05-08T10:01:00Z"},
    ]
    chosen = precedence_resolve(overrides)
    assert chosen["opening:o0"]["type"] == "opening_kind_override"


def test_precedence_last_created_wins_within_same_type():
    """Within the same precedence level, `created_at` newest wins."""
    overrides = [
        {"id": "a", "type": "opening_kind_override",
         "target": {"kind": "opening", "id": "o0"},
         "payload": {"new_kind_v5": "interior_door"},
         "created_at": "2026-05-08T10:00:00Z"},
        {"id": "b", "type": "opening_kind_override",
         "target": {"kind": "opening", "id": "o0"},
         "payload": {"new_kind_v5": "window"},
         "created_at": "2026-05-08T10:05:00Z"},
    ]
    chosen = precedence_resolve(overrides)
    assert chosen["opening:o0"]["id"] == "b"


# ---------------------------------------------------------------------------
# Signature stability (ADR §2.5)
# ---------------------------------------------------------------------------

def test_signature_changes_when_payload_changes(tmp_path: Path):
    """Two overrides with different payloads have different
    signatures."""
    run_dir, consensus_path = _materialise_run(tmp_path)
    s1 = save_override(
        run_dir,
        {"type": "opening_kind_override",
         "target": {"kind": "opening", "id": "o0"},
         "payload": {"new_kind_v5": "window"}},
        audit_actor="human",
        consensus_path=consensus_path, consensus=_toy_consensus(),
    )
    sig_1 = s1["overrides"][0]["signature"]

    # Sleep 1.1 s to ensure created_at differs (per-second precision)
    # — the function builds signature from {target, payload, author,
    # created_at}, so distinct timestamps suffice even if payload
    # were identical.
    time.sleep(1.1)

    s2 = save_override(
        run_dir,
        {"type": "opening_kind_override",
         "target": {"kind": "opening", "id": "o0"},
         "payload": {"new_kind_v5": "interior_passage"}},
        audit_actor="human",
        consensus_path=consensus_path, consensus=_toy_consensus(),
    )
    sig_2 = s2["overrides"][1]["signature"]
    assert sig_1 != sig_2
    assert len(sig_1) == 64 and len(sig_2) == 64


# ---------------------------------------------------------------------------
# overrides_apply_view (ADR §2.10.4)
# ---------------------------------------------------------------------------

def test_overrides_apply_view_marks_source_manual():
    """An opening_kind_override flips `source` from 'detected' to
    'manual' and preserves the original kind under
    `_kind_v5_original`."""
    consensus = _toy_consensus()
    overrides = [
        {"id": "1", "type": "opening_kind_override",
         "target": {"kind": "opening", "id": "o0"},
         "payload": {"new_kind_v5": "window"},
         "created_at": "2026-05-08T10:00:00Z"},
    ]
    view = overrides_apply_view(consensus, overrides)
    o0 = next(o for o in view["openings"] if o["id"] == "o0")
    assert o0["source"] == "manual"
    assert o0["kind_v5"] == "window"
    assert o0["_kind_v5_original"] == "interior_door"
    # Untouched opening remains 'detected'
    o1 = next(o for o in view["openings"] if o["id"] == "o1")
    assert o1["source"] == "detected"


def test_overrides_apply_view_marks_rejected():
    consensus = _toy_consensus()
    overrides = [
        {"id": "1", "type": "reject_element",
         "target": {"kind": "room", "id": "r0"},
         "payload": {},
         "created_at": "2026-05-08T10:00:00Z"},
    ]
    view = overrides_apply_view(consensus, overrides)
    r0 = next(r for r in view["rooms"] if r["id"] == "r0")
    assert r0["source"] == "override_rejected"
    assert r0["_rejected"] is True


def test_overrides_apply_view_preserves_original_room_label():
    consensus = _toy_consensus()
    overrides = [
        {"id": "1", "type": "room_label_override",
         "target": {"kind": "room", "id": "r1"},
         "payload": {"new_name": "KITCHEN"},
         "created_at": "2026-05-08T10:00:00Z"},
    ]
    view = overrides_apply_view(consensus, overrides)
    r1 = next(r for r in view["rooms"] if r["id"] == "r1")
    assert r1["name"] == "KITCHEN"
    assert r1["_name_original"] == "COZINHA"
    assert r1["source"] == "manual"


def test_overrides_apply_view_attaches_suspect_metadata():
    consensus = _toy_consensus()
    overrides = [
        {"id": "1", "type": "mark_suspect",
         "target": {"kind": "opening", "id": "o0"},
         "payload": {"severity": "high", "tag": "shape_unclear"},
         "created_at": "2026-05-08T10:00:00Z"},
    ]
    view = overrides_apply_view(consensus, overrides)
    o0 = next(o for o in view["openings"] if o["id"] == "o0")
    assert o0["_suspect"]["severity"] == "high"
    assert o0["_suspect"]["tag"] == "shape_unclear"
    # mark_suspect alone does NOT change source from 'detected'
    # (per ADR — element keeps its values + gets _suspect annotation)
    assert o0["source"] == "detected"


# ---------------------------------------------------------------------------
# overrides_for_element helper
# ---------------------------------------------------------------------------

def test_overrides_for_element_returns_newest_first():
    overrides = [
        {"id": "a", "type": "approve_element",
         "target": {"kind": "opening", "id": "o0"},
         "payload": {}, "created_at": "2026-05-08T10:00:00Z"},
        {"id": "b", "type": "mark_suspect",
         "target": {"kind": "opening", "id": "o0"},
         "payload": {"severity": "low"},
         "created_at": "2026-05-08T11:00:00Z"},
        # different element
        {"id": "c", "type": "approve_element",
         "target": {"kind": "room", "id": "r0"},
         "payload": {}, "created_at": "2026-05-08T12:00:00Z"},
    ]
    matches = overrides_for_element(overrides, "opening", "o0")
    assert [m["id"] for m in matches] == ["b", "a"]


# ---------------------------------------------------------------------------
# Atomic write: file shape on disk is valid JSON
# ---------------------------------------------------------------------------

def test_overrides_file_is_valid_json_on_disk(tmp_path: Path):
    run_dir, consensus_path = _materialise_run(tmp_path)
    save_override(
        run_dir,
        {"type": "approve_element",
         "target": {"kind": "opening", "id": "o0"},
         "payload": {}},
        audit_actor="human",
        consensus_path=consensus_path, consensus=_toy_consensus(),
    )
    raw = overrides_path(run_dir).read_text(encoding="utf-8")
    # Pretty-printed (indent=2) — must contain newlines
    assert "\n" in raw
    parsed = json.loads(raw)
    assert parsed["schema_version"] == "review_overrides_v1"


def test_override_constants_exposed():
    """Public surface mentioned in ADR is exported."""
    assert len(OVERRIDE_TYPES) == 6
    assert "opening_kind_override" in OVERRIDE_TYPES
    assert "block_skp_export" not in OVERRIDE_TYPES  # global, not per-element
    assert len(OPENING_KIND_VALUES) == 6
    assert "interior_door" in OPENING_KIND_VALUES
    assert SUSPECT_SEVERITIES == ("low", "medium", "high")
