"""CLI entry point for the skp_export bridge.

Usage::

    python -m skp_export --run-dir runs/proto/p12_v1_run [options]

Modes:

* ``--dry-run`` validates the schema and prints wall/opening/room
  counts without invoking SketchUp. CI-friendly.
* Without ``--dry-run`` the CLI locates SketchUp, shells out with
  ``-RubyStartup`` and blocks until the Ruby side either writes
  ``plant.skp`` or errors out.

Exit codes:

* ``0`` success (dry-run or SketchUp completion)
* ``1`` general error (missing run_dir, IO, etc.)
* ``2`` SketchUp not found on this host (Path B fallback expected)
* ``3`` observed_model.json fails schema validation
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

from . import bridge, validator


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="[skp_export] %(levelname)s %(message)s",
        stream=sys.stderr,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m skp_export",
        description="Convert observed_model.json into a .skp via SketchUp.",
    )
    parser.add_argument(
        "--run-dir",
        required=True,
        type=Path,
        help="Directory that contains observed_model.json.",
    )
    parser.add_argument(
        "--door-lib",
        type=Path,
        default=None,
        help="Optional path to the door .skp component library.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate schema and print counts; do not invoke SketchUp.",
    )
    parser.add_argument(
        "--output-name",
        default="plant.skp",
        help="Name of the output .skp file placed inside --run-dir.",
    )
    parser.add_argument(
        "--sketchup-exe",
        type=Path,
        default=None,
        help="Override the auto-detected SketchUp.exe path.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=90.0,
        help="Timeout in seconds for the SketchUp subprocess (default 90).",
    )
    parser.add_argument(
        "--floors",
        action="store_true",
        help="Also materialise Floor_<room_id> faces per detected room.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable debug logging.",
    )
    return parser


def _print_summary(summary: dict) -> None:
    # Single line, grep-friendly:
    #   walls=N rooms=N openings=N peitoris=N junctions=N
    #   drywall_count=N alvenaria_count=N floors=N
    # F9 appended drywall/alvenaria/floors so downstream tools and
    # humans can see the thickness breakdown + opt-in floor count
    # without having to re-parse observed_model.json.
    line = (
        f"walls={summary['walls']} "
        f"rooms={summary['rooms']} "
        f"openings={summary['openings']} "
        f"peitoris={summary['peitoris']} "
        f"junctions={summary['junctions']} "
        f"drywall_count={summary.get('drywall_count', 0)} "
        f"alvenaria_count={summary.get('alvenaria_count', 0)} "
        f"floors={summary.get('floors', 0)}"
    )
    print(line)


def main(argv: Optional[list] = None) -> int:
    args = _build_parser().parse_args(argv)
    _configure_logging(args.verbose)

    run_dir: Path = args.run_dir
    if not run_dir.is_dir():
        print(f"error: run-dir does not exist: {run_dir}", file=sys.stderr)
        return 1

    observed_path = run_dir / "observed_model.json"
    if not observed_path.is_file():
        print(
            f"error: observed_model.json missing in {run_dir}",
            file=sys.stderr,
        )
        return 1

    # Always validate schema before going further.
    result = validator.validate_run(run_dir)
    if not result.valid:
        print("schema validation failed:", file=sys.stderr)
        for err in result.errors:
            print(f"  - {err}", file=sys.stderr)
        return 3

    # Build + print summary (used by both dry-run and full-run).
    try:
        summary = bridge.dry_run(run_dir, floors=args.floors)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    _print_summary(summary)

    if args.dry_run:
        print("dry-run OK (skipped SketchUp invocation)", file=sys.stderr)
        return 0

    # Path A: invoke SketchUp.
    sketchup_exe: Optional[Path] = args.sketchup_exe or bridge.locate_sketchup()
    if sketchup_exe is None:
        print(
            "warning: SketchUp.exe not found on this host; skipping Ruby invocation. "
            "Re-run with --dry-run in CI or install SketchUp 2021+.",
            file=sys.stderr,
        )
        return 2

    if not Path(sketchup_exe).is_file():
        print(
            f"error: provided --sketchup-exe not a file: {sketchup_exe}",
            file=sys.stderr,
        )
        return 1

    exit_code, stdout, stderr = bridge.invoke_sketchup(
        sketchup_exe=sketchup_exe,
        run_dir=run_dir,
        door_lib=args.door_lib,
        output_name=args.output_name,
        timeout=args.timeout,
        floors=args.floors,
    )
    if stdout:
        sys.stdout.write(stdout)
    if stderr:
        sys.stderr.write(stderr)
    return exit_code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
