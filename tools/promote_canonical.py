#!/usr/bin/env python3
"""Promote a blessed build to the STABLE deliverable path artifacts/<plant>/.

The "current correct plant" should live at ONE predictable path — no timestamp
hunting through artifacts/review/<plant>/<ts>/final/. This copies a blessed
build's .skp + renders + report into artifacts/<plant>/ with fixed names, and
writes a metadata sidecar (sha + provenance), so:

    artifacts/<plant>/<plant>.skp        <- ALWAYS the latest blessed build

Usage:
    python -m tools.promote_canonical --src artifacts/review/planta_74/canonical_20260531/final
    python -m tools.promote_canonical --src runs/planta_74/glassfix --plant planta_74

Blessing (visual IMPROVED) stays Felipe's call — this only COPIES an
already-approved build to the stable path; it never builds or judges.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# src name -> stable deliverable name
_MAP = {
    "model.skp": "{plant}.skp",
    "model_iso.png": "{plant}_iso.png",
    "model_top.png": "{plant}_top.png",
    "geometry_report.json": "geometry_report.json",
}


def promote(src_final: Path, plant: str, repo: Path = REPO) -> dict:
    src_final = Path(src_final)
    if not src_final.is_dir():
        raise NotADirectoryError(f"src not a dir: {src_final}")
    skp_src = src_final / "model.skp"
    if not skp_src.is_file():
        raise FileNotFoundError(f"no model.skp in {src_final}")
    dst = repo / "artifacts" / plant
    dst.mkdir(parents=True, exist_ok=True)

    copied = []
    for s, d_tmpl in _MAP.items():
        sp = src_final / s
        if sp.is_file():
            d = d_tmpl.format(plant=plant)
            shutil.copy2(sp, dst / d)
            copied.append(d)

    skp = dst / f"{plant}.skp"
    sha = hashlib.sha256(skp.read_bytes()).hexdigest()
    try:
        prov = str(src_final.resolve().relative_to(repo.resolve()))
    except ValueError:
        prov = str(src_final)
    meta = {
        "plant": plant,
        "stable_path": f"artifacts/{plant}/{plant}.skp",
        "promoted_from": prov,
        "skp_sha256": sha,
        "skp_bytes": skp.stat().st_size,
        "files": copied,
        "note": "latest blessed build; promote via tools/promote_canonical.py",
    }
    (dst / f"{plant}.skp.metadata.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return {"dst": str(dst.relative_to(repo)), "copied": copied, "sha": sha[:12]}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="promote blessed build -> stable deliverable")
    ap.add_argument("--src", required=True,
                    help="build dir containing model.skp (a .../final or runs/<x>)")
    ap.add_argument("--plant", default="planta_74")
    a = ap.parse_args()
    res = promote(Path(a.src), a.plant)
    print(f"[promote] -> {res['dst']}/{a.plant}.skp  sha={res['sha']}  "
          f"files={res['copied']}")
