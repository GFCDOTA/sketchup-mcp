"""circulation_gate.py — P1 do VERDICT 6.5 (Felipe 2026-08-03): circulação
COMPROVADA, não presumida. "Não basta o móvel entrar geometricamente."

Checks (números do Felipe):
  1. corredor_principal: faixa livre CONTÍNUA >= 0.90m ligando os portais do
     cômodo social (entrada/corredor íntimo, cozinha, varanda) — via erosão do
     espaço livre por 0.45 e conectividade entre os portais.
  2. atras_das_cadeiras: >= 0.70m entre o encosto de cada cadeira e o obstáculo
     mais próximo (parede/móvel).
  3. cadeira_puxada: o envelope da cadeira PUXADA (recuo de 0.50m a partir da
     mesa) cabe no espaço livre — sem colidir com parede ou móvel.

Uso: gate(con, boxes, room_id) -> {"result": PASS|FAIL, "checks": {...}}
Obstáculo = box com z0 < 1.20m e altura real (tapete/decorativo não bloqueia).
Determinístico, shapely puro, sem I/O.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shapely.geometry import Point, Polygon           # noqa: E402
from shapely.ops import unary_union                   # noqa: E402

from core.scale import PT_TO_IN                       # noqa: E402
from tools.spatial_model import build_spatial_model   # noqa: E402

M2IN = 39.3700787402
CORRIDOR_M = 0.90
BEHIND_CHAIR_M = 0.70
PULL_M = 0.50
WALKABLE_MAX_Z_M = 0.06     # tapete/borda: pisável, não bloqueia
HEAD_MAX_Z0_M = 1.20        # acima disso (aéreo/maleiro/pendente) não bloqueia passo


def _footprint(b):
    if b.get("corners"):
        return Polygon([(c[0], c[1]) for c in b["corners"]])
    return Polygon([(b["x0"], b["y0"]), (b["x1"], b["y0"]),
                    (b["x1"], b["y1"]), (b["x0"], b["y1"])])


def _blockers(boxes):
    """Footprints que de fato bloqueiam passagem (nível do corpo)."""
    out = []
    for b in boxes:
        z0 = (b.get("z0_in") or 0) / M2IN
        top = z0 + (b.get("h_in") or 0) / M2IN
        if z0 >= HEAD_MAX_Z0_M:            # pendurado alto (pendente, maleiro, LED)
            continue
        if top <= WALKABLE_MAX_Z_M:        # tapete/rodapé fino: pisável
            continue
        out.append((b, _footprint(b)))
    return out


def _portais(sm, cell_in):
    """Pontos de acesso do cômodo: centro de cada zona de porta/passagem,
    projetado pra DENTRO do cell (2 passos de 0.25m na normal)."""
    pts = []
    for dz in (sm["_geom"].get("circ") or []):
        c = dz.centroid
        p = Point(c.x * PT_TO_IN, c.y * PT_TO_IN)
        if not cell_in.contains(p):
            q = cell_in.exterior.interpolate(cell_in.exterior.project(p))
            v = (q.x - p.x, q.y - p.y)
            n = (v[0] ** 2 + v[1] ** 2) ** 0.5 or 1.0
            p = Point(q.x + v[0] / n * 0.25 * M2IN, q.y + v[1] / n * 0.25 * M2IN)
        if cell_in.contains(p):
            pts.append(p)
    return pts


def gate(con, boxes, room_id):
    sm = build_spatial_model(con, room_id)
    cell_in = Polygon([(x * PT_TO_IN, y * PT_TO_IN)
                       for x, y in sm["_geom"]["cell"].exterior.coords])
    room = str(sm.get("room_name") or "")
    blockers = _blockers([b for b in boxes
                          if _footprint(b).intersection(cell_in).area > 1.0])
    occ = unary_union([g for _, g in blockers]) if blockers else None
    free = cell_in.difference(occ.buffer(0.5)) if occ is not None else cell_in

    checks: dict = {}

    # 1) corredor principal contínuo >= 0.90 entre portais
    eroded = free.buffer(-(CORRIDOR_M / 2) * M2IN)
    portais = _portais(sm, cell_in)
    corr_ok, detail = True, []
    if len(portais) >= 2 and not eroded.is_empty:
        regions = list(eroded.geoms) if eroded.geom_type == "MultiPolygon" else [eroded]

        def _region_of(p):
            best, bd = None, 1e18
            for i, r in enumerate(regions):
                d = r.distance(p)
                if d < bd:
                    best, bd = i, d
            return best if bd <= 0.30 * M2IN else None

        rids = [_region_of(p) for p in portais]
        base = next((r for r in rids if r is not None), None)
        for p, r in zip(portais, rids):
            ok = (r is not None) and (r == base)
            corr_ok &= ok
            detail.append({"portal": [round(p.x, 1), round(p.y, 1)], "conectado": ok})
    elif eroded.is_empty:
        corr_ok = False
        detail.append({"erro": "nenhuma faixa de 0.90m sobrou no cômodo"})
    checks["corredor_principal"] = {"result": "PASS" if corr_ok else "FAIL",
                                    "min_m": CORRIDOR_M, "portais": detail}

    # 2/3) cadeiras: 0.70 atrás + envelope PUXADA
    mesa = [g for b, g in blockers if str(b.get("module", "")).startswith("Mesa de jantar")]
    mesa_u = unary_union(mesa) if mesa else None
    # Agrupar as partes (foot/frame/seat/back) de CADA cadeira por INSTANCIA:
    # round(centroid.x) quebra pra cadeiras giradas 90 graus (nas pontas da
    # mesa) — o encosto/pernas dessas cadeiras variam em X quase tanto quanto
    # a distancia entre cadeiras vizinhas, e a peca vira "cadeira fantasma"
    # com folga zero (bug pago: 16 clusters pra 6 cadeiras reais). Fix:
    # clusteriza por PROXIMIDADE geometrica real (buffer pequeno + uniao) —
    # as partes de uma mesma cadeira ficam bem mais perto entre si (<0.5m)
    # do que a distancia real entre cadeiras (~0.7m+).
    cad_geoms = [g for b, g in blockers if str(b.get("module", "")).startswith("Cadeira")]
    cad: dict[int, list] = {}
    if cad_geoms:
        CLUSTER_PAD_IN = 0.08 * M2IN   # funde partes DA MESMA cadeira (quase encostadas),
        # bem abaixo do espacamento real entre cadeiras vizinhas (~0.21m de gap)
        merged = unary_union([g.buffer(CLUSTER_PAD_IN) for g in cad_geoms])
        clusters = list(merged.geoms) if merged.geom_type == "MultiPolygon" else [merged]
        for g in cad_geoms:
            ci = next(i for i, c in enumerate(clusters) if c.intersects(g))
            cad.setdefault(ci, []).append(g)
    behind_ok, pull_ok, cdetail = True, True, []
    if mesa_u is not None and cad:
        others = unary_union([g for b, g in blockers
                              if not str(b.get("module", "")).startswith(("Cadeira", "Mesa de jantar"))])
        for key, gs in cad.items():
            cg = unary_union(gs)
            c = cg.centroid
            m = mesa_u.centroid
            v = (c.x - m.x, c.y - m.y)
            n = (v[0] ** 2 + v[1] ** 2) ** 0.5 or 1.0
            ux, uy = v[0] / n, v[1] / n
            back = Point(c.x + ux * 0.25 * M2IN, c.y + uy * 0.25 * M2IN)
            livre_atras = min(cell_in.exterior.distance(back) / M2IN,
                              (others.distance(back) / M2IN) if not others.is_empty else 9.9)
            b_ok = livre_atras >= BEHIND_CHAIR_M - 0.25   # -0.25: 'back' já está 0.25 fora da cadeira
            pulled = Polygon([(p[0] + ux * PULL_M * M2IN, p[1] + uy * PULL_M * M2IN)
                              for p in cg.convex_hull.exterior.coords])
            p_ok = cell_in.contains(pulled) and (others.is_empty or others.intersection(pulled).area < 4.0)
            behind_ok &= b_ok
            pull_ok &= p_ok
            cdetail.append({"cadeira": [round(c.x, 1), round(c.y, 1)],
                            "livre_atras_m": round(livre_atras, 2),
                            "atras_ok": b_ok, "puxada_ok": p_ok})
    checks["atras_das_cadeiras"] = {"result": "PASS" if behind_ok else "FAIL",
                                    "min_m": BEHIND_CHAIR_M, "cadeiras": cdetail}
    checks["cadeira_puxada"] = {"result": "PASS" if pull_ok else "FAIL", "recuo_m": PULL_M}

    result = "PASS" if all(c["result"] == "PASS" for c in checks.values()) else "FAIL"
    return {"result": result, "room": room, "checks": checks}


def main():
    import json
    from tools.furnish_apartment import CONSENSUS, collect_boxes
    con = json.loads(CONSENSUS.read_text("utf-8"))
    boxes, _ = collect_boxes(con)
    out = gate(con, boxes, "r002")
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0 if out["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
