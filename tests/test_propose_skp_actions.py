"""Tests for `tools.propose_skp_actions` (Cycle 13).

Producer-side of the `proposed_actions_v1` schema specified in
ADR-001 §2.6. Each detection rule + the idempotence + the CLI shell
gets at least one focused test.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.propose_skp_actions import (
    ACTION_TYPES,
    GENERATOR_NAME,
    LOW_CONFIDENCE_THRESHOLD,
    PROPOSED_ACTIONS_SCHEMA_VERSION,
    _autodiscover_consensus,
    _consensus_sha256,
    propose_actions,
    write_proposed_actions,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


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
            {"id": "r1", "name": "COZINHA", "polygon_pts": [
                [50, 0], [100, 0], [100, 100], [50, 100],
            ], "area_pts2": 5000},
            {"id": "r2", "name": "TERRACO TECNICO",
             "polygon_pts": [[0, 100], [50, 100], [50, 130], [0, 130]],
             "area_pts2": 1500},
        ],
        "openings": [
            # Clean + high confidence — no rule should fire on this.
            {"id": "o0", "kind_v5": "interior_door",
             "decision": "clean", "confidence": 0.95,
             "evidence": {"room_left": "SALA", "room_right": "COZINHA"}},
            # Low confidence → mark_low_confidence
            {"id": "o1", "kind_v5": "window",
             "decision": "clean", "confidence": 0.55,
             "evidence": {"width_m": 1.2}},
            # Decision != clean → request_human_review
            {"id": "o2", "kind_v5": "interior_passage",
             "decision": "debug", "confidence": 0.85},
            # Unknown kind → classify_opening
            {"id": "o3", "kind_v5": "unknown",
             "decision": "clean", "confidence": 0.9,
             "evidence": {"room_left": "SALA", "room_right": "COZINHA",
                          "width_m": 0.85}},
        ],
    }


def _toy_fidelity_report() -> dict:
    return {
        "schema_version": "fidelity_v1",
        "global_fidelity": 0.917,
        "sub_scores": {"adjacency_f1": 0.67},
        "hard_fails": [],
        "warnings": [
            "TERRACO TECNICO area marginal: observed 1.61 m^2 vs expected [2.0, 8.0]",
            "adjacency_f1=0.67 below 0.80 advisory threshold",
        ],
    }


# ---- Schema shape ---------------------------------------------------

def test_propose_actions_returns_valid_v1_schema():
    doc = propose_actions(consensus=_toy_consensus())
    # Top-level required fields per ADR §2.4
    for k in ("schema_version", "run_id", "consensus_sha256",
              "generated_at", "generator", "actions"):
        assert k in doc, f"missing top-level field {k}"
    assert doc["schema_version"] == PROPOSED_ACTIONS_SCHEMA_VERSION
    assert doc["generator"] == GENERATOR_NAME
    assert isinstance(doc["actions"], list)


def test_each_action_carries_required_fields():
    doc = propose_actions(consensus=_toy_consensus())
    assert doc["actions"], "expected at least one action on the toy consensus"
    for a in doc["actions"]:
        for k in ("id", "type", "target", "payload", "confidence",
                  "rationale", "generator", "created_at"):
            assert k in a, f"action missing field {k}: {a}"
        assert a["type"] in ACTION_TYPES
        assert a["target"]["kind"] in ("opening", "room")
        assert isinstance(a["target"]["id"], str)
        assert 0.0 <= a["confidence"] <= 1.0
        assert a["generator"] == GENERATOR_NAME


# ---- Empty / no-op path ---------------------------------------------

def test_propose_actions_empty_when_all_clean_and_high_confidence():
    c = _toy_consensus()
    # Strip the openings that trigger rules; keep only o0
    c["openings"] = [c["openings"][0]]
    doc = propose_actions(consensus=c)
    assert doc["actions"] == []


def test_propose_actions_handles_missing_openings_and_rooms():
    doc = propose_actions(consensus={"walls": [], "rooms": [], "openings": []})
    assert doc["actions"] == []
    assert doc["schema_version"] == PROPOSED_ACTIONS_SCHEMA_VERSION


def test_propose_actions_handles_consensus_with_no_openings_or_rooms_keys():
    """Consensus might be malformed; producer should not crash."""
    doc = propose_actions(consensus={})
    assert doc["actions"] == []


# ---- Rule 1 — mark_low_confidence ----------------------------------

def test_propose_mark_low_confidence_fires_below_threshold():
    doc = propose_actions(consensus=_toy_consensus())
    by_type = [a for a in doc["actions"] if a["type"] == "mark_low_confidence"]
    assert len(by_type) == 1
    a = by_type[0]
    assert a["target"] == {"kind": "opening", "id": "o1"}
    assert a["payload"]["current_confidence"] == 0.55
    assert "0.7" in a["rationale"] or str(LOW_CONFIDENCE_THRESHOLD) in a["rationale"]


def test_propose_mark_low_confidence_skipped_when_at_threshold():
    """confidence == 0.7 should NOT fire (strictly below)."""
    c = _toy_consensus()
    for op in c["openings"]:
        op["confidence"] = 0.7
        op["decision"] = "clean"
        op["kind_v5"] = "interior_door"
    doc = propose_actions(consensus=c)
    assert not [a for a in doc["actions"] if a["type"] == "mark_low_confidence"]


# ---- Rule 2 — request_human_review on debug decision ----------------

def test_propose_request_human_review_on_debug_decision():
    doc = propose_actions(consensus=_toy_consensus())
    matches = [
        a for a in doc["actions"]
        if a["type"] == "request_human_review"
        and a["target"]["kind"] == "opening"
    ]
    assert len(matches) == 1
    a = matches[0]
    assert a["target"]["id"] == "o2"
    assert a["payload"]["reason_codes"] == ["decision_not_clean"]


# ---- Rule 3 — classify_opening on unknown kind ----------------------

def test_propose_classify_opening_on_unknown_kind():
    doc = propose_actions(consensus=_toy_consensus())
    matches = [a for a in doc["actions"] if a["type"] == "classify_opening"]
    assert len(matches) == 1
    a = matches[0]
    assert a["target"]["id"] == "o3"
    assert a["payload"]["suggested_kind"] == "interior_passage"
    # Evidence is sorted alphabetically; o3 has all three pointers.
    assert a["payload"]["evidence"] == ["room_left", "room_right", "width_m"]
    # Heuristic confidence — not high
    assert a["confidence"] <= 0.5


# ---- Rule 4 — request_human_review on fidelity warning -------------

def test_propose_review_on_room_in_fidelity_warning():
    doc = propose_actions(
        consensus=_toy_consensus(),
        fidelity_report=_toy_fidelity_report(),
    )
    matches = [
        a for a in doc["actions"]
        if a["type"] == "request_human_review"
        and a["target"]["kind"] == "room"
    ]
    assert len(matches) == 1
    a = matches[0]
    assert a["target"]["id"] == "r2"
    assert a["payload"]["reason_codes"] == ["fidelity_warning"]
    assert a["payload"]["warning_count"] >= 1


def test_propose_no_room_review_without_fidelity_report():
    doc = propose_actions(consensus=_toy_consensus())
    room_reviews = [
        a for a in doc["actions"]
        if a["type"] == "request_human_review"
        and a["target"]["kind"] == "room"
    ]
    assert room_reviews == []


# ---- Idempotence + sha256 binding -----------------------------------

def test_propose_actions_is_idempotent_for_same_input():
    """Run twice with the same inputs but different generated_at —
    action ids must be byte-identical because they're hashed over
    (type, target, payload, generator), not timestamp."""
    a1 = propose_actions(
        consensus=_toy_consensus(),
        generated_at="2026-05-09T00:00:00Z",
    )
    a2 = propose_actions(
        consensus=_toy_consensus(),
        generated_at="2099-12-31T23:59:59Z",
    )
    ids_1 = [x["id"] for x in a1["actions"]]
    ids_2 = [x["id"] for x in a2["actions"]]
    assert ids_1 == ids_2
    # Sanity: timestamp DID change
    assert a1["generated_at"] != a2["generated_at"]


def test_propose_actions_includes_consensus_sha256(tmp_path):
    consensus_path = tmp_path / "consensus.json"
    consensus_path.write_text(
        json.dumps(_toy_consensus()), encoding="utf-8",
    )
    sha = _consensus_sha256(consensus_path)
    doc = propose_actions(
        consensus=_toy_consensus(), consensus_sha256=sha,
    )
    assert doc["consensus_sha256"] == sha
    assert len(doc["consensus_sha256"]) == 64  # hex of 256 bits


def test_propose_actions_default_sha256_marker_when_not_provided():
    doc = propose_actions(consensus=_toy_consensus())
    assert doc["consensus_sha256"] == "<not_provided>"


# ---- Atomic write ---------------------------------------------------

def test_write_proposed_actions_round_trip(tmp_path):
    doc = propose_actions(consensus=_toy_consensus())
    out_path = tmp_path / "subdir" / "proposed_actions.json"
    write_proposed_actions(doc, out_path)
    assert out_path.exists()
    loaded = json.loads(out_path.read_text(encoding="utf-8"))
    assert loaded == doc
    # No leftover .tmp file
    assert not list(tmp_path.glob("**/*.tmp"))


# ---- Auto-discovery -------------------------------------------------

def test_autodiscover_consensus_picks_consensus_underscore_pattern(tmp_path):
    (tmp_path / "consensus_with_room_context.json").write_text(
        json.dumps(_toy_consensus()), encoding="utf-8",
    )
    (tmp_path / "consensus_minimal.json").write_text(
        json.dumps(_toy_consensus()), encoding="utf-8",
    )
    p = _autodiscover_consensus(tmp_path)
    # Sorted, so "minimal" comes before "with_room_context"
    assert p is not None
    assert p.name in (
        "consensus_minimal.json",
        "consensus_with_room_context.json",
    )


def test_autodiscover_consensus_falls_back_to_rooms_walls_pattern(tmp_path):
    (tmp_path / "snapshot.json").write_text(
        json.dumps(_toy_consensus()), encoding="utf-8",
    )
    p = _autodiscover_consensus(tmp_path)
    assert p is not None and p.name == "snapshot.json"


def test_autodiscover_consensus_returns_none_when_no_match(tmp_path):
    (tmp_path / "unrelated.json").write_text("{}", encoding="utf-8")
    assert _autodiscover_consensus(tmp_path) is None


# ---- CLI shell ------------------------------------------------------

def _venv_python() -> str:
    """Pick the venv python so the subprocess sees the same imports."""
    return sys.executable


def test_cli_help_runs():
    proc = subprocess.run(
        [_venv_python(), "-m", "tools.propose_skp_actions", "--help"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0
    assert "proposed_actions" in proc.stdout.lower()


def test_cli_with_run_dir_writes_output(tmp_path):
    run_dir = tmp_path / "fake_run"
    run_dir.mkdir()
    (run_dir / "consensus_with_room_context.json").write_text(
        json.dumps(_toy_consensus()), encoding="utf-8",
    )
    proc = subprocess.run(
        [
            _venv_python(), "-m", "tools.propose_skp_actions",
            "--run-dir", str(run_dir),
        ],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    out_path = run_dir / "proposed_actions.json"
    assert out_path.exists()
    doc = json.loads(out_path.read_text(encoding="utf-8"))
    assert doc["schema_version"] == PROPOSED_ACTIONS_SCHEMA_VERSION
    assert doc["run_id"] == run_dir.name


def test_cli_picks_up_fidelity_report_from_run_dir(tmp_path):
    run_dir = tmp_path / "fake_run_with_fidelity"
    run_dir.mkdir()
    (run_dir / "consensus_with_room_context.json").write_text(
        json.dumps(_toy_consensus()), encoding="utf-8",
    )
    (run_dir / "fidelity_report.json").write_text(
        json.dumps(_toy_fidelity_report()), encoding="utf-8",
    )
    proc = subprocess.run(
        [
            _venv_python(), "-m", "tools.propose_skp_actions",
            "--run-dir", str(run_dir),
        ],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    doc = json.loads(
        (run_dir / "proposed_actions.json").read_text(encoding="utf-8"),
    )
    # Fidelity warnings should have triggered the room-review rule
    room_reviews = [
        a for a in doc["actions"]
        if a["type"] == "request_human_review"
        and a["target"]["kind"] == "room"
    ]
    assert len(room_reviews) == 1


def test_cli_errors_when_no_consensus_or_run_dir():
    proc = subprocess.run(
        [_venv_python(), "-m", "tools.propose_skp_actions"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode != 0
    assert "consensus" in proc.stderr.lower() or "run-dir" in proc.stderr.lower()


# ---- Smoke against the real planta_74 baseline (skip if missing) ----

def test_smoke_on_planta_74_baseline():
    canonical = (
        REPO_ROOT / "runs" / "feature_room_context_2026_05_06"
        / "consensus_with_room_context.json"
    )
    if not canonical.exists():
        pytest.skip("canonical planta_74 c3 missing on stripped checkout")
    consensus = json.loads(canonical.read_text(encoding="utf-8"))
    doc = propose_actions(consensus=consensus)
    assert doc["schema_version"] == PROPOSED_ACTIONS_SCHEMA_VERSION
    # The planta_74 baseline has openings — at least sanity-check that
    # the producer ran without crashing and produced a list.
    assert isinstance(doc["actions"], list)
