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


def _faces_from_verts8(v):
    """6 faces de um box dado por 8 vertices [b0..b3 base, t0..t3 topo] — p/ pecas
    NAO-axis-aligned (ex. encosto inclinado pelo backrest_rake)."""
    return {"bottom": [v[0], v[1], v[2], v[3]], "top": [v[4], v[5], v[6], v[7]],
            "front": [v[0], v[1], v[5], v[4]], "back": [v[3], v[2], v[6], v[7]],
            "left": [v[0], v[3], v[7], v[4]], "right": [v[1], v[2], v[6], v[5]]}


# luz fixa p/ pecas de PERFIL (roundover real, FP-SOFA-PREMIUM): determinismo
# igual ao _SHADE nominal — topo claro, frente quase-clara, base escura.
_LIGHT = (-0.28, -0.42, 0.86)


def _shade_from_normal(n):
    """Brilho [0.45..1.0] pelo cosseno normal·luz — perfis curvos ganham o
    gradiente que denuncia o raio no clay (a razao de existir do roundover)."""
    import math
    nx, ny, nz = n
    ln = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
    d = (nx * _LIGHT[0] + ny * _LIGHT[1] + nz * _LIGHT[2]) / ln
    return 0.45 + 0.55 * max(0.0, d)


def _faces_from_profile_xz(p):
    """[(quad_ou_ngon, shade)] de um PERFIL 2D em (x,z) extrudado em Y
    (p['profile_xz'] = poligono CCW; y0..y1 = extrusao). Tampas nas duas
    pontas + um quad por aresta do perfil, sombreado pela normal real."""
    pts = p["profile_xz"]
    y0, y1 = p["y0"], p["y1"]
    out = [([(x, y0, z) for (x, z) in pts], _shade_from_normal((0, -1, 0))),
           ([(x, y1, z) for (x, z) in pts], _shade_from_normal((0, 1, 0)))]
    n = len(pts)
    for i in range(n):
        (xa, za), (xb, zb) = pts[i], pts[(i + 1) % n]
        quad = [(xa, y0, za), (xb, y0, zb), (xb, y1, zb), (xa, y1, za)]
        # normal 2D da aresta no plano (x,z), CCW -> normal externa = (dz, -dx)
        out.append((quad, _shade_from_normal((zb - za, 0.0, -(xb - xa)))))
    return out


def render_parts(parts, out_png, *, title=None, elev=24, azim=-56, bg=(0.82, 0.82, 0.84)):
    fig = plt.figure(figsize=(7.2, 5.4), dpi=150)
    ax = fig.add_subplot(111, projection="3d")
    ax.set_facecolor(bg)
    fig.patch.set_facecolor(bg)
    polys, colors, edges = [], [], []
    for p in parts:
        r, g, b = (c / 255.0 for c in p["rgb"])
        ec = (0, 0, 0, 0.22) if p.get("edge", True) else (0, 0, 0, 0.0)
        if p.get("profile_xz"):
            shaded = _faces_from_profile_xz(p)
        elif p.get("verts8"):
            shaded = [(q, _SHADE[n]) for n, q in _faces_from_verts8(p["verts8"]).items()]
        else:
            shaded = [(q, _SHADE[n]) for n, q in _faces(p).items()]
        for quad, s in shaded:
            polys.append(quad)
            colors.append((min(1, r * s), min(1, g * s), min(1, b * s)))
            edges.append(ec)
    ax.add_collection3d(Poly3DCollection(polys, facecolors=colors,
                                         edgecolors=edges, linewidths=0.3))
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
