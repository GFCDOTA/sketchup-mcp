"""render_scene_vray.py — fase V-Ray do Intent-to-Scene: renderiza a CENA composta
(scene.skp + scene.json de um run dir) com V-Ray premium, na MESMA camera 3/4 humana
do composer. So roda depois da composicao PASS no SpatialGate + GPT (gate do track).

Pipeline (reusa o caminho provado da suite01/mobiliar, agora no repo principal):
  1. copia scene.skp -> scratch (NUNCA muta o artefato)
  2. SketchUp <copy> -RubyStartup vray_export.rb  -> .vrscene (camera via VRAY_EYE/
     TARGET em INCHES, derivada da camera em METROS do scene.json)
  3. tweak_vrscene.py: exposicao de interior (iso/fnum/shutter/sky) + materiais
     premium por papel (os nomes fz_<item>__<label> da cena batem por substring:
     seat_cushion/arm -> tecido matte, rug -> tecido, etc.)
  4. vray.exe headless -> PNG premium
No-disrupt: pula se o SketchUp ja esta aberto. Path do run dir SEMPRE resolvido
absoluto (licao do cycle 002: SU resolve save/write contra o CWD DELE).

Uso: python -m tools.render_scene_vray [runs/scenes/<id>] [--out nome.png]
     [--iso 200 --fnum 4 --shutter 100 --sky 1.0 --width 1500 --height 1000]
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.scale import M_TO_IN                      # noqa: E402
from tools.tweak_vrscene import tweak_file          # noqa: E402

SU_EXE = Path(r"C:\Program Files\SketchUp\SketchUp 2026\SketchUp\SketchUp.exe")
VRAY_EXE = Path(r"C:\Program Files\Chaos\V-Ray\V-Ray for SketchUp\extension\vray\bin\vray.exe")
EXPORT_RB = ROOT / "tools" / "vray_export.rb"
SCRATCH = ROOT / ".claude" / "scratch"


def _su_running():
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq SketchUp.exe"],
                         capture_output=True, text=True)
    return "SketchUp.exe" in (out.stdout or "")


def _fmt_in(v_m):
    return f"{v_m * M_TO_IN:.2f}"


def render_scene_vray(scene_dir, out_png=None, iso=200, fnum=4.0, shutter=100,
                      sky=1.0, width=1500, height=1000, timeout_export=90,
                      timeout_render=240):
    """Devolve dict de status. fail-explicito em cada etapa (sem sucesso fabricado)."""
    d = Path(scene_dir).resolve()
    skp = d / "scene.skp"
    scene = json.loads((d / "scene.json").read_text("utf-8"))
    if not skp.exists():
        return {"status": "fail", "error": f"scene.skp ausente em {d}"}
    if not (SU_EXE.exists() and VRAY_EXE.exists()):
        return {"status": "skipped", "reason": "SU/vray.exe ausentes"}
    if _su_running():
        return {"status": "skipped", "reason": "SketchUp em uso (no-disrupt)"}

    cam = scene["camera"]
    eye = ",".join(_fmt_in(v) for v in cam["eye"])
    target = ",".join(_fmt_in(v) for v in cam["target"])

    SCRATCH.mkdir(parents=True, exist_ok=True)
    copy = SCRATCH / "vray_scene_copy.skp"
    vrs = SCRATCH / "scene.vrscene"
    log = SCRATCH / "vray_scene_log.txt"
    for p in (copy, vrs, log):
        if p.exists():
            p.unlink()
    import shutil
    shutil.copy2(skp, copy)
    base_hash = __import__("hashlib").sha256(skp.read_bytes()).hexdigest()

    env = dict(__import__("os").environ)
    env.update({"VRSCENE_OUT": str(vrs).replace("\\", "/"),
                "VRAY_LOG": str(log).replace("\\", "/"),
                "VRAY_EYE": eye, "VRAY_TARGET": target,
                "VRAY_FOV": "55"})
    ps = (f"Start-Process -FilePath '{SU_EXE}' "
          f"-ArgumentList '\"{copy}\"','-RubyStartup','\"{EXPORT_RB}\"'")
    t0 = time.time()
    subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                   env=env, capture_output=True, timeout=60)
    deadline = time.time() + timeout_export
    while time.time() < deadline:
        if log.exists():
            time.sleep(2)
            break
        time.sleep(2)
    subprocess.run(["taskkill", "/F", "/IM", "SketchUp.exe"], capture_output=True)
    time.sleep(1)
    log_txt = log.read_text("utf-8", errors="ignore") if log.exists() else ""
    if not vrs.exists():
        return {"status": "fail", "error": "export .vrscene falhou",
                "log": log_txt[-500:], "timing_s": round(time.time() - t0, 1)}

    tweak_file(str(vrs), iso=iso, fnum=fnum, shutter=shutter, sky=sky,
               width=width, height=height, materials=True)

    out_png = Path(out_png) if out_png else d / "vray_three_quarter.png"
    out_png = out_png.resolve()
    if out_png.exists():
        out_png.unlink()
    r = subprocess.run([str(VRAY_EXE), f"-sceneFile={vrs}", f"-imgFile={out_png}",
                        "-display=0", "-autoClose=1"],
                       capture_output=True, text=True, timeout=timeout_render)
    timing = round(time.time() - t0, 1)
    base_intact = __import__("hashlib").sha256(skp.read_bytes()).hexdigest() == base_hash
    if not out_png.exists():
        return {"status": "fail", "error": "vray.exe nao produziu imagem",
                "vray_tail": (r.stdout or "")[-400:], "timing_s": timing,
                "base_intact": base_intact}
    return {"status": "success", "image": str(out_png),
            "vrscene_bytes": vrs.stat().st_size, "camera": {"eye": eye, "target": target},
            "timing_s": timing, "base_intact": base_intact, "log": log_txt[-300:]}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("scene_dir", nargs="?",
                    default=str(ROOT / "runs/scenes/living_room_modern_warm_minimal"))
    ap.add_argument("--out", default=None)
    ap.add_argument("--iso", type=float, default=200)
    ap.add_argument("--fnum", type=float, default=4.0)
    ap.add_argument("--shutter", type=float, default=100)
    ap.add_argument("--sky", type=float, default=1.0)
    ap.add_argument("--width", type=int, default=1500)
    ap.add_argument("--height", type=int, default=1000)
    ns = ap.parse_args()
    res = render_scene_vray(ns.scene_dir, out_png=ns.out, iso=ns.iso, fnum=ns.fnum,
                            shutter=ns.shutter, sky=ns.sky, width=ns.width,
                            height=ns.height)
    print(json.dumps({k: v for k, v in res.items() if k != "log"},
                     indent=2, ensure_ascii=False))
    if res.get("log"):
        print("--- export log ---\n" + res["log"])
    sys.exit(0 if res["status"] == "success" else 1)
