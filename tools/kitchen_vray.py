"""kitchen_vray.py — V-Ray da COZINHA ISOLADA (KITCHEN_VRAY_MATERIAL_VALIDATION).

Esconde tudo menos a COZINHA (VRAY_ISOLATE) -> mata a oclusão do galley -> a câmera iso do
vray_export.rb auto-enquadra. Aplica madeira/pedra (kc_* tex_map) + exposição quente. NÃO
altera geometria. Uso: PT_TO_M=0.0259 .venv/Scripts/python.exe .claude/scratch/kitchen_vray.py [out.png]
"""
import hashlib
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

if not os.environ.get("PT_TO_M"):
    os.environ["PT_TO_M"] = "0.0259"
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.tweak_vrscene import tweak_file   # noqa: E402

SU = Path(r"C:\Program Files\SketchUp\SketchUp 2026\SketchUp\SketchUp.exe")
VRAY = Path(r"C:\Program Files\Chaos\V-Ray\V-Ray for SketchUp\extension\vray\bin\vray.exe")
RB = ROOT / "tools/vray_export.rb"
TEX = ROOT / "assets/textures/procedural"
BASE = ROOT / "artifacts/planta_74/furnished/planta_74_furnished.skp"
SCRATCH = ROOT / ".claude/scratch"
FDIR = ROOT / "artifacts/planta_74/furnished/kitchen_angles"

out_name = sys.argv[1] if len(sys.argv) > 1 else "cozinha_vray.png"
ISO = float(os.environ.get("ISO", 200))
FNUM = float(os.environ.get("FNUM", 4.0))
SHUTTER = float(os.environ.get("SHUTTER", 100))
SKY = float(os.environ.get("SKY", 0.6))
BURN = float(os.environ.get("BURN", 0.8))
FILL = float(os.environ.get("FILL_INT", 22))
FOV = os.environ.get("VRAY_FOV", "48")

copy = SCRATCH / "kvray_copy.skp"
vrs = SCRATCH / "kroom.vrscene"
log = SCRATCH / "kroom_log.txt"
for p in (copy, vrs, log):
    if p.exists():
        p.unlink()
shutil.copy2(BASE, copy)
base_hash = hashlib.sha256(BASE.read_bytes()).hexdigest()

env = dict(os.environ)
env.update({
    "VRSCENE_OUT": str(vrs).replace("\\", "/"), "VRAY_LOG": str(log).replace("\\", "/"),
    "VRAY_TEX_DIR": str(TEX), "VRAY_ISOLATE": os.environ.get("VRAY_ISOLATE", "COZINHA"),
    "VRAY_STONE": "1", "VRAY_CAM": os.environ.get("VRAY_CAM", "iso"), "VRAY_FOV": FOV,
    "VRAY_DEFER": "10",
})
# NÃO setar VRAY_EYE -> vray_export usa a câmera iso na bbox da cozinha isolada
env.pop("VRAY_EYE", None); env.pop("VRAY_TARGET", None)
if os.environ.get("VRAY_EYE"):
    env["VRAY_EYE"] = os.environ["VRAY_EYE"]; env["VRAY_TARGET"] = os.environ["VRAY_TARGET"]

ps = f"Start-Process -FilePath '{SU}' -ArgumentList '\"{copy}\"','-RubyStartup','\"{RB}\"'"
subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
               env=env, capture_output=True, timeout=60)
deadline = time.time() + 110
while time.time() < deadline:
    if log.exists():
        time.sleep(2)
        break
    time.sleep(2)
subprocess.run(["taskkill", "/F", "/IM", "SketchUp.exe"], capture_output=True)
time.sleep(1)
if not vrs.exists():
    print("EXPORT FAIL")
    print(log.read_text("utf-8", "ignore") if log.exists() else "(sem log)")
    sys.exit(1)
print("export OK:", log.read_text("utf-8", "ignore").replace("\n", " | ")[:300])

# RIG de luz dedicado (sphere area lights). Céu/sol baixos -> estes dominam = contraste/forma.
fills = []
# KEY: forte, frente-cima de um lado (define forma + sombra de profundidade), quente
fills.append({"pos": (float(os.environ.get("KEY_X", 168)), float(os.environ.get("KEY_Y", 600)),
                      float(os.environ.get("KEY_Z", 104))),
              "intensity": float(os.environ.get("KEY_INT", 80)), "radius": float(os.environ.get("KEY_R", 26)),
              "color": (1.0, 0.86, 0.62)})
# FILL: suave do outro lado (lift das sombras -> madeira não some), neutro-quente
fills.append({"pos": (176.0, 714.0, 64.0), "intensity": float(os.environ.get("FILL2_INT", 22)),
              "radius": 48.0, "color": (0.96, 0.93, 0.9)})
# LED LINEAR sob o aéreo: LightRectangle fina e longa = wash CONTÍNUO (não hotspots) — feedback GPT.
# u ao longo da bancada (y); normal aponta p/ wall+baixo (lava backsplash + bancada uniforme).
led_rect = [{
    "center": (62.0, 648.0, 56.5),
    "u_dir": (0, 1, 0), "v_dir": (0.93, 0, -0.37), "normal": (-0.37, 0, -0.93),
    "u_size": 50.0, "v_size": 2.5,
    "intensity": float(os.environ.get("LED_INT", 8)), "color": (1.0, 0.74, 0.45),
}]
tweak_file(str(vrs), iso=ISO, fnum=FNUM, shutter=SHUTTER, sky=SKY, burn=BURN,
           sun=float(os.environ.get("SUN", 0.2)), sun_size=float(os.environ.get("SUN_SIZE", 3.0)),
           materials=True, fill_lights=fills, rect_lights=led_rect, width=1500, height=1100)

img = (FDIR / out_name).resolve()
if img.exists():
    img.unlink()
r = subprocess.run([str(VRAY), f"-sceneFile={vrs}", f"-imgFile={img}", "-display=0", "-autoClose=1"],
                   capture_output=True, timeout=320)
intact = hashlib.sha256(BASE.read_bytes()).hexdigest() == base_hash
if not img.exists():
    print("RENDER FAIL", (r.stdout.decode("utf-8", "ignore")[-400:] if r.stdout else ""))
    sys.exit(1)
from PIL import Image  # noqa: E402
im = Image.open(img)
if im.mode == "RGBA":
    im = im.convert("RGB")
# crop hero: tira chão vazio + céu de sobra (mantém a cozinha). Tunável por env CROP_*.
W, H = im.size
cx0, cx1 = float(os.environ.get("CROP_X0", 0.10)), float(os.environ.get("CROP_X1", 0.93))
cy0, cy1 = float(os.environ.get("CROP_Y0", 0.02)), float(os.environ.get("CROP_Y1", 0.60))
im = im.crop((int(W * cx0), int(H * cy0), int(W * cx1), int(H * cy1)))
im.save(img)
print(f"OK base_intact={intact} -> {img}  ({im.size})")
