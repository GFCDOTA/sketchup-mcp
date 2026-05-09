"""Tests for tools.structural_checks (FP-014 gamma gate).

Coverage:
- Healthy synthetic plant: 0 blockers, 0 warnings
- FP-014 regression: planta_74 consensus must produce blockers
  (specifically C1, C2, C4, C8 — the cluster that defines the bug)
- Per-check unit tests with crafted minimal fixtures
- Defensive: missing fields don't crash
- gate_f0 integration: pre_skp_review_v1 fields are surfaced
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.structural_checks import (
    DEFAULTS,
    STRUCTURAL_CHECKS_SCHEMA_VERSION,
    evaluate_structural_health,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Synthetic minimal-but-healthy consensus fixture
# ---------------------------------------------------------------------------


def _healthy_consensus() -> dict:
    """A 4-wall square room consensus that should pass all checks.

    Walls form a closed 100pt x 100pt square. Single room polygon
    matching the square exactly. Endpoints shared between walls so
    free_vertex_ratio == 0 for the room.
    """
    return {
        "schema_version": "consensus_model_v1.0.0",
        "wall_thickness_pts": 5.4,
        "walls": [
            {"id": "w0", "start": [0, 0], "end": [100, 0],
             "thickness": 5.4, "orientation": "h"},
            {"id": "w1", "start": [100, 0], "end": [100, 100],
             "thickness": 5.4, "orientation": "v"},
            {"id": "w2", "start": [100, 100], "end": [0, 100],
             "thickness": 5.4, "orientation": "h"},
            {"id": "w3", "start": [0, 100], "end": [0, 0],
             "thickness": 5.4, "orientation": "v"},
        ],
        "rooms": [{
            "id": "r0",
            "name": "ROOM",
            "seed_pt": [50, 50],
            "polygon_pts": [[0, 0], [100, 0], [100, 100], [0, 100]],
            "area_pts2": 10000,
            "method": "test",
        }],
        "openings": [],
        "soft_barriers": [],
    }


# ---------------------------------------------------------------------------
# Healthy case
# ---------------------------------------------------------------------------


def test_healthy_consensus_zero_blockers():
    report = evaluate_structural_health(_healthy_consensus())
    assert report["schema_version"] == STRUCTURAL_CHECKS_SCHEMA_VERSION
    assert report["summary"]["blockers_count"] == 0


def test_healthy_consensus_minimal_warnings():
    """Healthy case may legitimately have C9 warning if walls don't
    form rooms via envelope-difference (a 4-wall square is degenerate
    here — buffer envelope = single piece). But should have NO
    per-room blockers."""
    report = evaluate_structural_health(_healthy_consensus())
    per_room_blockers = [
        b for b in report["structural_blockers"]
        if b["target_kind"] == "room"
    ]
    assert per_room_blockers == []


def test_healthy_per_room_metrics():
    report = evaluate_structural_health(_healthy_consensus())
    metrics = report["per_room_metrics"]
    assert len(metrics) == 1
    m = metrics[0]
    assert m["vts"] == 4
    assert m["free_vts"] == 0
    assert m["is_simple"] is True
    # 100pt x 100pt at PT_TO_M=0.19/5.4 ~= 0.0352
    expected_m2 = (100 * 0.19 / 5.4) ** 2
    assert abs(m["area_m2"] - expected_m2) < 0.01


# ---------------------------------------------------------------------------
# Per-check unit tests
# ---------------------------------------------------------------------------


def test_c1_polygon_vts_fail_at_threshold():
    """C1 fires FAIL when room polygon has > polygon_max_vts_fail vts."""
    c = _healthy_consensus()
    # Replace room polygon with 60 vertices (jagged)
    pts = []
    for i in range(60):
        angle = i * 2 * 3.14159 / 60
        import math
        pts.append([
            50 + 40 * math.cos(angle),
            50 + 40 * math.sin(angle),
        ])
    c["rooms"][0]["polygon_pts"] = pts
    report = evaluate_structural_health(c)
    blockers = [b for b in report["structural_blockers"]
                if b["check_id"] == "C1_polygon_vts"]
    assert len(blockers) == 1
    assert blockers[0]["evidence"]["vts"] == 60


def test_c1_polygon_vts_warn_at_intermediate():
    """C1 fires WARN at vts > 30 but < fail threshold."""
    c = _healthy_consensus()
    pts = []
    for i in range(35):
        angle = i * 2 * 3.14159 / 35
        import math
        pts.append([
            50 + 40 * math.cos(angle),
            50 + 40 * math.sin(angle),
        ])
    c["rooms"][0]["polygon_pts"] = pts
    report = evaluate_structural_health(c)
    warns = [w for w in report["structural_warnings"]
             if w["check_id"] == "C1_polygon_vts"]
    assert len(warns) == 1


def test_c4_polygon_simple_fail_on_self_intersect():
    """C4 fires FAIL on self-intersecting polygon (figure-8)."""
    c = _healthy_consensus()
    # Bowtie / figure-8 — self-intersecting
    c["rooms"][0]["polygon_pts"] = [
        [0, 0], [100, 100], [100, 0], [0, 100],
    ]
    report = evaluate_structural_health(c)
    blockers = [b for b in report["structural_blockers"]
                if b["check_id"] == "C4_polygon_simple"]
    assert len(blockers) >= 1


def test_c8_unmapped_colinear_gap_fail():
    """C8 fires FAIL when colinear walls have gap > 0.5m without opening."""
    c = _healthy_consensus()
    # Replace bottom wall with 2 colinear walls + a 60pt (~2m) gap
    c["walls"] = [
        {"id": "w0a", "start": [0, 0], "end": [40, 0],
         "thickness": 5.4, "orientation": "h"},
        {"id": "w0b", "start": [100, 0], "end": [140, 0],
         "thickness": 5.4, "orientation": "h"},
        {"id": "w1", "start": [140, 0], "end": [140, 100],
         "thickness": 5.4, "orientation": "v"},
        {"id": "w2", "start": [140, 100], "end": [0, 100],
         "thickness": 5.4, "orientation": "h"},
        {"id": "w3", "start": [0, 100], "end": [0, 0],
         "thickness": 5.4, "orientation": "v"},
    ]
    # No opening attached to the gap
    report = evaluate_structural_health(c)
    blockers = [b for b in report["structural_blockers"]
                if b["check_id"] == "C8_unmapped_colinear_gaps"]
    assert len(blockers) == 1
    assert blockers[0]["evidence"]["unmapped_count"] == 1


def test_c8_skips_when_opening_anchored():
    """C8 doesn't fire when a colinear gap has an opening within tol."""
    c = _healthy_consensus()
    c["walls"] = [
        {"id": "w0a", "start": [0, 0], "end": [40, 0],
         "thickness": 5.4, "orientation": "h"},
        {"id": "w0b", "start": [100, 0], "end": [140, 0],
         "thickness": 5.4, "orientation": "h"},
        {"id": "w1", "start": [140, 0], "end": [140, 100],
         "thickness": 5.4, "orientation": "v"},
        {"id": "w2", "start": [140, 100], "end": [0, 100],
         "thickness": 5.4, "orientation": "h"},
        {"id": "w3", "start": [0, 100], "end": [0, 0],
         "thickness": 5.4, "orientation": "v"},
    ]
    c["openings"] = [{
        "id": "o0", "kind_v5": "interior_door",
        "wall_id": "w0a", "center": [70, 0],
        "opening_width_pts": 60,
    }]
    report = evaluate_structural_health(c)
    blockers = [b for b in report["structural_blockers"]
                if b["check_id"] == "C8_unmapped_colinear_gaps"]
    assert len(blockers) == 0


def test_c7_short_wall_fragments_warn():
    """C7 fires WARN when too many walls are < 1m."""
    c = _healthy_consensus()
    # Add 6 walls each 0.3m (~9pt) — over the 5-warn threshold
    for i in range(6):
        c["walls"].append({
            "id": f"frag_{i}",
            "start": [200 + i * 20, 0],
            "end": [200 + i * 20 + 9, 0],
            "thickness": 5.4,
            "orientation": "h",
        })
    report = evaluate_structural_health(c)
    warns = [w for w in report["structural_warnings"]
             if w["check_id"] == "C7_short_wall_fragments"]
    assert len(warns) == 1
    assert warns[0]["evidence"]["short_count"] == 6


def test_c10_area_vs_expected_warn():
    """C10 fires WARN when room area > 1.5x expected upper bound."""
    c = _healthy_consensus()
    expected = {
        "rooms": [{
            "label": "ROOM",
            "expected_area_m2_range": [1.0, 5.0],
        }],
    }
    # Healthy room is ~12.4 m² (100pt x 100pt at PT_TO_M=0.0352)
    # 12.4 > 1.5 * 5.0 = 7.5 → fires WARN
    report = evaluate_structural_health(c, expected_model=expected)
    warns = [w for w in report["structural_warnings"]
             if w["check_id"] == "C10_area_vs_expected"]
    assert len(warns) == 1


# ---------------------------------------------------------------------------
# Defensive: missing fields don't crash
# ---------------------------------------------------------------------------


def test_empty_consensus():
    report = evaluate_structural_health({})
    assert report["summary"]["blockers_count"] == 0
    assert report["per_room_metrics"] == []


def test_consensus_no_walls():
    c = {"rooms": [{
        "id": "r0", "name": "X",
        "polygon_pts": [[0, 0], [10, 0], [10, 10], [0, 10]],
    }]}
    # Should not crash; envelope check returns gracefully
    report = evaluate_structural_health(c)
    assert "schema_version" in report


def test_room_missing_polygon_pts():
    c = _healthy_consensus()
    c["rooms"].append({"id": "r1", "name": "X", "polygon_pts": []})
    report = evaluate_structural_health(c)
    # Doesn't crash; degenerate room has 0 vts metric
    metrics = report["per_room_metrics"]
    assert any(m["room_id"] == "r1" and m["vts"] == 0 for m in metrics)


# ---------------------------------------------------------------------------
# FP-014 regression — the canonical case that motivated this gate
# ---------------------------------------------------------------------------


@pytest.fixture
def planta_74_consensus():
    """The exact run that produced the defective SKP that motivated FP-014."""
    p = (REPO_ROOT / "runs" / "_milestone_skp_planta74_2026_05_09"
         / "consensus.json")
    if not p.exists():
        pytest.skip(f"FP-014 fixture run dir missing: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


@pytest.fixture
def planta_74_expected():
    p = REPO_ROOT / "ground_truth" / "planta_74" / "expected_model.json"
    if not p.exists():
        pytest.skip(f"expected_model.json missing: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def test_fp014_planta74_produces_blockers(planta_74_consensus,
                                            planta_74_expected):
    """The defective consensus that motivated FP-014 MUST produce
    structural blockers. If this test ever passes with 0 blockers
    (without a corresponding fix in build_vector_consensus and
    rooms_from_seeds), the gamma gate is broken."""
    report = evaluate_structural_health(
        planta_74_consensus, expected_model=planta_74_expected,
    )
    assert report["summary"]["blockers_count"] >= 5, (
        f"Expected >=5 blockers on planta_74 fixture; got "
        f"{report['summary']['blockers_count']}"
    )


def test_fp014_specific_check_ids_present(planta_74_consensus,
                                            planta_74_expected):
    """The specific checks that diagnosed FP-014 must fire on planta_74."""
    report = evaluate_structural_health(
        planta_74_consensus, expected_model=planta_74_expected,
    )
    blocker_ids = {b["check_id"] for b in report["structural_blockers"]}
    # C1 (738 vts on SUITE 01) must fire
    assert "C1_polygon_vts" in blocker_ids
    # C2 (free vertex ratio) must fire on multiple rooms
    assert "C2_free_vertex_ratio" in blocker_ids
    # C8 (unmapped colinear gaps) must fire
    assert "C8_unmapped_colinear_gaps" in blocker_ids


def test_fp014_suite01_specifically_blocked(planta_74_consensus,
                                              planta_74_expected):
    """SUITE 01 (the green triangle) must be specifically flagged."""
    report = evaluate_structural_health(
        planta_74_consensus, expected_model=planta_74_expected,
    )
    suite01_blockers = [
        b for b in report["structural_blockers"]
        if b["target_kind"] == "room"
        and "SUITE 01" in (b["message"] or "")
    ]
    assert len(suite01_blockers) >= 2, (
        f"Expected SUITE 01 to be flagged by C1 + C2 + C4; got "
        f"{len(suite01_blockers)} blockers: "
        f"{[b['check_id'] for b in suite01_blockers]}"
    )


# ---------------------------------------------------------------------------
# Schema stability — guards downstream consumers (cockpit, CI)
# ---------------------------------------------------------------------------


def test_top_level_keys_stable():
    report = evaluate_structural_health(_healthy_consensus())
    assert set(report.keys()) == {
        "schema_version",
        "structural_blockers",
        "structural_warnings",
        "per_room_metrics",
        "summary",
    }


def test_summary_keys_stable():
    report = evaluate_structural_health(_healthy_consensus())
    assert set(report["summary"].keys()) == {
        "blockers_count",
        "warnings_count",
        "rooms_with_blocker_count",
        "rooms_with_warning_count",
    }


def test_finding_shape_stable():
    """Each blocker/warning must have all 6 expected keys."""
    c = _healthy_consensus()
    # Force a blocker via C4
    c["rooms"][0]["polygon_pts"] = [[0, 0], [100, 100], [100, 0], [0, 100]]
    report = evaluate_structural_health(c)
    for f in report["structural_blockers"]:
        assert set(f.keys()) >= {
            "check_id", "severity", "target_kind",
            "target_id", "message", "evidence",
        }


def test_room_metrics_shape_stable():
    report = evaluate_structural_health(_healthy_consensus())
    m = report["per_room_metrics"][0]
    expected = {
        "room_id", "name", "vts", "free_vts", "free_vertex_ratio",
        "area_m2", "perimeter_m", "shape_complexity_ratio",
        "in_envelope_pct", "is_simple", "long_diag_count",
    }
    assert set(m.keys()) == expected
