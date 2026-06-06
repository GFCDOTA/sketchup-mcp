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

# src name -> stable deliverable name. The top render's .proj.json sidecar is
# part of the deliverable: the deterministic wall_presence gate (overlay_diff)
# only runs when <render>.proj.json sits next to the render. Drop it and the
# gate self-skips, so the canonical ships unverified for wall presence.
_MAP = {
    "model.skp": "{plant}.skp",
    "model_iso.png": "{plant}_iso.png",
    "model_top.png": "{plant}_top.png",
    "model_top.png.proj.json": "{plant}_top.png.proj.json",
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
    # Carry the build sidecar (consensus_sha256 = cache key, build stats) and
    # rewrite the path fields to the canonical location — the artifact_policy
    # "promotion gotcha": the canonical sidecar must point at artifacts/, not
    # the runs/ build path, and must keep the consensus SHA.
    carried = {}
    src_sidecar = src_final / "model.skp.metadata.json"
    if src_sidecar.is_file():
        try:
            carried = json.loads(src_sidecar.read_text("utf-8"))
        except Exception:
            carried = {}
    meta = {
        **carried,
        "plant": plant,
        "stable_path": f"artifacts/{plant}/{plant}.skp",
        "skp_path": f"artifacts/{plant}/{plant}.skp",
        "source_run_path": carried.get("skp_path") or str(src_final / "model.skp"),
        "promoted_from": prov,
        "skp_sha256": sha,
        "skp_bytes": skp.stat().st_size,
        "files": copied,
        "note": "latest correct build at a fixed path; refresh via "
                "tools/promote_canonical.py or build_plan_shell_skp --promote",
    }
    (dst / f"{plant}.skp.metadata.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    # MUST (Felipe 2026-06-03): todo canonical promovido tem regression_summary, pra a
    # aba #planta NUNCA mostrar verdict UNKNOWN depois de gerar um novo SKP. O veredito
    # visual (IMPROVED/SAME/WORSE) e do Felipe; aqui so garantimos o arquivo existir, com
    # um provisorio WARN (= aguardando VISUAL_REVIEW) — sem sobrescrever um ja gravado.
    rs = dst / "regression_summary.md"
    if not rs.exists():
        rs.write_text(
            f"# Regression Summary — {plant}\n\n"
            f"Verdict: WARN\n\n"
            f"SKP promovido de `{prov}` (sha {sha[:12]}).\n"
            f"Verdict provisorio **WARN** = aguardando VISUAL_REVIEW do Felipe "
            f"(PDF × ANTES × AGORA). Ao aprovar, troque para `Verdict: IMPROVED`.\n",
            encoding="utf-8")
        copied.append("regression_summary.md")
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
