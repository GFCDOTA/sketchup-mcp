"""F8 smoke tests for the ``skp_export`` Python CLI + bridge.

Covers the Path B (dry-run) behaviour plus the schema v2 validator.
Never invokes SketchUp — the Ruby-side pipeline is exercised only
through mocks on ``bridge.invoke_sketchup`` / ``bridge.locate_sketchup``.
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

# Ensure the repo root is on sys.path so that `import skp_export` works
# whether or not pytest inserted it automatically.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from skp_export import __main__ as cli  # noqa: E402
from skp_export import bridge, validator  # noqa: E402


P12_RUN = REPO_ROOT / "runs" / "proto" / "p12_v1_run"
PLANTA_74_RUN = REPO_ROOT / "runs" / "f7_planta_74"


def _require_run(path: Path) -> None:
    if not (path / "observed_model.json").is_file():
        pytest.skip(f"observed_model.json missing at {path}")


# ---------------------------------------------------------------------------
# CLI-level tests
# ---------------------------------------------------------------------------


def test_cli_rejects_missing_run_dir(tmp_path, capsys):
    missing = tmp_path / "does_not_exist"
    exit_code = cli.main(["--run-dir", str(missing)])
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "run-dir" in captured.err.lower()


def test_cli_rejects_missing_observed_model(tmp_path, capsys):
    # Existing dir but no observed_model.json -> exit 1.
    (tmp_path / "README.txt").write_text("hello")
    exit_code = cli.main(["--run-dir", str(tmp_path)])
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "observed_model.json" in captured.err


def test_cli_rejects_invalid_schema(tmp_path, capsys):
    _require_run(P12_RUN)
    # Copy p12 observed_model but drop the mandatory 'walls' field.
    src = json.loads((P12_RUN / "observed_model.json").read_text(encoding="utf-8"))
    del src["walls"]
    run_dir = tmp_path / "bad_run"
    run_dir.mkdir()
    (run_dir / "observed_model.json").write_text(
        json.dumps(src), encoding="utf-8"
    )

    exit_code = cli.main(["--run-dir", str(run_dir)])
    assert exit_code == 3
    captured = capsys.readouterr()
    assert "schema validation failed" in captured.err


def test_cli_dry_run_without_sketchup(tmp_path, capsys):
    _require_run(P12_RUN)
    with mock.patch.object(bridge, "locate_sketchup", return_value=None):
        exit_code = cli.main([
            "--run-dir",
            str(P12_RUN),
            "--dry-run",
        ])
    assert exit_code == 0
    captured = capsys.readouterr()
    # dry-run prints a human-readable line on stderr even when SketchUp is
    # absent, and the summary line on stdout.
    assert "walls=33" in captured.out
    assert "dry-run OK" in captured.err


def test_cli_dry_run_counts_walls_p12(capsys):
    _require_run(P12_RUN)
    exit_code = cli.main(["--run-dir", str(P12_RUN), "--dry-run"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "walls=33" in captured.out
    assert "rooms=18" in captured.out
    assert "openings=6" in captured.out


def test_cli_dry_run_counts_walls_planta_74(capsys):
    _require_run(PLANTA_74_RUN)
    exit_code = cli.main(["--run-dir", str(PLANTA_74_RUN), "--dry-run"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "walls=133" in captured.out
    assert "rooms=15" in captured.out
    assert "openings=13" in captured.out


def test_cli_full_run_returns_2_when_no_sketchup(tmp_path, capsys):
    _require_run(P12_RUN)
    with mock.patch.object(bridge, "locate_sketchup", return_value=None):
        exit_code = cli.main(["--run-dir", str(P12_RUN)])
    assert exit_code == 2
    captured = capsys.readouterr()
    assert "sketchup" in captured.err.lower()


# ---------------------------------------------------------------------------
# Schema validator tests
# ---------------------------------------------------------------------------


def test_schema_v2_validates_p12_run():
    _require_run(P12_RUN)
    result = validator.validate_run(P12_RUN)
    assert result.valid, f"validation errors: {result.errors}"


def test_schema_v2_validates_planta_74_run():
    _require_run(PLANTA_74_RUN)
    result = validator.validate_run(PLANTA_74_RUN)
    assert result.valid, f"validation errors: {result.errors}"


def test_schema_v2_rejects_missing_walls():
    _require_run(P12_RUN)
    src = json.loads((P12_RUN / "observed_model.json").read_text(encoding="utf-8"))
    del src["walls"]
    result = validator.validate_dict(src)
    assert not result.valid
    # The error message should mention 'walls' somewhere.
    assert any("walls" in err for err in result.errors)


def test_schema_v2_rejects_wall_without_start():
    _require_run(P12_RUN)
    src = json.loads((P12_RUN / "observed_model.json").read_text(encoding="utf-8"))
    src = copy.deepcopy(src)
    del src["walls"][0]["start"]
    result = validator.validate_dict(src)
    assert not result.valid
    assert any("start" in err for err in result.errors)


def test_schema_v2_rejects_bad_schema_version():
    _require_run(P12_RUN)
    src = json.loads((P12_RUN / "observed_model.json").read_text(encoding="utf-8"))
    src = copy.deepcopy(src)
    src["schema_version"] = "1.0.0"
    result = validator.validate_dict(src)
    assert not result.valid
    assert any("schema_version" in err or "pattern" in err for err in result.errors)


# ---------------------------------------------------------------------------
# Bridge tests
# ---------------------------------------------------------------------------


def test_bridge_dry_run_returns_summary_dict():
    _require_run(P12_RUN)
    summary = bridge.dry_run(P12_RUN)
    assert summary["walls"] == 33
    assert summary["rooms"] == 18
    assert summary["openings"] == 6
    assert summary["peitoris"] == 2
    assert summary["junctions"] == 65
    assert summary["schema_version"].startswith("2.")


def test_bridge_dry_run_raises_on_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        bridge.dry_run(tmp_path)


def test_bridge_propagates_ruby_exit(tmp_path):
    """Mock subprocess.run to return an arbitrary exit code and confirm
    invoke_sketchup propagates it (plus stdout/stderr)."""
    _require_run(P12_RUN)
    fake_result = subprocess.CompletedProcess(
        args=["dummy"], returncode=5, stdout="hello\n", stderr="warn\n"
    )
    with mock.patch.object(subprocess, "run", return_value=fake_result):
        exit_code, stdout, stderr = bridge.invoke_sketchup(
            sketchup_exe=Path("C:/fake/SketchUp.exe"),
            run_dir=P12_RUN,
        )
    assert exit_code == 5
    assert stdout == "hello\n"
    assert stderr == "warn\n"


def test_bridge_timeout_returns_124():
    _require_run(P12_RUN)
    fake_timeout = subprocess.TimeoutExpired(cmd=["dummy"], timeout=1)
    with mock.patch.object(subprocess, "run", side_effect=fake_timeout):
        exit_code, _stdout, _stderr = bridge.invoke_sketchup(
            sketchup_exe=Path("C:/fake/SketchUp.exe"),
            run_dir=P12_RUN,
        )
    assert exit_code == 124


def test_bridge_locate_sketchup_returns_none_on_linux():
    with mock.patch.object(sys, "platform", "linux"):
        assert bridge.locate_sketchup() is None


def test_cli_uses_explicit_sketchup_exe(tmp_path, capsys):
    _require_run(P12_RUN)
    fake_exe = tmp_path / "nothing_here.exe"
    # No file -> CLI should report error 1.
    exit_code = cli.main([
        "--run-dir",
        str(P12_RUN),
        "--sketchup-exe",
        str(fake_exe),
    ])
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "sketchup-exe" in captured.err.lower() or "not a file" in captured.err.lower()
