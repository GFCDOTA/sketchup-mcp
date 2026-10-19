"""Fixture SINTÉTICA de builders isolados: cada classe (sofá reto, sofá chaise,
poltrona, cama queen/king, guarda-roupa, criado-mudo) em 0°, 90° e 30°, numa
grade longe do shell. Posiciona com place_sofa_boxes (o mesmo de produção) e
materializa com tools/place_layout_skp.rb via batch.run_script.

Esperado por instância (derivado do PRÓPRIO builder, não inventado):
  dims locais W×D×H = meta['bbox_m'] (ou extents das parts) do builder;
  AABB no mundo de um retângulo W×D girado θ = (W|cos|+D|sin|, W|sin|+D|cos|).
uso: PT_TO_M=<s> builders_fixture.py <base.skp> <out_dir>"""
import json
import math
import os
import shutil
import sys
from pathlib import Path

assert os.environ.get("PT_TO_M")
from core.scale import PT_TO_IN  # noqa: E402
from tools.rooms.shared.anatomy import bed_spec, nightstand_spec, sofa_spec, wardrobe_spec  # noqa: E402
from tools.rooms.shared.armchair_builder import ArmchairSpec, build_armchair  # noqa: E402
from tools.rooms.shared.bed import build_bed  # noqa: E402
from tools.rooms.shared.nightstand import build_nightstand  # noqa: E402
from tools.rooms.shared.sofa import build_sofa, place_sofa_boxes  # noqa: E402
from tools.rooms.shared.wardrobe import build_wardrobe  # noqa: E402
from tools.sketchup.batch import run_script  # noqa: E402
from tools.sketchup.process import SketchUp  # noqa: E402

REPO = Path(os.environ.get("L2_REPO") or Path(__file__).resolve().parents[3]).resolve()
base, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
out.mkdir(parents=True, exist_ok=True)

CLASSES = [
    ("sofa_straight", lambda: build_sofa(sofa_spec("straight"))),
    ("sofa_chaise_r", lambda: build_sofa(sofa_spec("chaise_right"))),
    ("poltrona", lambda: build_armchair(ArmchairSpec())),
    ("cama_queen", lambda: build_bed(bed_spec("queen"))),
    ("guarda_roupa", lambda: build_wardrobe(wardrobe_spec())),
    ("criado_mudo", lambda: build_nightstand(nightstand_spec())),
]
ANGLES = (0, 90, 30)
boxes, expected = [], []
M = 1.0 / 0.0254
for ci, (name, fn) in enumerate(CLASSES):
    parts, meta = fn()
    W = max(p["x1"] for p in parts) - min(p["x0"] for p in parts)
    D = max(p["y1"] for p in parts) - min(p["y0"] for p in parts)
    H = max(p["z1"] for p in parts) - min(p["z0"] for p in parts)
    for ai, ang in enumerate(ANGLES):
        cx, cy = 12.0 + ai * 4.0, 2.0 + ci * 4.0                 # metros, grade 4 m
        th = math.radians(ang)
        facing = (math.sin(th), -math.cos(th))                    # 0° = frente -Y (local)
        bx = place_sofa_boxes(parts, (cx * M, cy * M), facing)
        mod = f"{name}@{ang}"
        for b in bx:
            b["room"], b["module"] = "BUILDERS", mod
        boxes += bx
        c, s = abs(math.cos(th)), abs(math.sin(th))
        expected.append({"module": f"BUILDERS · {mod}", "class": name, "angle": ang,
                         "W": round(W, 4), "D": round(D, 4), "H": round(H, 4),
                         "aabb_xy_m": [round(W * c + D * s, 4), round(W * s + D * c, 4)],
                         "center_m": [cx, cy], "n_parts": len(parts),
                         "meta": {k: v for k, v in meta.items() if k in ("bbox_m", "n_parts", "kinds")}})
(out / "boxes.json").write_text(json.dumps({"pt_to_m": float(os.environ["PT_TO_M"]), "boxes": boxes,
                                           "expected": expected}, indent=1, default=str), encoding="utf-8")
copy = out / f"_base_{base.name}"
shutil.copy2(base, copy)
files = {k: out / f"builders{s}" for k, s in (("skp", ".skp"), ("top", "_top.png"), ("iso", "_iso.png"),
                                               ("log", "_log.txt"))}
for f in files.values():
    f.unlink(missing_ok=True)
env = {"PT_TO_M": os.environ["PT_TO_M"], "LAYOUT_BOXES": json.dumps(boxes),
       "LAYOUT_TEX_DIR": str((REPO / "assets/textures/procedural").resolve()),
       "LAYOUT_OUT": str(files["skp"]).replace("\\", "/"), "LAYOUT_AFTER_TOP": str(files["top"]).replace("\\", "/"),
       "LAYOUT_AFTER_ISO": str(files["iso"]).replace("\\", "/"), "LAYOUT_LOG": str(files["log"]).replace("\\", "/")}
run = run_script(SketchUp(), script=REPO / "tools" / "place_layout_skp.rb", done_marker=files["log"],
                 skp_in=copy, env_extra=env, timeout_s=300, mode="interactive")
run["n_boxes"] = len(boxes)
(out / "furnish_run.json").write_text(json.dumps(run, indent=1, default=str), encoding="utf-8")
print(json.dumps({k: run[k] for k in ("status", "pid", "elapsed_s", "n_boxes")}))
