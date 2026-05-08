"""Unit tests for ``tools.apply_overrides``.

Validates the pure function ``apply_overrides()`` and the CLI shell
against the contract defined in ADR-001 §2.5 / §2.10.

Boundary:
- No real run dirs, no SketchUp, no real consensus files; everything
  is materialised under ``tmp_path``.
- Slice 2 hasn't shipped yet, so we use schema-conformant synthetic
  ``review_overrides_v1`` fixtures matching ADR-001 §2.3 exactly.
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from tools.apply_overrides import (
    AMENDED_SCHEMA_VERSION,
    OVERRIDES_SCHEMA_VERSION,
    _consensus_sha256,
    apply_overrides,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _consensus_payload() -> dict:
    """Minimal consensus shape: 2 rooms + 1 opening connecting them."""
    return {
        "schema_version": "1.0.0",
        "wall_thickness_pts": 5.4,
        "plan_id": "test_fixture",
        "walls": [
            {"id": "w0", "start": [0, 0], "end": [100, 0],
             "thickness": 5.4, "orientation": "h"},
        ],
        "rooms": [
            {"id": "r0", "name": "SALA", "polygon_pts": [[0, 0], [100, 0],
                                                          [100, 100], [0, 100]],
             "area_pts2": 10000.0},
            {"id": "r1", "name": "COZINHA", "polygon_pts": [[100, 0], [200, 0],
                                                            [200, 100], [100, 100]],
             "area_pts2": 10000.0},
        ],
        "openings": [
            {"id": "o0", "wall_id": "w0", "kind_v5": "interior_door",
             "decision": "clean",
             "room_left_id": "r0", "room_right_id": "r1",
             "evidence": {"room_left": "SALA", "room_right": "COZINHA"}},
            {"id": "o1", "wall_id": "w0", "kind_v5": "window",
             "decision": "clean",
             "room_left_id": "r0", "room_right_id": None,
             "evidence": {"room_left": "SALA"}},
        ],
        "soft_barriers": [],
    }


def _override(otype: str, target_kind: str, target_id: str,
              payload: dict | None = None,
              author: str = "human:tester",
              created_at: str = "2026-05-08T20:00:00Z") -> dict:
    return {
        "id": str(uuid.uuid4()),
        "type": otype,
        "target": {"kind": target_kind, "id": target_id},
        "payload": payload or {},
        "author": author,
        "created_at": created_at,
        "reason": "test fixture",
        "signature": "deadbeef" * 8,
    }


def _overrides_doc(overrides: list[dict] | None = None,
                   consensus: dict | None = None,
                   global_block: bool = False,
                   block_reason: str | None = None,
                   sha_override: str | None = None) -> dict:
    sha = sha_override
    if sha is None and consensus is not None:
        sha = _consensus_sha256(consensus)
    elif sha is None:
        sha = "0" * 64
    return {
        "schema_version": OVERRIDES_SCHEMA_VERSION,
        "run_id": "test_run_id",
        "consensus_sha256": sha,
        "consensus_path": "runs/test_run_id/consensus.json",
        "created_at": "2026-05-08T20:00:00Z",
        "last_updated_at": "2026-05-08T20:00:00Z",
        "overrides": overrides or [],
        "global": {
            "block_skp_export": global_block,
            "block_reason": block_reason,
        },
        "audit_trail": [],
    }


# ---------------------------------------------------------------------------
# Test 1 — Empty / None overrides → identity copy with source=detected
# ---------------------------------------------------------------------------


def test_apply_overrides_none_returns_identity_with_detected_source():
    consensus = _consensus_payload()
    out = apply_overrides(consensus, None)
    assert out["_overrides_applied"] == 0
    assert out["_overrides_metadata"]["overrides_applied_count"] == 0
    assert out["_overrides_metadata"]["block_skp_export"] is False
    # All elements tagged source=detected
    for op in out["openings"]:
        assert op["source"] == "detected"
    for room in out["rooms"]:
        assert room["source"] == "detected"
    # Source consensus untouched
    assert "source" not in consensus["openings"][0]
    assert "source" not in consensus["rooms"][0]
    # Counts preserved
    assert len(out["openings"]) == len(consensus["openings"])
    assert len(out["rooms"]) == len(consensus["rooms"])


def test_apply_overrides_empty_list_is_identity():
    consensus = _consensus_payload()
    doc = _overrides_doc(overrides=[], consensus=consensus)
    out = apply_overrides(consensus, doc)
    assert out["_overrides_applied"] == 0
    for op in out["openings"]:
        assert op["source"] == "detected"


# ---------------------------------------------------------------------------
# Test 2 — opening_kind_override applies + preserves _kind_v5_original
# ---------------------------------------------------------------------------


def test_opening_kind_override_replaces_and_preserves_original():
    consensus = _consensus_payload()
    ov = _override("opening_kind_override", "opening", "o0",
                   payload={"new_kind_v5": "window"})
    doc = _overrides_doc(overrides=[ov], consensus=consensus)
    out = apply_overrides(consensus, doc)

    o0 = next(o for o in out["openings"] if o["id"] == "o0")
    assert o0["kind_v5"] == "window"
    assert o0["_kind_v5_original"] == "interior_door"
    assert o0["source"] == "manual"
    # Other opening unchanged
    o1 = next(o for o in out["openings"] if o["id"] == "o1")
    assert o1["kind_v5"] == "window"
    assert o1["source"] == "detected"
    assert "_kind_v5_original" not in o1
    assert out["_overrides_applied"] == 1


def test_opening_kind_override_invalid_kind_dropped():
    consensus = _consensus_payload()
    ov = _override("opening_kind_override", "opening", "o0",
                   payload={"new_kind_v5": "MEGA_DOOR"})
    doc = _overrides_doc(overrides=[ov], consensus=consensus)
    out = apply_overrides(consensus, doc)
    md = out["_overrides_metadata"]
    assert md["overrides_applied_count"] == 0
    assert md["overrides_dropped_count"] == 1
    assert any("MEGA_DOOR" in w for w in md["warnings"])


def test_opening_connects_override_replaces_and_preserves():
    consensus = _consensus_payload()
    ov = _override(
        "opening_connects_override", "opening", "o0",
        payload={"room_left_id": "r1", "room_right_id": "r0"},
    )
    doc = _overrides_doc(overrides=[ov], consensus=consensus)
    out = apply_overrides(consensus, doc)
    o0 = next(o for o in out["openings"] if o["id"] == "o0")
    assert o0["room_left_id"] == "r1"
    assert o0["room_right_id"] == "r0"
    assert o0["_room_left_id_original"] == "r0"
    assert o0["_room_right_id_original"] == "r1"
    assert o0["source"] == "manual"


def test_opening_connects_override_unknown_room_dropped():
    consensus = _consensus_payload()
    ov = _override(
        "opening_connects_override", "opening", "o0",
        payload={"room_left_id": "rZZZ"},
    )
    doc = _overrides_doc(overrides=[ov], consensus=consensus)
    out = apply_overrides(consensus, doc)
    md = out["_overrides_metadata"]
    assert md["overrides_dropped_count"] == 1
    o0 = next(o for o in out["openings"] if o["id"] == "o0")
    assert o0["room_left_id"] == "r0"  # unchanged


# ---------------------------------------------------------------------------
# Test 3 — reject_element drops from amended
# ---------------------------------------------------------------------------


def test_reject_element_drops_opening():
    consensus = _consensus_payload()
    ov = _override("reject_element", "opening", "o0", payload={})
    doc = _overrides_doc(overrides=[ov], consensus=consensus)
    out = apply_overrides(consensus, doc)
    ids = [o["id"] for o in out["openings"]]
    assert "o0" not in ids
    assert "o1" in ids
    md = out["_overrides_metadata"]
    assert md["rejected_opening_ids"] == ["o0"]
    assert md["overrides_applied_count"] == 1


def test_reject_element_drops_room():
    consensus = _consensus_payload()
    ov = _override("reject_element", "room", "r1", payload={})
    doc = _overrides_doc(overrides=[ov], consensus=consensus)
    out = apply_overrides(consensus, doc)
    ids = [r["id"] for r in out["rooms"]]
    assert "r1" not in ids
    md = out["_overrides_metadata"]
    assert md["rejected_room_ids"] == ["r1"]


# ---------------------------------------------------------------------------
# Test 4 — approve_element sets _approved
# ---------------------------------------------------------------------------


def test_approve_element_sets_approved_flag():
    consensus = _consensus_payload()
    ov = _override("approve_element", "opening", "o0", payload={})
    doc = _overrides_doc(overrides=[ov], consensus=consensus)
    out = apply_overrides(consensus, doc)
    o0 = next(o for o in out["openings"] if o["id"] == "o0")
    assert o0["_approved"] is True
    assert o0["source"] == "manual"


def test_approve_element_room():
    consensus = _consensus_payload()
    ov = _override("approve_element", "room", "r0", payload={})
    doc = _overrides_doc(overrides=[ov], consensus=consensus)
    out = apply_overrides(consensus, doc)
    r0 = next(r for r in out["rooms"] if r["id"] == "r0")
    assert r0["_approved"] is True


# ---------------------------------------------------------------------------
# Test 5 — sha mismatch → no apply, metadata warning
# ---------------------------------------------------------------------------


def test_sha_mismatch_rejects_all_overrides_and_warns():
    consensus = _consensus_payload()
    ov = _override("opening_kind_override", "opening", "o0",
                   payload={"new_kind_v5": "window"})
    # Bind to a wrong sha so the apply layer must reject
    doc = _overrides_doc(overrides=[ov], sha_override="ff" * 32)
    expected = _consensus_sha256(consensus)
    out = apply_overrides(consensus, doc, expected_sha=expected)
    assert out["_overrides_applied"] == 0
    md = out["_overrides_metadata"]
    assert md.get("sha_mismatch") is True
    assert any("consensus_sha256 mismatch" in w for w in md["warnings"])
    # Original opening preserved untouched (source=detected)
    o0 = next(o for o in out["openings"] if o["id"] == "o0")
    assert o0["kind_v5"] == "interior_door"
    assert o0["source"] == "detected"


def test_sha_match_applies_normally():
    consensus = _consensus_payload()
    ov = _override("opening_kind_override", "opening", "o0",
                   payload={"new_kind_v5": "window"})
    expected = _consensus_sha256(consensus)
    doc = _overrides_doc(overrides=[ov], sha_override=expected)
    out = apply_overrides(consensus, doc, expected_sha=expected)
    assert out["_overrides_applied"] == 1
    o0 = next(o for o in out["openings"] if o["id"] == "o0")
    assert o0["kind_v5"] == "window"


# ---------------------------------------------------------------------------
# Test 6 — Precedence: reject > mark_suspect > kind/connect/label > approve
# ---------------------------------------------------------------------------


def test_precedence_reject_dominates_kind_change():
    """If both a kind_override and a reject_element target the same
    element, the reject wins — the element is dropped, not retagged."""
    consensus = _consensus_payload()
    ovs = [
        _override("opening_kind_override", "opening", "o0",
                  payload={"new_kind_v5": "window"},
                  created_at="2026-05-08T18:00:00Z"),
        _override("reject_element", "opening", "o0", payload={},
                  created_at="2026-05-08T19:00:00Z"),
    ]
    doc = _overrides_doc(overrides=ovs, consensus=consensus)
    out = apply_overrides(consensus, doc)
    ids = [o["id"] for o in out["openings"]]
    assert "o0" not in ids


def test_precedence_mark_suspect_with_kind_change_both_apply():
    """mark_suspect is additive (it only sets _suspect, doesn't replace
    fields), so a kind_override + mark_suspect on the same element
    should apply BOTH — the suspect tag rides along."""
    consensus = _consensus_payload()
    ovs = [
        _override("opening_kind_override", "opening", "o0",
                  payload={"new_kind_v5": "exterior_door"},
                  created_at="2026-05-08T18:00:00Z"),
        _override("mark_suspect", "opening", "o0",
                  payload={"severity": "high", "tag": "needs_review"},
                  created_at="2026-05-08T19:00:00Z"),
    ]
    doc = _overrides_doc(overrides=ovs, consensus=consensus)
    out = apply_overrides(consensus, doc)
    o0 = next(o for o in out["openings"] if o["id"] == "o0")
    assert o0["kind_v5"] == "exterior_door"
    assert o0["_kind_v5_original"] == "interior_door"
    assert o0["_suspect"] == {"severity": "high", "tag": "needs_review"}


def test_room_label_override_renames_and_preserves():
    consensus = _consensus_payload()
    ov = _override("room_label_override", "room", "r0",
                   payload={"new_name": "LIVING ROOM"})
    doc = _overrides_doc(overrides=[ov], consensus=consensus)
    out = apply_overrides(consensus, doc)
    r0 = next(r for r in out["rooms"] if r["id"] == "r0")
    assert r0["name"] == "LIVING ROOM"
    assert r0["_name_original"] == "SALA"
    assert r0["source"] == "manual"


def test_mark_suspect_invalid_severity_dropped():
    consensus = _consensus_payload()
    ov = _override("mark_suspect", "room", "r0",
                   payload={"severity": "extreme", "tag": "noisy"})
    doc = _overrides_doc(overrides=[ov], consensus=consensus)
    out = apply_overrides(consensus, doc)
    md = out["_overrides_metadata"]
    assert md["overrides_dropped_count"] == 1


# ---------------------------------------------------------------------------
# Test 7 — block_skp_export
# ---------------------------------------------------------------------------


def test_global_block_skp_export_recorded_in_metadata():
    consensus = _consensus_payload()
    doc = _overrides_doc(consensus=consensus,
                         global_block=True,
                         block_reason="needs review")
    out = apply_overrides(consensus, doc)
    md = out["_overrides_metadata"]
    assert md["block_skp_export"] is True
    assert md["block_reason"] == "needs review"


# ---------------------------------------------------------------------------
# Test 8 — Schema version mismatch → safe ignore
# ---------------------------------------------------------------------------


def test_unknown_schema_version_is_ignored_with_warning():
    consensus = _consensus_payload()
    bad = _overrides_doc(consensus=consensus)
    bad["schema_version"] = "review_overrides_v999"
    out = apply_overrides(consensus, bad)
    md = out["_overrides_metadata"]
    assert out["_overrides_applied"] == 0
    assert any("schema_version" in w for w in md["warnings"])


# ---------------------------------------------------------------------------
# Test 9 — Target unknown → drop
# ---------------------------------------------------------------------------


def test_unknown_target_dropped_with_warning():
    consensus = _consensus_payload()
    ov = _override("opening_kind_override", "opening", "oZZZ",
                   payload={"new_kind_v5": "window"})
    doc = _overrides_doc(overrides=[ov], consensus=consensus)
    out = apply_overrides(consensus, doc)
    md = out["_overrides_metadata"]
    assert md["overrides_dropped_count"] == 1
    assert out["_overrides_applied"] == 0


# ---------------------------------------------------------------------------
# Test 10 — Source consensus is never mutated (deep copy invariant)
# ---------------------------------------------------------------------------


def test_apply_overrides_does_not_mutate_source_consensus():
    consensus = _consensus_payload()
    snap = copy.deepcopy(consensus)
    ov = _override("opening_kind_override", "opening", "o0",
                   payload={"new_kind_v5": "window"})
    doc = _overrides_doc(overrides=[ov], consensus=consensus)
    apply_overrides(consensus, doc)
    assert consensus == snap


# ---------------------------------------------------------------------------
# Test 11 — CLI shell smoke
# ---------------------------------------------------------------------------


def test_cli_writes_amended_observed(tmp_path: Path):
    consensus = _consensus_payload()
    cons_path = tmp_path / "consensus.json"
    cons_path.write_text(json.dumps(consensus), encoding="utf-8")

    sha = _consensus_sha256(consensus)
    ov = _override("opening_kind_override", "opening", "o0",
                   payload={"new_kind_v5": "window"})
    doc = _overrides_doc(overrides=[ov], sha_override=sha)
    ovs_path = tmp_path / "review_overrides.json"
    ovs_path.write_text(json.dumps(doc), encoding="utf-8")

    out_path = tmp_path / "amended_observed.json"
    cmd = [
        sys.executable, "-m", "tools.apply_overrides",
        "--consensus", str(cons_path),
        "--overrides", str(ovs_path),
        "--output", str(out_path),
    ]
    proc = subprocess.run(
        cmd, cwd=str(REPO_ROOT), capture_output=True, text=True,
    )
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    assert out_path.exists()
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["_overrides_applied"] == 1
    assert (payload["_overrides_metadata"]["schema_version"]
            == AMENDED_SCHEMA_VERSION)


def test_cli_help_exits_zero():
    """`python -m tools.apply_overrides --help` must succeed."""
    proc = subprocess.run(
        [sys.executable, "-m", "tools.apply_overrides", "--help"],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
    )
    assert proc.returncode == 0
    assert "apply_overrides" in proc.stdout.lower()


def test_cli_works_without_overrides_file(tmp_path: Path):
    """Identity-copy mode: --overrides is optional."""
    consensus = _consensus_payload()
    cons_path = tmp_path / "consensus.json"
    cons_path.write_text(json.dumps(consensus), encoding="utf-8")
    out_path = tmp_path / "amended_observed.json"
    cmd = [
        sys.executable, "-m", "tools.apply_overrides",
        "--consensus", str(cons_path),
        "--output", str(out_path),
    ]
    proc = subprocess.run(
        cmd, cwd=str(REPO_ROOT), capture_output=True, text=True,
    )
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["_overrides_applied"] == 0
    for op in payload["openings"]:
        assert op["source"] == "detected"
