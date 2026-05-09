"""Tests for tools.skp_inspection_report (Stage 1.6 inspector v2 reader)
+ source-grep contracts for tools/inspect_walls_report.rb.

Stage 1.6 boundary: the reader is pure JSON-in / dataclass-out. The
Ruby inspector contract tests assert the v2 fields are emitted by
grepping the source — same pattern as the other consume_consensus
contract tests.

NO mutation of consensus / SKP / Ruby. NO LLM. NO network.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from tools.skp_inspection_report import (
    INSPECTION_REPORT_SCHEMA_VERSION,
    InspectionReport,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
INSPECTOR_RB = REPO_ROOT / "tools" / "inspect_walls_report.rb"
PYTHON = sys.executable


# ---- Source-grep contract on Ruby inspector ----

def _ruby_source() -> str:
    return INSPECTOR_RB.read_text(encoding="utf-8")


def test_inspector_declares_schema_version_constant():
    src = _ruby_source()
    assert "INSPECTOR_REPORT_SCHEMA_VERSION" in src
    assert "'1.0'" in src or '"1.0"' in src


def test_inspector_emits_schema_version_in_report():
    src = _ruby_source()
    assert re.search(r"['\"]schema_version['\"]\s*=>\s*"
                     r"INSPECTOR_REPORT_SCHEMA_VERSION", src), (
        "inspect_walls_report.rb does not write schema_version into "
        "the report dict; downstream tools cannot detect v2 schema."
    )


def test_inspector_computes_skp_sha256():
    src = _ruby_source()
    assert "Digest::SHA256" in src or "Digest.SHA256" in src
    assert "sha256_of" in src
    assert "'skp_sha256'" in src or '"skp_sha256"' in src


def test_inspector_emits_skp_size_bytes():
    src = _ruby_source()
    assert "'skp_size_bytes'" in src or '"skp_size_bytes"' in src


def test_inspector_emits_consensus_fields_when_env_set():
    src = _ruby_source()
    assert "CONSENSUS_JSON_FOR_INSPECTION" in src
    assert "'consensus_path'" in src or '"consensus_path"' in src
    assert "'consensus_sha256'" in src or '"consensus_sha256"' in src


def test_inspector_emits_structural_section():
    src = _ruby_source()
    assert "'structural'" in src or '"structural"' in src
    for k in ("default_faces_count", "materials_count",
              "wall_overlaps_count", "components_count",
              "groups_by_layer"):
        assert f"'{k}'" in src or f'"{k}"' in src, (
            f"inspect_walls_report.rb missing structural.{k}"
        )


def test_inspector_emits_bounds_check_section():
    src = _ruby_source()
    assert "'bounds_check'" in src or '"bounds_check"' in src
    assert "build_bounds_check" in src
    for k in ("skp_bbox_in", "consensus_bbox_pt",
              "scaled_consensus_bbox_in", "delta_in",
              "within_tol_in", "delta_within_tol"):
        assert f"'{k}'" in src or f'"{k}"' in src, (
            f"inspect_walls_report.rb missing bounds_check.{k}"
        )


def test_inspector_preserves_legacy_fields():
    """v0 readers (inspect_metrics.py with old reports) must still
    work. The legacy top-level keys must remain emitted."""
    src = _ruby_source()
    for legacy in ("totals", "materials", "layers",
                    "wall_overlaps_top20", "default_faces_count",
                    "default_faces_sample", "groups",
                    "face_classification_counts"):
        assert f"'{legacy}'" in src or f'"{legacy}"' in src, (
            f"inspect_walls_report.rb dropped legacy top-level "
            f"key '{legacy}'; v0 readers would break."
        )


# ---- InspectionReport reader: schema versioning ----

def _v2_minimal_dict() -> dict:
    return {
        "schema_version": "1.0",
        "meta": {
            "inspected_at": "2026-05-06T22:00:00Z",
            "skp_path": "C:/x/model.skp",
            "skp_sha256": "a" * 64,
            "skp_size_bytes": 70556,
            "sketchup_version": "26.0",
            "consensus_path": None,
            "consensus_sha256": None,
        },
        "totals": {"groups": 33, "faces": 100, "materials": 13,
                    "layers": 6},
        "structural": {
            "default_faces_count": 0,
            "materials_count": 13,
            "wall_overlaps_count": 0,
            "components_count": 0,
            "groups_by_layer": {"walls": 33, "rooms": 11,
                                 "doors": 6, "windows": 1,
                                 "passages": 0},
        },
        "bounds_check": None,
        "materials": [], "layers": [], "wall_overlaps_top20": [],
        "default_faces_count": 0, "default_faces_sample": [],
        "groups": [],
        "face_classification_counts": {},
    }


def test_v2_report_parses_clean(tmp_path):
    p = tmp_path / "ir.json"
    p.write_text(json.dumps(_v2_minimal_dict()))
    r = InspectionReport.from_path(p)
    assert r.is_v2()
    assert r.schema_version == INSPECTION_REPORT_SCHEMA_VERSION
    assert r.skp_sha256 == "a" * 64
    assert r.materials_count == 13
    assert r.is_clean()
    assert r.strict_blockers() == []


def test_v2_report_default_faces_blocks_strict(tmp_path):
    d = _v2_minimal_dict()
    d["structural"]["default_faces_count"] = 7
    p = tmp_path / "ir.json"
    p.write_text(json.dumps(d))
    r = InspectionReport.from_path(p)
    assert not r.is_clean()
    blockers = r.strict_blockers()
    assert any("default_faces_count" in b for b in blockers)


def test_v2_report_components_block_strict(tmp_path):
    d = _v2_minimal_dict()
    d["structural"]["components_count"] = 1
    p = tmp_path / "ir.json"
    p.write_text(json.dumps(d))
    r = InspectionReport.from_path(p)
    assert any("components_count" in b for b in r.strict_blockers())


def test_v2_report_overlaps_block_strict(tmp_path):
    d = _v2_minimal_dict()
    d["structural"]["wall_overlaps_count"] = 3
    p = tmp_path / "ir.json"
    p.write_text(json.dumps(d))
    r = InspectionReport.from_path(p)
    assert any("wall_overlaps_count" in b for b in r.strict_blockers())


def test_v2_report_missing_sha_blocks_strict(tmp_path):
    d = _v2_minimal_dict()
    d["meta"]["skp_sha256"] = None
    p = tmp_path / "ir.json"
    p.write_text(json.dumps(d))
    r = InspectionReport.from_path(p)
    assert any("skp_sha256" in b for b in r.strict_blockers())


def test_v2_report_bounds_check_within_tol(tmp_path):
    d = _v2_minimal_dict()
    d["bounds_check"] = {
        "skp_bbox_in": [0, 0, 0, 100, 100, 100],
        "consensus_bbox_pt": [0, 0, 0, 100, 100, 0],
        "scaled_consensus_bbox_in": [0, 0, 0, 99, 99, 0],
        "delta_in": [0, 0, 1, 1],
        "within_tol_in": 5.0,
        "delta_within_tol": True,
    }
    p = tmp_path / "ir.json"
    p.write_text(json.dumps(d))
    r = InspectionReport.from_path(p)
    assert r.is_clean()
    assert r.strict_blockers() == []


def test_v2_report_bounds_check_out_of_tol_blocks(tmp_path):
    d = _v2_minimal_dict()
    d["bounds_check"] = {
        "skp_bbox_in": [0, 0, 0, 200, 200, 100],
        "consensus_bbox_pt": [0, 0, 0, 100, 100, 0],
        "scaled_consensus_bbox_in": [0, 0, 0, 99, 99, 0],
        "delta_in": [0, 0, 101, 101],
        "within_tol_in": 5.0,
        "delta_within_tol": False,
    }
    p = tmp_path / "ir.json"
    p.write_text(json.dumps(d))
    r = InspectionReport.from_path(p)
    assert not r.is_clean()
    assert any("bounds_check" in b for b in r.strict_blockers())


# ---- Backward compat: v0 reports should still parse ----

def _v0_minimal_dict() -> dict:
    return {
        "meta": {"inspected_at": "x", "skp_path": "y",
                  "sketchup_version": "26.0"},
        "totals": {"groups": 33, "faces": 100, "materials": 13,
                    "layers": 6},
        "materials": [{"name": "wall_dark"}] * 13,
        "layers": [],
        "wall_overlaps_top20": [],
        "default_faces_count": 0,
        "default_faces_sample": [],
        "groups": [],
        "face_classification_counts": {},
    }


def test_v0_report_parses_with_zero_schema_version(tmp_path):
    p = tmp_path / "ir.json"
    p.write_text(json.dumps(_v0_minimal_dict()))
    r = InspectionReport.from_path(p)
    assert r.schema_version == "0"
    assert not r.is_v2()
    # Counts derived from legacy fields
    assert r.materials_count == 13
    assert r.default_faces_count == 0
    # Strict mode blocks v0 because schema_version != "1.0"
    blockers = r.strict_blockers()
    assert any("schema_version" in b for b in blockers)


# ---- CLI ----

def test_cli_default_exits_zero_on_clean_v2(tmp_path):
    p = tmp_path / "ir.json"
    p.write_text(json.dumps(_v2_minimal_dict()))
    r = subprocess.run(
        [PYTHON, "-m", "tools.skp_inspection_report", str(p)],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    assert r.returncode == 0, r.stderr


def test_cli_strict_exits_nonzero_on_blocker(tmp_path):
    d = _v2_minimal_dict()
    d["structural"]["default_faces_count"] = 5
    p = tmp_path / "ir.json"
    p.write_text(json.dumps(d))
    r = subprocess.run(
        [PYTHON, "-m", "tools.skp_inspection_report", str(p), "--strict"],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    assert r.returncode != 0, r.stderr


# ---- inspect_metrics.py back-compat with v2 structural section ----

def test_inspect_metrics_reads_structural_section(tmp_path):
    """tools.inspect_metrics.FidelityMetrics should prefer structural
    counters over legacy top-level fields when v2 schema is detected."""
    from tools.inspect_metrics import FidelityMetrics
    d = _v2_minimal_dict()
    # Make legacy top-level disagree with structural
    d["default_faces_count"] = 999  # legacy
    d["structural"]["default_faces_count"] = 0  # v2 truth
    p = tmp_path / "ir.json"
    p.write_text(json.dumps(d))
    m = FidelityMetrics.from_inspect_report(p)
    assert m.default_faces_count == 0  # structural wins
    assert m.is_clean()


def test_inspect_metrics_falls_back_to_legacy_when_no_structural(tmp_path):
    from tools.inspect_metrics import FidelityMetrics
    d = _v0_minimal_dict()
    p = tmp_path / "ir.json"
    p.write_text(json.dumps(d))
    m = FidelityMetrics.from_inspect_report(p)
    assert m.default_faces_count == 0
    assert m.materials_count == 13
