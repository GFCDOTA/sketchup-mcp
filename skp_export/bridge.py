"""Bridge between the Python pipeline and the SketchUp Ruby exporter.

Three responsibilities:

1. ``locate_sketchup()`` — find a usable ``SketchUp.exe`` on Windows.
2. ``invoke_sketchup()`` — launch SketchUp with the Ruby entry point.
3. ``dry_run()`` — validate ``observed_model.json`` and summarise counts
   without ever touching SketchUp (Path B fallback for CI and for
   environments where SketchUp is not installed).

All functions are defensive: we never raise out of public functions for
expected failure modes (missing SketchUp, missing file). Instead we
return ``None`` / ``dict`` so the CLI can translate to exit codes.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

_PACKAGE_DIR = Path(__file__).resolve().parent
_RUBY_ENTRY = _PACKAGE_DIR / "main.rb"

# SketchUp years we are willing to probe, newest first.
_SKETCHUP_YEARS = [str(y) for y in range(2025, 2015, -1)]


def locate_sketchup() -> Optional[Path]:
    """Return the first SketchUp.exe we can find on this Windows host.

    Strategy:

    1. Check the Windows registry ``HKLM\\SOFTWARE\\SketchUp\\SketchUp 20XX``
       for an ``InstallLocation`` string value.
    2. Fall back to probing ``%ProgramFiles%\\SketchUp\\SketchUp 20XX\\SketchUp.exe``.

    Returns ``None`` if no candidate exists. Also returns ``None`` on
    non-Windows platforms (the Ruby side requires the Windows binary).
    """
    if sys.platform != "win32":
        return None

    # 1. Registry lookup.
    try:
        import winreg  # type: ignore
    except ImportError:
        winreg = None  # type: ignore

    if winreg is not None:
        for year in _SKETCHUP_YEARS:
            key_path = rf"SOFTWARE\SketchUp\SketchUp {year}"
            for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    with winreg.OpenKey(hive, key_path) as key:
                        install_location, _ = winreg.QueryValueEx(key, "InstallLocation")
                        candidate = Path(install_location) / "SketchUp.exe"
                        if candidate.is_file():
                            return candidate
                except OSError:
                    continue

    # 2. Directory fallback.
    program_files_candidates = [
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramW6432"),
        r"C:\Program Files",
    ]
    for pf in program_files_candidates:
        if not pf:
            continue
        for year in _SKETCHUP_YEARS:
            candidate = Path(pf) / "SketchUp" / f"SketchUp {year}" / "SketchUp.exe"
            if candidate.is_file():
                return candidate

    return None


def invoke_sketchup(
    sketchup_exe: Path,
    run_dir: Path,
    door_lib: Optional[Path] = None,
    output_name: str = "plant.skp",
    timeout: float = 90.0,
    floors: bool = False,
) -> Tuple[int, str, str]:
    """Invoke SketchUp with the Ruby entry point.

    Returns ``(exit_code, stdout, stderr)``. Propagates the SketchUp
    process's own exit code on success or Ruby failure; returns
    ``(124, stdout, stderr)`` on timeout.
    """
    sketchup_exe = Path(sketchup_exe)
    run_dir = Path(run_dir)

    cmd = [
        str(sketchup_exe),
        "-RubyStartup",
        str(_RUBY_ENTRY),
        "--",
        "--run-dir",
        str(run_dir),
        "--output-name",
        output_name,
    ]
    if door_lib is not None:
        cmd.extend(["--door-lib", str(door_lib)])
    if floors:
        cmd.append("--floors")

    logger.debug("invoking SketchUp: %s", cmd)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout or ""
        err = exc.stderr or ""
        if isinstance(out, bytes):
            out = out.decode("utf-8", errors="replace")
        if isinstance(err, bytes):
            err = err.decode("utf-8", errors="replace")
        return 124, out, err

    return result.returncode, result.stdout or "", result.stderr or ""


# F9 constants — must match lib/units.rb. Keep these in sync.
_DRYWALL_PX_THRESHOLD = 2.5


def classify_wall_thicknesses(walls: list) -> dict:
    """Classify each wall into drywall / alvenaria by source-pixel thickness.

    Mirrors ``SkpExport::Units.classify_wall_thicknesses`` in Ruby so
    the dry-run summary matches what SketchUp will emit downstream.
    """
    drywall = 0
    alvenaria = 0
    for w in walls or []:
        t = float(w.get("thickness", 0.0))
        if t < _DRYWALL_PX_THRESHOLD:
            drywall += 1
        else:
            alvenaria += 1
    return {"drywall": drywall, "alvenaria": alvenaria}


def count_candidate_floors(rooms: list) -> int:
    """Count rooms that have a usable polygon for floor materialisation.

    Mirrors ``SkpExport::BuildFloors.count_candidate_floors`` — a room
    only becomes a floor face if its polygon has >= 3 vertices.
    """
    count = 0
    for room in rooms or []:
        poly = room.get("polygon") or room.get("vertices") or []
        if isinstance(poly, list) and len(poly) >= 3:
            count += 1
    return count


def dry_run(run_dir: Path, floors: bool = False) -> dict:
    """Load ``observed_model.json`` from ``run_dir``, return a summary.

    Does not validate the schema. That is the caller's responsibility
    (see :mod:`skp_export.__main__`), which invokes :func:`validate_run`
    before ``dry_run``. This function is intentionally lenient so it can
    also be used on in-progress runs for quick introspection.

    When ``floors`` is True the summary also reports the count of
    candidate floor faces (rooms with polygon >= 3 vertices). When
    False, the ``floors`` field is always 0 so the CLI output is
    deterministic.
    """
    run_dir = Path(run_dir)
    observed_path = run_dir / "observed_model.json"
    if not observed_path.is_file():
        raise FileNotFoundError(f"observed_model.json not found in {run_dir}")

    data = json.loads(observed_path.read_text(encoding="utf-8"))
    walls = data.get("walls", [])
    thickness = classify_wall_thicknesses(walls)
    summary = {
        "run_dir": str(run_dir),
        "schema_version": data.get("schema_version"),
        "walls": len(walls),
        "openings": len(data.get("openings", [])),
        "rooms": len(data.get("rooms", [])),
        "peitoris": len(data.get("peitoris", [])),
        "junctions": len(data.get("junctions", [])),
        "drywall_count": thickness["drywall"],
        "alvenaria_count": thickness["alvenaria"],
        "floors": count_candidate_floors(data.get("rooms", [])) if floors else 0,
        "warnings": list(data.get("warnings", [])),
    }
    return summary
