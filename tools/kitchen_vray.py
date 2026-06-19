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

c = [float(v) for v in (os.environ.get("VRAY_TARGET", "0,0,40").split(","))]
fills = [{"pos": (c[0], c[1], 70.0), "intensity": FILL, "radius": 34.0, "color": (1.0, 0.84, 0.62)}] if FILL > 0 else None
tweak_file(str(vrs), iso=ISO, fnum=FNUM, shutter=SHUTTER, sky=SKY, burn=BURN,
           materials=True, fill_lights=fills, width=1500, height=1100)

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
    im.save(img)
print(f"OK base_intact={intact} -> {img}  ({im.size})")
