"""Regression against the real source-gated build (railing_source_fix).

Locks the fix: in the actual SKP build, the 8 bare/unsourced soft barriers
(sb000-sb007) must NOT render, only the sourced peitoril (h_sb000) does, and both
railing gates PASS. Skips if the review build artifact is absent.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.parapet_not_railing_fallback_gate import (
    audit_parapet_not_railing_fallback,
)
from tools.railing_exact_match_gate import audit_railing_exact_match

REPO = Path(__file__).resolve().parents[1]
_REPORT = (REPO / "artifacts" / "review" / "planta_74" / "railing_source_fix"
           / "final" / "geometry_report.json")
_CONS = (REPO / "fixtures" / "planta_74"
         / "consensus_with_human_walls_and_soft_barriers.json")


@pytest.mark.skipif(not _REPORT.exists(), reason="railing_source_fix build absent")
def test_real_build_only_sourced_barrier_rendered():
    con = json.loads(_CONS.read_text("utf-8"))
    rep = json.loads(_REPORT.read_text("utf-8"))
    barriers = rep["soft_barrier_groups"]["barriers"]
    rendered = sorted(b["id"] for b in barriers if b["rendered"])
    assert rendered == ["h_sb000"], rendered      # only the sourced peitoril
    unsourced = [b for b in barriers if not b["sourced"]]
    assert all(not b["rendered"] for b in unsourced)  # none invented


@pytest.mark.skipif(not _REPORT.exists(), reason="railing_source_fix build absent")
def test_real_build_passes_railing_gates():
    con = json.loads(_CONS.read_text("utf-8"))
    rep = json.loads(_REPORT.read_text("utf-8"))
    assert audit_parapet_not_railing_fallback(con, rep)["verdict"] == "PASS"
    assert audit_railing_exact_match(con, rep)["verdict"] == "PASS"
