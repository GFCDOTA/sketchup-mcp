"""Unit tests for tools.disarm_sketchup_autoruns.

Drives the helper against a temp directory pretending to be the SU
plugins folder, so the test never touches the real plugins dir and
never requires SketchUp to be installed.

Covers the contract that the FP-014 fix relies on:
1. Removes every ``*control.txt`` in the dir.
2. Leaves other files alone (autorun ``.rb`` scripts, ``.txt`` logs
   that don't end in ``control.txt``, subdirectories).
3. ``dry_run=True`` lists but does not delete.
4. Missing directory returns ``[]`` (no raise).
5. Idempotent: second call returns ``[]``.
"""
from __future__ import annotations

from pathlib import Path

from tools.disarm_sketchup_autoruns import disarm


def test_disarm_removes_all_control_files(tmp_path: Path) -> None:
    a = tmp_path / "autorun_control.txt"
    b = tmp_path / "autorun_inspector_control.txt"
    a.write_text("consensus\nskp\nrb", encoding="utf-8")
    b.write_text("a\nb\nc", encoding="utf-8")

    removed = disarm(tmp_path)

    assert sorted(p.name for p in removed) == [
        "autorun_control.txt",
        "autorun_inspector_control.txt",
    ]
    assert not a.exists()
    assert not b.exists()


def test_disarm_leaves_non_control_files_intact(tmp_path: Path) -> None:
    plugin = tmp_path / "autorun_consume.rb"
    log = tmp_path / "autorun_inspector_log.txt"
    progress = tmp_path / "render_axon_progress.txt"
    touch = tmp_path / "probe_loaded.txt"
    subdir = tmp_path / "habitat_site_context"
    plugin.write_text("require 'json'", encoding="utf-8")
    log.write_text("...", encoding="utf-8")
    progress.write_text("...", encoding="utf-8")
    touch.write_text("loaded at ...", encoding="utf-8")
    subdir.mkdir()

    # An armed control file alongside the noise.
    armed = tmp_path / "autorun_control.txt"
    armed.write_text("...", encoding="utf-8")

    removed = disarm(tmp_path)

    assert [p.name for p in removed] == ["autorun_control.txt"]
    assert plugin.exists()
    assert log.exists()
    assert progress.exists()
    assert touch.exists()
    assert subdir.is_dir()
    assert not armed.exists()


def test_disarm_dry_run_does_not_delete(tmp_path: Path) -> None:
    a = tmp_path / "autorun_control.txt"
    a.write_text("x", encoding="utf-8")

    listed = disarm(tmp_path, dry_run=True)

    assert [p.name for p in listed] == ["autorun_control.txt"]
    assert a.exists()  # NOT deleted


def test_disarm_missing_dir_is_no_op(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist"
    assert disarm(missing) == []
    # Should not have been created as a side-effect either.
    assert not missing.exists()


def test_disarm_idempotent(tmp_path: Path) -> None:
    (tmp_path / "autorun_control.txt").write_text("x", encoding="utf-8")
    first = disarm(tmp_path)
    second = disarm(tmp_path)
    assert len(first) == 1
    assert second == []


def test_disarm_returns_paths_under_plugins_dir(tmp_path: Path) -> None:
    p = tmp_path / "autorun_control.txt"
    p.write_text("x", encoding="utf-8")
    removed = disarm(tmp_path)
    assert removed == [p]
