"""Materializa CADA cômodo da planta_74 sozinho (os boxes do plano integrado, filtrados
por room) sobre uma cópia do shell canônico, com o place_layout_skp.rb de produção,
inspeciona o .skp reaberto e compara peça a peça com o .skp INTEGRADO.
uso: PT_TO_M=0.0259 planta_rooms_isolated.py <boxes.json> <integrated inspect.json> <base.skp> <out_dir>"""
import json
import os
import shutil
import sys
from pathlib import Path

from tools.sketchup import jobs
from tools.sketchup.batch import run_script
from tools.sketchup.process import SketchUp

REPO = Path.cwd().resolve()
boxes = json.load(open(sys.argv[1], encoding="utf-8"))["boxes"]
integ = json.load(open(sys.argv[2], encoding="utf-8"))["result"]["nodes"]
base, out = Path(sys.argv[3]).resolve(), Path(sys.argv[4]).resolve()
out.mkdir(parents=True, exist_ok=True)


def by_room(nodes, room):
    res = {}
    for n in nodes:
        if n["path"].startswith(room + " · "):
            res.setdefault(n["path"], []).append([round(v, 4) for v in n["bbox_world_m"]["min"] + n["bbox_world_m"]["max"]])
    return {k: sorted(v) for k, v in res.items()}


report = {}
for room in sorted({b["room"] for b in boxes}):
    rb = [b for b in boxes if b["room"] == room]
    slug = "".join(ch if ch.isalnum() else "_" for ch in room)[:40]
    d = out / slug
    d.mkdir(exist_ok=True)
    copy = d / f"_base_{base.name}"
    shutil.copy2(base, copy)
    skp, log = d / "room.skp", d / "room_log.txt"
    for f in (skp, log):
        f.unlink(missing_ok=True)
    env = {"PT_TO_M": os.environ["PT_TO_M"], "LAYOUT_BOXES": json.dumps(rb),
           "LAYOUT_TEX_DIR": str((REPO / "assets/textures/procedural").resolve()),
           "LAYOUT_OUT": str(skp).replace("\\", "/"), "LAYOUT_LOG": str(log).replace("\\", "/"),
           "LAYOUT_AFTER_TOP": str(d / "room_top.png").replace("\\", "/"), "LAYOUT_ZOOM_GROUP": "1",
           "LAYOUT_AFTER_ISO": str(d / "room_iso.png").replace("\\", "/")}
    run = run_script(SketchUp(), script=REPO / "tools" / "place_layout_skp.rb", done_marker=log,
                     skp_in=copy, env_extra=env, timeout_s=300, mode="interactive")
    if run.get("pid"):
        jobs.close(pid=run["pid"], force=True, confirm=True)
    ins = jobs.inspect_model(str(skp), max_depth=2, out_dir=str(d / "inspect"), mode="interactive")
    if ins.get("pid"):
        jobs.close(pid=ins["pid"], force=True, confirm=True)
    iso_nodes = ins["result"]["nodes"]
    a, b = by_room(iso_nodes, room), by_room(integ, room)
    others = [n["name"] for n in iso_nodes if "/" not in n["path"] and " · " in n["name"]
              and not n["name"].startswith(room + " · ")]
    shell_iso = {n["name"]: n["bbox_world_m"] for n in iso_nodes if "/" not in n["path"] and " · " not in n["name"]}
    shell_int = {n["name"]: n["bbox_world_m"] for n in integ if "/" not in n["path"] and " · " not in n["name"]}
    report[room] = {"boxes": len(rb), "placed_log": (log.read_text("utf-8", "replace").count("bbox") if log.exists() else 0),
                    "pieces_iso": sum(len(v) for v in a.values()), "pieces_integrated": sum(len(v) for v in b.values()),
                    "identical_to_integrated": a == b, "foreign_modules": others,
                    "shell_identical": shell_iso == shell_int, "run": run["status"], "inspect": ins["status"]}
    print(room, json.dumps(report[room], ensure_ascii=False), flush=True)
json.dump(report, open(out / "isolated_report.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)
