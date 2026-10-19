"""Mobilia um shell SINTÉTICO com os brains de produção (collect_boxes) e o
materializador de produção (tools/place_layout_skp.rb), pelo mesmo batch.run_script
do su_furnish — que é planta_74-only (exige PT_TO_M=0.0259).

A escala vem do ambiente (PT_TO_M) e precisa casar com a do shell sintético.
uso: PT_TO_M=<s> synth_furnish.py <consensus.json> <base.skp> <out_dir>"""
import json
import os
import shutil
import sys
from pathlib import Path

assert os.environ.get("PT_TO_M"), "defina PT_TO_M explicitamente (a do shell sintético)"
from core import scale  # noqa: E402
from tools.furnish_apartment import collect_boxes  # noqa: E402
from tools.sketchup.batch import run_script  # noqa: E402
from tools.sketchup.process import SketchUp  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
con_p, base, out = (Path(a).resolve() for a in sys.argv[1:4])
out.mkdir(parents=True, exist_ok=True)
con = json.loads(con_p.read_text("utf-8"))
boxes, summary = collect_boxes(con)
(out / "boxes.json").write_text(json.dumps({"pt_to_m": scale.PT_TO_M, "summary": summary, "boxes": boxes},
                                           indent=1, default=str), encoding="utf-8")
copy = out / f"_furnish_base_{base.name}"
shutil.copy2(base, copy)
files = {k: out / f"furnished{s}" for k, s in (("skp", ".skp"), ("before", "_before_top.png"),
                                                ("top", "_after_top.png"), ("iso", "_after_iso.png"),
                                                ("log", "_log.txt"))}
for f in files.values():
    f.unlink(missing_ok=True)
env = {"PT_TO_M": str(scale.PT_TO_M), "LAYOUT_BOXES": json.dumps(boxes),
       "LAYOUT_TEX_DIR": str((REPO / "assets/textures/procedural").resolve()),
       **{f"LAYOUT_{k}": str(files[v]).replace("\\", "/") for k, v in
          (("OUT", "skp"), ("BEFORE", "before"), ("AFTER_TOP", "top"), ("AFTER_ISO", "iso"), ("LOG", "log"))}}
style = os.environ.get("FURNISH_STYLE")
if style:
    from tools.style_spec import texture_env
    env.update(texture_env(style, (REPO / "assets/textures/procedural").resolve()))
run = run_script(SketchUp(), script=REPO / "tools" / "place_layout_skp.rb", done_marker=files["log"],
                 skp_in=copy, env_extra=env, timeout_s=300, mode="interactive")
run["summary"] = summary
run["n_boxes"] = len(boxes)
run["files"] = {k: str(v) for k, v in files.items() if v.exists()}
(out / "furnish_run.json").write_text(json.dumps(run, indent=1, default=str), encoding="utf-8")
print(json.dumps({k: run[k] for k in ("status", "pid", "elapsed_s", "n_boxes", "summary")}, default=str))
