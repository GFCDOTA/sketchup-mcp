"""F11 smoke test for scripts/validate_multiplant.py.

Goal: guarantee the runner script can be invoked end-to-end and exits 0 with
the frozen p12 + planta_74 fixtures. This is a *smoke* test — it does not
re-assert all numbers (the fixtures themselves do that); it verifies:

  - script is discoverable & runnable
  - exit code 0 under the current baseline
  - CSV report is produced with the expected header + rows
  - --skip-pipeline inventory mode works
  - determinism gate can be disabled via --no-determinism-check

Full pipeline runs are slow (3 pipeline invocations per validate + 3 for
determinism); tests are marked `slow` so they can be deselected locally with
`pytest -m "not slow"` when iterating on unrelated code.
"""
from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "validate_multiplant.py"
VALIDATION_DIR = REPO_ROOT / "runs" / "validation"
P12_PDF = REPO_ROOT / "runs" / "proto" / "p12_red.pdf"
PLANTA_PDF = REPO_ROOT / "planta_74.pdf"


def _require_inputs():
    missing = []
    if not SCRIPT.exists():
        missing.append(str(SCRIPT))
    if not (VALIDATION_DIR / "p12_red_expected.json").exists():
        missing.append("p12_red_expected.json")
    if not (VALIDATION_DIR / "planta_74_expected.json").exists():
        missing.append("planta_74_expected.json")
    if not P12_PDF.exists():
        missing.append(str(P12_PDF))
    if not PLANTA_PDF.exists():
        missing.append(str(PLANTA_PDF))
    if missing:
        pytest.skip(f"pre-reqs missing: {missing}")


def test_script_skip_pipeline_lists_fixtures():
    _require_inputs()
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--skip-pipeline"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert "p12_red" in out
    assert "planta_74" in out


def test_fixtures_are_valid_json():
    """Every *_expected.json must parse as JSON and carry a pdf_filename."""
    _require_inputs()
    fixtures = sorted(VALIDATION_DIR.glob("*_expected.json"))
    assert fixtures, "no fixtures found"
    for path in fixtures:
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "pdf_filename" in data, f"{path.name} missing pdf_filename"


@pytest.mark.slow
def test_script_runs_and_passes_all_gates(tmp_path):
    """Full smoke run: should exit 0, produce a CSV, and both plants must PASS."""
    _require_inputs()
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=600,
    )
    assert proc.returncode == 0, (
        f"stdout={proc.stdout!r}\nstderr={proc.stderr!r}"
    )
    # stdout must reference both plants as PASS.
    assert "[PASS] p12_red" in proc.stdout
    assert "[PASS] planta_74" in proc.stdout
    assert "2/2 fixtures passed" in proc.stdout
    # A report_*.csv must now exist with >= 2 data rows.
    reports = sorted(VALIDATION_DIR.glob("report_*.csv"))
    assert reports, "no CSV report produced"
    latest = reports[-1]
    with latest.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    names = {r["plant_name"] for r in rows}
    assert "p12_red" in names
    assert "planta_74" in names
    for row in rows:
        assert row["overall_ok"] == "True", f"{row['plant_name']} failed: {row}"


@pytest.mark.slow
def test_script_determinism_disabled_still_exits_zero():
    """--no-determinism-check should also exit 0 when both plants pass."""
    _require_inputs()
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--no-determinism-check"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=600,
    )
    assert proc.returncode == 0, (
        f"stdout={proc.stdout!r}\nstderr={proc.stderr!r}"
    )
    assert "disabled via --no-determinism-check" in proc.stdout
