"""circulation_gate.py — P1 do VERDICT 6.5 (Felipe 2026-08-03): circulação
COMPROVADA, não presumida. "Não basta o móvel entrar geometricamente."

Checks (números do Felipe):
  1. corredor_principal: faixa livre ligando os portais do cômodo social
     (entrada/corredor íntimo, cozinha, varanda) — DOIS thresholds, target
     por PAPEL do portal (não pela largura medida — consulta GPT-Docker
     2026-08-12, 2ª rodada): porta interior_door/interior_passage (espinha
     de distribuição — liga a OUTRO cômodo) é PRIMARY; glazed_balcony/window
     (destino terminal — varanda, não é passagem obrigatória de ninguém) é
     SECONDARY, permanentemente, independente de quanta mobília o cômodo tem.
     Achado 2026-08-12: sofá(ajustado ao nicho)+rack já deixam a faixa da
     varanda no fio da margem (~0.91-0.92m); mesa de jantar (mesmo compacta,
     testada exaustivamente com grid + anti-overlap) SEMPRE fecha essa faixa
     pra 0 sem afetar as portas reais — não é bug de posição, é dois móveis
     grandes dividindo um cômodo compacto. A varanda não é rota que outro
     cômodo depende para ser alcançado (não é ESPINHA), então 0.80m é o
     target correto pra ela, não 0.90m.
       - PRIMARY_TARGET_M (0.90): portais PRIMARY (portas reais).
       - SECONDARY_TARGET_M (0.80): portais SECONDARY (destino terminal, ex.
         varanda) OU PRIMARY cujo shell vazio só oferece 0.80-0.90 (gargalo
         herdado do shell, não da mobília).
       - IMMUTABLE_SHELL_FLOOR_M (0.75): abaixo do target mas >=0.75 já no
         shell vazio — WARN (nao bloqueia), porque a restrição É da planta
         (Hard Rule #1: nunca inventar/alargar parede), mas ainda falha se a
         MOBÍLIA piorar o gargalo em mais de GEOMETRY_TOLERANCE_M.
       - < 0.75 no shell vazio: FAIL_BASE_GEOMETRY_TOO_NARROW — não é
         mobília, é a planta; documentar, não silenciar.
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
# thresholds numéricos vêm de core/project_policy.py (value+source+scope+
# applicability) — achado 2026-08-12 (revisão GPT-Docker): esses números são
# POLICY DE PROJETO (apê residencial planta_74), não lei do engine; outro
# projeto/planta pode exigir valores diferentes. O motor aqui só lê `.value`.
from core.project_policy import (                                      # noqa: E402
    BEHIND_CHAIR_M as _POLICY_BEHIND_CHAIR,
    CHAIR_PULL_M as _POLICY_CHAIR_PULL,
    CIRCULATION_GEOMETRY_TOLERANCE_M as _POLICY_TOLERANCE,
    CIRCULATION_PRIMARY_TARGET_M as _POLICY_PRIMARY,
    CIRCULATION_SECONDARY_TARGET_M as _POLICY_SECONDARY,
    CIRCULATION_SHELL_FLOOR_M as _POLICY_SHELL_FLOOR,
)
CORRIDOR_M = 0.90            # mantido p/ compat (usado pelo 'min_m' do relatorio)
PRIMARY_TARGET_M = _POLICY_PRIMARY.value
SECONDARY_TARGET_M = _POLICY_SECONDARY.value
IMMUTABLE_SHELL_FLOOR_M = _POLICY_SHELL_FLOOR.value
GEOMETRY_TOLERANCE_M = _POLICY_TOLERANCE.value
BEHIND_CHAIR_M = _POLICY_BEHIND_CHAIR.value
PULL_M = _POLICY_CHAIR_PULL.value
WALKABLE_MAX_Z_M = 0.06     # tapete/borda: pisável, não bloqueia
HEAD_MAX_Z0_M = 1.20        # acima disso (aéreo/maleiro/pendente) não bloqueia passo


def _footprint(b):
    if b.get("corners"):
        return Polygon([(c[0], c[1]) for c in b["corners"]])
    return Polygon([(b["x0"], b["y0"]), (b["x1"], b["y0"]),
                    (b["x1"], b["y1"]), (b["x0"], b["y1"])])


def _blockers(boxes):
    """Footprints que de fato bloqueiam passagem (nível do corpo).

    Fonte primária: interaction_policy.circulation declarado (core/spatial_semantics.py)
    — WALKABLE/IGNORE/OVERHEAD nunca bloqueiam, independente de altura (tapete/
    decor/pendente ficam de fora mesmo se algum builder futuro der z0/h_in
    estranho). A checagem de altura (achado original, 2026-08) continua como
    SEGUNDA trava — só ela pode EXCLUIR um item marcado BLOCK que por algum
    motivo esteja alto/fino demais pra bloquear passo; nunca INCLUI algo que a
    política já isentou. Achado 2026-08-12 (consulta GPT-Docker): antes disso
    cada gate tinha sua própria heurística de "isso bloqueia?" — altura aqui,
    bool solto em geometry_sanity, substring em furniture_overlap_gate.
    """
    out = []
    for b in boxes:
        policy = (b.get("interaction_policy") or {}).get("circulation", "BLOCK")
        if policy != "BLOCK":
            continue
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


# Portais cujo 'kind' de abertura NÃO é espinha de distribuição (ninguém
# passa por eles pra chegar em outro cômodo) — destino terminal, target
# SECONDARY mesmo que a largura medida vazia bata 0.90m. Decisão GPT-Docker
# 2026-08-12 (2ª rodada): varanda (glazed_balcony) e janela não classificam
# como PRIMARY só porque o shell vazio é largo ali.
TERMINAL_OPENING_KINDS = {"glazed_balcony", "window"}


def _portal_kind(p, sm):
    """Kind da abertura mais próxima do portal p (door/interior_passage/
    glazed_balcony/...), por proximidade de centro — cada portal já nasce
    projetado a partir de UMA abertura específica."""
    best, bd = None, 1e18
    for o in sm.get("openings") or []:
        ox, oy = o["center"][0] * PT_TO_IN, o["center"][1] * PT_TO_IN
        d = ((p.x - ox) ** 2 + (p.y - oy) ** 2) ** 0.5
        if d < bd:
            best, bd = o.get("kind"), d
    return best


def _connected_at_width(polygon, width_m, pt_a, pt_b):
    """True se pt_a e pt_b caem na MESMA regiao conectada apos erodir
    'polygon' por width_m (corredor livre continuo dessa largura)."""
    eroded = polygon.buffer(-(width_m / 2) * M2IN)
    if eroded.is_empty:
        return False
    regions = list(eroded.geoms) if eroded.geom_type == "MultiPolygon" else [eroded]

    def _region_of(p):
        best, bd = None, 1e18
        for i, r in enumerate(regions):
            d = r.distance(p)
            if d < bd:
                best, bd = i, d
        return best if bd <= 0.30 * M2IN else None

    ra, rb = _region_of(pt_a), _region_of(pt_b)
    return ra is not None and ra == rb


def _bottleneck_width(polygon, pt_a, pt_b, lo=0.50, hi=1.00, tol=0.01):
    """Busca binaria: maior largura de corredor que ainda liga pt_a a pt_b
    dentro de 'polygon'. 0.0 se nem no 'lo' (minimo testado) conecta."""
    if not _connected_at_width(polygon, lo, pt_a, pt_b):
        return 0.0
    if _connected_at_width(polygon, hi, pt_a, pt_b):
        return hi
    while hi - lo > tol:
        mid = (lo + hi) / 2
        if _connected_at_width(polygon, mid, pt_a, pt_b):
            lo = mid
        else:
            hi = mid
    return round(lo, 2)


def gate(con, boxes, room_id):
    from core.spatial_semantics import annotate_all
    annotate_all(boxes)   # idempotente — garante geometry_intent/interaction_policy
    sm = build_spatial_model(con, room_id)
    cell_in = Polygon([(x * PT_TO_IN, y * PT_TO_IN)
                       for x, y in sm["_geom"]["cell"].exterior.coords])
    room = str(sm.get("room_name") or "")
    blockers = _blockers([b for b in boxes
                          if _footprint(b).intersection(cell_in).area > 1.0])
    occ = unary_union([g for _, g in blockers]) if blockers else None
    free = cell_in.difference(occ.buffer(0.5)) if occ is not None else cell_in

    checks: dict = {}

    # 1) corredor principal — dois thresholds + gargalo herdado do shell
    # (ver docstring do modulo; decisao GPT-Docker 2026-08-12).
    portais = _portais(sm, cell_in)
    corr_ok, detail = True, []
    if len(portais) >= 2:
        base_pt = portais[0]   # ancora: primeiro portal (mesmo criterio de sempre)
        for p in portais:
            # portal_role: DECLARADO pelo papel arquitetônico da abertura
            # (kind_v5 — porta real vs destino terminal), não inferido pela
            # largura medida. Explícito pra TODO portal, mesmo a âncora —
            # achado 2026-08-12 (revisão GPT-Docker): "nunca infira semântica
            # por forma/dimensão quando ela pode ser declarada".
            portal_role = ("SECONDARY" if _portal_kind(p, sm) in TERMINAL_OPENING_KINDS
                           else "PRIMARY")
            if p is base_pt:
                detail.append({"portal": [round(p.x, 1), round(p.y, 1)], "portal_role": portal_role,
                               "conectado": True, "status": "PASS", "w_empty_m": None,
                               "w_furnished_m": None})
                continue
            w_empty = _bottleneck_width(cell_in, base_pt, p)
            w_furnished = _bottleneck_width(free, base_pt, p)
            # target por PAPEL da abertura (fixo), não pela largura medida —
            # destino terminal (varanda/janela) nunca vira PRIMARY só porque
            # o shell vazio é largo ali (decisão GPT-Docker 2026-08-12, 2ª
            # rodada). Doors/passagens reais (espinha de distribuição) SEMPRE
            # tentam PRIMARY; se o shell vazio não sustenta, degrada pros
            # tiers abaixo (secundaria/shell_estreito/shell_impossivel) do
            # mesmo jeito que antes.
            role_target = SECONDARY_TARGET_M if portal_role == "SECONDARY" else PRIMARY_TARGET_M
            if w_empty >= role_target:
                target, tier = role_target, ("principal" if role_target == PRIMARY_TARGET_M
                                             else "secundaria")
            elif w_empty >= SECONDARY_TARGET_M:
                target, tier = SECONDARY_TARGET_M, "secundaria"
            elif w_empty >= IMMUTABLE_SHELL_FLOOR_M:
                target, tier = None, "shell_estreito"   # tratado abaixo (WARN)
            else:
                target, tier = None, "shell_impossivel"

            if tier in ("principal", "secundaria"):
                ok = w_furnished >= target
                status = "PASS" if ok else "FAIL_FURNITURE_BLOCKING_CIRCULATION"
            elif tier == "shell_estreito":
                # restricao JA existe na planta vazia (Hard Rule #1: nao
                # inventar/alargar parede) — so falha se a MOBILIA piorar.
                ok = w_furnished >= (w_empty - GEOMETRY_TOLERANCE_M)
                status = "PASS_WARN_BASE_GEOMETRY" if ok else "FAIL_FURNITURE_WORSENS_BASE_GEOMETRY"
            else:  # shell_impossivel
                ok = False
                status = "FAIL_BASE_GEOMETRY_TOO_NARROW"

            corr_ok &= ok
            detail.append({"portal": [round(p.x, 1), round(p.y, 1)], "portal_role": portal_role,
                           "conectado": ok, "status": status, "tier": tier,
                           "w_empty_m": w_empty, "w_furnished_m": w_furnished})
    else:
        detail.append({"erro": "menos de 2 portais no comodo"})
    checks["corredor_principal"] = {"result": "PASS" if corr_ok else "FAIL",
                                    "primary_target_m": PRIMARY_TARGET_M,
                                    "secondary_target_m": SECONDARY_TARGET_M,
                                    "shell_floor_m": IMMUTABLE_SHELL_FLOOR_M,
                                    "portais": detail}

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
