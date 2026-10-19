"""Launch SU on an existing .skp and write a perspective PNG render.

Runs in OUR OWN SketchUp process: `SketchUp.exe <model.skp> -RubyStartup
tools/sketchup/ruby/skmcp_launch.rb`, which loads render_view.rb (camera + write_image) with the
output path in `SKP_OUT`. It no longer writes autorun_control.txt into the user's global Plugins
folder (any other SketchUp opened meanwhile would have run it). SU is terminated after the .done
marker appears — only the process we started.

Used by the quadrado canonical success reference workflow (see
docs/specs/quadrado_demo_spec.md). Promoted from runs/quadrado_demo/
to a versioned location on 2026-05-24 so the success build is
reproducible from a fresh clone.
"""
import argparse
import os
import sys
import time
from pathlib import Path


def _repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").exists():
            return parent
    raise RuntimeError("raiz do repositório não encontrada")


sys.path.insert(0, str(_repo_root()))
from tools.sketchup.batch import LAUNCHER, launch_env  # noqa: E402
from tools.sketchup.process import spawn_detached  # noqa: E402

SKETCHUP_EXE = r"C:\Program Files\SketchUp\SketchUp 2026\SketchUp\SketchUp.exe"


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
    launch_error = out_png.with_name(out_png.name + ".launch_error.txt")

    if not skp.exists():
        print(f"[err] skp missing: {skp}")
        return 1
    if not render_rb.exists():
        print(f"[err] render rb missing: {render_rb}")
        return 1

    for p in (out_png, done_marker, launch_error):
        if p.exists():
            p.unlink()

    env = os.environ.copy()
    env.update(launch_env(render_rb, launch_error))
    env["SKP_OUT"] = str(out_png).replace("\\", "/")
    cmd = [SKETCHUP_EXE, str(skp), "-RubyStartup", str(LAUNCHER)]
    print(f"[run] {' '.join(cmd)}")
    proc = spawn_detached(cmd, env)

    deadline = time.time() + args.timeout
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
            if launch_error.exists():
                print(launch_error.read_text(encoding="utf-8", errors="replace"))
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


if __name__ == "__main__":
    sys.exit(main())
