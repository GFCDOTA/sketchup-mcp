"""Interferencia fisica entre geometrias CONSTRUIDAS (FP-055 P4) — area, contato e profundidade DIRECIONAL, separados.

Por que nao so area: uma tolerancia de area deixa passar o que e longo e raso (painel de 1 m entrando 2,5 mm na parede =
25 cm2) e o que e pequeno mas bloqueia um movimento (folha de porta pegando 2 x 10 cm no vaso). Por que nao o circulo inscrito:
ele mede a "gordura" da intersecao, nao quanto um objeto precisa andar para sair do outro. Fica so como metrica complementar.

Definicoes (A = objeto, B = obstaculo; geometria bruta, plano XY, metros):
  area(A, B)            area da intersecao.
  contact_length(A, B)  comprimento do contorno compartilhado (contorno de A dentro de B alargado de EPS_DEPTH).
  separation(A, B, d)   menor t >= 0 tal que area((A + t·d) ∩ B) <= EPS_AREA_FLOOR: quanto A precisa andar NA DIRECAO d
                        para deixar de sobrepor B. Puramente geometrica (sem folga de contato: a folga entra so na
                        CLASSIFICACAO, senao a profundidade sai subestimada em ~EPS_DEPTH). Bissecao, resolucao RES_M.
  mtd(A, B)             min de separation sobre N_DIRS direcoes: a menor translacao que separa (profundidade fisica).
  wall_depth(A, B, n)   min(separation(A, B, n), separation(A, B, -n)) com n = normal da parede: sair da parede pelo lado
                        mais curto, perpendicular a ela.
  outside_depth(A, R)   maior distancia de um ponto de A ate a regiao R (quanto A passa para fora do comodo).
  inscribed(A, B)       diametro do maior circulo inscrito na intersecao — so complementar.
Classificacao: NONE (nao se tocam) · CONTACT (profundidade direcional <= EPS_DEPTH: encosto tangencial com ruido de
arredondamento, qualquer que seja a area) · PENETRATION (profundidade > EPS_DEPTH, qualquer que seja a area). O criterio e explicito e nao depende do tipo de objeto;
o tipo entra na REGRA (parede e porta: qualquer PENETRATION reprova; objetos: idem, exceto pares hospedados/embutidos).

Propagacao do erro numerico:
  o Ruby exporta cada coordenada arredondada a 0,1 mm (SkmcpRuntime.to_m, 4 casas) -> erro <= 0,05 mm por coordenada;
  duas faces que se tocam exatamente podem aparecer sobrepostas ate 0,1 mm (0,05 + 0,05);
  shapely (double) acrescenta erro desprezivel (~1e-12 m nesta escala);
  a bissecao converge a RES_M = 0,05 mm.
  => EPS_DEPTH = 0,5 mm = 5x o pior caso de sobreposicao espuria. Testes: contato exato com ruido +-0,05 mm = CONTACT;
     1 mm de penetracao = PENETRATION.
"""
from __future__ import annotations

import math

from shapely.affinity import translate
from shapely.geometry import LineString, Point

ROUND_M = 0.00005                 # meio passo do arredondamento da exportacao (0,1 mm)
EPS_DEPTH = 0.0005                # 5x a sobreposicao espuria maxima entre dois objetos (2 x ROUND_M)
EPS_AREA_FLOOR = 1e-8             # piso numerico de area (0,01 mm2)
RES_M = 0.00005                   # resolucao da bissecao
N_DIRS = 32


def valid(g):
    """Geometria bruta pode vir invalida (arredondamento de exportacao): reparada com make_valid, nunca descartada."""
    if g is None or g.is_empty or g.is_valid:
        return g
    from shapely import make_valid
    return make_valid(g)


def contact_length(a, b) -> float:
    a, b = valid(a), valid(b)
    if a is None or b is None or a.is_empty or b.is_empty:
        return 0.0
    return a.boundary.intersection(b.buffer(EPS_DEPTH)).length


def _area_after(a, b, d, t) -> float:
    return translate(a, xoff=d[0] * t, yoff=d[1] * t).intersection(b).area


def separation(a, b, d, *, tmax: float | None = None) -> float:
    a, b = valid(a), valid(b)
    n = math.hypot(*d)
    d = (d[0] / n, d[1] / n)
    allow = EPS_AREA_FLOOR
    if _area_after(a, b, d, 0.0) <= allow:
        return 0.0
    hi = tmax if tmax is not None else (math.hypot(a.bounds[2] - a.bounds[0], a.bounds[3] - a.bounds[1])
                                        + math.hypot(b.bounds[2] - b.bounds[0], b.bounds[3] - b.bounds[1]))
    lo = 0.0
    while hi - lo > RES_M:
        mid = (lo + hi) / 2
        if _area_after(a, b, d, mid) <= allow:
            hi = mid
        else:
            lo = mid
    return hi


def mtd(a, b, n_dirs: int = N_DIRS) -> tuple[float, tuple[float, float]]:
    best = (math.inf, (0.0, 0.0))
    for k in range(n_dirs):
        ang = 2 * math.pi * k / n_dirs
        d = (math.cos(ang), math.sin(ang))
        s = separation(a, b, d)
        if s < best[0]:
            best = (s, d)
    return best


def inscribed_diameter(g) -> float:
    """Diametro do maior circulo inscrito (polylabel) — metrica COMPLEMENTAR, nao e profundidade de penetracao."""
    if g is None or g.is_empty or g.area <= 0:
        return 0.0
    return 2 * _mic_radius(g)


def _mic_radius(g) -> float:
    from shapely.ops import polylabel
    parts = getattr(g, "geoms", [g])
    best = 0.0
    for p in parts:
        if p.area <= 0:
            continue
        c = polylabel(p, tolerance=RES_M)
        best = max(best, p.exterior.distance(c) if not p.interiors else p.boundary.distance(c))
    return best


def classify(a, b, *, depth: float | None = None) -> dict:
    """Area, contato, profundidade (a dada, ou a MTD) e circulo inscrito — e a classe."""
    a, b = valid(a), valid(b)
    if a is None or b is None or a.is_empty or b.is_empty or not a.intersects(b):
        return {"class": "NONE", "area_m2": 0.0, "contact_m": 0.0, "depth_m": 0.0, "inscribed_m": 0.0}
    inter = a.intersection(b)
    area, contact = inter.area, contact_length(a, b)
    if depth is None:
        depth, _d = mtd(a, b)
    cls = "PENETRATION" if depth > EPS_DEPTH else "CONTACT"
    return {"class": cls, "area_m2": round(area, 8), "contact_m": round(contact, 5), "depth_m": round(depth, 5),
            "inscribed_m": round(inscribed_diameter(inter), 5)}


def outside_depth(a, region) -> float:
    a, region = valid(a), valid(region)
    if a is None or a.is_empty:
        return 0.0
    out = a.difference(region)
    if out.is_empty or out.area <= EPS_AREA_FLOOR:
        return 0.0
    pts = []
    for g in getattr(out, "geoms", [out]):
        if hasattr(g, "exterior"):
            pts += list(g.exterior.coords)
    return max((region.distance(Point(p)) for p in pts), default=0.0)


def door_open_angle(hinge, leaf_len, along, cross_sign, obstacles, *, leaf_thickness=0.04, step_deg=1.0,
                    max_deg=90.0) -> dict:
    """Movimento funcional: gira a folha a partir de fechada (ao longo de `along`) para o lado `cross_sign` e devolve o
    maior angulo alcancado sem PENETRATION com algum obstaculo (classe acima, profundidade direcional = MTD)."""
    ux, uy = along
    nx, ny = -uy * cross_sign, ux * cross_sign
    reached, hit = 0.0, None
    k = 0
    while k * step_deg <= max_deg + 1e-9:
        th = math.radians(k * step_deg)
        tip = (hinge[0] + leaf_len * (ux * math.cos(th) + nx * math.sin(th)),
               hinge[1] + leaf_len * (uy * math.cos(th) + ny * math.sin(th)))
        leaf = LineString([hinge, tip]).buffer(leaf_thickness / 2, cap_style=2)
        blocked = None
        for name, ob in obstacles.items():
            if leaf.intersects(ob) and classify(leaf, ob)["class"] == "PENETRATION":
                blocked = name
                break
        if blocked:
            hit = blocked
            break
        reached = k * step_deg
        k += 1
    return {"max_open_deg": reached, "blocked_by": hit, "required_deg": max_deg, "ok": reached >= max_deg}
