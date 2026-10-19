"""Convencao de montagem do gabinete (caixaria retangular + frentes lisas separadas) e geracao das pecas.

Quadro LOCAL (metros): origem no canto traseiro-esquerdo-inferior; +x = largura (esquerda -> direita vista de frente),
+y = profundidade (do fundo para a frente; a frente aponta para +y), +z = altura. Cada peca e uma caixa alinhada aos
eixos locais `[x0, x1] x [y0, y1] x [z0, z1]`. A pose leva o quadro local ao quadro do projeto: rotacao em torno de +z
(graus, anti-horaria vista de cima) e, depois, translacao da origem local para `pose.{x,y,z}`.

Montagem (nada de folga inventada: todas as medidas vem da requisicao):
- laterais: largura `side`, altura total, profundidade da caixaria `Dc = depth - front - front_clearance`;
- base e topo: entre as laterais, espessura `top_bottom`, profundidade `Dc`;
- fundo: entre as laterais e entre base/topo, espessura `back`, rente a face traseira (y = 0);
- prateleira (opcional): entre as laterais, de `back` a `Dc`, com a base em `shelf.height_from_bottom`;
- frentes lisas: separadas da caixaria por `front_clearance`, na face frontal (y de `depth - front` a `depth`),
  com `front_reveal` nas bordas e entre portas.
"""
from __future__ import annotations

from .model import Params

ROLE_OF_PART = {"side_left": "carcass", "side_right": "carcass", "bottom": "carcass", "top": "carcass",
                "back": "back", "shelf": "shelf", "front": "front"}


def carcass_depth(p: Params) -> float:
    return p.depth - p.front - p.front_clearance


def build_parts(p: Params) -> list[dict]:
    """Pecas em ordem estavel. `id` = `<request_id>/<parte>` (estavel entre reexecucoes e edicoes de parametro)."""
    W, D, H = p.width, p.depth, p.height
    Dc = carcass_depth(p)
    inner0, inner1 = p.side, W - p.side
    parts: list[dict] = []

    def add(name: str, x0: float, x1: float, y0: float, y1: float, z0: float, z1: float) -> None:
        role = ROLE_OF_PART["front" if name.startswith("front") else name]
        parts.append({
            "id": f"{p.request_id}/{name}", "name": name, "role": role,
            "min_m": [x0, y0, z0], "max_m": [x1, y1, z1],
            "size_m": [x1 - x0, y1 - y0, z1 - z0],
            "material": p.materials[role], "grain": p.grain[role],
        })

    add("side_left", 0.0, p.side, 0.0, Dc, 0.0, H)
    add("side_right", W - p.side, W, 0.0, Dc, 0.0, H)
    add("bottom", inner0, inner1, 0.0, Dc, 0.0, p.top_bottom)
    add("top", inner0, inner1, 0.0, Dc, H - p.top_bottom, H)
    add("back", inner0, inner1, 0.0, p.back, p.top_bottom, H - p.top_bottom)
    if p.shelf_count == 1:
        add("shelf", inner0, inner1, p.back, Dc, p.shelf_z, p.shelf_z + p.shelf_t)
    n, r = p.fronts, p.front_reveal
    fw = (W - 2 * r - (n - 1) * r) / n
    for i in range(n):
        x0 = r + i * (fw + r)
        add(f"front_{i + 1}" if n > 1 else "front", x0, x0 + fw, D - p.front, D, r, H - r)
    return parts


def definitions(parts: list[dict]) -> list[dict]:
    """Definicoes compartilhadas SO entre pecas semanticamente equivalentes (mesmo papel, tamanho e material).
    Alteracao local de uma instancia exige `make_unique`; editar a definicao so propaga quando pedido de forma explicita."""
    groups: dict[tuple, list[dict]] = {}
    for part in parts:
        key = (part["role"], tuple(round(v, 9) for v in part["size_m"]), part["material"], part["grain"])
        groups.setdefault(key, []).append(part)
    out = []
    for key, members in groups.items():
        out.append({"key": "def:" + members[0]["name"].rstrip("_0123456789") + ":" + "x".join(f"{v * 1000:.3f}" for v in key[1]),
                    "role": key[0], "size_m": list(key[1]), "material": key[2], "instances": [m["id"] for m in members],
                    "shared": len(members) > 1})
    return out
