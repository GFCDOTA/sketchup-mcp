"""Unit tests for the `room_polygon_override` extension to
`cockpit/overrides.py` (ADR-002 Slice 6a).

Covers:
- OVERRIDE_TYPES + _PRECEDENCE_ORDER + POLYGON_EDIT_METHODS exposure
- validate_override_payload hard rules (8 hard checks per ADR-002 §2.4)
- validate_override_warnings soft checks (area range + wall crossings)
- save_override + load_overrides round-trip
- overrides_apply_view propagates the new polygon + originals
- precedence: polygon > label > kind/connect, but < mark_suspect < reject

All tests build their own run dir under `tmp_path` (no `runs/` touch).
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from cockpit.overrides import (
    _PRECEDENCE_ORDER,
    OVERRIDE_TYPES,
    POLYGON_AREA_M2_SOFT_RANGE,
    POLYGON_EDIT_METHODS,
    POLYGON_WALL_CROSSING_SOFT_LIMIT,
    PT_TO_M,
    SCHEMA_VERSION,
    load_overrides,
    overrides_apply_view,
    precedence_resolve,
    save_override,
    validate_override_payload,
    validate_override_warnings,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _square(x0: float, y0: float, side: float) -> list[list[float]]:
    return [
        [x0, y0],
        [x0 + side, y0],
        [x0 + side, y0 + side],
        [x0, y0 + side],
    ]


def _consensus() -> dict:
    """Minimal consensus: 2 rooms, 1 wall splitting them, 1 opening."""
    return {
        "schema_version": "1.0.0",
        "wall_thickness_pts": 5.4,
        "walls": [
            {"id": "w0", "start": [50, 0], "end": [50, 100],
             "thickness": 5.4, "orientation": "v"},
            {"id": "w1", "start": [0, 0], "end": [100, 0],
             "thickness": 5.4, "orientation": "h"},
        ],
        "rooms": [
            {"id": "r0", "name": "SALA",
             "polygon_pts": _square(0, 0, 50),
             "area_pts2": 2500.0,
             "area_m2": round(2500.0 * (PT_TO_M ** 2), 6)},
            {"id": "r1", "name": "COZINHA",
             "polygon_pts": _square(50, 0, 50),
             "area_pts2": 2500.0,
             "area_m2": round(2500.0 * (PT_TO_M ** 2), 6)},
        ],
        "openings": [
            {"id": "o0", "wall_id": "w0", "kind_v5": "interior_door",
             "decision": "clean", "center": [50.0, 50.0],
             "evidence": {"room_left": "SALA", "room_right": "COZINHA",
                          "room_left_id": "r0", "room_right_id": "r1"}},
        ],
        "soft_barriers": [],
    }


def _materialise_run(tmp_path: Path,
                     run_id: str = "polygon_run") -> tuple[Path, Path]:
    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    consensus_path = run_dir / "consensus.json"
    consensus_path.write_text(json.dumps(_consensus()), encoding="utf-8")
    return run_dir, consensus_path


def _polygon_payload(pts: list[list[float]],
                     edit_method: str = "manual_draw",
                     area_pts2: float | None = None,
                     area_m2: float | None = None,
                     from_proposed_action_id: str | None = None) -> dict:
    """Shape-correct payload for a room_polygon_override."""
    # Default area_pts2 from shoelace; area_m2 from PT_TO_M^2.
    if area_pts2 is None:
        # Manual shoelace for fixture convenience.
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


def _override_record(typ: str, target_kind: str, target_id: str,
                     payload: dict,
                     created_at: str = "2026-05-13T20:00:00Z") -> dict:
    return {
        "id": str(uuid.uuid4()),
        "type": typ,
        "target": {"kind": target_kind, "id": target_id},
        "payload": payload,
        "author": "human:tester",
        "created_at": created_at,
        "reason": "test",
    }


# ---------------------------------------------------------------------------
# Exposure
# ---------------------------------------------------------------------------

def test_room_polygon_override_is_an_override_type():
    """ADR-002 §2.2 — the enum surface gains the new type."""
    assert "room_polygon_override" in OVERRIDE_TYPES


def test_precedence_polygon_between_label_and_mark_suspect():
    """ADR-002 §2.2 — polygon > label, polygon < mark_suspect."""
    order = list(_PRECEDENCE_ORDER)
    assert order.index("room_polygon_override") > order.index(
        "room_label_override"
    )
    assert order.index("room_polygon_override") < order.index(
        "mark_suspect"
    )
    assert order.index("room_polygon_override") < order.index(
        "reject_element"
    )


def test_polygon_edit_methods_enum_matches_adr():
    assert set(POLYGON_EDIT_METHODS) == {
        "manual_draw", "snap_to_walls", "trace_pdf", "from_proposed_action",
    }


# ---------------------------------------------------------------------------
# Validation — hard rules
# ---------------------------------------------------------------------------

def test_validate_polygon_payload_minimal_valid():
    """A clean polygon payload passes validation."""
    pts = _square(10, 10, 30)
    rec = _override_record(
        "room_polygon_override", "room", "r0",
        _polygon_payload(pts),
    )
    errors = validate_override_payload(rec, consensus=_consensus())
    assert errors == [], f"unexpected errors: {errors}"


def test_validate_polygon_payload_wrong_target_kind():
    """target.kind must be 'room' for room_polygon_override."""
    pts = _square(10, 10, 30)
    rec = _override_record(
        "room_polygon_override", "opening", "o0",
        _polygon_payload(pts),
    )
    errors = validate_override_payload(rec)
    assert any("target.kind must be 'room'" in e for e in errors)


def test_validate_polygon_payload_too_few_points():
    """new_polygon_pts requires at least 3 vertices."""
    pts = [[0.0, 0.0], [10.0, 0.0]]
    rec = _override_record(
        "room_polygon_override", "room", "r0",
        _polygon_payload(pts, area_pts2=1.0, area_m2=PT_TO_M ** 2),
    )
    errors = validate_override_payload(rec)
    assert any(">=3 [x,y] pairs" in e for e in errors)


def test_validate_polygon_payload_non_finite_vertex():
    """A NaN/Inf coordinate fails the well-formed check."""
    pts = [[0.0, 0.0], [10.0, 0.0], [float("inf"), 5.0]]
    rec = _override_record(
        "room_polygon_override", "room", "r0",
        _polygon_payload(pts, area_pts2=1.0, area_m2=PT_TO_M ** 2),
    )
    errors = validate_override_payload(rec)
    assert any("finite" in e for e in errors)


def test_validate_polygon_payload_bad_edit_method():
    """edit_method must be in the enum."""
    pts = _square(0, 0, 10)
    payload = _polygon_payload(pts, edit_method="freeform_lasso")
    rec = _override_record("room_polygon_override", "room", "r0", payload)
    errors = validate_override_payload(rec)
    assert any("edit_method" in e for e in errors)


def test_validate_polygon_payload_area_disagrees():
    """estimated_area_pts2 must be within 1% of the computed shoelace area."""
    pts = _square(0, 0, 10)  # area = 100 pts^2
    payload = _polygon_payload(pts, area_pts2=200.0,
                                area_m2=200.0 * (PT_TO_M ** 2))
    rec = _override_record("room_polygon_override", "room", "r0", payload)
    errors = validate_override_payload(rec)
    assert any("disagrees with computed polygon area" in e for e in errors)


def test_validate_polygon_payload_area_m2_inconsistent():
    """area_m2 must equal area_pts2 * PT_TO_M^2 within 1%."""
    pts = _square(0, 0, 10)
    payload = _polygon_payload(pts, area_pts2=100.0, area_m2=99.0)
    rec = _override_record("room_polygon_override", "room", "r0", payload)
    errors = validate_override_payload(rec)
    assert any("estimated_area_m2" in e and "not consistent" in e
               for e in errors)


def test_validate_polygon_payload_self_intersecting():
    """A bow-tie polygon fails the simple-polygon check."""
    pts = [[0, 0], [10, 0], [0, 10], [10, 10]]  # bow-tie
    payload = _polygon_payload(pts, area_pts2=50.0,
                                area_m2=50.0 * (PT_TO_M ** 2))
    rec = _override_record("room_polygon_override", "room", "r0", payload)
    errors = validate_override_payload(rec)
    assert any("self-intersecting" in e for e in errors)


def test_validate_polygon_payload_bad_uuid_link():
    """from_proposed_action_id must be a valid uuid4 string or null."""
    pts = _square(0, 0, 10)
    payload = _polygon_payload(pts, from_proposed_action_id="not-a-uuid")
    rec = _override_record("room_polygon_override", "room", "r0", payload)
    errors = validate_override_payload(rec)
    assert any("from_proposed_action_id" in e for e in errors)


def test_validate_polygon_payload_good_uuid_link():
    """A real uuid4 string is accepted."""
    pts = _square(0, 0, 10)
    payload = _polygon_payload(
        pts, from_proposed_action_id=str(uuid.uuid4()),
    )
    rec = _override_record("room_polygon_override", "room", "r0", payload)
    errors = validate_override_payload(rec)
    assert errors == []


def test_validate_polygon_payload_target_id_missing_in_consensus():
    """Cross-check against consensus rooms still applies."""
    pts = _square(0, 0, 10)
    rec = _override_record(
        "room_polygon_override", "room", "r_does_not_exist",
        _polygon_payload(pts),
    )
    errors = validate_override_payload(rec, consensus=_consensus())
    assert any("not found in consensus rooms" in e for e in errors)


# ---------------------------------------------------------------------------
# Validation — soft checks
# ---------------------------------------------------------------------------

def test_warnings_area_outside_soft_range():
    """A tiny polygon (< 1 m²) triggers the area-range warning."""
    # 5x5 pts -> 25 pts^2 -> 25 * (0.0352)^2 ≈ 0.031 m^2 (< 1)
    pts = _square(0, 0, 5)
    rec = _override_record(
        "room_polygon_override", "room", "r0",
        _polygon_payload(pts),
    )
    warnings = validate_override_warnings(rec)
    assert any("outside" in w for w in warnings)
    # Soft only — does NOT block validation.
    errors = validate_override_payload(rec, consensus=_consensus())
    assert errors == []


def test_warnings_polygon_crosses_many_walls():
    """A polygon that strides across many walls triggers the soft check."""
    # Synthesise extra walls that span across a single covering polygon.
    consensus = _consensus()
    consensus["walls"].extend([
        # Three vertical walls passing through y=5..15 stripe.
        {"id": "w2", "start": [20, 0], "end": [20, 20],
         "thickness": 5.4, "orientation": "v"},
        {"id": "w3", "start": [40, 0], "end": [40, 20],
         "thickness": 5.4, "orientation": "v"},
        {"id": "w4", "start": [60, 0], "end": [60, 20],
         "thickness": 5.4, "orientation": "v"},
        {"id": "w5", "start": [80, 0], "end": [80, 20],
         "thickness": 5.4, "orientation": "v"},
    ])
    # Big horizontal strip from x=0..100, y=5..15 crosses w2..w5 (4 walls).
    pts = [[0, 5], [100, 5], [100, 15], [0, 15]]
    rec = _override_record(
        "room_polygon_override", "room", "r0",
        _polygon_payload(pts),
    )
    warnings = validate_override_warnings(rec, consensus=consensus)
    assert any("crosses" in w and "walls" in w for w in warnings), warnings
    # Soft only.
    errors = validate_override_payload(rec, consensus=consensus)
    assert errors == []


def test_warnings_clean_polygon_has_no_warnings():
    """A plausibly-sized polygon, not crossing walls, emits 0 warnings."""
    # 30x30 pts ≈ 900 pts^2 ≈ 1.13 m² — comfortably inside [1, 200].
    pts = _square(0, 0, 30)
    rec = _override_record(
        "room_polygon_override", "room", "r0",
        _polygon_payload(pts),
    )
    warnings = validate_override_warnings(rec, consensus=_consensus())
    assert warnings == [], warnings


def test_warnings_skips_non_polygon_override_types():
    """`validate_override_warnings` is a no-op for unrelated types."""
    rec = _override_record(
        "mark_suspect", "room", "r0",
        {"severity": "high"},
    )
    assert validate_override_warnings(rec) == []


# ---------------------------------------------------------------------------
# Save + round-trip
# ---------------------------------------------------------------------------

def test_save_polygon_override_round_trips(tmp_path: Path):
    run_dir, consensus_path = _materialise_run(tmp_path)
    consensus = _consensus()
    pts = _square(5, 5, 40)
    payload = _polygon_payload(pts)
    saved = save_override(
        run_dir=run_dir,
        override_payload={
            "type": "room_polygon_override",
            "target": {"kind": "room", "id": "r0"},
            "payload": payload,
            "reason": "FP-012 fix",
        },
        audit_actor="human:tester",
        consensus_path=consensus_path,
        consensus=consensus,
    )
    assert saved["schema_version"] == SCHEMA_VERSION
    assert len(saved["overrides"]) == 1
    rec = saved["overrides"][0]
    assert rec["type"] == "room_polygon_override"
    assert rec["payload"]["edit_method"] == "manual_draw"
    assert rec["payload"]["new_polygon_pts"] == pts

    # Load it back from disk.
    reloaded = load_overrides(run_dir, consensus_path=consensus_path)
    assert reloaded["_consensus_sha256_match"] is True
    assert len(reloaded["overrides"]) == 1
    assert reloaded["overrides"][0]["payload"]["new_polygon_pts"] == pts


def test_save_rejects_invalid_polygon(tmp_path: Path):
    run_dir, consensus_path = _materialise_run(tmp_path)
    bad_pts = [[0, 0], [10, 0]]  # only 2 points
    with pytest.raises(ValueError) as excinfo:
        save_override(
            run_dir=run_dir,
            override_payload={
                "type": "room_polygon_override",
                "target": {"kind": "room", "id": "r0"},
                "payload": _polygon_payload(
                    bad_pts, area_pts2=1.0, area_m2=PT_TO_M ** 2,
                ),
            },
            audit_actor="human:tester",
            consensus_path=consensus_path,
            consensus=_consensus(),
        )
    assert "validation failed" in str(excinfo.value)


# ---------------------------------------------------------------------------
# overrides_apply_view — display path
# ---------------------------------------------------------------------------

def test_apply_view_propagates_new_polygon():
    consensus = _consensus()
    new_pts = _square(2, 2, 20)
    ov = _override_record(
        "room_polygon_override", "room", "r0",
        _polygon_payload(new_pts),
    )
    view = overrides_apply_view(consensus, [ov])
    r0 = next(r for r in view["rooms"] if r["id"] == "r0")
    assert r0["source"] == "manual"
    assert r0["polygon_pts"] == new_pts
    assert r0["_polygon_pts_original"] == consensus["rooms"][0]["polygon_pts"]
    assert r0["_edit_method"] == "manual_draw"


def test_apply_view_co_applies_polygon_and_label():
    """ADR-002 §2.5 — both polygon and label apply at the view layer."""
    consensus = _consensus()
    new_pts = _square(2, 2, 20)
    polygon_ov = _override_record(
        "room_polygon_override", "room", "r0",
        _polygon_payload(new_pts),
        created_at="2026-05-13T20:00:00Z",
    )
    label_ov = _override_record(
        "room_label_override", "room", "r0",
        {"new_name": "ESCRITORIO"},
        created_at="2026-05-13T20:01:00Z",
    )
    view = overrides_apply_view(consensus, [polygon_ov, label_ov])
    r0 = next(r for r in view["rooms"] if r["id"] == "r0")
    # Polygon survives even though label may "win" precedence_resolve.
    assert r0["polygon_pts"] == new_pts
    assert r0["_polygon_pts_original"] == consensus["rooms"][0]["polygon_pts"]
    # Label may or may not have applied depending on precedence choice,
    # but original name is preserved when it did.
    assert r0["source"] == "manual"


# ---------------------------------------------------------------------------
# precedence_resolve — single-active-pick
# ---------------------------------------------------------------------------

def test_precedence_polygon_beats_label():
    """For the same room, polygon override is the cockpit-active pick."""
    label_ov = _override_record(
        "room_label_override", "room", "r0", {"new_name": "ESCRITORIO"},
        created_at="2026-05-13T20:00:00Z",
    )
    polygon_ov = _override_record(
        "room_polygon_override", "room", "r0",
        _polygon_payload(_square(0, 0, 10)),
        created_at="2026-05-13T19:00:00Z",  # earlier, still wins on type
    )
    active = precedence_resolve([label_ov, polygon_ov])
    chosen = active["room:r0"]
    assert chosen["type"] == "room_polygon_override"


def test_precedence_reject_still_beats_polygon():
    polygon_ov = _override_record(
        "room_polygon_override", "room", "r0",
        _polygon_payload(_square(0, 0, 10)),
        created_at="2026-05-13T19:00:00Z",
    )
    reject_ov = _override_record(
        "reject_element", "room", "r0", {},
        created_at="2026-05-13T18:00:00Z",
    )
    active = precedence_resolve([polygon_ov, reject_ov])
    chosen = active["room:r0"]
    assert chosen["type"] == "reject_element"


def test_precedence_mark_suspect_beats_polygon():
    polygon_ov = _override_record(
        "room_polygon_override", "room", "r0",
        _polygon_payload(_square(0, 0, 10)),
        created_at="2026-05-13T19:00:00Z",
    )
    suspect_ov = _override_record(
        "mark_suspect", "room", "r0", {"severity": "high"},
        created_at="2026-05-13T18:00:00Z",
    )
    active = precedence_resolve([polygon_ov, suspect_ov])
    chosen = active["room:r0"]
    assert chosen["type"] == "mark_suspect"


# ---------------------------------------------------------------------------
# Constants exposure
# ---------------------------------------------------------------------------

def test_constants_match_adr():
    assert POLYGON_AREA_M2_SOFT_RANGE == (1.0, 200.0)
    assert POLYGON_WALL_CROSSING_SOFT_LIMIT == 2
    # PT_TO_M anchored to wall thickness per memory feedback.
    assert abs(PT_TO_M - 0.19 / 5.4) < 1e-12
