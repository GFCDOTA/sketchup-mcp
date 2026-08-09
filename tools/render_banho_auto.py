"""render_banho_auto.py — enquadra e ilumina QUALQUER banho da planta_74 com a
receita aprovada no BANHO 01 (loop GPT 6.3 -> 9.6), em vez de coordenada na mão.

Deriva do brain (bathroom_layout) o bbox real do cômodo e a posição do hero
(bancada) e do box, e monta a mesma gramática de câmera/luz que o juiz aprovou:
câmera na parede da bancada olhando pro fundo, washes na parede do espelho,
rectangle light no teto DENTRO do box. Delega o render ao render_banho_vray.

Uso: python -m tools.render_banho_auto --room r006 --out artifacts/.../x.png
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# MESMA escala do furnish (0.0259): o brain só devolve as coordenadas reais do
# .skp mobiliado se PT_TO_M estiver congelado ANTES do import — com o default
# as peças saem 1.36x maiores e a câmera aponta pro vazio.
os.environ.setdefault("PT_TO_M", "0.0259")
from tools.bathroom_layout import build_boxes            # noqa: E402

CONSENSUS = ROOT / "fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json"
EYE_Z, TGT_Z = 64.0, 45.0          # 1.63m de olho, mira a 1.14m (receita p23)
WALL_PAD = 8.0                     # a câmera nunca encosta na pele (preto total)
FILL_PAD = 18.0                    # fill a menos disso da parede vira DISCO ESCURO


def _bbox(boxes, kinds=None):
    sel = [b for b in boxes if kinds is None or b["kind"] in kinds]
    if not sel:
        return None
    return (min(b["x0"] for b in sel), min(b["y0"] for b in sel),
            max(b["x1"] for b in sel), max(b["y1"] for b in sel))


def frame(room_id: str) -> dict:
    con = json.loads(CONSENSUS.read_text("utf-8"))
    boxes, meta = build_boxes(con, room_id)
    if not boxes:
        raise SystemExit(f"{room_id}: {meta.get('result')}")
    x0, y0, x1, y1 = _bbox(boxes)
    w, d = x1 - x0, y1 - y0
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    hero = _bbox(boxes, {"bancada_banho"}) or (x0, y0, x1, y1)
    box = _bbox(boxes, {"box_vidro", "kb_folha"})
    hcx, hcy = (hero[0] + hero[2]) / 2, (hero[1] + hero[3]) / 2

    if box:
        # RECEITA DO BANHO 01 (aprovada 9.6): câmera colada na parede do lado
        # da entrada, ATRÁS da bancada e empurrada pro lado oposto a ela — a
        # bancada entra em primeiro plano lateral e o box fica no fundo.
        bcx, bcy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        if abs(bcy - cy) >= abs(bcx - cx):          # box no fundo do eixo Y
            near = y1 - WALL_PAD if bcy < cy else y0 + WALL_PAD
            ex = hcx - 0.45 * w if hcx > cx else hcx + 0.45 * w
            eye = (ex, near, EYE_Z)
            tgt = (cx + (hcx - cx) * 0.55,
                   (y0 + d * 0.38) if bcy < cy else (y1 - d * 0.38), TGT_Z)
        else:                                        # box no fundo do eixo X
            near = x1 - WALL_PAD if bcx < cx else x0 + WALL_PAD
            ey = hcy - 0.45 * d if hcy > cy else hcy + 0.45 * d
            eye = (near, ey, EYE_Z)
            tgt = ((x0 + w * 0.38) if bcx < cx else (x1 - w * 0.38),
                   cy + (hcy - cy) * 0.55, TGT_Z)
    else:
        # LAVABO (sem box): o hero É a bancada+espelho — câmera no canto
        # diagonal oposto, mirando o conjunto.
        ex = x1 - WALL_PAD if hcx < cx else x0 + WALL_PAD
        ey = y1 - WALL_PAD if hcy < cy else y0 + WALL_PAD
        eye = (ex, ey, EYE_Z)
        tgt = (hcx, hcy, TGT_Z - 3)

    # Fills no MIOLO: colado em parede a fill esférica projeta a própria
    # silhueta (disco escuro no espelho/halo — gotcha pago no p04 e de novo
    # aqui). Tudo clampado a FILL_PAD das faces.
    def _in(v, lo, hi):
        return min(max(v, lo + FILL_PAD), hi - FILL_PAD) if hi - lo > 2 * FILL_PAD \
            else (lo + hi) / 2

    mx, my = _in(cx, x0, x1), _in(cy, y0, y1)
    hx, hy = _in(hcx, x0, x1), _in(hcy, y0, y1)
    fills = [(mx, my, 72, 30, 10), (mx, _in(y0 + d * 0.25, y0, y1), 68, 36, 8),
             (hx, hy, 55, 34, 9), (hx, hy, 76, 34, 9),
             (mx, _in((cy + hcy) / 2, y0, y1), 88, 18, 10)]
    rects = []
    if box:
        bx0, by0, bx1, by1 = box
        rects.append(((bx0 + bx1) / 2, (by0 + by1) / 2, 93,
                      max(14.0, (bx1 - bx0) / 2), max(12.0, (by1 - by0) / 2), 62))
    return {"room": meta.get("room_name"), "theme": meta.get("theme"),
            "eye": eye, "target": tgt, "fills": fills, "rects": rects}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--room", required=True, help="room_id (r005/r006/r007)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--width", type=int, default=1100)
    ap.add_argument("--height", type=int, default=1375)
    ap.add_argument("--dry", action="store_true", help="só imprime o enquadramento")
    ns = ap.parse_args()

    f = frame(ns.room)
    cmd = [sys.executable, "-m", "tools.render_banho_vray",
           "--eye", ",".join(f"{v:.1f}" for v in f["eye"]),
           "--target", ",".join(f"{v:.1f}" for v in f["target"]),
           "--fov", "60", "--iso", "160", "--shutter", "80", "--fnum", "5.6",
           "--sky", "0.16", "--sun", "0.05", "--burn", "0.5",
           "--hide", "porta,door", "--width", str(ns.width), "--height", str(ns.height),
           "--fill", ";".join(",".join(f"{v:.1f}" for v in fl) for fl in f["fills"]),
           "--out", ns.out]
    if f["rects"]:
        cmd += ["--rect", ";".join(",".join(f"{v:.1f}" for v in r) + ",0,0,-1"
                                   for r in f["rects"])]
    print(json.dumps({k: f[k] for k in ("room", "theme", "eye", "target")}, ensure_ascii=False))
    if ns.dry:
        print(" ".join(cmd))
        return
    subprocess.run(cmd, cwd=ROOT, check=False)


if __name__ == "__main__":
    main()
