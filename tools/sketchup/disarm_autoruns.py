"""Remove every ``*_control.txt`` file from SketchUp's Plugins folder.

Any of our autorun plugins (``autorun_consume.rb``,
``autorun_inspector.rb``, …) becomes a no-op when its companion
control file is absent. Leaving a control file behind after a
batch run is a footgun: every subsequent SU launch — including
the user double-clicking a ``.skp`` to look at it — fires the
autorun against stale paths, which can ``model.entities.clear!``,
``model.save`` over the file the user just opened, or even call
``Sketchup.quit`` (this happened in 2026-05-20). See
``docs/learning/failure_patterns.md`` §"autorun_control_files".

This module exposes:

* ``disarm(plugins_dir, *, dry_run=False)`` — library entrypoint.
  Returns the list of paths that were removed (or would be, with
  ``dry_run=True``). Safe to call when the directory is missing
  or has no control files (returns ``[]``).
* ``python -m tools.disarm_sketchup_autoruns`` — CLI. Prints what
  it does. Supports ``--dry-run`` and ``--plugins <path>``.

Launchers (``skp_from_consensus.py``, ``build_room_ring_skp.py``)
should call ``disarm(plugins_dir)`` BEFORE every SU launch as
defence-in-depth on top of their own try/finally cleanup.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import List

PLUGINS_DIR_DEFAULT = Path(os.path.expandvars(
    r"%APPDATA%\SketchUp\SketchUp 2026\SketchUp\Plugins"
))

# Glob pattern that matches every autorun control file we know
# about today (``autorun_control.txt``, ``autorun_inspector_control.txt``,
# any future ``autorun_<thing>_control.txt``). The trailing literal
# ``_control.txt`` and ``control.txt`` are both covered.
CONTROL_GLOB = "*control.txt"


def disarm(plugins_dir: Path = PLUGINS_DIR_DEFAULT,
           *, dry_run: bool = False) -> List[Path]:
    """Remove every ``*control.txt`` in ``plugins_dir``.

    Returns the list of paths affected (removed, or — with
    ``dry_run=True`` — listed but kept).

    Never raises for a missing directory or read-only file: a
    cleanup helper that fails noisily is worse than one that
    quietly leaves a single stubborn file behind. Hard errors
    are still propagated for unexpected ``OSError`` kinds.
    """
    if not plugins_dir.exists():
        return []
    removed: List[Path] = []
    for p in sorted(plugins_dir.glob(CONTROL_GLOB)):
        if not p.is_file():
            continue
        if dry_run:
            removed.append(p)
            continue
        try:
            p.unlink()
            removed.append(p)
        except FileNotFoundError:
            # Race: someone else cleaned it up between glob and unlink.
            pass
        except PermissionError as e:
            # Leave a breadcrumb but keep going — the user can rm by hand.
            print(f"[warn] could not remove {p}: {e}", file=sys.stderr)
    return removed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Disarm SketchUp autorun control files."
    )
    ap.add_argument(
        "--plugins", type=Path, default=PLUGINS_DIR_DEFAULT,
        help=f"SketchUp Plugins dir (default: {PLUGINS_DIR_DEFAULT})",
    )
    ap.add_argument(
        "--dry-run", action="store_true",
        help="List matching files without deleting them.",
    )
    args = ap.parse_args(argv)
    affected = disarm(args.plugins, dry_run=args.dry_run)
    if not affected:
        print(f"[disarm] no control files in {args.plugins}")
        return 0
    verb = "would remove" if args.dry_run else "removed"
    for p in affected:
        print(f"[disarm] {verb} {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
