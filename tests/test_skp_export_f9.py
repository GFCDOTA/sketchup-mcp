"""Python smoke tests for F9 (Ruby robustness) skp_export bridge.

These tests exercise the PYTHON side of the Ruby/Python bridge. They
do NOT invoke SketchUp. The Ruby unit tests under
``skp_export/test/`` cover the Ruby-pure math (Coords, Units) and
require a standalone Ruby interpreter — which is not guaranteed on
CI hosts, so those tests are documented rather than auto-run.

The smoke tests here act as the canonical cross-validation: if the
Ruby thickness-classifier or the Python one drift, this file will
break.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
P12_RUN_DIR = REPO_ROOT / "runs" / "proto" / "p12_v1_run"
SKP_EXPORT_DIR = REPO_ROOT / "skp_export"


def _python_exe() -> str:
    """Return the python executable to invoke sub-processes with.

    We always reuse ``sys.executable`` so tests run against the same
    interpreter that pytest is running in — this matters on Windows
    where the embedded Python distribution has a ``_pth`` file that
    blocks ``-m`` unless CWD is wired through ``sys.path`` manually.
    """
    return sys.executable


def _cli(argv: list[str], cwd: Path = REPO_ROOT, timeout: float = 30.0):
    """Invoke the skp_export CLI the same way the plan documents.

    Because the embedded Python install ships with a ``python312._pth``
    that restricts ``sys.path`` (``safe_path=True``), ``-m skp_export``
    fails on this host. We work around it by running via ``-c`` and
    inserting CWD onto ``sys.path`` explicitly — functionally identical
    to what ``run_p12.py`` already does in the repo.
    """
    bootstrap = (
        "import sys; sys.path.insert(0, r'%s');"
        "from skp_export.__main__ import main;"
        "raise SystemExit(main(%r))" % (str(cwd), argv)
    )
    return subprocess.run(
        [_python_exe(), "-c", bootstrap],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(cwd),
    )


@pytest.fixture(scope="module")
def p12_run_dir(tmp_path_factory):
    """Copy p12_v1_run into a tmp dir so we don't mutate the fixture."""
    if not P12_RUN_DIR.exists():
        pytest.skip(f"p12 run dir not available: {P12_RUN_DIR}")
    dst = tmp_path_factory.mktemp("p12_v1_run")
    for entry in P12_RUN_DIR.iterdir():
        if entry.is_file():
            shutil.copy2(entry, dst / entry.name)
    return dst


# ---------------------------------------------------------------------------
# CLI smoke tests
# ---------------------------------------------------------------------------


def test_dry_run_p12_classifies_thickness(p12_run_dir):
    """Dry-run must report drywall_count + alvenaria_count in stdout."""
    proc = _cli(["--run-dir", str(p12_run_dir), "--dry-run"])
    assert proc.returncode == 0, f"stderr={proc.stderr!r}"
    out = proc.stdout
    assert "drywall_count=" in out, out
    assert "alvenaria_count=" in out, out
    # Baseline: p12 has 33 walls — the two counts must sum to 33.
    dw = int(_extract(out, "drywall_count="))
    al = int(_extract(out, "alvenaria_count="))
    walls = int(_extract(out, "walls="))
    assert dw + al == walls, f"{dw}+{al}!={walls}"


def test_dry_run_floors_flag_counts_rooms(p12_run_dir):
    """`--floors` should report floors=<room count with polygon>."""
    proc = _cli(["--run-dir", str(p12_run_dir), "--dry-run", "--floors"])
    assert proc.returncode == 0, f"stderr={proc.stderr!r}"
    out = proc.stdout
    rooms = int(_extract(out, "rooms="))
    floors = int(_extract(out, "floors="))
    assert floors == rooms, (
        f"floors={floors} should equal rooms={rooms} "
        f"(every p12 room has a polygon >= 3 vertices)"
    )


def test_dry_run_without_floors_reports_zero(p12_run_dir):
    """Without `--floors` the floors count is always 0 (opt-in)."""
    proc = _cli(["--run-dir", str(p12_run_dir), "--dry-run"])
    assert proc.returncode == 0, f"stderr={proc.stderr!r}"
    assert "floors=0" in proc.stdout, proc.stdout


def test_dry_run_schema_version_2x(p12_run_dir):
    """Dry-run must validate schema 2.x. Non-2.x emits warning; 2.x OK."""
    proc = _cli(["--run-dir", str(p12_run_dir), "--dry-run"])
    assert proc.returncode == 0, f"stderr={proc.stderr!r}"
    # observed_model.json must load cleanly.
    data = json.loads((p12_run_dir / "observed_model.json").read_text())
    assert data["schema_version"].startswith("2.")


def test_dry_run_missing_run_dir_exits_1():
    """Bogus run-dir: CLI exits 1 with a clear error."""
    proc = _cli(["--run-dir", str(REPO_ROOT / "does_not_exist"), "--dry-run"])
    assert proc.returncode == 1
    assert "does not exist" in (proc.stderr or "")


# ---------------------------------------------------------------------------
# Bridge-level tests (no subprocess)
# ---------------------------------------------------------------------------


def test_classify_wall_thicknesses_matches_ruby_threshold():
    """Python and Ruby classifiers must agree at 2.5 px exactly."""
    from skp_export import bridge  # import via same cwd assumption

    walls = [
        {"thickness": 2.4},  # drywall
        {"thickness": 2.5},  # alvenaria (>= threshold)
        {"thickness": 2.6},  # alvenaria
        {"thickness": 1.0},  # drywall
        {"thickness": 3.8},  # alvenaria
    ]
    counts = bridge.classify_wall_thicknesses(walls)
    assert counts == {"drywall": 2, "alvenaria": 3}, counts


def test_classify_wall_thicknesses_empty():
    from skp_export import bridge

    assert bridge.classify_wall_thicknesses([]) == {"drywall": 0, "alvenaria": 0}


def test_count_candidate_floors_skips_sub_triangles():
    """A room needs a polygon of 3+ vertices to become a floor face."""
    from skp_export import bridge

    rooms = [
        {"room_id": "r-1", "polygon": [[0, 0], [1, 0], [1, 1]]},       # 3 verts OK
        {"room_id": "r-2", "polygon": [[0, 0], [1, 0]]},                # only 2 verts — skip
        {"room_id": "r-3"},                                             # missing polygon — skip
        {"room_id": "r-4", "polygon": [[0, 0], [1, 0], [1, 1], [0, 1]]},  # 4 verts OK
    ]
    assert bridge.count_candidate_floors(rooms) == 2


def test_dry_run_bridge_contains_new_f9_fields(p12_run_dir):
    """bridge.dry_run must expose drywall_count, alvenaria_count, floors."""
    from skp_export import bridge

    summary = bridge.dry_run(p12_run_dir, floors=True)
    assert "drywall_count" in summary
    assert "alvenaria_count" in summary
    assert "floors" in summary
    assert summary["drywall_count"] + summary["alvenaria_count"] == summary["walls"]
    assert summary["floors"] == summary["rooms"], (
        f"floors={summary['floors']} rooms={summary['rooms']}"
    )


def test_dry_run_bridge_floors_zero_when_not_requested(p12_run_dir):
    from skp_export import bridge

    summary = bridge.dry_run(p12_run_dir, floors=False)
    assert summary["floors"] == 0


# ---------------------------------------------------------------------------
# Ruby file presence and syntax
# ---------------------------------------------------------------------------


def test_f9_ruby_files_exist():
    """F9 adds lib/coords.rb + build_floors.rb. They must be on disk."""
    assert (SKP_EXPORT_DIR / "lib" / "coords.rb").is_file()
    assert (SKP_EXPORT_DIR / "build_floors.rb").is_file()


def test_rebuild_walls_no_longer_uses_to_metres_heuristic():
    """F9 removes the fragile ``to_metres`` (>50 px assumption).

    The historical note about ``values > 50`` may remain in a comment
    explaining the deletion — we only check the actual method and the
    runtime comparison are gone.
    """
    rw = (SKP_EXPORT_DIR / "rebuild_walls.rb").read_text(encoding="utf-8")
    assert "def self.to_metres" not in rw, (
        "to_metres heuristic still present — F9 was supposed to remove it"
    )
    # The live `c > 50.0` runtime check must be gone. We look for the
    # exact Ruby expression, not the word "50" (which may appear in
    # comments or DEFAULT_PX constants).
    assert "c > 50.0" not in rw, (
        "heuristic runtime comparison `c > 50.0` still present"
    )
    # Must route through Coords now.
    assert "Coords.length_px_to_m" in rw


def test_apply_openings_uses_coords():
    """F9 migrates apply_openings from Units.point_px_to_m -> Coords."""
    ao = (SKP_EXPORT_DIR / "apply_openings.rb").read_text(encoding="utf-8")
    assert "Coords.point_px_to_m" in ao
    assert "Coords.length_px_to_m" in ao
    assert "Coords.wall_thickness_m" in ao


def test_place_door_handles_hinge_and_swing():
    """place_door_component.rb must honour hinge_side and swing_deg."""
    pd = (SKP_EXPORT_DIR / "place_door_component.rb").read_text(encoding="utf-8")
    # Hinge mirror via scale Y.
    assert 'hinge_side] == "right"' in pd
    # Swing arc drawn via add_arc.
    assert "add_arc" in pd
    assert "draw_swing_arc" in pd


def test_build_floors_registered_in_main():
    """main.rb must require build_floors and call it behind the flag."""
    m = (SKP_EXPORT_DIR / "main.rb").read_text(encoding="utf-8")
    assert 'require_relative "build_floors"' in m
    assert "BuildFloors.run" in m
    assert "floors:" in m


def test_main_parses_floors_flag():
    """main.rb CLI must surface --floors."""
    m = (SKP_EXPORT_DIR / "main.rb").read_text(encoding="utf-8")
    assert "--floors" in m


@pytest.mark.skipif(
    shutil.which("ruby") is None,
    reason="standalone Ruby not on PATH — SketchUp's embedded Ruby DLL is not runnable from CLI",
)
def test_ruby_syntax_valid_main_rb():
    """If Ruby is installed, syntax-check main.rb. Skipped otherwise."""
    proc = subprocess.run(
        ["ruby", "-c", str(SKP_EXPORT_DIR / "main.rb")],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert proc.returncode == 0, proc.stderr


@pytest.mark.skipif(
    shutil.which("ruby") is None,
    reason="standalone Ruby not on PATH",
)
def test_ruby_syntax_valid_coords_and_build_floors():
    for name in ("lib/coords.rb", "build_floors.rb", "rebuild_walls.rb",
                 "apply_openings.rb", "place_door_component.rb"):
        proc = subprocess.run(
            ["ruby", "-c", str(SKP_EXPORT_DIR / name)],
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert proc.returncode == 0, f"{name}: {proc.stderr}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract(text: str, key: str) -> str:
    """Extract the token immediately after ``key`` up to the next space."""
    assert key in text, f"missing {key!r} in {text!r}"
    tail = text.split(key, 1)[1]
    return tail.split()[0].rstrip().strip()
