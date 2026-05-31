"""promote_canonical — blessed build -> stable deliverable path."""
from __future__ import annotations

import json

import pytest

from tools.promote_canonical import promote


def _fake_build(d):
    d.mkdir(parents=True, exist_ok=True)
    (d / "model.skp").write_bytes(b"SKPDATA-123")
    (d / "model_iso.png").write_bytes(b"iso")
    (d / "model_top.png").write_bytes(b"top")
    (d / "geometry_report.json").write_text("{}", encoding="utf-8")
    return d


def test_promote_copies_to_fixed_named_deliverable(tmp_path):
    src = _fake_build(tmp_path / "build" / "final")
    promote(src, "planta_X", repo=tmp_path)
    dst = tmp_path / "artifacts" / "planta_X"
    assert (dst / "planta_X.skp").read_bytes() == b"SKPDATA-123"
    assert (dst / "planta_X_iso.png").exists()
    assert (dst / "planta_X_top.png").exists()
    assert (dst / "geometry_report.json").exists()


def test_promote_writes_metadata_with_sha_and_provenance(tmp_path):
    src = _fake_build(tmp_path / "runs" / "glassfix")
    promote(src, "planta_X", repo=tmp_path)
    meta = json.loads(
        (tmp_path / "artifacts" / "planta_X" / "planta_X.skp.metadata.json")
        .read_text("utf-8"))
    assert meta["stable_path"] == "artifacts/planta_X/planta_X.skp"
    assert len(meta["skp_sha256"]) == 64
    assert "runs/glassfix" in meta["promoted_from"].replace("\\", "/")


def test_promote_is_idempotent(tmp_path):
    src = _fake_build(tmp_path / "b" / "final")
    promote(src, "p", repo=tmp_path)
    promote(src, "p", repo=tmp_path)   # second run must not raise / corrupt
    assert (tmp_path / "artifacts" / "p" / "p.skp").read_bytes() == b"SKPDATA-123"


def test_promote_requires_model_skp(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(FileNotFoundError):
        promote(empty, "p", repo=tmp_path)
