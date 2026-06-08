#!/usr/bin/env python3
"""render_parts_iso.py — render iso DETERMINISTICO de pecas-caixa (movel) em PNG, SEM
SketchUp. Cada part = caixa axis-aligned (x0,y0,x1,y1,z0,z1,rgb em m). Sombreamento
simples por face (topo claro -> laterais escuras) pra leitura 3D.

Por que existe: fecha o fidelity loop de MOVEL sem o elo fragil do SU. Mesmo estilo p/
before/after => comparacao VALIDA (render constante; so a geometria muda). NAO substitui
o render canonico SU/V-Ray — e o renderer barato de PROPORCAO/ANATOMIA pro juiz (GPT).
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # noqa: E402

# fator de luz por face (da normal): topo claro, base escura, laterais intermediarias
_SHADE = {"top": 1.0, "bottom": 0.45, "back": 0.80, "front": 0.95, "right": 0.66, "left": 0.78}


def _faces(p):
    x0, y0, z0, x1, y1, z1 = p["x0"], p["y0"], p["z0"], p["x1"], p["y1"], p["z1"]
    return {
        "top":    [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)],
        "bottom": [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0)],
        "front":  [(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)],
        "back":   [(x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1)],
        "left":   [(x0, y0, z0), (x0, y1, z0), (x0, y1, z1), (x0, y0, z1)],
        "right":  [(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)],
    }


def render_parts(parts, out_png, *, title=None, elev=24, azim=-56, bg=(0.82, 0.82, 0.84)):
    fig = plt.figure(figsize=(7.2, 5.4), dpi=150)
    ax = fig.add_subplot(111, projection="3d")
    ax.set_facecolor(bg)
    fig.patch.set_facecolor(bg)
    polys, colors = [], []
    for p in parts:
        r, g, b = (c / 255.0 for c in p["rgb"])
        for fname, quad in _faces(p).items():
            s = _SHADE[fname]
            polys.append(quad)
            colors.append((min(1, r * s), min(1, g * s), min(1, b * s)))
    ax.add_collection3d(Poly3DCollection(polys, facecolors=colors,
                                         edgecolors=(0, 0, 0, 0.22), linewidths=0.3))
    xs = [p["x0"] for p in parts] + [p["x1"] for p in parts]
    ys = [p["y0"] for p in parts] + [p["y1"] for p in parts]
    zs = [p["z0"] for p in parts] + [p["z1"] for p in parts]
    ax.set_xlim(min(xs), max(xs))
    ax.set_ylim(min(ys), max(ys))
    ax.set_zlim(min(zs), max(zs))
    ax.set_box_aspect((max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)))
    ax.view_init(elev=elev, azim=azim)
    ax.set_axis_off()
    if title:
        ax.set_title(title, fontsize=11)
    Path(out_png).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, bbox_inches="tight", facecolor=bg)
    plt.close(fig)
    return str(out_png)
