"""T0.2 preparatory: pure fail-closed plan for SketchUp inspection scratch.

No executor is changed here: integration with cabinet.inspect would invalidate
its L2 proof and therefore requires a fresh Windows SketchUp L2 before merge.
"""
from __future__ import annotations

import hashlib
import re
import secrets
import time
from pathlib import Path

from tools.sketchup import paths

_ALLOWED = {"cabinet_inspect", "shaker_inspect"}
_STAMP = re.compile(r"^[A-Za-z0-9_-]{3,80}$")


def plan_inspect_workspace(
    source: str | Path, *, job: str,
    repo: Path | None = None, stamp: str | None = None
) -> dict:
    """Return paths under runs/, never beside source SKP, without creating files."""
    root = Path(repo if repo is not None else paths.REPO_ROOT).resolve()
    src = paths.resolve(source, repo=root)
    if job not in _ALLOWED:
        raise ValueError(f"unsupported inspection job: {job}")
    if src.suffix.lower() != ".skp" or not src.is_file():
        raise ValueError(f"source must be an existing .skp file: {src}")
    run_id = stamp if stamp is not None else time.strftime("%Y%m%d_%H%M%S") + "_" + secrets.token_hex(6)
    if not _STAMP.fullmatch(run_id):
        raise ValueError("invalid run stamp")
    fingerprint = hashlib.sha256(str(src).encode("utf-8")).hexdigest()[:12]
    folder = paths.default_out_dir(job, repo=root, stamp=run_id) / f"{src.stem}_{fingerprint}"
    copy = paths.check_output(folder / f"_copy_{src.name}", inputs=(src,), repo=root)
    if not copy.is_relative_to(root / "runs"):
        raise ValueError("inspection workspace escaped runs/")
    return {"job": job, "source": src, "job_dir": copy.parent, "copy_skp": copy,
            "execution_authorized": False}
