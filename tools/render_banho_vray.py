"""render_banho_vray.py — V-Ray dos BANHOS da planta_74 mobiliada (Estudio
Banheiro). Copia o furnished.skp, exporta .vrscene com camera custom (inches),
aplica o theme estudio_banho (_ph_*) + fills e renderiza com vray.exe.

Uso: python -m tools.render_banho_vray --eye x,y,z --target x,y,z --out png
     [--fov 55 --iso 160 --fnum 5.6 --shutter 56 --sky 0.3 --width 1100
      --height 1375 --fill "x,y,z,int[,raio_in];..."  (tudo em INCHES)]
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
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.tweak_vrscene import tweak_file          # noqa: E402

SU_EXE = Path(r"C:\Program Files\SketchUp\SketchUp 2026\SketchUp\SketchUp.exe")
VRAY_EXE = Path(r"C:\Program Files\Chaos\V-Ray\V-Ray for SketchUp\extension\vray\bin\vray.exe")
EXPORT_RB = ROOT / "tools" / "vray_export.rb"
SCRATCH = ROOT / ".claude" / "scratch"
BASE = ROOT / "artifacts/planta_74/furnished/planta_74_furnished.skp"


def _flatten_alpha(png_path):
    from PIL import Image
    im = Image.open(png_path)
    if im.mode == "RGBA":
        im.convert("RGB").save(png_path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--eye", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--fov", type=float, default=55)
    ap.add_argument("--iso", type=float, default=160)
    ap.add_argument("--fnum", type=float, default=5.6)
    ap.add_argument("--shutter", type=float, default=56)
    ap.add_argument("--sky", type=float, default=0.3)
    ap.add_argument("--sun", type=float, default=None)
    ap.add_argument("--width", type=int, default=1100)
    ap.add_argument("--height", type=int, default=1375)
    ap.add_argument("--fill", default="", help="INCHES: 'x,y,z,int[,raio]' ;-separados")
    ns = ap.parse_args()

    SCRATCH.mkdir(parents=True, exist_ok=True)
    copy = SCRATCH / "banho_vray_copy.skp"
    vrs = SCRATCH / "banho.vrscene"
    log = SCRATCH / "banho_vray_log.txt"
    for p in (copy, vrs, log):
        if p.exists():
            p.unlink()
    subprocess.run(["taskkill", "/F", "/IM", "SketchUp.exe"], capture_output=True)
    time.sleep(1)
    shutil.copy2(BASE, copy)
    base_hash = hashlib.sha256(BASE.read_bytes()).hexdigest()

    env = dict(os.environ)
    env.update({"VRSCENE_OUT": str(vrs).replace("\\", "/"),
                "VRAY_LOG": str(log).replace("\\", "/"),
                "VRAY_EYE": ns.eye, "VRAY_TARGET": ns.target,
                "VRAY_FOV": str(ns.fov),
                "VRAY_BATH_THEME": "estudio",
                "VRAY_TEX_DIR": str(ROOT / "assets/textures/procedural").replace("\\", "/")})
    subprocess.Popen([str(SU_EXE), str(copy), "-RubyStartup", str(EXPORT_RB)],
                     env=env, creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    t0 = time.time()
    deadline = time.time() + 120
    while time.time() < deadline:
        if log.exists():
            time.sleep(2)
            break
        time.sleep(2)
    subprocess.run(["taskkill", "/F", "/IM", "SketchUp.exe"], capture_output=True)
    time.sleep(1)
    if not vrs.exists():
        print(json.dumps({"status": "fail", "error": "export .vrscene falhou",
                          "log": log.read_text("utf-8", errors="ignore")[-400:]
                          if log.exists() else ""}))
        sys.exit(1)

    fills = None
    if ns.fill:
        fills = []
        for spec in ns.fill.split(";"):
            v = [float(x) for x in spec.split(",")]
            fills.append({"pos": (v[0], v[1], v[2]), "intensity": v[3],
                          "radius": v[4] if len(v) > 4 else 14.0,
                          "color": (1.0, 0.8, 0.55)})
    tweak_file(str(vrs), iso=ns.iso, fnum=ns.fnum, shutter=ns.shutter, sky=ns.sky, sun=ns.sun,
               width=ns.width, height=ns.height, materials=True,
               theme="estudio_banho", fill_lights=fills)

    out_png = Path(ns.out).resolve()
    if out_png.exists():
        out_png.unlink()
    subprocess.run([str(VRAY_EXE), f"-sceneFile={vrs}", f"-imgFile={out_png}",
                    "-display=0", "-autoClose=1"], capture_output=True, timeout=300)
    ok = out_png.exists()
    if ok:
        _flatten_alpha(out_png)
    print(json.dumps({"status": "success" if ok else "fail",
                      "image": str(out_png) if ok else None,
                      "timing_s": round(time.time() - t0, 1),
                      "base_intact": hashlib.sha256(BASE.read_bytes()).hexdigest() == base_hash,
                      "log": (log.read_text('utf-8', errors='ignore')[-200:]
                              if log.exists() else "")}))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
