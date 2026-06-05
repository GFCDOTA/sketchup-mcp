"""furnish_apartment.py — mobilia a planta INTEIRA num UNICO .skp: classifica
cada comodo (tools.room_type), roda o brain certo por tipo, junta TODOS os boxes
e materializa um so planta_74_furnished.skp (+ renders) no shell real. REUSA
tools/place_layout_skp.rb (generico). Pasta fixa artifacts/planta_74/furnished/.

Hoje mobilia: BEDROOM (bedroom_layout). Arquitetura cresce: e so registrar mais
brains em BRAINS (KITCHEN, BATHROOM, LIVING). Felipe 2026-06-05. Placeholders,
NAO 3D Warehouse.

ATENCAO: sem --dry-run, da taskkill SketchUp.exe e LANCA o SketchUp.
Uso: python tools/furnish_apartment.py [--dry-run]
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # roda standalone
from tools.bathroom_layout import build_boxes as bath_boxes   # noqa: E402
from tools.kitchen_layout import build_boxes as kitchen_boxes   # noqa: E402
from tools.place_bedroom_skp import build_boxes as bedroom_boxes   # noqa: E402
from tools.place_layout_skp import build_boxes as living_boxes   # noqa: E402
from tools.room_type import (BATHROOM, BEDROOM, KITCHEN, LIVING,   # noqa: E402
                             classify_rooms)

ROOT = Path(__file__).resolve().parents[1]
SKETCHUP_EXE = r"C:\Program Files\SketchUp\SketchUp 2026\SketchUp\SketchUp.exe"
CONSENSUS = ROOT / "fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json"
BASE_SKP = ROOT / "artifacts/planta_74/planta_74.skp"
OUT_DIR = ROOT / "artifacts/planta_74/furnished"   # pasta UNICA fixa
RB = ROOT / "tools/place_layout_skp.rb"

# dispatch por tipo de comodo (cresce conforme novos brains entram)
BRAINS = {BEDROOM: bedroom_boxes, KITCHEN: kitchen_boxes, LIVING: living_boxes,
          BATHROOM: bath_boxes}


def collect_boxes(con):
    """Junta os boxes de TODOS os comodos com brain disponivel. Devolve
    (boxes, summary[(id,name,type,result,n_boxes)])."""
    rooms = classify_rooms(con)
    all_boxes, summary = [], []
    for r in rooms:
        brain = BRAINS.get(r["room_type"])
        if brain is None:
            summary.append((r["id"], r["name"], r["room_type"], "skip(sem brain)", 0))
            continue
        boxes, out = brain(con, r["id"])
        n = len(boxes) if boxes else 0
        all_boxes += boxes or []
        summary.append((r["id"], r["name"], r["room_type"], out.get("result"), n))
    return all_boxes, summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    con = json.loads(CONSENSUS.read_text("utf-8"))
    boxes, summary = collect_boxes(con)
    n_rooms = sum(1 for s in summary if s[4])
    print(f"[furnish-apt] {len(boxes)} placeholders em {n_rooms} comodo(s):")
    for rid, name, rt, res, n in summary:
        print(f"  {str(rid):5} {str(name)[:28]:28} {rt:9} {str(res):16} {n} boxes")
    if args.dry_run or not boxes:
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    skp_out = OUT_DIR / "planta_74_furnished.skp"
    before = OUT_DIR / "planta_74_furnished_before_top.png"
    after_top = OUT_DIR / "planta_74_furnished_after_top.png"
    after_iso = OUT_DIR / "planta_74_furnished_after_iso.png"
    log_path = OUT_DIR / "planta_74_furnished_log.txt"
    for p in (skp_out, before, after_top, after_iso, log_path):
        if p.exists():
            p.unlink()

    env = os.environ.copy()
    env["LAYOUT_BOXES"] = json.dumps(boxes)
    env["LAYOUT_OUT"] = str(skp_out).replace("\\", "/")
    env["LAYOUT_BEFORE"] = str(before).replace("\\", "/")
    env["LAYOUT_AFTER_TOP"] = str(after_top).replace("\\", "/")
    env["LAYOUT_AFTER_ISO"] = str(after_iso).replace("\\", "/")
    env["LAYOUT_LOG"] = str(log_path).replace("\\", "/")

    subprocess.run(["taskkill", "/F", "/IM", "SketchUp.exe"], capture_output=True)
    time.sleep(1)
    cmd = [SKETCHUP_EXE, str(BASE_SKP), "-RubyStartup", str(RB)]
    print("[furnish-apt] launching SU...")
    subprocess.Popen(cmd, env=env, creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    deadline = time.time() + 240
    while time.time() < deadline:
        if log_path.exists():
            time.sleep(2)
            break
        time.sleep(1)
    subprocess.run(["taskkill", "/F", "/IM", "SketchUp.exe"], capture_output=True)

    if log_path.exists():
        print("[furnish-apt] LOG:")
        print(log_path.read_text("utf-8"))
    else:
        print("[furnish-apt] TIMEOUT — SU nao produziu log")
        sys.exit(1)
    print(f"\n[furnish-apt] -> {OUT_DIR}/")
    print(f"  SKP:   {skp_out.name}")
    print(f"  AFTER: {after_top.name} / {after_iso.name}")


if __name__ == "__main__":
    main()
