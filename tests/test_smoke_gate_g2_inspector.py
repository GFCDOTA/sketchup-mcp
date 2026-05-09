"""Tests for gate G2 (Inspector v2 structural check) in
``scripts.smoke.smoke_skp_export``.

Stage 1.6 Cycle 5 boundary: gate G2 only CONSUMES an existing
``inspect_report.json`` (produced by an earlier
``tools/inspect_walls_report.rb`` run). It does NOT launch SketchUp
and does NOT mutate the consensus / SKP. Default mode is
non-blocking; ``--inspect-strict`` opts into fail-on-blocker.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from scripts.smoke.smoke_skp_export import GateResult, SmokeReport, gate_g2

REPO_ROOT = Path(__file__).resolve().parent.parent


# ---- helpers ----

def _v2_clean_report() -> dict:
    return {
        "schema_version": "1.0",
        "meta": {
            "inspected_at": "2026-05-07T00:00:00Z",
            "skp_path": "C:/x/model.skp",
            "skp_sha256": "a" * 64,
            "skp_size_bytes": 70556,
            "sketchup_version": "26.0",
            "consensus_path": None, "consensus_sha256": None,
        },
        "totals": {"groups": 33, "faces": 100, "materials": 13, "layers": 6},
        "structural": {
            "default_faces_count": 0,
            "materials_count": 13,
            "wall_overlaps_count": 0,
            "components_count": 0,
            "groups_by_layer": {"walls": 33, "rooms": 11},
        },
        "bounds_check": None,
        "materials": [], "layers": [], "wall_overlaps_top20": [],
        "default_faces_count": 0, "default_faces_sample": [],
        "groups": [], "face_classification_counts": {},
    }


def _make_args(out_dir: Path, *, skip_skp=False, force_skp=False,
                inspect_strict=False) -> argparse.Namespace:
    return argparse.Namespace(
        skip_skp=skip_skp, force_skp=force_skp,
        inspect_strict=inspect_strict,
    )


def _make_report(out_dir: Path, *, cache_hit=False) -> SmokeReport:
    return SmokeReport(
        consensus_path="x", out_dir=str(out_dir),
        cache_hit=cache_hit, started_at="2026-05-07T00:00:00Z",
    )


# ---- gate G2 behavior ----

def test_g2_skip_when_skip_skp_flag_set(tmp_path):
    args = _make_args(tmp_path, skip_skp=True)
    report = _make_report(tmp_path)
    g = gate_g2(args, report)
    assert g.status == "skip"
    assert "--skip-skp" in g.message


def test_g2_skip_when_cache_hit_and_not_forced(tmp_path):
    args = _make_args(tmp_path, force_skp=False)
    report = _make_report(tmp_path, cache_hit=True)
    g = gate_g2(args, report)
    assert g.status == "skip"
    assert "cache" in g.message.lower()


def test_g2_skip_when_no_inspect_report_present(tmp_path):
    args = _make_args(tmp_path)
    report = _make_report(tmp_path)
    g = gate_g2(args, report)
    assert g.status == "skip"
    assert "no inspect_report.json" in g.message
    assert "deferred" in g.message


def test_g2_pass_on_clean_v2_report_default_mode(tmp_path):
    (tmp_path / "inspect_report.json").write_text(
        json.dumps(_v2_clean_report()), encoding="utf-8"
    )
    args = _make_args(tmp_path)
    report = _make_report(tmp_path)
    g = gate_g2(args, report)
    assert g.status == "pass"
    assert "schema=1.0" in g.message
    assert "materials=13" in g.message
    assert g.artifacts and "inspect_report.json" in g.artifacts[0]


def test_g2_pass_with_blockers_in_default_mode(tmp_path):
    """Non-strict default: blockers are reported but gate still passes
    so existing smoke flows do not regress."""
    d = _v2_clean_report()
    d["structural"]["default_faces_count"] = 5
    (tmp_path / "inspect_report.json").write_text(
        json.dumps(d), encoding="utf-8"
    )
    args = _make_args(tmp_path)
    report = _make_report(tmp_path)
    g = gate_g2(args, report)
    assert g.status == "pass"
    assert "would-block" in g.message
    assert "default_faces_count" in g.message


def test_g2_fail_with_blockers_in_strict_mode(tmp_path):
    d = _v2_clean_report()
    d["structural"]["default_faces_count"] = 5
    (tmp_path / "inspect_report.json").write_text(
        json.dumps(d), encoding="utf-8"
    )
    args = _make_args(tmp_path, inspect_strict=True)
    report = _make_report(tmp_path)
    g = gate_g2(args, report)
    assert g.status == "fail"
    assert "strict blockers fired" in g.message


def test_g2_fail_on_unparseable_report(tmp_path):
    (tmp_path / "inspect_report.json").write_text(
        "not valid json {", encoding="utf-8"
    )
    args = _make_args(tmp_path)
    report = _make_report(tmp_path)
    g = gate_g2(args, report)
    assert g.status == "fail"
    assert "failed to parse" in g.message


def test_g2_fail_strict_on_v0_report_due_to_schema(tmp_path):
    """A v0 report (no schema_version) is a strict blocker because
    the gate cannot guarantee the structural fields it depends on."""
    legacy = {
        "meta": {"inspected_at": "x", "skp_path": "y",
                  "sketchup_version": "26.0"},
        "totals": {"groups": 33, "faces": 100, "materials": 13,
                    "layers": 6},
        "materials": [], "layers": [], "wall_overlaps_top20": [],
        "default_faces_count": 0, "default_faces_sample": [],
        "groups": [], "face_classification_counts": {},
    }
    (tmp_path / "inspect_report.json").write_text(
        json.dumps(legacy), encoding="utf-8"
    )
    args = _make_args(tmp_path, inspect_strict=True)
    report = _make_report(tmp_path)
    g = gate_g2(args, report)
    assert g.status == "fail"
    assert "schema_version" in g.message


def test_g2_pass_on_v0_report_default_mode(tmp_path):
    """A v0 report passes in default (non-strict) mode, just with a
    warning. Backward compat for reports generated before inspector v2."""
    legacy = {
        "meta": {"inspected_at": "x", "skp_path": "y",
                  "sketchup_version": "26.0"},
        "totals": {"groups": 33, "faces": 100, "materials": 13,
                    "layers": 6},
        "materials": [{"name": "wall_dark"}] * 13,
        "layers": [], "wall_overlaps_top20": [],
        "default_faces_count": 0, "default_faces_sample": [],
        "groups": [], "face_classification_counts": {},
    }
    (tmp_path / "inspect_report.json").write_text(
        json.dumps(legacy), encoding="utf-8"
    )
    args = _make_args(tmp_path)
    report = _make_report(tmp_path)
    g = gate_g2(args, report)
    assert g.status == "pass"
    assert "would-block" in g.message  # schema_version warning


# ---- pipeline integration ----

def test_pipeline_includes_gate_g2():
    """Sanity: main() pipeline tuple includes gate_g2 between G and H.

    The original orphan-branch assertion was a single-line substring
    match; the post-Slice-3 pipeline tuple breaks across lines (gate_f0
    sits before gate_f). Relax to a regex over the full ``pipeline = (
    ... )`` block so the assertion survives benign reformatting.
    """
    import re

    import scripts.smoke.smoke_skp_export as mod

    src = Path(mod.__file__).read_text(encoding="utf-8")
    assert "gate_g2" in src, "gate_g2 missing from smoke harness source"
    assert "pipeline = (" in src, "pipeline tuple definition missing"

    # The pipeline tuple may span multiple physical lines; capture the
    # full body between the opening ``(`` and the matching ``)``.
    m = re.search(r"pipeline\s*=\s*\((.*?)\)", src, re.DOTALL)
    assert m is not None, "could not locate pipeline = (...) block"
    body = m.group(1)
    assert "gate_g2" in body, (
        "gate_g2 not in pipeline tuple body (only in imports / defs); "
        f"body was:\n{body}"
    )


def test_inspect_strict_arg_in_parser():
    """Sanity: --inspect-strict flag is registered."""
    from scripts.smoke.smoke_skp_export import _build_parser
    p = _build_parser()
    args = p.parse_args(["--inspect-strict"])
    assert args.inspect_strict is True
    args = p.parse_args([])
    assert args.inspect_strict is False
