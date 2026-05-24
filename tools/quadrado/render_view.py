"""Launch SU on an existing .skp and write a perspective PNG render.

Reuses the autorun_consume.rb plugin mechanism: writes autorun_control.txt
with [dummy_line, output_png_path, render_script_path] then launches SU
with the input .skp as positional. The plugin loads render_view.rb which
sets a camera and calls write_image. SU is terminated after the .done
marker appears.

Used by the quadrado canonical success reference workflow (see
docs/specs/quadrado_demo_spec.md). Promoted from runs/quadrado_demo/
to a versioned location on 2026-05-24 so the success build is
reproducible from a fresh clone.
"""
import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

SKETCHUP_EXE = r"C:\Program Files\SketchUp\SketchUp 2026\SketchUp\SketchUp.exe"
PLUGINS_DIR = Path(os.path.expandvars(
    r"%APPDATA%\SketchUp\SketchUp 2026\SketchUp\Plugins"
))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("skp", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--timeout", type=int, default=90)
    args = ap.parse_args()

    skp = args.skp.resolve()
    out_png = args.out.resolve()
    render_rb = Path(__file__).resolve().with_name("render_view.rb")
    done_marker = out_png.with_name(out_png.name + ".done")

    if not skp.exists():
        print(f"[err] skp missing: {skp}")
        return 1
    if not render_rb.exists():
        print(f"[err] render rb missing: {render_rb}")
        return 1

    for p in (out_png, done_marker):
        if p.exists():
            p.unlink()

    ctrl = PLUGINS_DIR / "autorun_control.txt"
    ctrl.write_text("\n".join([
        "ignored",
        str(out_png).replace("\\", "/"),
        str(render_rb).replace("\\", "/"),
    ]), encoding="utf-8")

    cmd = [SKETCHUP_EXE, str(skp)]
    print(f"[run] {' '.join(cmd)}")
    proc = subprocess.Popen(
        cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "DETACHED_PROCESS", 0),
    )

    deadline = time.time() + args.timeout
    try:
        while time.time() < deadline:
            if done_marker.exists() and out_png.exists():
                time.sleep(2)
                print(f"[ok] {out_png} ({out_png.stat().st_size} bytes)")
                try:
                    proc.terminate()
                except Exception:
                    pass
                return 0
            if proc.poll() is not None:
                print(f"[err] SU exited prematurely code={proc.returncode}")
                return 2
            time.sleep(1)
        print("[err] timeout")
        try:
            proc.terminate()
            time.sleep(2)
            proc.kill()
        except Exception:
            pass
        return 3
    finally:
        if ctrl.exists():
            ctrl.unlink()


if __name__ == "__main__":
    sys.exit(main())
