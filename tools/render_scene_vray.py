"""render_scene_vray.py — fase V-Ray do Intent-to-Scene: renderiza a CENA composta
(scene.skp + scene.json de um run dir) com V-Ray premium, na MESMA camera 3/4 humana
do composer. So roda depois da composicao PASS no SpatialGate + GPT (gate do track).

Pipeline (reusa o caminho provado da suite01/mobiliar, agora no repo principal):
  1. garante scene_closed.skp — modelo FECHADO (4 paredes + teto, NADA escondido;
     o scene.skp canonico e' dollhouse e deixa a luz de ceu lavar o interior)
  2. SketchUp <closed copy> -RubyStartup vray_export.rb -> .vrscene (camera via
     VRAY_EYE/TARGET em INCHES, derivada da camera em METROS do scene.json)
  3. tweak_vrscene.py: exposicao de INTERIOR (receita suite01: iso100/f7/sh160/
     sky0.3) + materiais premium por papel + fill lights opcionais
  4. vray.exe headless -> PNG premium
No-disrupt: pula se o SketchUp ja esta aberto. Path do run dir SEMPRE resolvido
absoluto (licao do cycle 002: SU resolve save/write contra o CWD DELE).

Uso: python -m tools.render_scene_vray [runs/scenes/<id>] [--out nome.png]
     [--iso 100 --fnum 7 --shutter 160 --sky 0.3 --fov 65 --width 1500
      --height 1000 --fill x,y,z,int[,raio];...   (fill em METROS)]
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


def _ensure_closed_skp(d, force=False):
    """Constroi scene_closed.skp: TODAS as parts (4 paredes + teto + moveis), nada
    escondido — o modelo que o V-Ray interior precisa. Reusa o provider SU."""
    closed = d / "scene_closed.skp"
    if closed.exists() and not force:
        return {"status": "cached", "skp": str(closed)}
    parts = json.loads((d / "scene_parts.json").read_text("utf-8"))
    from interior.renderers.render_provider import RenderRequest
    from interior.renderers.sketchup_basic_provider import SketchUpBasicProvider
    from tools.render_scene_views import scene_boxes
    prov = SketchUpBasicProvider()
    if not prov.available():
        return {"status": "fail", "error": "provider SU indisponivel"}
    req = RenderRequest(boxes=scene_boxes(parts), out_skp=str(closed),
                        renderer="furniture", label="scene_closed", renders={})
    res = prov.render(req)
    if res.status != "success" or not closed.exists():
        return {"status": "fail", "error": f"closed skp falhou: {res.error}",
                "log": (res.log or "")[-300:]}
    return {"status": "built", "skp": str(closed)}


def render_scene_vray(scene_dir, out_png=None, iso=100, fnum=7.0, shutter=160,
                      sky=0.3, sun=None, sun_size=None, fov=65, width=1500,
                      height=1000, fills_m=None,
                      timeout_export=90, timeout_render=240):
    """Devolve dict de status. fail-explicito em cada etapa (sem sucesso fabricado).
    fills_m: lista de dicts {pos:(x,y,z) em METROS, intensity, radius_m opcional}."""
    d = Path(scene_dir).resolve()
    if not (d / "scene_parts.json").exists():
        return {"status": "fail", "error": f"scene_parts.json ausente em {d}"}
    scene = json.loads((d / "scene.json").read_text("utf-8"))
    if not (SU_EXE.exists() and VRAY_EXE.exists()):
        return {"status": "skipped", "reason": "SU/vray.exe ausentes"}
    if _su_running():
        return {"status": "skipped", "reason": "SketchUp em uso (no-disrupt)"}
    closed = _ensure_closed_skp(d)
    if closed["status"] == "fail":
        return {"status": "fail", "error": closed["error"], "log": closed.get("log", "")}
    skp = Path(closed["skp"])

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
                "VRAY_FOV": str(fov)})
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

    fills = None
    if fills_m:
        fills = [{"pos": tuple(v * M_TO_IN for v in f["pos"]),
                  "intensity": f["intensity"],
                  "radius": f.get("radius_m", 0.35) * M_TO_IN,
                  "color": f.get("color", (1.0, 0.8, 0.55))} for f in fills_m]
    tweak_file(str(vrs), iso=iso, fnum=fnum, shutter=shutter, sky=sky, sun=sun,
               sun_size=sun_size, width=width, height=height, materials=True,
               fill_lights=fills)

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
    ap.add_argument("--iso", type=float, default=100)
    ap.add_argument("--fnum", type=float, default=7.0)
    ap.add_argument("--shutter", type=float, default=160)
    ap.add_argument("--sky", type=float, default=0.3)
    ap.add_argument("--sun", type=float, default=None)
    ap.add_argument("--sun-size", type=float, default=None)
    ap.add_argument("--fov", type=float, default=65)
    ap.add_argument("--width", type=int, default=1500)
    ap.add_argument("--height", type=int, default=1000)
    ap.add_argument("--fill", default="",
                    help="fills em METROS: 'x,y,z,int[,raio_m]' separados por ';'")
    ns = ap.parse_args()
    fills_m = None
    if ns.fill:
        fills_m = []
        for spec in ns.fill.split(";"):
            v = [float(x) for x in spec.split(",")]
            fills_m.append({"pos": (v[0], v[1], v[2]), "intensity": v[3],
                            **({"radius_m": v[4]} if len(v) > 4 else {})})
    res = render_scene_vray(ns.scene_dir, out_png=ns.out, iso=ns.iso, fnum=ns.fnum,
                            shutter=ns.shutter, sky=ns.sky, sun=ns.sun,
                            sun_size=ns.sun_size, fov=ns.fov,
                            width=ns.width, height=ns.height, fills_m=fills_m)
    print(json.dumps({k: v for k, v in res.items() if k != "log"},
                     indent=2, ensure_ascii=False))
    if res.get("log"):
        print("--- export log ---\n" + res["log"])
    sys.exit(0 if res["status"] == "success" else 1)
