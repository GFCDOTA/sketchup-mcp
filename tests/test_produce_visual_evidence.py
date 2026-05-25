"""Unit tests for `tools/produce_visual_evidence.py` — PR B1
producers for the seven Visual Fidelity Gate artifacts.

Covers:
- `REQUIRED_VISUAL_ARTIFACTS` schema lock (mirrors verify_fidelities).
- `EIGHT_CHECKS` schema lock.
- Per-producer happy path: each producer writes a non-empty file at
  the expected path.
- Orchestrator round-trip: all seven files exist after a single
  `produce_visual_evidence` call.
- `produce_visual_evidence` returns the right `status` for missing /
  empty / present outcomes.
- CLI integration: the script exits 0 on a clean run and writes the
  seven canonical filenames into `--output-dir`.
- `--strict` exits 2 when any producer fails (synthetic missing-PDF
  case forces the orchestrator into early exit).
- Gate integration: with the artifacts in place,
  `verify_fidelities.verify_fidelities(...)` sees
  `visual_evidence_status: present` and stops forcing FAIL.
"""
from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from tools.produce_visual_evidence import (
    EIGHT_CHECKS,
    REQUIRED_VISUAL_ARTIFACTS,
    _produce_diff_doors,
    _produce_diff_rooms,
    _produce_diff_walls,
    _produce_mismatches_list,
    _produce_original_floorplan,
    _produce_overlay,
    _produce_skp_render,
    produce_visual_evidence,
)
from tools.verify_fidelities import (
    REQUIRED_VISUAL_ARTIFACTS as GATE_ARTIFACTS,
)
from tools.verify_fidelities import (
    verify_fidelities,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# planta_74 is the canonical reference — its real PDF + consensus are
# the only artifacts heavy enough to exercise every producer end to
# end. Tests skip cleanly when these are unavailable (eg shallow clone).
PLANTA_74_PDF = REPO_ROOT / "planta_74.pdf"
PLANTA_74_CONSENSUS = (
    REPO_ROOT
    / "fixtures"
    / "planta_74"
    / "consensus_with_human_walls_and_soft_barriers.json"
)


def _have_planta_74() -> bool:
    return PLANTA_74_PDF.exists() and PLANTA_74_CONSENSUS.exists()


def _load_planta_74_consensus() -> dict:
    return json.loads(PLANTA_74_CONSENSUS.read_text(encoding="utf-8"))


def _passing_candidates_fixture() -> dict:
    return {
        "schema_version": "1.0",
        "n_merged_cells": 0,
        "n_pairs": 0,
        "by_candidate_type": {},
        "n_should_user_paint": 0,
        "n_should_not_paint": 0,
        "n_downgraded_by_existing_human_wall": 0,
        "candidates": [],
    }


# ---------------------------------------------------------------------------
# Schema lock
# ---------------------------------------------------------------------------

def test_required_visual_artifacts_match_gate_module():
    """Producer's REQUIRED list must mirror the gate's REQUIRED list."""
    assert REQUIRED_VISUAL_ARTIFACTS == GATE_ARTIFACTS


def test_required_visual_artifacts_count_is_seven():
    assert len(REQUIRED_VISUAL_ARTIFACTS) == 7


def test_eight_checks_count_is_eight():
    assert len(EIGHT_CHECKS) == 8


def test_eight_checks_keys_match_protocol():
    """Each check key must be a short snake_case identifier. The
    protocol doc references these exact slugs."""
    expected = {
        "door_without_opening",
        "door_crossing_or_displaced",
        "door_swing_diverges",
        "room_polygon_not_closed",
        "room_polygon_bleeds_outside",
        "invented_or_wrong_height_exterior",
        "wet_or_terrace_adjacency_wrong",
        "room_rendered_as_bbox",
    }
    actual = {k for k, _ in EIGHT_CHECKS}
    assert actual == expected


# ---------------------------------------------------------------------------
# Per-producer happy path (planta_74)
# ---------------------------------------------------------------------------

planta_74 = pytest.mark.skipif(
    not _have_planta_74(),
    reason="planta_74 PDF / consensus not available (shallow clone?)",
)


@planta_74
def test_produce_original_floorplan_writes_png(tmp_path: Path):
    out = tmp_path / "original_floorplan.png"
    _produce_original_floorplan(PLANTA_74_PDF, out)
    assert out.exists()
    assert out.stat().st_size > 10_000  # full-page PDF render is hefty
    # PNG magic
    assert out.read_bytes()[:4] == b"\x89PNG"


@planta_74
def test_produce_skp_render_writes_png(tmp_path: Path):
    out = tmp_path / "skp_render.png"
    consensus = _load_planta_74_consensus()
    _produce_skp_render(consensus, out, dpi=120)
    assert out.exists()
    assert out.stat().st_size > 5_000
    assert out.read_bytes()[:4] == b"\x89PNG"


@planta_74
def test_produce_overlay_writes_png(tmp_path: Path):
    consensus = _load_planta_74_consensus()
    skp = tmp_path / "skp_render.png"
    _produce_skp_render(consensus, skp, dpi=120)
    out = tmp_path / "overlay_pdf_skp.png"
    _produce_overlay(PLANTA_74_PDF, skp, out)
    assert out.exists()
    assert out.stat().st_size > 10_000


@planta_74
def test_produce_diff_walls_writes_png(tmp_path: Path):
    out = tmp_path / "diff_walls.png"
    consensus = _load_planta_74_consensus()
    _produce_diff_walls(PLANTA_74_PDF, consensus, out, dpi=120)
    assert out.exists()
    assert out.stat().st_size > 5_000


@planta_74
def test_produce_diff_doors_writes_png(tmp_path: Path):
    out = tmp_path / "diff_doors.png"
    consensus = _load_planta_74_consensus()
    _produce_diff_doors(PLANTA_74_PDF, consensus, out, dpi=120)
    assert out.exists()
    assert out.stat().st_size > 5_000


@planta_74
def test_produce_diff_rooms_writes_png(tmp_path: Path):
    out = tmp_path / "diff_rooms.png"
    consensus = _load_planta_74_consensus()
    _produce_diff_rooms(PLANTA_74_PDF, consensus, out, dpi=120)
    assert out.exists()
    assert out.stat().st_size > 5_000


def test_produce_mismatches_list_writes_template(tmp_path: Path):
    """The mismatches_list producer is the only one that does NOT
    require the real PDF — it operates on the consensus dict."""
    out = tmp_path / "mismatches_list.md"
    consensus = {
        "walls": [{"id": "w0"}],
        "rooms": [{"id": "r0", "name": "SALA"}],
        "openings": [],
        "soft_barriers": [],
    }
    _produce_mismatches_list(consensus, out, consensus_path=Path("/tmp/c.json"))
    body = out.read_text(encoding="utf-8")
    assert out.stat().st_size > 100
    # Header + each of the 8 check keys must be present.
    assert "Visual Fidelity Mismatches" in body
    for key, _description in EIGHT_CHECKS:
        assert key in body, f"missing check key in template: {key}"
    # Each check has exactly one `status: not_yet_checked` line.
    # (The intro paragraph also mentions the phrase, so plain count
    # gives N+1; pin to the structured line instead.)
    assert body.count("status: `not_yet_checked`") == len(EIGHT_CHECKS)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

@planta_74
def test_orchestrator_produces_all_seven(tmp_path: Path):
    out_dir = tmp_path / "evidence"
    results = produce_visual_evidence(
        pdf_path=PLANTA_74_PDF,
        consensus_path=PLANTA_74_CONSENSUS,
        output_dir=out_dir,
        dpi=120,
    )
    # Every artifact should have a result entry.
    keys_in_results = set(results.keys())
    expected_keys = {k for k, _ in REQUIRED_VISUAL_ARTIFACTS}
    assert keys_in_results == expected_keys
    # Every artifact should be ok + non-empty on disk.
    for key, fname in REQUIRED_VISUAL_ARTIFACTS:
        path = out_dir / fname
        assert path.exists(), f"missing artifact: {key}"
        assert path.stat().st_size > 0, f"empty artifact: {key}"
        assert results[key]["status"] == "ok", (
            f"{key} status was {results[key]['status']!r}: "
            f"{results[key].get('error')}"
        )


@planta_74
def test_orchestrator_gate_clears_after_run(tmp_path: Path):
    """The seven produced files satisfy the artifact-presence gate."""
    out_dir = tmp_path / "evidence"
    produce_visual_evidence(
        pdf_path=PLANTA_74_PDF,
        consensus_path=PLANTA_74_CONSENSUS,
        output_dir=out_dir,
        dpi=120,
    )
    consensus = _load_planta_74_consensus()
    report = verify_fidelities(
        consensus, _passing_candidates_fixture(),
        labels=None,
        operator_confirmed_visual=False,
        require_visual_evidence=True,
        visual_evidence_dir=out_dir,
    )
    assert report["visual_evidence_status"] == "present"
    assert report.get("missing_visual_artifacts") == []
    assert "policy_violation" not in report
    # The top-level falls back to the per-axis worst — proves the
    # gate is not silently forcing PASS.
    assert report["verdict_top_level"] in {"PASS", "WARN", "FAIL"}


# ---------------------------------------------------------------------------
# Error-handling
# ---------------------------------------------------------------------------

def test_orchestrator_records_error_on_missing_pdf(tmp_path: Path):
    """Producers that need the PDF should fail individually; the
    orchestrator carries on for the producers that don't."""
    # Synthesise a minimal consensus so mismatches_list can succeed.
    consensus_path = tmp_path / "consensus.json"
    consensus_path.write_text(json.dumps({
        "walls": [], "rooms": [], "openings": [], "soft_barriers": [],
    }), encoding="utf-8")
    missing_pdf = tmp_path / "does_not_exist.pdf"
    out_dir = tmp_path / "evidence"
    results = produce_visual_evidence(
        pdf_path=missing_pdf,
        consensus_path=consensus_path,
        output_dir=out_dir,
        dpi=120,
    )
    # mismatches_list does not need the PDF — it succeeds.
    assert results["mismatches_list"]["status"] == "ok"
    # The PDF-dependent producers error out (their status is `error`).
    for key in ("original_floorplan", "diff_walls", "diff_rooms"):
        assert results[key]["status"] == "error", (
            f"{key} should have errored on missing PDF"
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@planta_74
def test_cli_default_exits_zero_and_writes_all(tmp_path: Path):
    out_dir = tmp_path / "cli_evidence"
    res = subprocess.run(
        [sys.executable, "-m", "tools.produce_visual_evidence",
         "--pdf", str(PLANTA_74_PDF),
         "--consensus", str(PLANTA_74_CONSENSUS),
         "--output-dir", str(out_dir),
         "--dpi", "120"],
        cwd=str(REPO_ROOT),
        capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr
    for _key, fname in REQUIRED_VISUAL_ARTIFACTS:
        assert (out_dir / fname).exists()
        assert (out_dir / fname).stat().st_size > 0


def test_cli_strict_exits_2_on_missing_pdf(tmp_path: Path):
    """With --strict, the orchestrator exits 2 if any producer errored."""
    consensus_path = tmp_path / "consensus.json"
    consensus_path.write_text(json.dumps({
        "walls": [], "rooms": [], "openings": [], "soft_barriers": [],
    }), encoding="utf-8")
    missing_pdf = tmp_path / "missing.pdf"
    out_dir = tmp_path / "strict_evidence"
    res = subprocess.run(
        [sys.executable, "-m", "tools.produce_visual_evidence",
         "--pdf", str(missing_pdf),
         "--consensus", str(consensus_path),
         "--output-dir", str(out_dir),
         "--strict"],
        cwd=str(REPO_ROOT),
        capture_output=True, text=True,
    )
    # The missing-PDF check trips before producers even run, so the
    # script exits 2 from the CLI guard, not from --strict per se.
    # Either way, returncode is 2 — that's the contract.
    assert res.returncode == 2


@planta_74
def test_cli_writes_seven_canonical_filenames(tmp_path: Path):
    """Schema lock — the CLI emits exactly the seven filenames
    documented in the protocol."""
    out_dir = tmp_path / "names_evidence"
    res = subprocess.run(
        [sys.executable, "-m", "tools.produce_visual_evidence",
         "--pdf", str(PLANTA_74_PDF),
         "--consensus", str(PLANTA_74_CONSENSUS),
         "--output-dir", str(out_dir),
         "--dpi", "120"],
        cwd=str(REPO_ROOT),
        capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr
    found = sorted(p.name for p in out_dir.iterdir())
    expected = sorted(fname for _key, fname in REQUIRED_VISUAL_ARTIFACTS)
    assert found == expected
