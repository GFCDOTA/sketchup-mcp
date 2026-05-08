"""Smoke tests for the argparse-based CLI on the proto_*.py + render_sidebyside.py
scripts.

History: these scripts used to hardcode ``C:/Users/felip_local/Documents/paredes.png``
and were ruff-excluded as documented tech debt. They were refactored to take
``argparse`` flags on 2026-05-08 (`refactor/proto-cli-args-cleanup`); these
smoke tests guard the public surface (--help) so the next refactor wave
catches accidental regression of the entry point.

Each test invokes the script through ``python <script> --help`` as a
subprocess so we exercise the real ``__main__`` path rather than just
the importable parser.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _run_help(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, script, "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_proto_red_help_runs():
    cp = _run_help("proto_red.py")
    assert cp.returncode == 0, cp.stderr
    assert "usage: proto_red.py" in cp.stdout
    assert "--input" in cp.stdout
    assert "--output-dir" in cp.stdout


def test_proto_colored_help_runs():
    cp = _run_help("proto_colored.py")
    assert cp.returncode == 0, cp.stderr
    assert "usage: proto_colored.py" in cp.stdout
    assert "--input" in cp.stdout
    assert "--output-dir" in cp.stdout
    assert "--min-peitoril-area" in cp.stdout
    assert "--peitoril-height-m" in cp.stdout


def test_render_sidebyside_help_runs():
    cp = _run_help("render_sidebyside.py")
    assert cp.returncode == 0, cp.stderr
    assert "usage: render_sidebyside.py" in cp.stdout
    assert "--painted" in cp.stdout
    assert "--overlay" in cp.stdout
    assert "--output" in cp.stdout
    assert "--no-history" in cp.stdout


def test_proto_red_missing_input_exits_nonzero():
    """Required --input must surface a usage error (exit 2) when omitted."""
    cp = subprocess.run(
        [sys.executable, "proto_red.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert cp.returncode != 0
    assert "--input" in cp.stderr or "required" in cp.stderr.lower()


def test_render_sidebyside_crop_validator_rejects_bad_spec():
    """--crop must reject a non-4-tuple spec with a clear argparse error."""
    cp = subprocess.run(
        [
            sys.executable,
            "render_sidebyside.py",
            "--painted",
            "x.png",
            "--overlay",
            "y.png",
            "--output",
            "z.png",
            "--crop",
            "1,2,3",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert cp.returncode != 0
    assert "--crop" in cp.stderr or "x1,y1,x2,y2" in cp.stderr
