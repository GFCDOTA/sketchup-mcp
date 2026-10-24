"""Folgas geometricas compartilhadas entre os brains de comodo: massa das paredes, giro de porta e pegada de caixa.

Tudo em PONTOS do consensus (o quadro dos brains do `shapely`); caixas dos brains vem em POLEGADAS (`corners`), por isso a
conversao `pol / PT_TO_IN`. Nenhuma funcao aqui muda o consensus nem escolhe layout: so mede e devolve geometria.

Por que existe (FP-043/P3a-03): o vao de mobiliar dos brains e a LAJE do comodo, que entra 0,4*espessura sob a parede (D-007),
entao um movel encostado na borda da laje pode ficar DENTRO da parede; e o giro da folha da porta e um quarto de circulo
(largura x largura a partir da dobradica). Usado pela auditoria L1 e pelo recorte do ralo/vidro do banho.
"""
from __future__ import annotations

import math

from shapely.geometry import Polygon
from shapely.ops import unary_union

DOOR_KINDS = ("interior_door",)
EPS_AREA_PT2 = 1e-2          # ~0,07 cm2: ruido de arredondamento dos cantos (0,01 pol), nao penetracao


def wall_mass_pt(con: dict):
    """Massa solida das paredes EXTRUDADAS de verdade (poligono do shell, com vaos recortados), em pontos."""
    from tools.sketchup.shell.build_plan_shell_skp import build_shell_polygon
    pieces, _ = build_shell_polygon(con)
    return unary_union(pieces)


SOFT_BARRIER_THICKNESS_IN = 1.5   # espessura CONSTRUIDA da barreira (`SOFT_BARRIER_THICKNESS_IN` no shell Ruby; teste de contrato textual)


def barrier_is_sourced(sb: dict) -> bool:
    """Mesma regra do shell (`barrier_source` em build_plan_shell_skp.rb): so barreira com tipo, confirmacao humana ou texto do
    PDF vira geometria. Traco sem fonte (sb000-sb007 da planta_74) NAO e construido e nao e barreira para este gate."""
    return bool(str(sb.get("barrier_type") or "").strip() or sb.get("human_confirmed") or sb.get("confirmed")
                or sb.get("pdf_text") or sb.get("source_label"))


def soft_barrier_masses_pt(con: dict) -> list[tuple[str, object, float | None]]:
    """[(id, massa em pontos, altura em m ou None)] de cada guarda-corpo/peitoril/mureta CONSTRUIDO (com fonte), com a espessura que o
    shell constroi (1,5 pol; a laje, em `compute_room_floors`, recua mais: meia parede de cada lado). Altura ausente = None: quem consome trata como barreira
    de qualquer altura (fecha para o lado seguro), nunca inventa uma medida (FP-056 contrato 3)."""
    from shapely.geometry import LineString

    from core.scale import PT_TO_M
    half_pt = SOFT_BARRIER_THICKNESS_IN * 0.0254 / 2.0 / PT_TO_M
    out = []
    for sb in con.get("soft_barriers", []) or []:
        pts = sb.get("polyline_pts") or []
        if len(pts) >= 2 and barrier_is_sourced(sb):
            h = sb.get("height_m")
            out.append((str(sb["id"]), LineString([tuple(p) for p in pts]).buffer(half_pt, cap_style=2, join_style=2),
                        float(h) if h is not None else None))
    return out


def door_swings_pt(con: dict) -> dict[str, Polygon]:
    """Giro da folha de cada porta interior: quarto de circulo (raio = largura do vao) a partir da dobradica, do lado do swing."""
    walls = {w["id"]: w for w in con["walls"]}
    out: dict[str, Polygon] = {}
    for o in con.get("openings", []):
        if o.get("kind") != "door" and o.get("kind_v5") not in DOOR_KINDS:
            continue
        w = walls[o["wall_id"]]
        horiz = abs(w["start"][1] - w["end"][1]) < 1e-6
        cx, cy = o["center"]
        hw = float(o["opening_width_pts"]) / 2
        t = float(w.get("thickness", 5.4)) / 2
        sgn = 1 if o.get("swing_side") == "pos" else -1
        along, cross = (cx, cy) if horiz else (cy, cx)
        h_al = along - hw if o.get("hinge_side") == "left" else along + hw
        u = 1 if o.get("hinge_side") == "left" else -1
        h_cr = cross + sgn * t
        r = 2 * hw
        pts = [(h_al, h_cr)] + [(h_al + u * r * math.cos(a), h_cr + sgn * r * math.sin(a))
                                for a in [k * math.pi / 2 / 24 for k in range(25)]]
        out[o["id"]] = Polygon([(a, c) if horiz else (c, a) for a, c in pts])
    return out


def box_footprint_pt(box: dict, pt_to_in: float) -> Polygon | None:
    """Pegada (pontos) de uma caixa dos brains (cantos em polegadas)."""
    if not box.get("corners"):
        return None
    return Polygon([(c[0] / pt_to_in, c[1] / pt_to_in) for c in box["corners"]]).buffer(0)


def depth_cm(inter, pt_to_m: float) -> float:
    """Profundidade aproximada da interseção (area / maior dimensao), em cm — mesma definicao do L2 FP-042."""
    minx, miny, maxx, maxy = inter.bounds
    return round(inter.area * pt_to_m**2 / max((maxx - minx) * pt_to_m, (maxy - miny) * pt_to_m, 1e-9) * 100, 1)


def to_inches(geom, pt_to_in: float):
    """Geometria em pontos -> polegadas (o quadro dos boxes dos brains)."""
    from shapely.affinity import scale
    return scale(geom, pt_to_in, pt_to_in, origin=(0, 0))


def obstacles_in(con: dict, pt_to_in: float):
    """(massa de parede, {porta: giro}) ja em polegadas, para filtrar candidatos de mobilia."""
    return (to_inches(wall_mass_pt(con), pt_to_in),
            {k: to_inches(v, pt_to_in) for k, v in door_swings_pt(con).items()})


def clip_box_outside(box: dict, wall_in) -> dict | None:
    """Corta uma caixa AXIAL (cantos em polegadas) para fora da massa de parede; None se nada sobra.

    So para pecas finas e rentes ao chao que o desenho estende ate a parede (ralo linear, painel de vidro): encurta o
    comprimento em vez de enterrar a ponta. Mantem todos os demais campos da caixa.
    """
    fp = Polygon(box["corners"])
    if fp.intersection(wall_in).area < EPS_AREA_PT2:
        return box
    rest = fp.difference(wall_in)
    if rest.is_empty:
        return None
    if rest.geom_type != "Polygon":
        rest = max(rest.geoms, key=lambda g: g.area)
    x0, y0, x1, y1 = (round(v, 2) for v in rest.bounds)
    return {**box, "x0": x0, "y0": y0, "x1": x1, "y1": y1, "corners": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]}

