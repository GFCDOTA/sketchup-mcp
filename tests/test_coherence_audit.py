"""Tests for tools.coherence_audit — Stage 1 of the uncertainty
pipeline.

Stage 1 boundary: audit emits report + questions but does NOT
mutate consensus geometry, does NOT call SU, does NOT call any LLM,
and is non-blocking by default.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.assumptions_loader import (
    DEFAULT_ASSUMPTIONS_PATH,
    AmbiguityPolicy,
    Assumptions,
    load_assumptions,
)
from tools.coherence_audit import (
    COHERENCE_REPORT_SCHEMA_VERSION,
    QUESTIONS_SCHEMA_VERSION,
    build_coherence_report,
    build_questions,
    evaluate_strict,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


# ---- helpers ----

def _minimal_consensus() -> dict:
    """Two rooms + one wall + one classified opening (clean decision)."""
    return {
        "schema_version": "1.0.0",
        "wall_thickness_pts": 5.4,
        "walls": [
            {"id": "w000", "start": [0.0, 100.0],
             "end": [200.0, 100.0], "thickness": 5.4,
             "orientation": "h"},
        ],
        "rooms": [
            {"id": "r000", "name": "SUITE 02",
             "seed_pt": [100.0, 50.0],
             "polygon_pts": [[0, 0], [200, 0], [200, 95], [0, 95]]},
            {"id": "r001", "name": "BANHO 02",
             "seed_pt": [100.0, 150.0],
             "polygon_pts": [[0, 105], [200, 105], [200, 200], [0, 200]]},
        ],
        "openings": [
            {"id": "o000", "wall_id": "w000",
             "center": [100.0, 100.0],
             "opening_width_pts": 29.0,
             "geometry_origin": "svg_arc",
             "kind_v5": "interior_door",
             "kind_v5_reason": "room_context: SUITE 02 <-> BANHO 02",
             "confidence": 0.92, "decision": "clean",
             "hypotheses": [
                {"kind": "interior_door", "prob": 0.92,
                 "reason": "private pair, fits"},
                {"kind": "interior_passage", "prob": 0.10,
                 "reason": "narrow"},
             ],
             "evidence": {"room_left": "SUITE 02", "room_right": "BANHO 02",
                            "width_m": 1.02, "geometry_origin": "svg_arc"}},
        ],
        "soft_barriers": [],
    }


def _write_consensus(tmp_path: Path, c: dict) -> Path:
    p = tmp_path / "consensus.json"
    p.write_text(json.dumps(c), encoding="utf-8")
    return p


@pytest.fixture
def default_assumptions() -> Assumptions:
    return load_assumptions(DEFAULT_ASSUMPTIONS_PATH)


# ---- Schema versioning ----

def test_report_includes_schema_version_1_0(tmp_path, default_assumptions):
    c = _minimal_consensus()
    cp = _write_consensus(tmp_path, c)
    r = build_coherence_report(c, cp, default_assumptions)
    assert r["schema_version"] == COHERENCE_REPORT_SCHEMA_VERSION
    assert COHERENCE_REPORT_SCHEMA_VERSION == "1.0"


def test_questions_includes_schema_version_1_0(tmp_path,
                                                 default_assumptions):
    c = _minimal_consensus()
    cp = _write_consensus(tmp_path, c)
    r = build_coherence_report(c, cp, default_assumptions)
    q = build_questions(c, r)
    assert q["schema_version"] == QUESTIONS_SCHEMA_VERSION
    assert QUESTIONS_SCHEMA_VERSION == "1.0"


# ---- Report shape ----

def test_report_top_level_keys(tmp_path, default_assumptions):
    c = _minimal_consensus()
    cp = _write_consensus(tmp_path, c)
    r = build_coherence_report(c, cp, default_assumptions)
    expected = {
        "schema_version", "generated_at", "consensus_path",
        "consensus_sha256", "assumptions", "summary", "facts",
        "hypotheses", "ambiguities", "drops", "issues", "risks",
    }
    assert expected.issubset(set(r.keys()))


def test_report_summary_counts_openings(tmp_path, default_assumptions):
    c = _minimal_consensus()
    cp = _write_consensus(tmp_path, c)
    r = build_coherence_report(c, cp, default_assumptions)
    assert r["summary"]["openings_total"] == 1
    assert r["summary"]["by_decision"]["clean"] == 1
    assert r["summary"]["by_kind"]["interior_door"] == 1


def test_report_records_hypotheses_per_opening(tmp_path,
                                                  default_assumptions):
    c = _minimal_consensus()
    cp = _write_consensus(tmp_path, c)
    r = build_coherence_report(c, cp, default_assumptions)
    assert len(r["hypotheses"]) == 1
    h = r["hypotheses"][0]
    assert h["opening_id"] == "o000"
    assert h["selected"] == "interior_door"
    assert h["decision"] == "clean"
    assert len(h["candidates"]) >= 1


def test_clean_opening_not_in_ambiguities_or_drops(tmp_path,
                                                     default_assumptions):
    c = _minimal_consensus()
    cp = _write_consensus(tmp_path, c)
    r = build_coherence_report(c, cp, default_assumptions)
    assert r["ambiguities"] == []
    assert r["drops"] == []


# ---- Issue detectors ----

def test_floating_door_detected_when_wall_id_unknown(tmp_path,
                                                       default_assumptions):
    c = _minimal_consensus()
    c["openings"][0]["wall_id"] = "w_does_not_exist"
    cp = _write_consensus(tmp_path, c)
    r = build_coherence_report(c, cp, default_assumptions)
    floating = r["issues"]["floating_doors"]
    assert len(floating) == 1
    assert floating[0]["wall_id_claimed"] == "w_does_not_exist"


def test_invalid_room_polygon_detected(tmp_path, default_assumptions):
    c = _minimal_consensus()
    c["rooms"][0]["polygon_pts"] = [[0, 0]]  # only 1 point
    cp = _write_consensus(tmp_path, c)
    r = build_coherence_report(c, cp, default_assumptions)
    assert len(r["issues"]["invalid_rooms"]) == 1


def test_duplicate_walls_detected(tmp_path, default_assumptions):
    c = _minimal_consensus()
    c["walls"].append({
        "id": "w000_dup", "start": [50.0, 100.0], "end": [150.0, 100.0],
        "thickness": 5.4, "orientation": "h",
    })
    cp = _write_consensus(tmp_path, c)
    r = build_coherence_report(c, cp, default_assumptions)
    dups = r["issues"]["duplicate_walls"]
    assert len(dups) == 1


# ---- Decision routing via classifier ----

def test_ambiguity_appears_when_decision_is_ask(tmp_path,
                                                  default_assumptions):
    c = _minimal_consensus()
    op = c["openings"][0]
    op["confidence"] = 0.30
    op["decision"] = "ask"
    cp = _write_consensus(tmp_path, c)
    r = build_coherence_report(c, cp, default_assumptions)
    assert len(r["ambiguities"]) == 1
    assert r["ambiguities"][0]["opening_id"] == "o000"


def test_drop_appears_when_decision_is_drop(tmp_path,
                                              default_assumptions):
    c = _minimal_consensus()
    op = c["openings"][0]
    op["confidence"] = 0.10
    op["decision"] = "drop"
    cp = _write_consensus(tmp_path, c)
    r = build_coherence_report(c, cp, default_assumptions)
    assert len(r["drops"]) == 1


# ---- Questions builder ----

def test_questions_only_for_ask_decisions(tmp_path,
                                            default_assumptions):
    c = _minimal_consensus()
    op = c["openings"][0]
    op["confidence"] = 0.30
    op["decision"] = "ask"
    cp = _write_consensus(tmp_path, c)
    r = build_coherence_report(c, cp, default_assumptions)
    q = build_questions(c, r)
    assert len(q["questions"]) == 1
    assert q["questions"][0]["subject_id"] == "o000"
    # default fallback always present
    assert q["questions"][0]["default_if_unanswered"] == "debug"


def test_no_questions_when_no_ambiguities(tmp_path,
                                            default_assumptions):
    c = _minimal_consensus()
    cp = _write_consensus(tmp_path, c)
    r = build_coherence_report(c, cp, default_assumptions)
    q = build_questions(c, r)
    assert q["questions"] == []


# ---- Strict mode ----

def test_strict_blocker_fires_on_ask_when_configured(tmp_path):
    c = _minimal_consensus()
    c["openings"][0]["confidence"] = 0.30
    c["openings"][0]["decision"] = "ask"
    cp = _write_consensus(tmp_path, c)
    a = Assumptions(
        schema_version="1.0", goal="furniture_layout",
        risk_policy="conservative",
        ambiguity=AmbiguityPolicy(),
        strict_blockers=["opening_decision_ask"],
    )
    r = build_coherence_report(c, cp, a)
    fired = evaluate_strict(r, a)
    assert "opening_decision_ask" in fired


def test_strict_blocker_silent_when_not_configured(tmp_path):
    c = _minimal_consensus()
    c["openings"][0]["confidence"] = 0.30
    c["openings"][0]["decision"] = "ask"
    cp = _write_consensus(tmp_path, c)
    a = Assumptions(
        schema_version="1.0", goal="furniture_layout",
        risk_policy="conservative",
        ambiguity=AmbiguityPolicy(),
        strict_blockers=[],
    )
    r = build_coherence_report(c, cp, a)
    assert evaluate_strict(r, a) == []


def test_strict_blocker_floating_door(tmp_path):
    c = _minimal_consensus()
    c["openings"][0]["wall_id"] = "missing_wall"
    cp = _write_consensus(tmp_path, c)
    a = Assumptions(
        schema_version="1.0", goal="furniture_layout",
        risk_policy="conservative",
        ambiguity=AmbiguityPolicy(),
        strict_blockers=["floating_door"],
    )
    r = build_coherence_report(c, cp, a)
    fired = evaluate_strict(r, a)
    assert "floating_door" in fired


# ---- CLI exit codes (subprocess) ----

def test_cli_default_exits_zero_with_drops(tmp_path):
    c = _minimal_consensus()
    c["openings"][0]["confidence"] = 0.10
    c["openings"][0]["decision"] = "drop"
    cp = _write_consensus(tmp_path, c)
    r = subprocess.run(
        [sys.executable, "-m", "tools.coherence_audit", str(cp),
         "--out-dir", str(tmp_path)],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "coherence_report.json").exists()
    assert (tmp_path / "questions.json").exists()


def test_cli_strict_exits_nonzero_when_blockers_present(tmp_path):
    c = _minimal_consensus()
    c["openings"][0]["confidence"] = 0.10
    c["openings"][0]["decision"] = "drop"
    cp = _write_consensus(tmp_path, c)
    r = subprocess.run(
        [sys.executable, "-m", "tools.coherence_audit", str(cp),
         "--out-dir", str(tmp_path), "--strict"],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    assert r.returncode != 0, (
        f"strict mode should fail when drops present. stdout={r.stdout} "
        f"stderr={r.stderr}"
    )


def test_cli_strict_exits_zero_when_clean(tmp_path):
    c = _minimal_consensus()  # default has clean opening, no issues
    cp = _write_consensus(tmp_path, c)
    r = subprocess.run(
        [sys.executable, "-m", "tools.coherence_audit", str(cp),
         "--out-dir", str(tmp_path), "--strict"],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    assert r.returncode == 0, (
        f"strict mode should pass when no blockers. stdout={r.stdout} "
        f"stderr={r.stderr}"
    )


# ---- Stage 1 boundary contracts (do NOT mutate / call out) ----

def test_audit_does_not_mutate_consensus(tmp_path, default_assumptions):
    c = _minimal_consensus()
    cp = _write_consensus(tmp_path, c)
    snapshot_before = json.dumps(c, sort_keys=True)
    build_coherence_report(c, cp, default_assumptions)
    snapshot_after = json.dumps(c, sort_keys=True)
    assert snapshot_before == snapshot_after


def test_audit_does_not_invoke_sketchup_or_llm(monkeypatch, tmp_path,
                                                  default_assumptions):
    """Crude guard: blow up any subprocess.run / requests / urllib
    network call attempted by build_coherence_report. Stage 1 must be
    pure file I/O."""
    import subprocess as _sp
    import urllib.request as _ur
    def boom(*a, **kw):
        raise AssertionError("Stage 1 must not invoke subprocess")
    def boom_url(*a, **kw):
        raise AssertionError("Stage 1 must not call out to network")
    monkeypatch.setattr(_sp, "run", boom)
    monkeypatch.setattr(_sp, "Popen", boom)
    monkeypatch.setattr(_ur, "urlopen", boom_url)
    c = _minimal_consensus()
    cp = _write_consensus(tmp_path, c)
    build_coherence_report(c, cp, default_assumptions)
