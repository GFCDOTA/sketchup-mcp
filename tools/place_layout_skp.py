"""place_layout_skp.py — materializa o layout VENCEDOR (Etapa B+C) no .skp real
como PLACEHOLDERS (boxes coloridos extrudados), pra o Felipe ver o layout na
planta_74 e dar o veredito visual. NAO usa 3D Warehouse, NAO baixa asset.

Slice minimo (gate :8765, opcao A): so a sala r002, m013 marcado AMBIGUOUS,
render before/after pra VISUAL_REVIEW. Felipe 2026-06-04.

Coordenadas: usa a MESMA conversao do furnish_plan (SU = pdf * PT_TO_IN, sem
flip de Y) que comprovadamente bate com o shell artifacts/planta_74.skp.

Uso: python tools/place_layout_skp.py [--room r002]
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from tools.layout_candidates import EXTRA_TEMPLATES, TEMPLATES, _tv_setup, run

ROOT = Path(r"E:\Claude\sketchup-mcp")
SKETCHUP_EXE = r"C:\Program Files\SketchUp\SketchUp 2026\SketchUp\SketchUp.exe"
PT_TO_IN = (0.19 / 5.4) * 39.3700787402
CONSENSUS = ROOT / "fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json"
BASE_SKP = ROOT / "artifacts/planta_74/planta_74.skp"
OUT_DIR = ROOT / "runs/planta_74"

# altura de extrusao do placeholder por tipo (m) e cor RGB (= cores do PNG 2D)
KIND_H_M = {"sofa_3": 0.80, "sofa_2": 0.80, "rack_tv": 0.45,
            "mesa_centro": 0.40, "poltrona": 0.80,
            "tapete": 0.02, "aparador": 0.85}
KIND_RGB = {"sofa_3": [21, 101, 192], "sofa_2": [21, 101, 192],
            "rack_tv": [106, 27, 154], "mesa_centro": [239, 108, 0],
            "poltrona": [0, 131, 143], "tapete": [201, 185, 160],
            "aparador": [121, 85, 72]}


def build_boxes(con, room_id, template_name=None):
    """Roda o cerebro de layout e converte o layout em boxes SU (inches).
    Sem template_name: materializa o VENCEDOR do ranking. Com template_name:
    materializa esse template direto (offset 0), util pra prototipar composicao
    antes do score premia-la."""
    sm, out = run(con, room_id)
    tv = _tv_setup(sm)
    if tv is None:
        return None, out
    ambiguous = out["tv_wall"].get("confidence") == "ambiguous"
    if template_name:
        fn = EXTRA_TEMPLATES.get(template_name) or dict(TEMPLATES).get(template_name)
        if fn is None:
            return None, {"result": "NO_TEMPLATE",
                          "reason": f"template '{template_name}' desconhecido",
                          "tv_wall": out["tv_wall"]}
        items_raw = fn(tv)
        out["chosen_candidate"] = template_name
    elif out["result"] != "OK":
        return None, out
    else:
        cand = next(c for c in out["candidates"] if c["template"] == out["chosen_candidate"])
        items_raw = cand["_items"]
    boxes = []
    for it in items_raw:
        x0, y0, x1, y1 = it["box"].bounds
        kind = it["kind"]
        is_tv_wall = kind == "rack_tv"   # rack mora na parede-TV
        # cantos reais do poligono (preserva rotacao p/ moveis angulados); o .rb
        # desenha via add_face(corners), nao via bbox.
        coords = list(it["box"].exterior.coords)[:-1]
        corners = [[round(px * PT_TO_IN, 2), round(py * PT_TO_IN, 2)] for px, py in coords]
        boxes.append({
            "kind": kind,
            "x0": x0 * PT_TO_IN, "y0": y0 * PT_TO_IN,
            "x1": x1 * PT_TO_IN, "y1": y1 * PT_TO_IN,
            "corners": corners,
            "h_in": KIND_H_M.get(kind, 0.5) * 39.3700787402,
            "rgb": KIND_RGB.get(kind, [120, 120, 120]),
            "label": kind + ("_AMBIGUOUS" if (is_tv_wall and ambiguous) else ""),
            "ambiguous": bool(is_tv_wall and ambiguous),
            "decorative": bool(it.get("decorative")),
        })
    return boxes, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--room", default="r002")
    ap.add_argument("--template", default=None,
                    help="forcar um template (ex: estar_ancorado); default = vencedor do score")
    ap.add_argument("--dry-run", action="store_true",
                    help="monta os boxes e imprime, sem lancar o SketchUp")
    args = ap.parse_args()
    con = json.loads(CONSENSUS.read_text("utf-8"))
    boxes, out = build_boxes(con, args.room, args.template)
    if boxes is None:
        print(f"[place] {out['result']}: {out.get('reason')} — nada a materializar")
        sys.exit(2)

    if args.dry_run:
        print(f"[dry-run] sala {args.room} | vencedor {out['chosen_candidate']} | "
              f"{len(boxes)} boxes (SU inches):")
        for b in boxes:
            print(f"  {b['label']:22} x[{b['x0']:.0f}..{b['x1']:.0f}] "
                  f"y[{b['y0']:.0f}..{b['y1']:.0f}] h={b['h_in']:.0f} rgb={b['rgb']}")
        if out.get("tv_wall_uncertainty"):
            print(f"  /!\\ {out['tv_wall_uncertainty']}")
        return

    chosen = out["chosen_candidate"]
    score = next((c["total_score"] for c in out.get("candidates", []) if c["template"] == chosen), None)
    score_str = f"{score} pts" if score is not None else "(template forcado, fora do ranking)"
    print(f"[place] sala {args.room} | layout: {chosen} {score_str} | {len(boxes)} placeholders")
    if out.get("tv_wall_uncertainty"):
        print(f"[place] /!\\ {out['tv_wall_uncertainty']}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tag = f"_{args.template}" if args.template else ""
    skp_out = OUT_DIR / f"planta_74_layout_{args.room}{tag}.skp"
    before_png = OUT_DIR / f"layout_{args.room}{tag}_before_top.png"
    after_top = OUT_DIR / f"layout_{args.room}{tag}_after_top.png"
    after_iso = OUT_DIR / f"layout_{args.room}{tag}_after_iso.png"
    log_path = OUT_DIR / f"layout_{args.room}{tag}_place_log.txt"
    for p in (skp_out, before_png, after_top, after_iso, log_path):
        if p.exists():
            p.unlink()

    env = os.environ.copy()
    env["LAYOUT_BOXES"] = json.dumps(boxes)
    env["LAYOUT_OUT"] = str(skp_out).replace("\\", "/")
    env["LAYOUT_BEFORE"] = str(before_png).replace("\\", "/")
    env["LAYOUT_AFTER_TOP"] = str(after_top).replace("\\", "/")
    env["LAYOUT_AFTER_ISO"] = str(after_iso).replace("\\", "/")
    env["LAYOUT_LOG"] = str(log_path).replace("\\", "/")

    subprocess.run(["taskkill", "/F", "/IM", "SketchUp.exe"], capture_output=True)
    time.sleep(1)
    cmd = [SKETCHUP_EXE, str(BASE_SKP), "-RubyStartup", str(ROOT / "tools/place_layout_skp.rb")]
    print(f"[place] launching SU (base={BASE_SKP.name})...")
    subprocess.Popen(cmd, env=env, creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))

    deadline = time.time() + 240
    while time.time() < deadline:
        if log_path.exists():
            time.sleep(2)
            break
        time.sleep(1)
    subprocess.run(["taskkill", "/F", "/IM", "SketchUp.exe"], capture_output=True)

    if log_path.exists():
        print("[place] LOG:")
        print(log_path.read_text("utf-8"))
    else:
        print("[place] TIMEOUT — SU nao produziu log")
        sys.exit(1)

    # cross-check deterministico de coordenadas (o gate alertou: offset/escala)
    print("\n[place] === COORD CROSS-CHECK ===")
    bx = [b["x0"] for b in boxes] + [b["x1"] for b in boxes]
    by = [b["y0"] for b in boxes] + [b["y1"] for b in boxes]
    print(f"  bbox moveis (SU in): x[{min(bx):.0f}..{max(bx):.0f}] "
          f"y[{min(by):.0f}..{max(by):.0f}]")
    print(f"  (se no render TOP os boxes caem DENTRO da sala da planta, coord OK)")
    print(f"\n[place] artefatos -> {OUT_DIR}/")
    print(f"  SKP:    {skp_out.name}")
    print(f"  BEFORE: {before_png.name}")
    print(f"  AFTER:  {after_top.name} / {after_iso.name}")


if __name__ == "__main__":
    main()
