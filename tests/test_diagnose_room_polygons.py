"""Smoke tests for tools.diagnose_room_polygons.

Read-only diagnostic for room polygons in a consensus_model.json.
These tests pin the report shape and verify the tool runs end-to-end
against the canonical quadrado fixture (1 room, no merges expected).

No PDF is required for the basic `diagnose()` path; overlay rendering
(`--overlay-room`) is exercised separately when a PDF is available.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.diagnose_room_polygons import diagnose

REPO_ROOT = Path(__file__).resolve().parent.parent
QUADRADO_CONSENSUS = REPO_ROOT / "fixtures" / "quadrado" / "consensus_with_window.json"


def _load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


# ---- shape contract --------------------------------------------------


def test_report_carries_schema_version_and_tool_name() -> None:
    consensus = _load(QUADRADO_CONSENSUS)
    rep = diagnose(consensus)
    assert rep["schema_version"] == "1.0.0"
    assert rep["tool"] == "diagnose_room_polygons"


def test_report_top_level_keys_are_stable() -> None:
    consensus = _load(QUADRADO_CONSENSUS)
    rep = diagnose(consensus)
    assert set(rep.keys()) == {"schema_version", "tool", "constants", "rooms", "summary"}


def test_report_constants_block_carries_known_thresholds() -> None:
    consensus = _load(QUADRADO_CONSENSUS)
    rep = diagnose(consensus)
    c = rep["constants"]
    for key in ("PT_TO_M", "OVERLAP_AREA_MIN_M2", "SB_TOUCH_MIN_M",
                "DUP_VERTEX_EPS_PTS", "CONCAVITY_SUSPICIOUS"):
        assert key in c, f"missing constant {key}"
        assert isinstance(c[key], (int, float))


def test_summary_block_carries_known_counts() -> None:
    consensus = _load(QUADRADO_CONSENSUS)
    rep = diagnose(consensus)
    s = rep["summary"]
    for key in ("total_rooms", "rooms_with_suspicious_merge",
                "rooms_with_self_intersections", "rooms_with_invalid_polygon",
                "median_vertex_count", "median_area_m2"):
        assert key in s, f"missing summary key {key}"


# ---- quadrado canonical -----------------------------------------------


def test_quadrado_canonical_reports_one_room() -> None:
    consensus = _load(QUADRADO_CONSENSUS)
    rep = diagnose(consensus)
    assert rep["summary"]["total_rooms"] == 1
    assert len(rep["rooms"]) == 1


def test_quadrado_canonical_has_no_suspicious_merges() -> None:
    consensus = _load(QUADRADO_CONSENSUS)
    rep = diagnose(consensus)
    assert rep["summary"]["rooms_with_suspicious_merge"] == 0
    assert rep["summary"]["rooms_with_self_intersections"] == 0
    assert rep["summary"]["rooms_with_invalid_polygon"] == 0


def test_quadrado_canonical_room_polygon_is_valid() -> None:
    consensus = _load(QUADRADO_CONSENSUS)
    rep = diagnose(consensus)
    room = rep["rooms"][0]
    assert room.get("polygon_valid") is True
    assert room.get("self_intersects") in (False, None)


# ---- empty / missing input ---------------------------------------------


def test_empty_consensus_does_not_crash() -> None:
    rep = diagnose({"rooms": [], "soft_barriers": []})
    assert rep["summary"]["total_rooms"] == 0
    assert rep["rooms"] == []


def test_missing_rooms_key_treated_as_empty() -> None:
    rep = diagnose({})
    assert rep["summary"]["total_rooms"] == 0


# ---- CLI smoke ---------------------------------------------------------


def test_cli_help_loads_cleanly() -> None:
    result = subprocess.run(
        [sys.executable, "tools/diagnose_room_polygons.py", "--help"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert "Diagnose room polygon" in result.stdout
    assert "--out" in result.stdout
    assert "consensus" in result.stdout.lower()


def test_cli_end_to_end_writes_report(tmp_path: Path) -> None:
    out = tmp_path / "report.json"
    result = subprocess.run(
        [sys.executable, "tools/diagnose_room_polygons.py",
         str(QUADRADO_CONSENSUS), "--out", str(out)],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert out.exists()
    rep = json.loads(out.read_text(encoding="utf-8"))
    assert rep["tool"] == "diagnose_room_polygons"
    assert rep["summary"]["total_rooms"] == 1
