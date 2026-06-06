"""--promote hook in build_plan_shell_skp: build+promote fused, gate-guarded.

A green build lands at the stable deliverable automatically; a red gate, a
cached build, or a missing report must NOT promote (never push an
unverified/broken build to the fixed path).
"""
from __future__ import annotations

import json
import types

import pytest

from tools.build_plan_shell_skp import _auto_promote, _infer_plant


def _args(out, consensus, promote=True, plant=None):
    return types.SimpleNamespace(
        promote=promote, out=out, consensus=consensus, plant=plant)


def _build_dir(tmp_path, gates):
    b = tmp_path / "runs" / "x"
    b.mkdir(parents=True, exist_ok=True)
    (b / "model.skp").write_bytes(b"SKP")
    (b / "model_iso.png").write_bytes(b"i")
    (b / "model_top.png").write_bytes(b"t")
    (b / "geometry_report.json").write_text(
        json.dumps({"gates_self_check": gates}), encoding="utf-8")
    return b


def _consensus(tmp_path, plant="planta_Z"):
    c = tmp_path / "fixtures" / plant / "c.json"
    c.parent.mkdir(parents=True, exist_ok=True)
    c.write_text("{}", encoding="utf-8")
    return c


def test_infer_plant():
    from pathlib import Path
    assert _infer_plant(Path("a/fixtures/planta_74/c.json")) == "planta_74"
    assert _infer_plant(Path("x.json"), "override") == "override"
    assert _infer_plant(Path("nowhere/x.json")) == "planta_74"  # fallback


def _patch_det(monkeypatch, overall="PASS", gates=None):
    import tools.run_deterministic_gates as rdg
    monkeypatch.setattr(rdg, "run_all",
                        lambda **k: {"overall": overall, "gates": gates or {}})


def test_green_build_promotes_to_stable_path(tmp_path, monkeypatch):
    b = _build_dir(tmp_path, {"a": True, "b": True})
    c = _consensus(tmp_path)
    _patch_det(monkeypatch, "PASS")  # deterministic suite tested separately
    import tools.promote_canonical as pc
    orig = pc.promote
    monkeypatch.setattr(pc, "promote",
                        lambda src, plant, repo=None: orig(src, plant, repo=tmp_path))
    line = _auto_promote(_args(b / "model.skp", c), {"ok": True})
    assert "PROMOTED" in line and "planta_Z" in line
    assert (tmp_path / "artifacts" / "planta_Z" / "planta_Z.skp").read_bytes() == b"SKP"


def test_deterministic_fail_blocks_promote(tmp_path, monkeypatch):
    # self-check gates green, but the deterministic suite FAILs -> no promote.
    b = _build_dir(tmp_path, {"a": True})
    c = _consensus(tmp_path)
    _patch_det(monkeypatch, "FAIL", {"wall_presence": {"verdict": "FAIL"}})
    line = _auto_promote(_args(b / "model.skp", c), {"ok": True})
    assert "PROMOTE_SKIPPED" in line and "deterministic" in line
    assert not (tmp_path / "artifacts" / "planta_Z").exists()


def test_deterministic_incomplete_blocks_promote(tmp_path, monkeypatch):
    b = _build_dir(tmp_path, {"a": True})
    c = _consensus(tmp_path)
    _patch_det(monkeypatch, "INCOMPLETE",
               {"wall_presence": {"verdict": "SKIPPED_NO_SIDECAR"}})
    line = _auto_promote(_args(b / "model.skp", c), {"ok": True})
    assert "PROMOTE_SKIPPED" in line and "INCOMPLETE" in line


def test_failed_gate_does_not_promote(tmp_path):
    b = _build_dir(tmp_path, {"floors_separated_from_walls": False, "ok2": True})
    line = _auto_promote(_args(b / "model.skp", _consensus(tmp_path)), {"ok": True})
    assert "PROMOTE_SKIPPED" in line and "floors_separated_from_walls" in line


def test_cached_build_does_not_promote(tmp_path):
    b = _build_dir(tmp_path, {"a": True})
    line = _auto_promote(_args(b / "model.skp", _consensus(tmp_path)),
                         {"ok": True, "skipped": True})
    assert "PROMOTE_SKIPPED" in line and "cached" in line


def test_missing_report_does_not_promote(tmp_path):
    b = tmp_path / "runs" / "y"
    b.mkdir(parents=True)
    (b / "model.skp").write_bytes(b"SKP")
    line = _auto_promote(_args(b / "model.skp", _consensus(tmp_path)), {"ok": True})
    assert "PROMOTE_SKIPPED" in line


def test_promote_flag_off_is_noop(tmp_path):
    b = _build_dir(tmp_path, {"a": True})
    assert _auto_promote(_args(b / "model.skp", _consensus(tmp_path), promote=False),
                         {"ok": True}) is None
