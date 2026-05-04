"""Tests for the consensus-hash skip logic in tools.skp_from_consensus.

The tests target the *helpers* (`metadata_path`, `read_metadata`,
`write_metadata`, `should_skip`) and the `run()` short-circuit when
the sidecar matches. They do NOT spawn SketchUp — the actual export
path is exercised manually per
docs/validation/sketchup_smoke_workflow.md.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools import skp_from_consensus as sfc


@pytest.fixture()
def consensus(tmp_path: Path) -> Path:
    p = tmp_path / "consensus_model.json"
    p.write_text(json.dumps({"walls": [], "rooms": [], "openings": []}))
    return p


def test_metadata_path_lives_next_to_skp(tmp_path):
    skp = tmp_path / "model.skp"
    assert sfc.metadata_path(skp) == tmp_path / "model.skp.metadata.json"


def test_read_metadata_returns_none_when_missing(tmp_path):
    assert sfc.read_metadata(tmp_path / "nope.skp") is None


def test_read_metadata_returns_none_when_corrupt(tmp_path):
    skp = tmp_path / "model.skp"
    sfc.metadata_path(skp).write_text("{not json")
    assert sfc.read_metadata(skp) is None


def test_write_then_read_roundtrip(tmp_path):
    skp = tmp_path / "model.skp"
    skp.write_bytes(b"x")  # tiny placeholder
    fake_exe = Path("C:/SU/SU.exe")
    written = sfc.write_metadata(
        skp,
        consensus_sha256="a" * 64,
        sketchup_exe=fake_exe,
        command=[str(fake_exe), "boot.skp"],
    )
    assert written.exists()
    meta = sfc.read_metadata(skp)
    assert meta is not None
    assert meta["consensus_sha256"] == "a" * 64
    assert meta["skp_path"] == str(skp)
    # Compare via Path so the Windows backslash form and POSIX form
    # both resolve to the same canonical exe.
    assert Path(meta["sketchup_path"]) == fake_exe
    assert "SU.exe" in meta["command"]
    assert "created_at" in meta and meta["created_at"]
    assert "git_commit" in meta


def test_should_skip_false_when_skp_missing(tmp_path):
    skp = tmp_path / "model.skp"  # never created
    sfc.write_metadata(
        skp, consensus_sha256="x" * 64,
        sketchup_exe=Path("a"), command=["a"],
    )
    # The metadata exists but the .skp doesn't — must not skip.
    assert sfc.should_skip(skp, "x" * 64) is False


def test_should_skip_false_when_metadata_missing(tmp_path):
    skp = tmp_path / "model.skp"
    skp.write_bytes(b"x")
    assert sfc.should_skip(skp, "x" * 64) is False


def test_should_skip_false_when_hash_differs(tmp_path):
    skp = tmp_path / "model.skp"
    skp.write_bytes(b"x")
    sfc.write_metadata(
        skp, consensus_sha256="a" * 64,
        sketchup_exe=Path("a"), command=["a"],
    )
    assert sfc.should_skip(skp, "b" * 64) is False


def test_should_skip_true_when_hash_matches(tmp_path):
    skp = tmp_path / "model.skp"
    skp.write_bytes(b"x")
    sfc.write_metadata(
        skp, consensus_sha256="c" * 64,
        sketchup_exe=Path("a"), command=["a"],
    )
    assert sfc.should_skip(skp, "c" * 64) is True


def test_run_skips_when_metadata_matches(tmp_path, consensus, monkeypatch):
    """Full `run` short-circuit: sidecar matches, .skp exists,
    force_skp=False → returns immediately without launching SU."""
    skp = tmp_path / "model.skp"
    skp.write_bytes(b"existing 58k of sketchup data")
    consensus_sha = sfc._file_sha256(consensus)
    sfc.write_metadata(
        skp, consensus_sha256=consensus_sha,
        sketchup_exe=Path("C:/fake/SU.exe"), command=["fake"],
    )

    # Booby-trap: if Popen is called, fail loudly.
    def _fail_popen(*a, **kw):
        raise AssertionError("subprocess.Popen must not be called on a skip")
    monkeypatch.setattr(sfc.subprocess, "Popen", _fail_popen)

    result = sfc.run(
        consensus, skp, sketchup_exe=Path("C:/fake/SU.exe"),
        plugins_dir=tmp_path / "plugins",
        timeout_s=5,
    )
    assert result["ok"] is True
    assert result["skipped"] is True
    assert result["consensus_sha256"] == consensus_sha
    # Existing .skp must be preserved on skip.
    assert skp.exists() and skp.stat().st_size > 0


def test_run_force_skp_bypasses_skip(tmp_path, consensus, monkeypatch):
    """force_skp=True must NOT short-circuit even when the sidecar
    matches. We don't actually want SU to fire in tests, so we let
    Popen attempt and the timeout kick in immediately."""
    skp = tmp_path / "model.skp"
    skp.write_bytes(b"existing skp")
    consensus_sha = sfc._file_sha256(consensus)
    sfc.write_metadata(
        skp, consensus_sha256=consensus_sha,
        sketchup_exe=Path("C:/fake/SU.exe"), command=["fake"],
    )

    popen_calls = {"n": 0}

    class _FakeProc:
        returncode = None
        def poll(self):
            self.returncode = 1
            return self.returncode
        def terminate(self):
            return None
        def kill(self):
            return None

    def _fake_popen(*a, **kw):
        popen_calls["n"] += 1
        return _FakeProc()

    monkeypatch.setattr(sfc.subprocess, "Popen", _fake_popen)

    result = sfc.run(
        consensus, skp, sketchup_exe=Path("C:/fake/SU.exe"),
        plugins_dir=tmp_path / "plugins",
        timeout_s=2,
        force_skp=True,
    )
    # SU was invoked (Popen called), and since the fake proc
    # exits prematurely, run reports failure — that's fine for
    # this test; the assertion is about the bypass, not export.
    assert popen_calls["n"] == 1
    assert result["skipped"] is False


def test_run_writes_metadata_after_successful_export(tmp_path, consensus, monkeypatch):
    """When SU writes the .skp before timeout, run must persist a
    fresh sidecar so the next call skips."""
    skp = tmp_path / "model.skp"

    class _SimulatedSU:
        """Pretends to be SU: on first poll, writes the .skp."""
        returncode = None
        _wrote = False
        def __init__(self, target):
            self.target = target
        def poll(self):
            if not self._wrote:
                self.target.write_bytes(b"\x00" * 1500)
                self._wrote = True
            return None  # still running until terminated
        def terminate(self):
            self.returncode = 0
        def kill(self):
            self.returncode = -9

    def _fake_popen(cmd, **kw):
        return _SimulatedSU(skp)

    monkeypatch.setattr(sfc.subprocess, "Popen", _fake_popen)
    # Speed up: skip the 2-second flush wait inside run().
    monkeypatch.setattr(sfc.time, "sleep", lambda *a, **kw: None)

    result = sfc.run(
        consensus, skp, sketchup_exe=Path("C:/fake/SU.exe"),
        plugins_dir=tmp_path / "plugins",
        timeout_s=5,
    )
    assert result["ok"] is True
    assert result["skipped"] is False
    assert skp.exists()
    meta = sfc.read_metadata(skp)
    assert meta is not None
    assert meta["consensus_sha256"] == sfc._file_sha256(consensus)
    assert Path(meta["sketchup_path"]) == Path("C:/fake/SU.exe")


def test_run_clears_stale_metadata_when_re_exporting(tmp_path, consensus, monkeypatch):
    """If a previous run left a sidecar but force_skp triggers a
    fresh export, the OLD sidecar must be removed before the new
    one is written so a mid-export crash leaves no stale state."""
    skp = tmp_path / "model.skp"
    skp.write_bytes(b"old")
    sfc.write_metadata(
        skp, consensus_sha256="aa" * 32,
        sketchup_exe=Path("a"), command=["a"],
    )
    old_meta = sfc.read_metadata(skp)
    assert old_meta is not None

    # Make Popen exit immediately (premature) so we don't actually
    # wait. The point is: the unlink path runs and old metadata is
    # cleared.
    class _Fail:
        returncode = None
        def poll(self):
            self.returncode = 1
            return 1
        def terminate(self): return None
        def kill(self): return None

    monkeypatch.setattr(sfc.subprocess, "Popen", lambda *a, **kw: _Fail())
    monkeypatch.setattr(sfc.time, "sleep", lambda *a, **kw: None)

    result = sfc.run(
        consensus, skp, sketchup_exe=Path("C:/fake/SU.exe"),
        plugins_dir=tmp_path / "plugins",
        timeout_s=1,
        force_skp=True,
    )
    # After forced re-export attempt, the old .skp and metadata
    # are both gone (export failed before producing a new .skp).
    assert result["ok"] is False
    assert not skp.exists()
    assert not sfc.metadata_path(skp).exists()
