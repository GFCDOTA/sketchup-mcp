"""Unit tests for `scripts/smoke/smoke_skp_export.py`.

Tests are scoped to the cheap gates (A, B, C, E, H) and the helper
functions. Gates D, F, G drive subprocess calls into render_axon /
skp_from_consensus and require matplotlib / SketchUp respectively;
those are exercised manually per `docs/validation/sketchup_smoke_workflow.md`.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "smoke" / "smoke_skp_export.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("smoke_skp_export", SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["smoke_skp_export"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def smoke():
    return _load_module()


@pytest.fixture()
def synthetic_consensus_dict():
    return {
        "walls": [
            {"start": [0.0, 0.0], "end": [10.0, 0.0], "orientation": "h"},
            {"start": [10.0, 0.0], "end": [10.0, 10.0], "orientation": "v"},
        ],
        "rooms": [{"id": "r1", "polygon": [[0, 0], [10, 0], [10, 10], [0, 10]]}],
        "openings": [],
    }


@pytest.fixture()
def synthetic_consensus_path(tmp_path, synthetic_consensus_dict):
    p = tmp_path / "consensus.json"
    p.write_text(json.dumps(synthetic_consensus_dict), encoding="utf-8")
    return p


def _make_args(smoke, **overrides):
    """Build argparse Namespace with the same defaults as the parser."""
    parser = smoke._build_parser()
    args = parser.parse_args([])
    for k, v in overrides.items():
        setattr(args, k, v)
    return args


def _make_report(smoke, **overrides):
    defaults = {
        "consensus_path": "/x/consensus.json",
        "out_dir": "/x/out",
        "started_at": "2026-05-03T00:00:00Z",
    }
    defaults.update(overrides)
    return smoke.SmokeReport(**defaults)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def test_validate_consensus_shape_passes(smoke, synthetic_consensus_dict):
    smoke._validate_consensus_shape(synthetic_consensus_dict)


@pytest.mark.parametrize("missing", ["walls", "rooms", "openings"])
def test_validate_consensus_shape_fails_missing(smoke, synthetic_consensus_dict, missing):
    del synthetic_consensus_dict[missing]
    with pytest.raises(ValueError, match=missing):
        smoke._validate_consensus_shape(synthetic_consensus_dict)


def test_validate_consensus_shape_fails_bad_wall(smoke, synthetic_consensus_dict):
    synthetic_consensus_dict["walls"][0]["start"] = "not a list"
    with pytest.raises(ValueError, match=r"walls\[0\].start"):
        smoke._validate_consensus_shape(synthetic_consensus_dict)


def test_validate_consensus_shape_fails_non_dict(smoke):
    with pytest.raises(ValueError, match="object"):
        smoke._validate_consensus_shape(["not", "a", "dict"])


def test_sha256_path_deterministic(smoke, tmp_path):
    f = tmp_path / "x.bin"
    f.write_bytes(b"hello world")
    h1 = smoke._sha256_path(f)
    h2 = smoke._sha256_path(f)
    assert h1 == h2
    assert len(h1) == 64


def test_compute_cache_key_changes_with_consensus(smoke, tmp_path, monkeypatch):
    """Different consensus hash must yield different cache key, even
    when the source files in CACHE_KEY_INPUTS are unchanged."""
    monkeypatch.setattr(smoke, "REPO_ROOT", tmp_path)
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "skp_from_consensus.py").write_bytes(b"a")
    (tmp_path / "tools" / "consume_consensus.rb").write_bytes(b"b")
    k1 = smoke._compute_cache_key("consensus_hash_1", tmp_path)
    k2 = smoke._compute_cache_key("consensus_hash_2", tmp_path)
    assert k1 != k2


def test_compute_cache_key_handles_absent_inputs(smoke, tmp_path):
    """If a source file is missing, the cache key must still be deterministic."""
    k1 = smoke._compute_cache_key("h", tmp_path)
    k2 = smoke._compute_cache_key("h", tmp_path)
    assert k1 == k2


# ---------------------------------------------------------------------------
# Argparse
# ---------------------------------------------------------------------------


def test_parser_defaults(smoke):
    args = smoke._build_parser().parse_args([])
    assert args.skip_skp is False
    assert args.force_skp is False
    assert args.open_after is False
    assert args.timeout == 180


def test_parser_flags(smoke):
    args = smoke._build_parser().parse_args(["--skip-skp", "--force-skp"])
    assert args.skip_skp is True
    assert args.force_skp is True


# ---------------------------------------------------------------------------
# Gate A
# ---------------------------------------------------------------------------


def test_gate_a_creates_out_dir(smoke, tmp_path):
    out_dir = tmp_path / "smoke_run"
    args = _make_args(smoke, out_dir=out_dir, sketchup=None, skip_skp=True)
    report = _make_report(smoke, out_dir=str(out_dir))
    g = smoke.gate_a(args, report)
    assert g.status == "pass"
    assert out_dir.is_dir()


def test_gate_a_fails_when_sketchup_missing_and_not_skip(smoke, tmp_path):
    args = _make_args(
        smoke,
        out_dir=tmp_path / "out",
        sketchup=tmp_path / "definitely_does_not_exist.exe",
        skip_skp=False,
    )
    report = _make_report(smoke)
    g = smoke.gate_a(args, report)
    assert g.status == "fail"
    assert "sketchup not found" in g.message.lower()


# ---------------------------------------------------------------------------
# Gate B
# ---------------------------------------------------------------------------


def test_gate_b_loads_valid_json(smoke, tmp_path, synthetic_consensus_path):
    args = _make_args(smoke, consensus=synthetic_consensus_path,
                      out_dir=tmp_path / "out", skip_skp=True)
    report = _make_report(smoke, out_dir=str(tmp_path / "out"))
    g = smoke.gate_b(args, report)
    assert g.status == "pass"
    assert report.consensus_sha256
    assert hasattr(args, "_consensus_data")


def test_gate_b_fails_on_missing_file(smoke, tmp_path):
    args = _make_args(smoke, consensus=tmp_path / "nope.json",
                      out_dir=tmp_path / "out", skip_skp=True)
    report = _make_report(smoke)
    g = smoke.gate_b(args, report)
    assert g.status == "fail"


def test_gate_b_fails_on_bad_json(smoke, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    args = _make_args(smoke, consensus=bad,
                      out_dir=tmp_path / "out", skip_skp=True)
    report = _make_report(smoke)
    g = smoke.gate_b(args, report)
    assert g.status == "fail"
    assert "json" in g.message.lower()


# ---------------------------------------------------------------------------
# Gate C
# ---------------------------------------------------------------------------


def test_gate_c_passes_on_valid_shape(smoke, synthetic_consensus_dict):
    args = argparse.Namespace(_consensus_data=synthetic_consensus_dict)
    report = _make_report(smoke)
    g = smoke.gate_c(args, report)
    assert g.status == "pass"
    assert "walls=2" in g.message


def test_gate_c_fails_on_invalid_shape(smoke):
    args = argparse.Namespace(_consensus_data={"walls": "not a list"})
    report = _make_report(smoke)
    g = smoke.gate_c(args, report)
    assert g.status == "fail"


def test_gate_c_skips_without_data(smoke):
    args = argparse.Namespace()
    report = _make_report(smoke)
    g = smoke.gate_c(args, report)
    assert g.status == "skip"


# ---------------------------------------------------------------------------
# Gate E
# ---------------------------------------------------------------------------


def test_gate_e_cache_miss_when_no_marker(smoke, tmp_path):
    out_dir = tmp_path / "smoke" / "run1"
    out_dir.mkdir(parents=True)
    args = _make_args(smoke, out_dir=out_dir, force_skp=False)
    report = _make_report(smoke, out_dir=str(out_dir),
                          consensus_sha256="deadbeef" * 8)
    g = smoke.gate_e(args, report)
    assert g.status == "pass"
    assert report.cache_hit is False
    assert "cache miss" in g.message


def test_gate_e_cache_hit_when_marker_matches(smoke, tmp_path):
    smoke_dir = tmp_path / "smoke"
    out_dir = smoke_dir / "run1"
    out_dir.mkdir(parents=True)
    consensus_sha = "a" * 64
    args = _make_args(smoke, out_dir=out_dir, force_skp=False)
    report = _make_report(smoke, out_dir=str(out_dir),
                          consensus_sha256=consensus_sha)
    expected_key = smoke._compute_cache_key(consensus_sha, smoke.REPO_ROOT)
    (smoke_dir / "_skp_cache.json").write_text(
        json.dumps({"cache_key": expected_key, "verdict": "pass",
                    "run_id": "run0", "skp_path": "old.skp"}),
        encoding="utf-8",
    )
    g = smoke.gate_e(args, report)
    assert g.status == "pass"
    assert report.cache_hit is True
    assert "cache hit" in g.message


def test_gate_e_force_skp_bypasses_cache(smoke, tmp_path):
    smoke_dir = tmp_path / "smoke"
    out_dir = smoke_dir / "run1"
    out_dir.mkdir(parents=True)
    consensus_sha = "a" * 64
    args = _make_args(smoke, out_dir=out_dir, force_skp=True)
    report = _make_report(smoke, out_dir=str(out_dir),
                          consensus_sha256=consensus_sha)
    expected_key = smoke._compute_cache_key(consensus_sha, smoke.REPO_ROOT)
    (smoke_dir / "_skp_cache.json").write_text(
        json.dumps({"cache_key": expected_key, "verdict": "pass"}),
        encoding="utf-8",
    )
    g = smoke.gate_e(args, report)
    assert report.cache_hit is False
    assert "force-skp" in g.message.lower()


# ---------------------------------------------------------------------------
# Gate H
# ---------------------------------------------------------------------------


def test_gate_h_writes_reports(smoke, tmp_path):
    out_dir = tmp_path / "smoke" / "run1"
    out_dir.mkdir(parents=True)
    args = _make_args(smoke, out_dir=out_dir, skip_skp=True)
    report = _make_report(smoke, out_dir=str(out_dir),
                          consensus_sha256="x" * 64)
    report.add(smoke.GateResult(name="A. Preparation", status="pass"))
    g = smoke.gate_h(args, report)
    assert g.status == "pass"
    assert (out_dir / "sketchup_smoke_report.json").exists()
    assert (out_dir / "sketchup_smoke_report.md").exists()
    payload = json.loads((out_dir / "sketchup_smoke_report.json").read_text())
    assert payload["verdict"] == "pass"


def test_gate_h_marks_failure_when_any_gate_failed(smoke, tmp_path):
    out_dir = tmp_path / "smoke" / "run2"
    out_dir.mkdir(parents=True)
    args = _make_args(smoke, out_dir=out_dir, skip_skp=True)
    report = _make_report(smoke, out_dir=str(out_dir))
    report.add(smoke.GateResult(name="X", status="fail", message="oops"))
    g = smoke.gate_h(args, report)
    assert g.status == "pass"  # H itself succeeded writing the report
    assert report.verdict == "fail"


def test_gate_h_skips_cache_marker_when_skip_skp(smoke, tmp_path):
    """With --skip-skp, no .skp is produced, so the cache marker must
    not be written (otherwise we'd lie about a successful export)."""
    out_dir = tmp_path / "smoke" / "run3"
    out_dir.mkdir(parents=True)
    args = _make_args(smoke, out_dir=out_dir, skip_skp=True)
    report = _make_report(smoke, out_dir=str(out_dir))
    smoke.gate_h(args, report)
    assert not (out_dir.parent / "_skp_cache.json").exists()
