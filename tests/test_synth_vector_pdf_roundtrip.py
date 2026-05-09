"""End-to-end round-trip test for the synthetic vector PDF generator.

Cycle 11c (2026-05-08). Companion to
``tests/test_fidelity_engine_round_trip.py`` (which tests the
fidelity engine self-consistency without touching the real
extraction pipeline). This test exercises the FULL pipeline:

    tools.synth.make_synthetic_vector_pdf -> *.pdf
        -> tools.build_vector_consensus -> c0
        -> tools.extract_room_labels -> labels
        -> tools.rooms_from_seeds -> c1
        -> tools.extract_openings_vector -> c2
        -> tools.classify_openings_by_room_context -> c3
        -> tools.fidelity.compare_generated_to_expected vs
           ground_truth/synth_l2/expected_model.json

Assertions:
- the synth PDF is ingestable by the vector pipeline (no
  rasterized-fallback emergency exit)
- 2 rooms detected (SALA SYNTH, SUITE SYNTH)
- fidelity engine returns global_fidelity == 1.0 with 0 hard_fails

This catches the class of regressions where the PDF parser
or any pipeline stage subtly changes its output shape — the
self-consistent fidelity engine wouldn't notice, but the
round-trip on real pipeline does.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.fidelity.compare_generated_to_expected import (
    PT_TO_M_DEFAULT,
    compare,
)
from tools.synth.make_synthetic_vector_pdf import (
    EXAMPLE_SPEC_2_ROOM_L,
    write_pdf,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable


def _run(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PYTHON, *args], cwd=str(cwd),
        capture_output=True, text=True, check=True,
    )


def test_synth_l2_roundtrip(tmp_path: Path) -> None:
    """Generate the L2 synth, run the full 5-stage pipeline against
    it, then check the fidelity engine returns global=1.0."""
    expected_path = (REPO_ROOT / "ground_truth" / "synth_l2"
                     / "expected_model.json")
    if not expected_path.exists():
        pytest.skip("ground_truth/synth_l2/expected_model.json missing")
    expected = json.loads(expected_path.read_text(encoding="utf-8"))

    pdf_path = tmp_path / "synth_l2.pdf"
    write_pdf(EXAMPLE_SPEC_2_ROOM_L, pdf_path)
    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 200  # not empty / not crippled

    c0 = tmp_path / "c0.json"
    labels = tmp_path / "labels.json"
    c1 = tmp_path / "c1.json"
    c2 = tmp_path / "c2.json"
    c3 = tmp_path / "c3.json"

    _run("-m", "tools.build_vector_consensus", str(pdf_path),
         "--out", str(c0), "--detect-openings", cwd=REPO_ROOT)
    _run("-m", "tools.extract_room_labels", str(pdf_path),
         "--out", str(labels), cwd=REPO_ROOT)
    _run("-m", "tools.rooms_from_seeds", str(c0), str(labels),
         "--out", str(c1), "--canonicalize-rooms",
         "--room-canonicalization-tol", "8", cwd=REPO_ROOT)
    _run("-m", "tools.extract_openings_vector", str(pdf_path),
         "--consensus", str(c1), "--out", str(c2),
         "--mode", "replace", "--classify-kind",
         "--detect-wall-gaps", cwd=REPO_ROOT)
    _run("-m", "tools.classify_openings_by_room_context", str(c2),
         "--out", str(c3), cwd=REPO_ROOT)

    consensus = json.loads(c3.read_text(encoding="utf-8"))

    # Structural sanity
    room_labels = sorted((r.get("name") or "").strip()
                         for r in consensus.get("rooms") or [])
    assert room_labels == ["SALA SYNTH", "SUITE SYNTH"], room_labels
    assert len(consensus["rooms"]) == 2

    # Fidelity round-trip
    report = compare(
        observed=consensus, expected=expected,
        pt_to_m=PT_TO_M_DEFAULT,
    )
    assert report["hard_fails"] == [], (
        "synth round-trip should produce 0 hard_fails, got "
        f"{report['hard_fails']}"
    )
    assert report["global_fidelity"] == 1.0, (
        "synth round-trip should produce global_fidelity=1.0 exact, "
        f"got {report['global_fidelity']}; sub_scores={report['sub_scores']}"
    )


def test_write_pdf_produces_vector_pdf(tmp_path: Path) -> None:
    """Lower-level test: write_pdf output starts with the PDF
    header and contains the binary marker that PDF readers use to
    tag binary-safe content."""
    pdf_path = tmp_path / "x.pdf"
    write_pdf(EXAMPLE_SPEC_2_ROOM_L, pdf_path)
    head = pdf_path.read_bytes()[:32]
    assert head.startswith(b"%PDF-1.4\n"), head
    assert b"%\xe2\xe3\xcf\xd3" in head, head
    # tail must end with %%EOF
    tail = pdf_path.read_bytes()[-16:]
    assert tail.rstrip().endswith(b"%%EOF"), tail


def test_write_pdf_contains_filled_rect_operators(tmp_path: Path) -> None:
    """The walls must be FILLED rectangles (re + f), not stroked
    (which would be re + S). The pipeline's `_identify_wall_paths`
    keeps only `fillmode != 0 and stroke_on == 0`."""
    pdf_path = tmp_path / "x.pdf"
    write_pdf(EXAMPLE_SPEC_2_ROOM_L, pdf_path)
    body = pdf_path.read_bytes()
    # The content stream ends each wall with `f\n` (fill, no stroke).
    assert b" re\nf\n" in body, "no filled-rect wall operator found"
    # Must NOT contain stroke-only walls.
    assert b" re\nS\n" not in body, "found stroked rect — would be filtered"
