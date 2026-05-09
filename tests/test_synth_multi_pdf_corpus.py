"""End-to-end round-trip tests for the multi-PDF synth corpus.

Cycle 11e (2026-05-08). Companion to
``tests/test_synth_vector_pdf_roundtrip.py`` (the L2 baseline).
This test parametrizes over ALL specs in
``tools.synth.make_synthetic_vector_pdf.SPECS`` other than ``l2``
(the existing roundtrip already covers L2). For each new spec it:

    spec -> .pdf via make_synthetic_vector_pdf
        -> tools.build_vector_consensus -> c0
        -> tools.extract_room_labels -> labels
        -> tools.rooms_from_seeds (--no-concave-hull) -> c1
        -> tools.extract_openings_vector -> c2
        -> tools.classify_openings_by_room_context -> c3
        -> tools.fidelity.compare_generated_to_expected vs the
           paired ``ground_truth/synth_<spec>/expected_model.json``

The new specs (T, Plus, long-hall) use the rectangular-envelope path
(``--no-concave-hull``) because the default concave-hull envelope
traces inward at every wall junction in non-rectangular topologies,
carving large rooms into broken slivers. The L2 baseline still uses
the default concave-hull (its envelope is essentially convex with one
notch).

Honest scope note (Cycle 11e): synthetic PDF round-trips broaden the
algorithmic round-trip test surface. They do NOT cover detector
generalisation on REAL PDFs — real-PDF coverage remains Felipe-blocked
(awaiting a corpus of 3+ vetted real plant PDFs, see
``.ai_bridge/TODO_NEXT.md``). This test catches regressions in the
synth → consensus → fidelity loop only.

Skip behaviour: if ``python -m tools.<X>`` fails because the worktree
isn't on sys.path (e.g., isolated Python install with python._pth
forcing -I), the test is skipped with a clear message — the failure is
environmental, not a code regression.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tools.fidelity.compare_generated_to_expected import (
    PT_TO_M_DEFAULT,
    compare,
)
from tools.synth.make_synthetic_vector_pdf import SPECS, write_pdf

REPO_ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable

# Spec id -> ground-truth folder name. Add new specs here when they
# get an expected_model.json companion.
NEW_SPECS = ("t3", "plus4", "hall5")
GT_DIR = REPO_ROOT / "ground_truth"


def _have_tools_module() -> bool:
    """Return True if ``python -m tools.build_vector_consensus --help``
    succeeds. Some Python installs (with ``python._pth`` forcing
    isolated mode) refuse to honour PYTHONPATH for subprocesses, in
    which case the pipeline can't be exercised from the harness."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    try:
        r = subprocess.run(
            [PYTHON, "-m", "tools.build_vector_consensus", "--help"],
            cwd=str(REPO_ROOT), env=env,
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0


def _run(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PYTHON, *args], cwd=str(cwd),
        capture_output=True, text=True, check=True,
    )


@pytest.mark.parametrize("spec_id", NEW_SPECS)
def test_synth_corpus_roundtrip(spec_id: str, tmp_path: Path) -> None:
    """Generate the synth PDF for ``spec_id``, run the full 5-stage
    pipeline against it, and assert the fidelity engine returns
    ``global_fidelity >= 0.85`` with 0 hard fails."""
    expected_path = GT_DIR / f"synth_{spec_id}" / "expected_model.json"
    if not expected_path.exists():
        pytest.skip(f"ground_truth/synth_{spec_id}/expected_model.json missing")
    if not _have_tools_module():
        pytest.skip(
            "pipeline tools not invocable via 'python -m tools.X' from this "
            "harness (likely an isolated Python install). The synth + "
            "expected_model are still validated by the structural tests."
        )

    expected = json.loads(expected_path.read_text(encoding="utf-8"))

    spec = SPECS[spec_id]
    pdf_path = tmp_path / f"synth_{spec_id}.pdf"
    write_pdf(spec, pdf_path)
    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 200

    c0 = tmp_path / "c0.json"
    labels = tmp_path / "labels.json"
    c1 = tmp_path / "c1.json"
    c2 = tmp_path / "c2.json"
    c3 = tmp_path / "c3.json"

    _run("-m", "tools.build_vector_consensus", str(pdf_path),
         "--out", str(c0), "--detect-openings", cwd=REPO_ROOT)
    _run("-m", "tools.extract_room_labels", str(pdf_path),
         "--out", str(labels), cwd=REPO_ROOT)
    # Non-rectangular topologies (T, +, long-hall) need the convex/
    # rectangular envelope to avoid concave-hull notches at wall
    # junctions carving rooms into slivers. See test docstring.
    _run("-m", "tools.rooms_from_seeds", str(c0), str(labels),
         "--out", str(c1), "--canonicalize-rooms",
         "--room-canonicalization-tol", "8",
         "--no-concave-hull", cwd=REPO_ROOT)
    _run("-m", "tools.extract_openings_vector", str(pdf_path),
         "--consensus", str(c1), "--out", str(c2),
         "--mode", "replace", "--classify-kind",
         "--detect-wall-gaps", cwd=REPO_ROOT)
    _run("-m", "tools.classify_openings_by_room_context", str(c2),
         "--out", str(c3), cwd=REPO_ROOT)

    consensus = json.loads(c3.read_text(encoding="utf-8"))

    # Structural sanity — count of detected rooms matches the spec
    expected_room_count = expected["expected_counts"]["rooms"]
    assert len(consensus["rooms"]) == expected_room_count, (
        f"{spec_id}: expected {expected_room_count} rooms, got "
        f"{len(consensus['rooms'])}"
    )

    # Fidelity round-trip
    report = compare(
        observed=consensus, expected=expected,
        pt_to_m=PT_TO_M_DEFAULT,
    )
    assert report["hard_fails"] == [], (
        f"{spec_id}: round-trip should produce 0 hard_fails, got "
        f"{report['hard_fails']}"
    )
    # Task gate is >= 0.85; the new specs all hit 1.0 with the
    # rectangular-envelope path. We assert the task gate, leaving
    # headroom for non-zero-cost detector evolution.
    assert report["global_fidelity"] >= 0.85, (
        f"{spec_id}: global_fidelity={report['global_fidelity']} < 0.85; "
        f"sub_scores={report['sub_scores']}"
    )


@pytest.mark.parametrize("spec_id", NEW_SPECS)
def test_synth_corpus_writes_valid_pdf(spec_id: str, tmp_path: Path) -> None:
    """Lower-level: every new spec must produce a syntactically valid
    PDF-1.4 with the binary marker and ``%%EOF`` trailer. Independent
    of the pipeline harness — runs even if ``tools.X`` modules can't
    be subprocess-invoked."""
    spec = SPECS[spec_id]
    pdf_path = tmp_path / f"synth_{spec_id}.pdf"
    write_pdf(spec, pdf_path)
    head = pdf_path.read_bytes()[:32]
    assert head.startswith(b"%PDF-1.4\n"), head
    assert b"%\xe2\xe3\xcf\xd3" in head, head
    tail = pdf_path.read_bytes()[-16:]
    assert tail.rstrip().endswith(b"%%EOF"), tail


@pytest.mark.parametrize("spec_id", NEW_SPECS)
def test_synth_corpus_specs_are_registered(spec_id: str) -> None:
    """The SPECS mapping in make_synthetic_vector_pdf must expose every
    new spec by its short id, so the CLI ``--spec <id>`` works and the
    test parametrize stays in sync."""
    assert spec_id in SPECS, (
        f"spec {spec_id!r} missing from SPECS mapping; CLI/test will "
        f"fail to enumerate"
    )
    spec = SPECS[spec_id]
    assert "page_w" in spec and "page_h" in spec
    assert spec["walls"], f"{spec_id}: empty walls"
    assert spec["labels"], f"{spec_id}: empty labels"


def test_expected_models_present_for_new_specs() -> None:
    """Each new spec must have a paired expected_model.json under
    ground_truth/synth_<spec>/. Fails early if a corpus entry is
    half-shipped (spec without ground truth)."""
    missing = []
    for spec_id in NEW_SPECS:
        gt = GT_DIR / f"synth_{spec_id}" / "expected_model.json"
        if not gt.exists():
            missing.append(str(gt.relative_to(REPO_ROOT)))
    assert not missing, f"missing expected_model.json: {missing}"
