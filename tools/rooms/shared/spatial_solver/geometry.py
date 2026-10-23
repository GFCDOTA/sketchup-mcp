"""Geometria COMPARTILHADA do solver espacial (FP-054 F2B): uma unica implementacao das medicoes usadas pela validacao
(F1B/F1C) e pelo solver (F2). Polegadas do plano para geometria, metros para medidas; tolerancias em `core.units`.

- `_free_without`: espaco livre do comodo sem a peca avaliada (bloqueio = regra do circulation_gate, folga 0,5 in);
- `usable_face`: trecho da interface que da para o espaco livre; `measure_front` (bissecao da profundidade livre);
- `measure_entry_width`: vao livre de entrada; `measure_reach`: maior largura portal -> zona de uso, com regiao alcancavel
  e GARGALO como testemunha (conectividade no espaco erodido por w/2, regioes cacheadas por (poligono, largura)).
Robustez: comparacoes de contencao usam `buffer(1e-6)`; bissecoes com resolucao de 0,5 cm (folga) e 1 cm (passagem).
"""
from __future__ import annotations

import math

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import nearest_points, unary_union

M2IN = 39.3700787402
PORTAL_SNAP_M = 0.30           # mesma tolerancia do `circulation_gate._region_of`
SEARCH_MAX_M = 2.0


def _front_rect(face: LineString, n, depth_in: float, inset_in: float = 0.5) -> Polygon:
    (x0, y0), (x1, y1) = face.coords
    ux, uy = (x1 - x0), (y1 - y0)
    L = math.hypot(ux, uy) or 1.0
    ux, uy = ux / L, uy / L
    inset_in = min(inset_in, L / 4)
    a = (x0 + ux * inset_in, y0 + uy * inset_in)
    b = (x1 - ux * inset_in, y1 - uy * inset_in)
    return Polygon([a, b, (b[0] + n[0] * depth_in, b[1] + n[1] * depth_in), (a[0] + n[0] * depth_in, a[1] + n[1] * depth_in)])


def _bisect(fits, lo=0.0, hi=SEARCH_MAX_M, tol=0.005) -> float:
    if not fits(tol):
        return 0.0
    if fits(hi):
        return hi
    lo = tol
    while hi - lo > tol:
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if fits(mid) else (lo, mid)
    return round(lo, 3)


def measure_front(face, n, free: Polygon) -> float:
    room = free.buffer(1e-6)
    return _bisect(lambda d: room.contains(_front_rect(face, n, d * M2IN)))


def usable_face(face: LineString, n, free: Polygon) -> LineString | None:
    """Maior trecho da interface que da para o espaco livre (sondado 1 in a frente), devolvido SOBRE a linha da interface.
    Ex.: a ponta do vao do box encostada no revestimento da parede sai; o resto e o vao usavel. None = nada livre."""
    probe = LineString([(x + n[0] * 1.0, y + n[1] * 1.0) for x, y in face.coords]).intersection(free.buffer(1e-6))
    parts = [g for g in getattr(probe, "geoms", [probe]) if not g.is_empty and g.geom_type == "LineString"]
    if not parts:
        return None
    best = max(parts, key=lambda g: g.length)
    return LineString([(x - n[0] * 1.0, y - n[1] * 1.0) for x, y in best.coords])


def measure_entry_width(face: LineString, n, free: Polygon) -> float:
    """Largura livre do vao de entrada (m) = comprimento do trecho usavel da entrada."""
    u = usable_face(face, n, free)
    return 0.0 if u is None else round(u.length / M2IN, 3)


def _reach_components(wkb, portals, w):
    from tools.validation.circulation_gate import _eroded_regions
    regions = _eroded_regions(wkb, w)
    near = [r for r in regions if any(r.distance(p) <= PORTAL_SNAP_M * M2IN for p in portals)]
    return regions, near


def measure_reach(free: Polygon, portals: list[Point], zone: Polygon) -> tuple[float, dict]:
    """Maior largura (m) de passagem portal -> zona de uso (0.0 = desconectado ate 0,30 m) + testemunha geometrica."""
    wkb = free.wkb

    def reaches(w):
        return any(r.intersects(zone) for r in _reach_components(wkb, portals, w)[1])
    lo = 0.30
    if not reaches(lo):
        regions, near = _reach_components(wkb, portals, lo)
        gap = _gap_witness(near, [r for r in regions if r not in near], zone)
        return 0.0, {"reachable_region_m": None, "reachable_region": _multi_coords(unary_union(near) if near else None),
                     "bottleneck": gap}
    w = 1.50 if reaches(1.50) else max(_bisect(reaches, lo=lo, hi=1.50, tol=0.01), lo)
    _, near_w = _reach_components(wkb, portals, w)
    comp = unary_union([r for r in near_w if r.intersects(zone)])
    regions_up, near_up = _reach_components(wkb, portals, round(w + 0.02, 3))
    gap = None
    if w < 1.50:
        gap = _gap_witness(near_up, [r for r in regions_up if r not in near_up and r.intersects(zone.buffer(w * M2IN))], zone)
        if gap is None and portals:                 # com w + 2 cm a regiao do proprio portal some: o gargalo e a entrada
            pt = [round(portals[0].x, 2), round(portals[0].y, 2)]
            gap = {"point": pt, "segment": [pt, pt], "at": "portal"}
        if gap:
            gap["width_m"] = w
    return w, {"reachable_region_m": w, "reachable_region": _multi_coords(comp), "bottleneck": gap}


def _gap_witness(portal_side, zone_side, zone):
    """Ponto do gargalo: meio do menor segmento entre o lado do portal e o lado da zona quando a passagem se rompe."""
    if not portal_side:
        return None
    a = unary_union(portal_side)
    b = unary_union(zone_side) if zone_side else zone
    pa, pb = nearest_points(a, b)
    return {"point": [round((pa.x + pb.x) / 2, 2), round((pa.y + pb.y) / 2, 2)],
            "segment": [[round(pa.x, 2), round(pa.y, 2)], [round(pb.x, 2), round(pb.y, 2)]]}


def _multi_coords(geom, nd=1):
    if geom is None or geom.is_empty:
        return []
    return [[[round(x, nd), round(y, nd)] for x, y in g.exterior.coords] for g in getattr(geom, "geoms", [geom])]


def _coords(geom, nd=2):
    return [[round(x, nd), round(y, nd)] for x, y in geom.exterior.coords] if geom is not None and not geom.is_empty else []


def _free_without(cell, room_boxes, module):
    from tools.validation import circulation_gate as cg
    blockers = cg._blockers([b for b in room_boxes if b.get("module") != module])
    occ = unary_union([g for _, g in blockers]) if blockers else None
    return cell.difference(occ.buffer(0.5)) if occ is not None else cell
