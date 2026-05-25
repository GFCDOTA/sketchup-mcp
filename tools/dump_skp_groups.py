"""Open an existing .skp (or .skb) in SU 2026 and dump its top-level
Groups to JSON without modifying the file.

Used for diffing two .skp files — e.g., a .skb (backup, BEFORE the
user's edit) vs the current .skp (AFTER) — to identify which Groups
the user removed in SketchUp.

The script does NOT touch the input file: it copies the input to a
temp .skp (if extension is .skb), opens SU with the temp as
positional arg, runs `tools/dump_skp_groups.rb` via the autorun
plugin to emit JSON, then deletes the temp.
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
RUBY_DUMP = Path(__file__).resolve().parent / "dump_skp_groups.rb"
CONTROL_FILE = "autorun_control.txt"


def write_control(plugins_dir: Path, skp_path: Path,
                  out_json: Path) -> None:
    # autorun_consume.rb reads 3 lines; we only need line 2 (SKP_OUT
    # — reused here as the dump destination) and line 3 (the script
    # to load). Line 1 (CONSENSUS_JSON) is set to the .skp itself
    # just so the cfg.length >= 3 guard passes; the dump script
    # ignores it.
    plugins_dir.mkdir(parents=True, exist_ok=True)
    txt = "\n".join([
        str(skp_path.resolve()).replace("\\", "/"),
        str(out_json.resolve()).replace("\\", "/"),
        str(RUBY_DUMP.resolve()).replace("\\", "/"),
    ])
    (plugins_dir / CONTROL_FILE).write_text(txt, encoding="utf-8")


def run(skp_path: Path, out_json: Path, *,
        sketchup_exe: Path = Path(SKETCHUP_EXE_DEFAULT),
        plugins_dir: Path = PLUGINS_DIR_DEFAULT,
        timeout_s: int = 90) -> bool:
    # SU 2026 only opens .skp from the positional CLI arg. Rename
    # .skb (or any other extension) to a temp .skp so the open
    # succeeds. Deleted on exit.
    started = time.time()
    tmp_skp: Path | None = None
    actual_skp = skp_path
    if skp_path.suffix.lower() != ".skp":
        tmp_skp = skp_path.with_name(skp_path.stem + ".__dump_tmp__.skp")
        shutil.copy2(skp_path, tmp_skp)
        actual_skp = tmp_skp
        print(f"[dump] copied {skp_path.name} -> {tmp_skp.name}")

    if out_json.exists():
        out_json.unlink()

    # Defence-in-depth: clear orphan autorun control files from a
    # prior crashed run before we arm our own.
    for p in disarm_autoruns(plugins_dir):
        print(f"[pre-launch disarm] removed orphan {p.name}")
    write_control(plugins_dir, actual_skp, out_json)

    cmd = [str(sketchup_exe), str(actual_skp)]
    print(f"[run] launching SU: {cmd[0]} {actual_skp.name}")
    proc = subprocess.Popen(
        cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "DETACHED_PROCESS", 0),
    )

    try:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if out_json.exists():
                time.sleep(1)
                try:
                    proc.terminate()
                except Exception:  # noqa: BLE001
                    pass
                elapsed = time.time() - started
                print(f"[ok] {out_json} ({out_json.stat().st_size} bytes) "
                      f"in {elapsed:.1f}s")
                return True
            if proc.poll() is not None:
                err_file = plugins_dir / "autorun_error.txt"
                if err_file.exists():
                    print(err_file.read_text(
                        encoding="utf-8", errors="replace"
                    ))
                return False
            time.sleep(1)
        print(f"[err] timeout {timeout_s}s")
        try:
            proc.terminate()
            time.sleep(1)
            proc.kill()
        except Exception:  # noqa: BLE001
            pass
        return False
    finally:
        for p in disarm_autoruns(plugins_dir):
            print(f"[post-run disarm] removed {p.name}")
        # Clean up the temp .skp if we created one.
        if tmp_skp and tmp_skp.exists():
            try:
                tmp_skp.unlink()
                print(f"[dump] removed temp {tmp_skp.name}")
            except OSError as e:
                print(f"[warn] could not remove {tmp_skp}: {e}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("skp", type=Path, help="input .skp or .skb file")
    ap.add_argument("--out", type=Path, required=True,
                    help="output JSON path")
    ap.add_argument("--sketchup", type=Path,
                    default=Path(SKETCHUP_EXE_DEFAULT))
    ap.add_argument("--plugins", type=Path, default=PLUGINS_DIR_DEFAULT)
    ap.add_argument("--timeout", type=int, default=90)
    args = ap.parse_args()
    ok = run(args.skp.resolve(), args.out.resolve(),
             sketchup_exe=args.sketchup,
             plugins_dir=args.plugins,
             timeout_s=args.timeout)
    raise SystemExit(0 if ok else 1)
