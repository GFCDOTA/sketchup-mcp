"""place_bedroom_skp.py — materializa o layout VENCEDOR de QUARTO (bedroom_layout)
no .skp real como PLACEHOLDERS (boxes coloridos extrudados), pra o Felipe ABRIR
no SketchUp e dar o veredito visual. REUSA tools/place_layout_skp.rb (generico,
desenha qualquer LAYOUT_BOXES). NAO usa 3D Warehouse / asset.

Mesma conversao do furnish_plan/place_layout_skp (SU = pdf * PT_TO_IN, sem flip
de Y) que bate com o shell artifacts/planta_74.skp. ROOT vem de __file__ -> roda
na worktree onde o script vive (isolamento multi-agente). Felipe 2026-06-05.

ATENCAO: sem --dry-run, isto da `taskkill SketchUp.exe` e LANCA o SketchUp.

Uso: python tools/place_bedroom_skp.py --room r003 [--dry-run]
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # roda standalone
from tools.bedroom_layout import run   # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SKETCHUP_EXE = r"C:\Program Files\SketchUp\SketchUp 2026\SketchUp\SketchUp.exe"
from core.scale import PT_TO_IN  # noqa: E402  (fonte unica de escala; nao redefinir)
CONSENSUS = ROOT / "fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json"
BASE_SKP = ROOT / "artifacts/planta_74/planta_74.skp"
# PASTA CANONICA fixa do mobiliado (NAO scratch): committed + servida + GitHub.
# Felipe 2026-06-05: parar de espalhar .skp em runs/ — UMA pasta so, sempre.
OUT_DIR = ROOT / "artifacts/planta_74/furnished"
RB = ROOT / "tools/place_layout_skp.rb"   # generico, reutilizado (nao alterado)

# altura de extrusao (m) + cor RGB (= cores do diagrama 2D) por tipo de movel
KIND_H_M = {"bed": 0.55, "nightstand": 0.60, "wardrobe": 2.20}
KIND_RGB = {"bed": [21, 101, 192], "nightstand": [0, 131, 143],
            "wardrobe": [106, 27, 154]}


def build_boxes(con, room_id):
    """Roda o bedroom brain e converte o layout VENCEDOR em boxes SU (inches)."""
    sm, out = run(con, room_id)
    if out["result"] != "OK":
        return None, out
    wid = out["chosen"]["headboard_wall"]
    cand = next(c for c in out["candidates"]
                if c["headboard_wall"] == wid and c["valid"])
    boxes = []
    for it in cand["_items"]:
        x0, y0, x1, y1 = it["box"].bounds
        kind = it["kind"]
        coords = list(it["box"].exterior.coords)[:-1]
        corners = [[round(px * PT_TO_IN, 2), round(py * PT_TO_IN, 2)] for px, py in coords]
        boxes.append({
            "kind": kind,
            "x0": x0 * PT_TO_IN, "y0": y0 * PT_TO_IN,
            "x1": x1 * PT_TO_IN, "y1": y1 * PT_TO_IN,
            "corners": corners,
            "h_in": KIND_H_M.get(kind, 0.5) * 39.3700787402,
            "rgb": KIND_RGB.get(kind, [120, 120, 120]),
            "label": kind,
            "ambiguous": False,
            "decorative": False,
        })
    return boxes, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--room", default="r003")
    ap.add_argument("--dry-run", action="store_true",
                    help="monta os boxes e imprime, sem lancar o SketchUp")
    args = ap.parse_args()
    con = json.loads(CONSENSUS.read_text("utf-8"))
    boxes, out = build_boxes(con, args.room)
    if boxes is None:
        print(f"[bedroom-place] {out['result']}: {out.get('reason')} — nada a materializar")
        sys.exit(2)
    print(f"[bedroom-place] quarto {args.room} ('{out.get('room_name')}') | "
          f"cama {out['bed_size']} | cabeceira {out['chosen']['headboard_wall']} | "
          f"{len(boxes)} placeholders")

    if args.dry_run:
        for b in boxes:
            print(f"  {b['label']:12} x[{b['x0']:.0f}..{b['x1']:.0f}] "
                  f"y[{b['y0']:.0f}..{b['y1']:.0f}] h={b['h_in']:.0f} rgb={b['rgb']}")
        bx = [b['x0'] for b in boxes] + [b['x1'] for b in boxes]
        by = [b['y0'] for b in boxes] + [b['y1'] for b in boxes]
        print(f"  bbox moveis (SU in): x[{min(bx):.0f}..{max(bx):.0f}] "
              f"y[{min(by):.0f}..{max(by):.0f}]")
        print("  (se no render TOP os boxes caem DENTRO do quarto, coord OK)")
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    skp_out = OUT_DIR / f"planta_74_bedroom_{args.room}.skp"
    before = OUT_DIR / f"bedroom_{args.room}_before_top.png"
    after_top = OUT_DIR / f"bedroom_{args.room}_after_top.png"
    after_iso = OUT_DIR / f"bedroom_{args.room}_after_iso.png"
    log_path = OUT_DIR / f"bedroom_{args.room}_place_log.txt"
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
    print(f"[bedroom-place] launching SU (base={BASE_SKP.name})...")
    subprocess.Popen(cmd, env=env, creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))

    deadline = time.time() + 240
    while time.time() < deadline:
        if log_path.exists():
            time.sleep(2)
            break
        time.sleep(1)
    subprocess.run(["taskkill", "/F", "/IM", "SketchUp.exe"], capture_output=True)

    if log_path.exists():
        print("[bedroom-place] LOG:")
        print(log_path.read_text("utf-8"))
    else:
        print("[bedroom-place] TIMEOUT — SU nao produziu log")
        sys.exit(1)
    print(f"\n[bedroom-place] artefatos -> {OUT_DIR}/")
    print(f"  SKP:   {skp_out.name}")
    print(f"  AFTER: {after_top.name} / {after_iso.name}")


if __name__ == "__main__":
    main()
