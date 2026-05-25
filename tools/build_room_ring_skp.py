"""Launcher for build_room_ring_skp.rb.

Reuses the autorun_consume.rb plugin already installed in SU 2026
plugins dir — only line 3 of autorun_control.txt changes, pointing
at build_room_ring_skp.rb instead of consume_consensus.rb.

This launcher is intentionally minimal and SEPARATE from
tools/skp_from_consensus.py so that the production exporter
(consume_consensus.rb) is untouched.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import time
from pathlib import Path

from tools.disarm_sketchup_autoruns import disarm as disarm_autoruns

SKETCHUP_EXE_DEFAULT = (
    r"C:\Program Files\SketchUp\SketchUp 2026\SketchUp\SketchUp.exe"
)
PLUGINS_DIR_DEFAULT = Path(os.path.expandvars(
    r"%APPDATA%\SketchUp\SketchUp 2026\SketchUp\Plugins"
))
RUBY_TEMPLATE = Path(__file__).resolve().parent / "build_room_ring_skp.rb"
CONTROL_FILE = "autorun_control.txt"


def write_control(plugins_dir: Path, consensus: Path, out_skp: Path) -> None:
    plugins_dir.mkdir(parents=True, exist_ok=True)
    txt = "\n".join([
        str(consensus.resolve()).replace("\\", "/"),
        str(out_skp.resolve()).replace("\\", "/"),
        str(RUBY_TEMPLATE.resolve()).replace("\\", "/"),
    ])
    (plugins_dir / CONTROL_FILE).write_text(txt, encoding="utf-8")


def find_bootstrap(out_skp: Path) -> Path | None:
    # Same trick as skp_from_consensus.py: SU 2026 trial shows a Welcome
    # dialog without a positional .skp, blocking the autorun plugin.
    candidates = sorted(
        (p for p in out_skp.parent.glob("*.skp") if p != out_skp),
        key=lambda p: -p.stat().st_mtime,
    )
    if candidates:
        return candidates[0]
    template_dir = Path(
        r"C:\Program Files\SketchUp\SketchUp 2026\SketchUp"
        r"\resources\en-US\Templates"
    )
    for name in ("Temp01a - Simple.skp", "Temp01b - Simple.skp"):
        t = template_dir / name
        if t.exists():
            bootstrap = out_skp.parent / "_bootstrap.skp"
            if not bootstrap.exists():
                shutil.copy2(t, bootstrap)
            return bootstrap
    return None


def run(consensus: Path, out_skp: Path, sketchup_exe: Path,
        plugins_dir: Path = PLUGINS_DIR_DEFAULT,
        timeout_s: int = 120,
        out_png: Path | None = None,
        out_report: Path | None = None) -> bool:
    out_skp.parent.mkdir(parents=True, exist_ok=True)
    # Default derivations match what the Ruby script does when ENV is unset.
    if out_png is None:
        out_png = out_skp.with_suffix(".png")
    if out_report is None:
        out_report = out_skp.with_name(
            out_skp.stem + "_geometry_report.json"
        )
    # Clean any stale outputs so we don't read a previous run.
    for p in (out_skp, out_png, out_report,
              out_skp.with_name(out_skp.name + ".metadata.json")):
        if p.exists():
            p.unlink()

    # Defence-in-depth: clear any orphan autorun control file before
    # we arm our own (see docs/learning/failure_patterns.md).
    for p in disarm_autoruns(plugins_dir):
        print(f"[pre-launch disarm] removed orphan {p.name}")

    write_control(plugins_dir, consensus, out_skp)
    err_file = plugins_dir / "autorun_error.txt"
    if err_file.exists():
        err_file.unlink()

    bootstrap = find_bootstrap(out_skp)
    cmd = [str(sketchup_exe)]
    if bootstrap:
        cmd.append(str(bootstrap))
    # Pass PNG_OUT and REPORT_OUT via the child environment. SU on
    # Windows inherits the launching process's env, and our Ruby
    # script reads ENV['PNG_OUT'] / ENV['REPORT_OUT'] with fallbacks.
    env = os.environ.copy()
    env["PNG_OUT"] = str(out_png.resolve()).replace("\\", "/")
    env["REPORT_OUT"] = str(out_report.resolve()).replace("\\", "/")
    print(f"[run] launching SU: {' '.join(cmd)}")
    print(f"[run]   PNG_OUT={env['PNG_OUT']}")
    print(f"[run]   REPORT_OUT={env['REPORT_OUT']}")
    proc = subprocess.Popen(
        cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "DETACHED_PROCESS", 0),
        env=env,
    )

    try:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if out_skp.exists():
                time.sleep(2)  # flush
                print(f"[ok] {out_skp} ({out_skp.stat().st_size} bytes)")
                try:
                    proc.terminate()
                except Exception:
                    pass
                return True
            if proc.poll() is not None:
                print(f"[err] SU exited prematurely code={proc.returncode}")
                if err_file.exists():
                    print("---- ruby error ----")
                    print(err_file.read_text(encoding='utf-8', errors='replace'))
                return False
            time.sleep(1)
        print(f"[err] timeout after {timeout_s}s")
        if err_file.exists():
            print("---- ruby error ----")
            print(err_file.read_text(encoding='utf-8', errors='replace'))
        try:
            proc.terminate()
            time.sleep(2)
            proc.kill()
        except Exception:
            pass
        return False
    finally:
        # ALWAYS disarm every autorun control file on the way out
        # (success / exit / timeout). Delegated to disarm_autoruns so
        # we also clear orphans from sibling launchers — not just the
        # autorun_control.txt our own write_control wrote.
        for p in disarm_autoruns(plugins_dir):
            print(f"[post-run disarm] removed {p.name}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("consensus", type=Path)
    ap.add_argument("--out", type=Path, required=True,
                    help="output .skp path")
    ap.add_argument("--out-png", type=Path, default=None,
                    help="output PNG path (default: <out>.png)")
    ap.add_argument("--out-report", type=Path, default=None,
                    help="output geometry_report.json path "
                         "(default: <out_stem>_geometry_report.json)")
    ap.add_argument("--sketchup", type=Path,
                    default=Path(SKETCHUP_EXE_DEFAULT))
    ap.add_argument("--plugins", type=Path, default=PLUGINS_DIR_DEFAULT)
    ap.add_argument("--timeout", type=int, default=120)
    args = ap.parse_args()
    ok = run(
        args.consensus.resolve(),
        args.out.resolve(),
        args.sketchup,
        args.plugins,
        args.timeout,
        out_png=args.out_png.resolve() if args.out_png else None,
        out_report=args.out_report.resolve() if args.out_report else None,
    )
    raise SystemExit(0 if ok else 1)
