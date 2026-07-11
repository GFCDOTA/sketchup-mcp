#!/usr/bin/env python3
"""sofa_premium_harness.py — FP-SOFA-PREMIUM itens 2-3: driver do harness SU.

Exporta as parts do sofa premium (build_sofa com a spec acumulada alt_001-005)
pra JSON, lança o SketchUp com sofa_premium_harness.rb (-RubyStartup, padrão
do repo) e espera o DONE. Com --alt006, o .rb aplica o roundover nativo de
25mm nas arestas verticais frontais dos braços (interseção de sólidos).

Uso:
    python -m tools.sofa_premium_harness [--alt006] [--tag baseline]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKETCHUP_EXE = r"C:\Program Files\SketchUp\SketchUp 2026\SketchUp\SketchUp.exe"
RB = ROOT / "tools/sofa_premium_harness.rb"
TEMPLATE = ROOT / "artifacts/planta_74/planta_74.skp"  # so pra abrir o SU; o rb limpa


def premium_spec():
    from tools.sofa_class import derive_living_sofa
    s = derive_living_sofa(2.1)
    s.arm_width = 0.14
    s.arm_height = 0.56
    s.arm_profile = "rounded"
    s.arm_front_recess = 0.07
    s.arm_edge_radius = 0.03
    s.base_style = "plinth"
    s.back_style = "single_crowned"
    s.seat_style = "single_crowned"
    s.base_rail = "recessed_rounded"
    return s


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--alt006", action="store_true")
    ap.add_argument("--tag", default=None)
    args = ap.parse_args()
    tag = args.tag or ("alt006" if args.alt006 else "baseline")

    from tools.sofa_builder import build_sofa
    parts, meta = build_sofa(premium_spec())
    out_dir = ROOT / "runs/sofa_premium/harness"
    out_dir.mkdir(parents=True, exist_ok=True)
    pj = out_dir / f"parts_{tag}.json"
    pj.write_text(json.dumps(parts), "utf-8")

    boot = out_dir / "_bootstrap.skp"
    shutil.copyfile(TEMPLATE, boot)
    out_skp = (out_dir / f"sofa_premium_harness_{tag}.skp").resolve()
    log = out_dir / f"harness_{tag}.log"
    for p in [out_skp, log] + list(out_dir.glob(f"{tag}_*.png")):
        try:
            Path(p).unlink()
        except OSError:
            pass

    env = os.environ.copy()
    env["SOFA_HARNESS_JSON"] = str(pj.resolve())
    env["SOFA_HARNESS_OUT"] = str(out_skp).replace("\\", "/")
    env["SOFA_HARNESS_PNG"] = str((out_dir / tag).resolve()).replace("\\", "/")
    env["SOFA_HARNESS_ALT006"] = "1" if args.alt006 else "0"
    env["SOFA_HARNESS_LOG"] = str(log.resolve()).replace("\\", "/")

    subprocess.run(["taskkill", "/F", "/IM", "SketchUp.exe"], capture_output=True)
    time.sleep(1.5)
    print(f"[harness] launching SU tag={tag} alt006={args.alt006}")
    subprocess.Popen([SKETCHUP_EXE, str(boot), "-RubyStartup", str(RB)], env=env,
                     creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    deadline = time.time() + 300
    while time.time() < deadline:
        if log.exists() and "DONE" in log.read_text("utf-8", errors="ignore"):
            print(f"[harness] DONE — {out_skp.name}")
            print(log.read_text("utf-8", errors="ignore")[-600:])
            return 0
        if log.exists() and "FATAL" in log.read_text("utf-8", errors="ignore"):
            print("[harness] FATAL no rb:")
            print(log.read_text("utf-8", errors="ignore")[-900:])
            return 2
        time.sleep(3)
    print("[harness] TIMEOUT; log parcial:")
    if log.exists():
        print(log.read_text("utf-8", errors="ignore")[-900:])
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
