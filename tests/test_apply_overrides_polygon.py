"""Unit tests for the `room_polygon_override` extension to
`tools/apply_overrides.py` (ADR-002 Slice 6a).

Covers:
- Apply replaces polygon_pts / area_pts2 / area_m2 + preserves
  `_polygon_pts_original` / `_area_pts2_original` / `_area_m2_original`.
- `source: manual` + `_edit_method` + optional `_source_proposed_action_id`.
- `_overrides_metadata.polygon_overrides_applied_count` tracks count.
- Validation drop reasons (bad edit_method / bad pts / missing area).
- Precedence: reject still drops the room; mark_suspect still flags it;
  polygon + label coapply on disjoint fields.
- CLI round-trip writes the new metadata field.
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

PT_TO_M = 0.19 / 5.4


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _consensus_payload() -> dict:
    """Minimal consensus: 2 rooms, 1 wall, 1 opening."""
    return {
        "schema_version": "1.0.0",
        "wall_thickness_pts": 5.4,
        "plan_id": "test_polygon_fixture",
        "walls": [
            {"id": "w0", "start": [50, 0], "end": [50, 100],
             "thickness": 5.4, "orientation": "v"},
        ],
        "rooms": [
            {"id": "r0", "name": "SALA",
             "polygon_pts": [[0, 0], [50, 0], [50, 100], [0, 100]],
             "area_pts2": 5000.0,
             "area_m2": round(5000.0 * (PT_TO_M ** 2), 6)},
            {"id": "r1", "name": "COZINHA",
             "polygon_pts": [[50, 0], [100, 0], [100, 100], [50, 100]],
             "area_pts2": 5000.0,
             "area_m2": round(5000.0 * (PT_TO_M ** 2), 6)},
        ],
        "openings": [
            {"id": "o0", "wall_id": "w0", "kind_v5": "interior_door",
             "decision": "clean",
             "room_left_id": "r0", "room_right_id": "r1",
             "evidence": {"room_left": "SALA", "room_right": "COZINHA"}},
        ],
        "soft_barriers": [],
    }


def _polygon_payload(pts: list,
                     edit_method: str = "manual_draw",
                     area_pts2: float | None = None,
                     area_m2: float | None = None,
                     from_proposed_action_id: str | None = None) -> dict:
    if area_pts2 is None:
        acc = 0.0
        n = len(pts)
        for i in range(n):
            x0, y0 = pts[i]
            x1, y1 = pts[(i + 1) % n]
            acc += x0 * y1 - x1 * y0
        area_pts2 = abs(acc) * 0.5
    if area_m2 is None:
        area_m2 = area_pts2 * (PT_TO_M ** 2)
    body = {
        "new_polygon_pts": pts,
        "edit_method": edit_method,
        "estimated_area_pts2": float(area_pts2),
        "estimated_area_m2": float(area_m2),
    }
    if from_proposed_action_id is not None:
        body["from_proposed_action_id"] = from_proposed_action_id
    return body


def _override(otype: str, target_kind: str, target_id: str,
              payload: dict | None = None,
              author: str = "human:tester",
              created_at: str = "2026-05-13T20:00:00Z") -> dict:
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


def _overrides_doc(overrides: list[dict] | None,
                   consensus: dict | None,
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
        "created_at": "2026-05-13T20:00:00Z",
        "last_updated_at": "2026-05-13T20:00:00Z",
        "overrides": list(overrides or []),
        "global": {"block_skp_export": False, "block_reason": None},
        "audit_trail": [],
    }


# ---------------------------------------------------------------------------
# Apply: replacement + originals preserved
# ---------------------------------------------------------------------------

def test_polygon_override_replaces_geometry_and_preserves_originals():
    consensus = _consensus_payload()
    new_pts = [[10, 10], [40, 10], [40, 40], [10, 40]]  # 30x30 = 900 pts²
    payload = _polygon_payload(new_pts)
    ov = _override("room_polygon_override", "room", "r0", payload)
    doc = _overrides_doc([ov], consensus)
    amended = apply_overrides(consensus, doc)

    r0 = next(r for r in amended["rooms"] if r["id"] == "r0")
    assert r0["polygon_pts"] == new_pts
    assert r0["area_pts2"] == pytest.approx(900.0)
    assert r0["area_m2"] == pytest.approx(900.0 * (PT_TO_M ** 2))
    # Originals preserved
    assert r0["_polygon_pts_original"] == consensus["rooms"][0]["polygon_pts"]
    assert r0["_area_pts2_original"] == consensus["rooms"][0]["area_pts2"]
    assert r0["_area_m2_original"] == consensus["rooms"][0]["area_m2"]
    # Source attribution
    assert r0["source"] == "manual"
    assert r0["_edit_method"] == "manual_draw"


def test_polygon_override_records_proposed_action_link():
    consensus = _consensus_payload()
    fpa_id = str(uuid.uuid4())
    payload = _polygon_payload(
        [[10, 10], [40, 10], [40, 40], [10, 40]],
        edit_method="from_proposed_action",
        from_proposed_action_id=fpa_id,
    )
    ov = _override("room_polygon_override", "room", "r0", payload)
    amended = apply_overrides(consensus, _overrides_doc([ov], consensus))
    r0 = next(r for r in amended["rooms"] if r["id"] == "r0")
    assert r0["_source_proposed_action_id"] == fpa_id
    assert r0["_edit_method"] == "from_proposed_action"


# ---------------------------------------------------------------------------
# Metadata counter
# ---------------------------------------------------------------------------

def test_polygon_overrides_applied_count_zero_without_polygon_overrides():
    consensus = _consensus_payload()
    # A non-polygon override only.
    ov = _override("room_label_override", "room", "r0",
                    {"new_name": "ESCRITORIO"})
    amended = apply_overrides(consensus, _overrides_doc([ov], consensus))
    md = amended.get("_overrides_metadata") or {}
    assert md.get("polygon_overrides_applied_count") == 0
    # overrides_applied_count still ticks for the label change.
    assert md.get("overrides_applied_count") == 1


def test_polygon_overrides_applied_count_increments_per_polygon_override():
    consensus = _consensus_payload()
    polygon_r0 = _override(
        "room_polygon_override", "room", "r0",
        _polygon_payload([[10, 10], [40, 10], [40, 40], [10, 40]]),
        created_at="2026-05-13T19:00:00Z",
    )
    polygon_r1 = _override(
        "room_polygon_override", "room", "r1",
        _polygon_payload([[60, 10], [90, 10], [90, 40], [60, 40]]),
        created_at="2026-05-13T19:05:00Z",
    )
    amended = apply_overrides(
        consensus, _overrides_doc([polygon_r0, polygon_r1], consensus),
    )
    md = amended["_overrides_metadata"]
    assert md["polygon_overrides_applied_count"] == 2
    assert md["overrides_applied_count"] == 2


# ---------------------------------------------------------------------------
# Validation drops
# ---------------------------------------------------------------------------

def test_polygon_override_dropped_when_target_kind_is_opening():
    consensus = _consensus_payload()
    payload = _polygon_payload([[0, 0], [10, 0], [10, 10], [0, 10]])
    bad = _override("room_polygon_override", "opening", "o0", payload)
    amended = apply_overrides(consensus, _overrides_doc([bad], consensus))
    md = amended["_overrides_metadata"]
    assert md["polygon_overrides_applied_count"] == 0
    assert md["overrides_dropped_count"] == 1
    assert any("target.kind must be 'room'" in w for w in md["warnings"])


def test_polygon_override_dropped_when_edit_method_invalid():
    consensus = _consensus_payload()
    payload = _polygon_payload(
        [[0, 0], [10, 0], [10, 10], [0, 10]],
        edit_method="freeform_lasso",
    )
    bad = _override("room_polygon_override", "room", "r0", payload)
    amended = apply_overrides(consensus, _overrides_doc([bad], consensus))
    md = amended["_overrides_metadata"]
    assert md["polygon_overrides_applied_count"] == 0
    assert md["overrides_dropped_count"] == 1
    assert any("edit_method" in w for w in md["warnings"])


def test_polygon_override_dropped_when_pts_below_three():
    consensus = _consensus_payload()
    body = _polygon_payload([[0, 0], [10, 0]], area_pts2=1.0,
                              area_m2=1.0 * (PT_TO_M ** 2))
    bad = _override("room_polygon_override", "room", "r0", body)
    amended = apply_overrides(consensus, _overrides_doc([bad], consensus))
    md = amended["_overrides_metadata"]
    assert md["polygon_overrides_applied_count"] == 0
    assert md["overrides_dropped_count"] == 1
    assert any(">=3" in w for w in md["warnings"])


def test_polygon_override_dropped_when_area_missing_or_negative():
    consensus = _consensus_payload()
    pts = [[0, 0], [10, 0], [10, 10], [0, 10]]
    body = {
        "new_polygon_pts": pts,
        "edit_method": "manual_draw",
        "estimated_area_pts2": -1.0,
        "estimated_area_m2": 5.0,
    }
    bad = _override("room_polygon_override", "room", "r0", body)
    amended = apply_overrides(consensus, _overrides_doc([bad], consensus))
    md = amended["_overrides_metadata"]
    assert md["overrides_dropped_count"] == 1
    assert any("estimated_area_pts2" in w for w in md["warnings"])


# ---------------------------------------------------------------------------
# Precedence interactions
# ---------------------------------------------------------------------------

def test_reject_element_still_drops_room_with_polygon_override():
    """ADR-002 §2.5 — reject dominates; polygon is a no-op."""
    consensus = _consensus_payload()
    polygon = _override(
        "room_polygon_override", "room", "r0",
        _polygon_payload([[10, 10], [40, 10], [40, 40], [10, 40]]),
        created_at="2026-05-13T19:00:00Z",
    )
    reject = _override(
        "reject_element", "room", "r0", {},
        created_at="2026-05-13T20:00:00Z",
    )
    amended = apply_overrides(
        consensus, _overrides_doc([polygon, reject], consensus),
    )
    # r0 dropped from rooms entirely.
    assert all(r["id"] != "r0" for r in amended["rooms"])
    md = amended["_overrides_metadata"]
    assert "r0" in md.get("rejected_room_ids", [])
    # Polygon never applied.
    assert md["polygon_overrides_applied_count"] == 0


def test_polygon_and_label_coapply_on_same_room():
    """Both apply — polygon mutates geometry, label mutates name."""
    consensus = _consensus_payload()
    new_pts = [[10, 10], [40, 10], [40, 40], [10, 40]]
    polygon = _override(
        "room_polygon_override", "room", "r0",
        _polygon_payload(new_pts),
        created_at="2026-05-13T19:00:00Z",
    )
    label = _override(
        "room_label_override", "room", "r0",
        {"new_name": "ESCRITORIO"},
        created_at="2026-05-13T19:10:00Z",
    )
    amended = apply_overrides(
        consensus, _overrides_doc([polygon, label], consensus),
    )
    r0 = next(r for r in amended["rooms"] if r["id"] == "r0")
    assert r0["name"] == "ESCRITORIO"
    assert r0["polygon_pts"] == new_pts
    assert r0["_name_original"] == "SALA"
    assert r0["_polygon_pts_original"] == consensus["rooms"][0]["polygon_pts"]
    md = amended["_overrides_metadata"]
    assert md["overrides_applied_count"] == 2
    assert md["polygon_overrides_applied_count"] == 1


def test_mark_suspect_polygon_room_keeps_both_signals():
    consensus = _consensus_payload()
    new_pts = [[10, 10], [40, 10], [40, 40], [10, 40]]
    polygon = _override(
        "room_polygon_override", "room", "r0",
        _polygon_payload(new_pts),
        created_at="2026-05-13T19:00:00Z",
    )
    suspect = _override(
        "mark_suspect", "room", "r0",
        {"severity": "high", "tag": "geometry_unclear"},
        created_at="2026-05-13T19:05:00Z",
    )
    amended = apply_overrides(
        consensus, _overrides_doc([polygon, suspect], consensus),
    )
    r0 = next(r for r in amended["rooms"] if r["id"] == "r0")
    assert r0["polygon_pts"] == new_pts
    assert r0["_suspect"] == {"severity": "high", "tag": "geometry_unclear"}


# ---------------------------------------------------------------------------
# Schema header — amended doc still well-formed
# ---------------------------------------------------------------------------

def test_amended_schema_version_unchanged():
    """ADR-002 is additive — schema_version stays at v1."""
    consensus = _consensus_payload()
    amended = apply_overrides(consensus, _overrides_doc(None, consensus))
    md = amended["_overrides_metadata"]
    assert md["schema_version"] == AMENDED_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# CLI round-trip
# ---------------------------------------------------------------------------

def test_cli_round_trip_writes_polygon_count(tmp_path: Path):
    consensus = _consensus_payload()
    pts = [[10, 10], [40, 10], [40, 40], [10, 40]]
    polygon = _override(
        "room_polygon_override", "room", "r0",
        _polygon_payload(pts),
    )
    consensus_path = tmp_path / "consensus.json"
    consensus_path.write_text(json.dumps(consensus), encoding="utf-8")
    overrides_path = tmp_path / "review_overrides.json"
    overrides_path.write_text(
        json.dumps(_overrides_doc([polygon], consensus)),
        encoding="utf-8",
    )
    out_path = tmp_path / "amended_observed.json"

    res = subprocess.run(
        [sys.executable, "-m", "tools.apply_overrides",
         "--consensus", str(consensus_path),
         "--overrides", str(overrides_path),
         "--output", str(out_path)],
        cwd=str(REPO_ROOT),
        capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr
    amended = json.loads(out_path.read_text(encoding="utf-8"))
    md = amended["_overrides_metadata"]
    assert md["polygon_overrides_applied_count"] == 1
    r0 = next(r for r in amended["rooms"] if r["id"] == "r0")
    assert r0["polygon_pts"] == pts
    assert r0["_polygon_pts_original"] == consensus["rooms"][0]["polygon_pts"]
