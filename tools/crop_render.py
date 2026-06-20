"""crop_render.py — corta margens (top/bottom/left/right) de um PNG de render.

GPT NEXT_ACTION recorrente em enquadramento: "ajustar o crop/framebuffer para remover a faixa
cinza inferior SEM aproximar a camera, preservando os moveis inteiros". Crop em POS resolve isso
sem re-render (preserva o framing dos moveis, so remove faixa morta/teto-aberto).

Uso: python tools/crop_render.py <in.png> <out.png> --bottom 180 --top 60 [--left 0 --right 0]
(valores em PIXELS a remover de cada borda)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image


def crop(in_path, out_path, top=0, bottom=0, left=0, right=0):
    im = Image.open(in_path)
    w, h = im.size
    box = (left, top, w - right, h - bottom)
    if box[2] <= box[0] or box[3] <= box[1]:
        raise ValueError(f"crop invalido: {box} de {(w,h)}")
    im.crop(box).save(out_path)
    return im.size, (box[2] - box[0], box[3] - box[1])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("infile"); ap.add_argument("outfile")
    ap.add_argument("--top", type=int, default=0); ap.add_argument("--bottom", type=int, default=0)
    ap.add_argument("--left", type=int, default=0); ap.add_argument("--right", type=int, default=0)
    a = ap.parse_args()
    old, new = crop(a.infile, a.outfile, a.top, a.bottom, a.left, a.right)
    print(f"crop {old} -> {new} :: {a.outfile}")
    sys.exit(0)
