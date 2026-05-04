"""Generate a SketchUp .skp from a consensus_model.json.

Workflow: render the consume_consensus.rb template with the user-
provided paths, write a temp .rb, launch SketchUp 2026 with
-RubyStartup pointing at the temp file. The Ruby script builds the
3D model in SketchUp and saves the .skp, then quits.

We poll for the .skp and time out the process; SketchUp's GUI runs
even with a Ruby script, so the script's own ``Sketchup.quit`` call
is what shuts it down cleanly.

Skip-on-unchanged-consensus
---------------------------

Per the perf baseline (`docs/performance/current_perf_baseline.md`),
the SU launch + autorun + save costs ~8 seconds and dominates the
pipeline (~91% of wall-clock). When the consensus has not changed,
re-running this step is pure waste.

`run()` writes a sidecar metadata file alongside the .skp:

    out_skp.parent / (out_skp.name + ".metadata.json")

with `consensus_sha256`, `skp_path`, `created_at`, `git_commit`,
`sketchup_path`, and `command`. On the next call, if the sidecar
exists, the .skp exists, and the consensus hash matches, `run()`
returns immediately without launching SU. Pass `force_skp=True`
(or `--force-skp` from the CLI) to bypass.

Return shape: a dict ``{"ok": bool, "skipped": bool, "skp_path":
str, "consensus_sha256": str | None, "elapsed_s": float}``.
Existing callers that read the value as boolean still see truthy
on success because a non-empty dict is truthy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SKETCHUP_EXE_DEFAULT = (
    r"C:\Program Files\SketchUp\SketchUp 2026\SketchUp\SketchUp.exe"
)
PLUGINS_DIR_DEFAULT = Path(os.path.expandvars(
    r"%APPDATA%\SketchUp\SketchUp 2026\SketchUp\Plugins"
))
RUBY_TEMPLATE = Path(__file__).resolve().parent / "consume_consensus.rb"
CONTROL_FILE = "autorun_control.txt"
METADATA_SUFFIX = ".metadata.json"


def write_control(plugins_dir: Path, consensus: Path, out_skp: Path) -> None:
    """The autorun_consume.rb plugin reads this file on startup."""
    plugins_dir.mkdir(parents=True, exist_ok=True)
    txt = "\n".join([
        str(consensus.resolve()).replace("\\", "/"),
        str(out_skp.resolve()).replace("\\", "/"),
        str(RUBY_TEMPLATE.resolve()).replace("\\", "/"),
    ])
    (plugins_dir / CONTROL_FILE).write_text(txt, encoding="utf-8")


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parent.parent,
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return "unknown"


def metadata_path(out_skp: Path) -> Path:
    """Path of the sidecar metadata file for a given .skp."""
    return out_skp.with_name(out_skp.name + METADATA_SUFFIX)


def read_metadata(out_skp: Path) -> dict[str, Any] | None:
    """Read the sidecar metadata. Returns None if missing or unparseable."""
    p = metadata_path(out_skp)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def write_metadata(out_skp: Path, *, consensus_sha256: str,
                   sketchup_exe: Path, command: list[str]) -> Path:
    """Write the sidecar metadata next to the .skp. Returns the path written."""
    p = metadata_path(out_skp)
    data = {
        "schema_version": "1.0.0",
        "consensus_sha256": consensus_sha256,
        "skp_path": str(out_skp),
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_commit": _git_commit(),
        "sketchup_path": str(sketchup_exe),
        "command": " ".join(command),
    }
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return p


def should_skip(out_skp: Path, consensus_sha256: str) -> bool:
    """Decide whether to skip the SU launch.

    True iff: out_skp exists, sidecar metadata exists, and its
    consensus_sha256 matches. Caller is responsible for honoring
    `force_skp` BEFORE calling this — we don't take that flag here
    so the helper stays trivially testable.
    """
    if not out_skp.exists():
        return False
    meta = read_metadata(out_skp)
    if not meta:
        return False
    return meta.get("consensus_sha256") == consensus_sha256


def run(consensus: Path, out_skp: Path, sketchup_exe: Path,
        plugins_dir: Path = PLUGINS_DIR_DEFAULT,
        timeout_s: int = 90,
        bootstrap_skp: Path | None = None,
        force_skp: bool = False) -> dict[str, Any]:
    """Build a .skp from a consensus JSON. Returns a result dict.

    If a sidecar metadata file at ``<out_skp>.metadata.json`` exists
    and its ``consensus_sha256`` matches the current consensus,
    skip the SU launch and return immediately (unless `force_skp`).
    """
    started = time.time()
    consensus_sha = _file_sha256(consensus) if consensus.exists() else None

    # ---- skip path: re-use unchanged .skp ----
    if (
        not force_skp
        and consensus_sha is not None
        and should_skip(out_skp, consensus_sha)
    ):
        elapsed = time.time() - started
        print(f"[skip] {out_skp} unchanged consensus "
              f"(sha {consensus_sha[:12]}); skipped SU launch")
        return {
            "ok": True,
            "skipped": True,
            "skp_path": str(out_skp),
            "consensus_sha256": consensus_sha,
            "elapsed_s": round(elapsed, 4),
        }

    # ---- normal export path ----
    out_skp.parent.mkdir(parents=True, exist_ok=True)
    if out_skp.exists():
        out_skp.unlink()
    # Stale metadata must be cleared too — otherwise a failed export
    # could leave a sidecar that points at a missing or wrong .skp.
    meta_p = metadata_path(out_skp)
    if meta_p.exists():
        meta_p.unlink()

    write_control(plugins_dir, consensus, out_skp)
    err_file = plugins_dir / "autorun_error.txt"
    if err_file.exists():
        err_file.unlink()

    # SU2026 trial shows a Welcome dialog when launched without a
    # positional .skp, blocking the autorun plugin from ever firing
    # (FP-007 / LL-009). Pass any existing .skp positional to skip
    # it. If no .skp is present in `out_skp.parent`, copy a template
    # from the SU 2026 install as `_bootstrap.skp`.
    if bootstrap_skp is None:
        candidates = sorted(
            (p for p in out_skp.parent.glob("*.skp") if p != out_skp),
            key=lambda p: -p.stat().st_mtime,
        )
        if candidates:
            bootstrap_skp = candidates[0]
        else:
            template_dir = Path(
                r"C:\Program Files\SketchUp\SketchUp 2026\SketchUp"
                r"\resources\en-US\Templates"
            )
            for name in ("Temp01a - Simple.skp", "Temp01b - Simple.skp"):
                t = template_dir / name
                if t.exists():
                    bootstrap_target = out_skp.parent / "_bootstrap.skp"
                    if not bootstrap_target.exists():
                        shutil.copy2(t, bootstrap_target)
                    bootstrap_skp = bootstrap_target
                    break

    cmd = [str(sketchup_exe)]
    if bootstrap_skp and bootstrap_skp.exists():
        cmd.append(str(bootstrap_skp))
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
            elapsed = time.time() - started
            if consensus_sha is not None:
                write_metadata(
                    out_skp,
                    consensus_sha256=consensus_sha,
                    sketchup_exe=sketchup_exe,
                    command=cmd,
                )
            return {
                "ok": True,
                "skipped": False,
                "skp_path": str(out_skp),
                "consensus_sha256": consensus_sha,
                "elapsed_s": round(elapsed, 4),
            }
        if proc.poll() is not None:
            print(f"[err] SketchUp exited prematurely (code={proc.returncode})")
            return {
                "ok": False,
                "skipped": False,
                "skp_path": str(out_skp),
                "consensus_sha256": consensus_sha,
                "elapsed_s": round(time.time() - started, 4),
            }
        time.sleep(1)
    print(f"[err] timeout after {timeout_s}s waiting for {out_skp}")
    try:
        proc.terminate()
        time.sleep(2)
        proc.kill()
    except Exception:
        pass
    return {
        "ok": False,
        "skipped": False,
        "skp_path": str(out_skp),
        "consensus_sha256": consensus_sha,
        "elapsed_s": round(time.time() - started, 4),
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("consensus", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--sketchup", type=Path,
                    default=Path(SKETCHUP_EXE_DEFAULT))
    ap.add_argument("--plugins", type=Path, default=PLUGINS_DIR_DEFAULT)
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--force-skp", action="store_true",
                    help="bypass the consensus-hash skip, always launch SU")
    args = ap.parse_args()
    result = run(
        args.consensus.resolve(), args.out.resolve(),
        args.sketchup, args.plugins, args.timeout,
        force_skp=args.force_skp,
    )
    if result["skipped"]:
        sys.stdout.write(
            f"SKIPPED_UNCHANGED_CONSENSUS sha={result['consensus_sha256'][:12]}\n"
        )
    raise SystemExit(0 if result["ok"] else 1)
