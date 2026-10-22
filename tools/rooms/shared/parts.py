"""Primitivas de peca compartilhadas pelos builders de movel (Gen1): caixa por papel, cor derivada e posicionamento na planta.

Antes moravam em `shared/sofa.py`, e cama, guarda-roupa, criado-mudo, mesas, rack e decor importavam o modulo do SOFA para
criar uma caixa ou girar um movel (dependencia na direcao errada). Agora o sofa e mais um consumidor; `sofa.py` reexporta os
nomes antigos (`_p`, `_darker`, `parts_to_boxes`, `place_sofa_boxes`) para quem ainda os importa de la.

Convencao de todas as pecas: metros no quadro LOCAL do movel, X = largura, Y = profundidade (frente = -Y), Z = altura,
origem no canto (0, 0, 0). A saida `boxes` e o formato do `place_layout_skp.rb` (polegadas, cantos, h_in, z0_in).
"""
from __future__ import annotations

import math

from core.scale import (
    M_TO_IN as PT_TO_IN,  # noqa: F401  (m -> in; reexportado por quem converte boxes)
)


def darker(rgb, f):
    """Cor `rgb` escurecida pelo fator `f` (0..1), sem sair de 0..255."""
    return [max(0, int(c * f)) for c in rgb]


def part(label, kind, x0, y0, x1, y1, z0, z1, rgb):
    """Peca = caixa alinhada aos eixos locais, normalizada (min/max) e arredondada a 0,1 mm."""
    return {"label": label, "kind": kind,
            "x0": round(min(x0, x1), 4), "y0": round(min(y0, y1), 4),
            "x1": round(max(x0, x1), 4), "y1": round(max(y0, y1), 4),
            "z0": round(z0, 4), "z1": round(z1, 4), "rgb": list(rgb)}


def place_parts(parts, center_in, facing):
    """Posiciona um movel (parts em m, frente = -Y local) na PLANTA: gira para a frente apontar `facing` (vetor 2D) e
    translada o centro para `center_in` (polegadas, coordenadas do shell). Gera cantos girados, entao qualquer angulo vale.
    Custo O(pecas + pontos de perfil)."""
    cx_in, cy_in = center_in
    fx, fy = facing
    nrm = math.hypot(fx, fy) or 1.0
    fx, fy = fx / nrm, fy / nrm
    theta = math.atan2(fx, -fy)        # frente local (0,-1) -> facing
    ct, st = math.cos(theta), math.sin(theta)
    W = max(p["x1"] for p in parts)
    D = max(p["y1"] for p in parts)
    cxl, cyl = W / 2.0, D / 2.0        # centro local do movel
    boxes = []
    for p in parts:
        corners = []
        for lx, ly in ((p["x0"], p["y0"]), (p["x1"], p["y0"]),
                       (p["x1"], p["y1"]), (p["x0"], p["y1"])):
            rx, ry = lx - cxl, ly - cyl
            wx, wy = rx * ct - ry * st, rx * st + ry * ct
            corners.append([round(cx_in + wx * PT_TO_IN, 2), round(cy_in + wy * PT_TO_IN, 2)])
        xs = [c[0] for c in corners]
        ys = [c[1] for c in corners]
        box = {
            "kind": p["kind"], "x0": min(xs), "y0": min(ys), "x1": max(xs), "y1": max(ys),
            "corners": corners,
            "h_in": round((p["z1"] - p["z0"]) * PT_TO_IN, 2),
            "z0_in": round(p["z0"] * PT_TO_IN, 2),
            "rgb": p["rgb"], "label": p["label"], "ambiguous": False, "decorative": False,
        }
        # PERFIL (coroamento/arredondado): carrega a face 3D JA no mundo (mesma rotacao theta + translacao dos corners)
        # + o vetor de extrusao, pro place_layout_skp desenhar as CURVAS em vez de caixa. z do perfil e ABSOLUTO.
        _pxz, _pyz = p.get("profile_xz"), p.get("profile_yz")
        if _pxz or _pyz:
            def _w(lx, ly, lz):
                rx, ry = lx - cxl, ly - cyl
                wx, wy = rx * ct - ry * st, rx * st + ry * ct
                return [round(cx_in + wx * PT_TO_IN, 3),
                        round(cy_in + wy * PT_TO_IN, 3), round(lz * PT_TO_IN, 3)]
            if _pxz:   # face no plano y=y0 local (pts x,z); extruda local +y por (y1-y0)
                dep = (p["y1"] - p["y0"]) * PT_TO_IN
                box["profile_world"] = [_w(px, p["y0"], pz) for (px, pz) in _pxz]
                box["extrude_vec"] = [round(-st * dep, 3), round(ct * dep, 3), 0.0]
            else:      # face no plano x=x0 local (pts y,z); extruda local +x por (x1-x0)
                dep = (p["x1"] - p["x0"]) * PT_TO_IN
                box["profile_world"] = [_w(p["x0"], py, pz) for (py, pz) in _pyz]
                box["extrude_vec"] = [round(ct * dep, 3), round(st * dep, 3), 0.0]
        boxes.append(box)
    return boxes


def parts_to_boxes(parts, ox=0.0, oy=0.0):
    """Converte parts (m) para o formato boxes do place_layout_skp.rb (polegadas), sem girar; `ox`/`oy` deslocam o movel."""
    boxes = []
    for p in parts:
        x0, y0, x1, y1 = (p["x0"] + ox) * PT_TO_IN, (p["y0"] + oy) * PT_TO_IN, \
                         (p["x1"] + ox) * PT_TO_IN, (p["y1"] + oy) * PT_TO_IN
        boxes.append({
            "kind": p["kind"], "x0": x0, "y0": y0, "x1": x1, "y1": y1,
            "corners": [[round(x0, 2), round(y0, 2)], [round(x1, 2), round(y0, 2)],
                        [round(x1, 2), round(y1, 2)], [round(x0, 2), round(y1, 2)]],
            "h_in": round((p["z1"] - p["z0"]) * PT_TO_IN, 2),
            "z0_in": round(p["z0"] * PT_TO_IN, 2),
            "rgb": p["rgb"], "label": p["label"], "ambiguous": False, "decorative": False,
        })
    return boxes
