"""Generate a SketchUp .skp from a consensus_model.json.

Workflow: render the consume_consensus.rb template with the user-
provided paths, write a temp .rb, launch SketchUp 2026 with
-RubyStartup pointing at the temp file. The Ruby script builds the
3D model in SketchUp and saves the .skp, then quits.

We poll for the .skp and time out the process; SketchUp's GUI runs
even with a Ruby script, so the script's own ``Sketchup.quit`` call
is what shuts it down cleanly.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import time
from pathlib import Path


SKETCHUP_EXE_DEFAULT = (
    r"C:\Program Files\SketchUp\SketchUp 2026\SketchUp\SketchUp.exe"
)
PLUGINS_DIR_DEFAULT = Path(os.path.expandvars(
    r"%APPDATA%\SketchUp\SketchUp 2026\SketchUp\Plugins"
))
RUBY_TEMPLATE = Path(__file__).resolve().parent / "consume_consensus.rb"
CONTROL_FILE = "autorun_control.txt"


def write_control(plugins_dir: Path, consensus: Path, out_skp: Path) -> None:
    """The autorun_consume.rb plugin reads this file on startup."""
    plugins_dir.mkdir(parents=True, exist_ok=True)
    txt = "\n".join([
        str(consensus.resolve()).replace("\\", "/"),
        str(out_skp.resolve()).replace("\\", "/"),
        str(RUBY_TEMPLATE.resolve()).replace("\\", "/"),
    ])
    (plugins_dir / CONTROL_FILE).write_text(txt, encoding="utf-8")


def run(consensus: Path, out_skp: Path, sketchup_exe: Path,
        plugins_dir: Path = PLUGINS_DIR_DEFAULT,
        timeout_s: int = 90) -> bool:
    out_skp.parent.mkdir(parents=True, exist_ok=True)
    if out_skp.exists():
        out_skp.unlink()
    write_control(plugins_dir, consensus, out_skp)
    err_file = plugins_dir / "autorun_error.txt"
    if err_file.exists():
        err_file.unlink()

    cmd = [str(sketchup_exe)]
    print(f"[run] launching SU: {' '.join(cmd)}")
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if out_skp.exists():
            # Wait a couple more seconds for the file write to flush
            time.sleep(2)
            print(f"[ok] {out_skp} ({out_skp.stat().st_size} bytes)")
            try:
                proc.terminate()
            except Exception:
                pass
            return True
        if proc.poll() is not None:
            print(f"[err] SketchUp exited prematurely (code={proc.returncode})")
            return False
        time.sleep(1)
    print(f"[err] timeout after {timeout_s}s waiting for {out_skp}")
    try:
        proc.terminate()
        time.sleep(2)
        proc.kill()
    except Exception:
        pass
    return False


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("consensus", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--sketchup", type=Path,
                    default=Path(SKETCHUP_EXE_DEFAULT))
    ap.add_argument("--plugins", type=Path, default=PLUGINS_DIR_DEFAULT)
    ap.add_argument("--timeout", type=int, default=120)
    args = ap.parse_args()
    ok = run(args.consensus.resolve(), args.out.resolve(),
             args.sketchup, args.plugins, args.timeout)
    raise SystemExit(0 if ok else 1)
