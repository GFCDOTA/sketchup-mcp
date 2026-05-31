"""Tests for tools/promote_artifact.py.

Focus: the three things most likely to go wrong in production —
  1. Missing required files should block promotion (no silent partial copy).
  2. Sidecar rewrite: skp_path must point to artifact/, source_run_path preserved.
  3. Existing artifact without --force should return 2 (not overwrite silently).

No real SKP, no real SketchUp, no side-by-side (PDF not present in tmp).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.promote_artifact import _rewrite_sidecar, _validate_run, promote


# ---- helpers ----------------------------------------------------------


def _make_run(tmp: Path, plant: str, *, skip_report: bool = False) -> Path:
    """Create a minimal valid run directory."""
    run = tmp / "runs" / plant
    run.mkdir(parents=True)
    (run / f"{plant}.skp").write_bytes(b"skp")
    (run / "model_top.png").write_bytes(b"png")
    (run / "model_iso.png").write_bytes(b"png")
    if not skip_report:
        (run / "geometry_report.json").write_text(
            json.dumps({"consensus_sha256": "abc123", "gates_self_check": {}}),
            encoding="utf-8",
        )
    return run


# ---- _validate_run ---------------------------------------------------


def test_validate_ok(tmp_path):
    run = _make_run(tmp_path, "quadrado")
    assert _validate_run(run, "quadrado") == []


def test_validate_missing_skp(tmp_path):
    run = _make_run(tmp_path, "quadrado")
    (run / "quadrado.skp").unlink()
    missing = _validate_run(run, "quadrado")
    assert "quadrado.skp" in missing


def test_validate_missing_report(tmp_path):
    run = _make_run(tmp_path, "quadrado", skip_report=True)
    missing = _validate_run(run, "quadrado")
    assert "geometry_report.json" in missing


# ---- sidecar rewrite -------------------------------------------------


def test_sidecar_rewrite_updates_skp_path_and_adds_source(tmp_path):
    """The promoted sidecar must point skp_path to artifacts/ and preserve source."""
    run = _make_run(tmp_path, "p74")
    run_skp = run / "p74.skp"
    artifact_dir = tmp_path / "artifacts" / "p74"
    artifact_dir.mkdir(parents=True)
    artifact_skp = artifact_dir / "p74.skp"

    # Write a minimal run-side sidecar
    run_sidecar = run_skp.with_suffix(".skp.metadata.json")
    run_sidecar.write_text(json.dumps({
        "schema_version": "1.0.0",
        "exporter": "build_plan_shell_skp",
        "consensus_sha256": "deadbeef",
        "skp_path": str(run_skp),
        "created_at": "2026-05-31T00:00:00Z",
    }), encoding="utf-8")

    meta = _rewrite_sidecar(artifact_skp, run_skp, "deadbeef", "2026-05-31T01:00:00Z")

    assert meta["skp_path"] == str(artifact_skp)
    assert meta["source_run_path"] == str(run_skp)
    # original fields preserved
    assert meta["consensus_sha256"] == "deadbeef"
    assert meta["schema_version"] == "1.0.0"

    # artifact sidecar written to disk
    art_sidecar = artifact_skp.with_suffix(".skp.metadata.json")
    assert art_sidecar.exists()
    on_disk = json.loads(art_sidecar.read_text(encoding="utf-8"))
    assert on_disk["skp_path"] == str(artifact_skp)


def test_sidecar_rewrite_no_run_sidecar(tmp_path):
    """If there is no run-side sidecar, a minimal one is created without crashing."""
    run = _make_run(tmp_path, "p74")
    run_skp = run / "p74.skp"
    artifact_dir = tmp_path / "artifacts" / "p74"
    artifact_dir.mkdir(parents=True)
    artifact_skp = artifact_dir / "p74.skp"

    meta = _rewrite_sidecar(artifact_skp, run_skp, "newsha", "2026-05-31T01:00:00Z")
    assert meta["skp_path"] == str(artifact_skp)
    assert meta["source_run_path"] == str(run_skp)
    assert meta["consensus_sha256"] == "newsha"


# ---- promote() integration -------------------------------------------


def test_promote_copies_files(tmp_path, monkeypatch):
    """Happy path: all required files present, artifacts/ empty → files copied."""
    monkeypatch.setattr("tools.promote_artifact.REPO_ROOT", tmp_path)
    run = _make_run(tmp_path, "p74")
    # PDF absent → side-by-side will be skipped (not an error)

    rc = promote("p74", run_dir=run)
    assert rc == 0

    art = tmp_path / "artifacts" / "p74"
    assert (art / "p74.skp").exists()
    assert (art / "p74_top.png").exists()
    assert (art / "p74_iso.png").exists()
    assert (art / "geometry_report.json").exists()
    # sidecar written
    assert (art / "p74.skp.metadata.json").exists()
    # README written
    assert (art / "README.md").exists()


def test_promote_blocks_missing_files(tmp_path, monkeypatch):
    """Missing required file → return 1, no partial write."""
    monkeypatch.setattr("tools.promote_artifact.REPO_ROOT", tmp_path)
    run = _make_run(tmp_path, "p74", skip_report=True)  # report missing

    rc = promote("p74", run_dir=run)
    assert rc == 1
    # artifact dir should not have been populated
    art = tmp_path / "artifacts" / "p74"
    assert not (art / "p74.skp").exists()


def test_promote_blocks_existing_without_force(tmp_path, monkeypatch):
    """Existing artifact without --force → return 2 (safe default)."""
    monkeypatch.setattr("tools.promote_artifact.REPO_ROOT", tmp_path)
    run = _make_run(tmp_path, "p74")
    # Pre-create an existing artifact
    art = tmp_path / "artifacts" / "p74"
    art.mkdir(parents=True)
    (art / "p74.skp").write_bytes(b"old")

    rc = promote("p74", run_dir=run)
    assert rc == 2
    # Original untouched
    assert (art / "p74.skp").read_bytes() == b"old"


def test_promote_force_overwrites(tmp_path, monkeypatch):
    """--force overwrites existing artifact."""
    monkeypatch.setattr("tools.promote_artifact.REPO_ROOT", tmp_path)
    run = _make_run(tmp_path, "p74")
    art = tmp_path / "artifacts" / "p74"
    art.mkdir(parents=True)
    (art / "p74.skp").write_bytes(b"old")

    rc = promote("p74", run_dir=run, force=True)
    assert rc == 0
    assert (art / "p74.skp").read_bytes() == b"skp"  # new content


def test_promote_dry_run_writes_nothing(tmp_path, monkeypatch):
    """--dry-run shows plan but writes NOTHING."""
    monkeypatch.setattr("tools.promote_artifact.REPO_ROOT", tmp_path)
    run = _make_run(tmp_path, "p74")

    rc = promote("p74", run_dir=run, dry_run=True)
    assert rc == 0
    art = tmp_path / "artifacts" / "p74"
    assert not art.exists() or not (art / "p74.skp").exists()
