"""Tests for tools/spec_coverage_report.py.

The coverage report is an observational tool, NOT a gate. Tests pin
the cross-reference logic so a future hand-edit of
``KNOWN_FP_SPEC_LINKS`` doesn't silently lose discrimination power.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from tools.spec_coverage_report import (
    KNOWN_FP_SPEC_LINKS,
    build_coverage_report,
    main,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def _write_minimal_spec(path: Path, contract_ids: list[str]) -> Path:
    """Write a minimal spec YAML with the given contract ids; each
    contract gets a trivial expected_room_names rule so the YAML is
    well-formed against the harness loader."""
    body = {
        "schema_version": "1.0.0",
        "target": path.stem,
        "contracts": [
            {
                "id": cid,
                "severity": "warn",
                "rule": {"type": "expected_room_names", "required": []},
            }
            for cid in contract_ids
        ],
    }
    path.write_text(yaml.safe_dump(body), encoding="utf-8")
    return path


def _write_minimal_fp_md(path: Path, fp_ids: list[str]) -> Path:
    """Write a minimal failure_patterns.md containing the given
    FP-NNN headings + a one-line body each."""
    lines = ["# Failure patterns\n"]
    for fp in fp_ids:
        lines.append(f"## {fp} — synthetic test fixture\n")
        lines.append(f"Synthetic body for {fp}.\n\n")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


# ---- live-repo integration smoke -------------------------------------


def test_live_repo_coverage_runs_clean() -> None:
    """The shipped failure_patterns.md and specs/ must produce a
    well-formed coverage report. No assertion on the actual coverage
    percentage — that's expected to drift as PRs ship — but the
    structural fields must be present."""
    fp_md = REPO_ROOT / "docs" / "learning" / "failure_patterns.md"
    specs = REPO_ROOT / "specs"
    if not fp_md.exists() or not specs.exists():
        import pytest
        pytest.skip("live repo paths not present in test env")
    report = build_coverage_report(fp_md, specs)
    assert report["schema_version"] == "1.0.0"
    assert "fps" in report and isinstance(report["fps"], list)
    assert "summary" in report
    assert report["summary"]["total_fps_in_md"] >= 1
    assert report["summary"]["coverage_percentage"] >= 0.0
    assert report["summary"]["coverage_percentage"] <= 100.0


# ---- synthetic fixtures pin the core logic ---------------------------


def test_fp_with_no_spec_coverage_is_surfaced(tmp_path: Path) -> None:
    """An FP in the md that's not in KNOWN_FP_SPEC_LINKS yet (the
    common case for a freshly-added FP) is surfaced under
    ``fps_in_md_missing_from_links`` AND counted as 'without
    coverage'.

    Tests use the FP-9XX range so they never collide with real
    failure-pattern entries when this test runs from inside the
    live repo (no monkeypatch needed for fresh ids)."""
    fp_md = _write_minimal_fp_md(tmp_path / "fp.md",
                                  ["FP-999"])  # not in KNOWN_FP_SPEC_LINKS
    specs_dir = tmp_path / "specs"
    specs_dir.mkdir()
    _write_minimal_spec(specs_dir / "demo.spec.yaml", ["demo-1"])
    report = build_coverage_report(fp_md, specs_dir)
    assert "FP-999" in report["summary"]["fps_in_md_missing_from_links"]
    # No spec coverage → FP-999 row has covered_by=[]
    fp_row = next(r for r in report["fps"] if r["fp_id"] == "FP-999")
    assert fp_row["covered_by"] == []
    assert fp_row["has_spec_coverage"] is False


def test_orphan_contract_surfaced(tmp_path: Path) -> None:
    """A spec contract that no FP references is reported as an
    orphan. This isn't a bug per se — it's informational — but the
    report should surface them so the team can decide which orphans
    deserve an FP back-link."""
    fp_md = _write_minimal_fp_md(tmp_path / "fp.md", [])
    specs_dir = tmp_path / "specs"
    specs_dir.mkdir()
    _write_minimal_spec(specs_dir / "demo.spec.yaml",
                         ["orphan-contract-a", "orphan-contract-b"])
    report = build_coverage_report(fp_md, specs_dir)
    assert "orphan-contract-a" in report["orphan_contracts"]
    assert "orphan-contract-b" in report["orphan_contracts"]
    assert report["summary"]["orphan_contracts_count"] == 2


def test_bad_contract_reference_caught(tmp_path: Path,
                                       monkeypatch) -> None:
    """If KNOWN_FP_SPEC_LINKS references a contract that doesn't exist
    in any spec YAML, it must be surfaced as a bad reference. This
    is a TYPO catcher — pointing at a renamed/deleted contract is a
    silent regression in the curated link table.

    FP-NNN values must match the parsing regex ``FP-\\d+``; synthetic
    tests use the 900-series so they never collide with real FPs."""
    fp_md = _write_minimal_fp_md(tmp_path / "fp.md", ["FP-900"])
    specs_dir = tmp_path / "specs"
    specs_dir.mkdir()
    _write_minimal_spec(specs_dir / "demo.spec.yaml",
                         ["real-contract-id"])
    # Inject a bad reference for the duration of this test only.
    monkeypatch.setitem(KNOWN_FP_SPEC_LINKS, "FP-900",
                         ["non-existent-contract"])
    report = build_coverage_report(fp_md, specs_dir)
    bad = report["summary"]["bad_contract_references"]
    assert any(b["fp_id"] == "FP-900"
               and b["contract_id"] == "non-existent-contract"
               for b in bad), (
        f"expected bad-ref entry for FP-900/non-existent-contract; got {bad}"
    )


def test_full_coverage_yields_100_pct(tmp_path: Path,
                                       monkeypatch) -> None:
    """When every FP in the md has at least one spec contract back-
    linking it, coverage_percentage must be 100. Asserts the
    fundamental percentage formula."""
    fp_md = _write_minimal_fp_md(tmp_path / "fp.md",
                                  ["FP-901", "FP-902"])
    specs_dir = tmp_path / "specs"
    specs_dir.mkdir()
    _write_minimal_spec(specs_dir / "demo.spec.yaml",
                         ["a-contract", "b-contract"])
    monkeypatch.setitem(KNOWN_FP_SPEC_LINKS, "FP-901", ["a-contract"])
    monkeypatch.setitem(KNOWN_FP_SPEC_LINKS, "FP-902", ["b-contract"])
    report = build_coverage_report(fp_md, specs_dir)
    assert report["summary"]["coverage_percentage"] == 100.0
    assert report["summary"]["fps_with_spec_coverage"] == 2


def test_zero_coverage_yields_zero_pct(tmp_path: Path) -> None:
    """All FPs missing spec back-links → 0.0% coverage."""
    fp_md = _write_minimal_fp_md(tmp_path / "fp.md", ["FP-903", "FP-904"])
    specs_dir = tmp_path / "specs"
    specs_dir.mkdir()
    _write_minimal_spec(specs_dir / "demo.spec.yaml", ["unrelated"])
    report = build_coverage_report(fp_md, specs_dir)
    assert report["summary"]["coverage_percentage"] == 0.0


def test_cli_writes_report(tmp_path: Path) -> None:
    """End-to-end: `python -m tools.spec_coverage_report --out X`
    writes a JSON file that's loadable + has the summary block."""
    fp_md = _write_minimal_fp_md(tmp_path / "fp.md", ["FP-905"])
    specs_dir = tmp_path / "specs"
    specs_dir.mkdir()
    _write_minimal_spec(specs_dir / "demo.spec.yaml", ["c1"])
    out = tmp_path / "report.json"
    code = main([
        "--failure-patterns", str(fp_md),
        "--specs-dir", str(specs_dir),
        "--out", str(out),
    ])
    assert code == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["schema_version"] == "1.0.0"
    assert "summary" in data


def test_link_table_no_duplicate_contract_per_fp() -> None:
    """KNOWN_FP_SPEC_LINKS must not list the same contract id twice
    under one FP — a duplicate is a curation error. (Different FPs
    listing the same contract IS fine — one contract can cover
    multiple FPs.)"""
    for fp_id, contract_ids in KNOWN_FP_SPEC_LINKS.items():
        assert len(contract_ids) == len(set(contract_ids)), (
            f"FP {fp_id} lists a duplicate contract: {contract_ids}"
        )
