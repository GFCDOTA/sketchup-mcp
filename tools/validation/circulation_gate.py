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

Uso: gate(con, boxes, room_id) -> {"result": PASS|FAIL|BLOCKED_MISSING_INPUT|NOT_APPLICABLE, "checks": {...},
"constraints": [ConstraintResult...]} (FP-054 F1, #380): sem portal (ou portal sem ponto interno) o corredor fica
BLOCKED_MISSING_INPUT; com 1 portal, NOT_APPLICABLE; sem conjunto de jantar, as cadeiras ficam NOT_APPLICABLE. O
resultado agrega por `core.constraint_result.combine` — nada medido nunca vira PASS.
Obstáculo = box com z0 < 1.20m e altura real (tapete/decorativo não bloqueia).
Determinístico, shapely puro, sem I/O.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from functools import lru_cache                       # noqa: E402
from shapely import wkb                               # noqa: E402
from shapely.geometry import Point, Polygon           # noqa: E402
from shapely.ops import unary_union                   # noqa: E402

from core.constraint_result import ConstraintResult, combine  # noqa: E402
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
    """Pontos de acesso do cômodo (só os pontos; ver `_portal_points`)."""
    return _portal_points(sm, cell_in)[0]


def _portal_points(sm, cell_in):
    """Pontos de acesso do cômodo: centro de cada zona de porta/passagem,
    projetado pra DENTRO do cell (um passo de 0.25m na normal). Devolve
    (pontos, descartados): zona cujo ponto não cai dentro do cômodo NÃO some
    em silêncio (FP-054 #380) — vira entrada faltante e bloqueia o corredor."""
    pts, dropped = [], []
    for i, dz in enumerate(sm["_geom"].get("circ") or []):
        c = dz.centroid
        p = Point(c.x * PT_TO_IN, c.y * PT_TO_IN)
        if not cell_in.contains(p):
            q = cell_in.exterior.interpolate(cell_in.exterior.project(p))
            v = (q.x - p.x, q.y - p.y)
            n = (v[0] ** 2 + v[1] ** 2) ** 0.5 or 1.0
            p = Point(q.x + v[0] / n * 0.25 * M2IN, q.y + v[1] / n * 0.25 * M2IN)
        if cell_in.contains(p):
            pts.append(p)
        else:
            dropped.append({"zone": i, "why": "ponto do portal fora do comodo depois da projecao"})
    return pts, dropped


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


@lru_cache(maxsize=2048)
def _eroded_regions(polygon_wkb: bytes, width_m: float) -> tuple:
    """Regioes livres de `polygon` erodido por width_m. Funcao pura de (poligono, largura): a busca binaria de cada portal,
    os varios portais de um comodo e as ~95 chamadas do gate por apartamento repetem as mesmas larguras (0.50, 1.00, 0.75...)
    sobre o MESMO poligono (o comodo vazio, sobretudo). Cache limitado (2048 entradas) troca ~54 mil `buffer` por algumas
    centenas — medido em docs/reports/construction_core/geometry_hot_paths.md."""
    eroded = wkb.loads(polygon_wkb).buffer(-(width_m / 2) * M2IN)
    if eroded.is_empty:
        return ()
    return tuple(eroded.geoms) if eroded.geom_type == "MultiPolygon" else (eroded,)


def _connected_at_width(polygon, width_m, pt_a, pt_b):
    """True se pt_a e pt_b caem na MESMA regiao conectada apos erodir
    'polygon' por width_m (corredor livre continuo dessa largura)."""
    regions = _eroded_regions(polygon.wkb, width_m)
    if not regions:
        return False

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


def corridor_slack_m(result: dict) -> float | None:
    """Folga do corredor num resultado do `gate`: menor (largura mobiliada - largura exigida) entre os portais medidos.
    Exigida = alvo do tier (principal/secundaria) ou a largura do shell vazio menos a tolerancia (shell_estreito).
    Usada para ORDENAR buscas (quem tem mais folga sobrevive melhor a um deslize); nao muda o veredito do gate.
    None se nenhum portal foi medido."""
    slacks = []
    for p in result.get("checks", {}).get("corredor_principal", {}).get("portais", []):
        w, tier = p.get("w_furnished_m"), p.get("tier")
        if w is None:
            continue
        if tier == "principal":
            slacks.append(w - PRIMARY_TARGET_M)
        elif tier == "secundaria":
            slacks.append(w - SECONDARY_TARGET_M)
        elif tier == "shell_estreito" and p.get("w_empty_m") is not None:
            slacks.append(w - (p["w_empty_m"] - GEOMETRY_TOLERANCE_M))
    return round(min(slacks), 4) if slacks else None


def verdict_note(result: dict, context: str) -> str:
    """Frase de registro para quem aceita PASS ou NOT_APPLICABLE (ex.: gates de plano da cozinha): diz QUAL dos dois foi
    e, no N/A, por que nada foi medido — para nenhum registro chamar de PASS o que nao se mediu."""
    if result["result"] == "PASS":
        return f"zonas de porta livres e circulation_gate PASS {context}"
    reasons = "; ".join(f"{k}: {v.get('reason_code')}" for k, v in sorted(result.get("checks", {}).items()))
    return f"zonas de porta livres; circulation_gate {result['result']} {context} ({reasons}) — nada medido, nao e PASS"


def gate(con, boxes, room_id, *, decide_only: bool = False):
    """Gate de circulacao do comodo. Com `decide_only=True` (para BUSCAS, que so precisam do veredito): checa as cadeiras
    primeiro (barato) e para no primeiro portal que reprova — o `result` e EXATAMENTE o do gate completo (FAIL se qualquer
    check falha); num FAIL antecipado `checks` vem vazio e `decided_by` diz quem reprovou. Num PASS todos os checks foram
    calculados e a saida e a mesma do modo normal (a busca usa o detalhe para a folga do corredor)."""
    return GateSession(con, [], room_id).check(boxes, decide_only=decide_only)


class GateSession:
    """O mesmo gate, para BUSCAS que testam muitos candidatos contra a mesma sala e a mesma mobilia fixa: o que so depende
    do comodo (modelo espacial, celula, portais e seus papeis) e da mobilia fixa (anotacao + pegadas que bloqueiam) e
    calculado UMA vez; cada `check(extra)` processa so as caixas do candidato. Resultado identico a
    `gate(con, base + extra, room_id)`: `annotate_all` e `_blockers` trabalham caixa a caixa, entao a lista de bloqueios
    tem os mesmos itens na mesma ordem (base depois candidato)."""

    def __init__(self, con, base_boxes, room_id):
        # PREGUICOSA: nada e calculado nem anotado ate o 1o `check` — exatamente quando o gate antigo anotava as caixas.
        # (Anotar na criacao mudava `_semantics_provenance` de caixas que nenhum candidato chegou a testar.)
        self._args = (con, base_boxes, room_id)
        self._ready = False

    def _prepare(self):
        from core.spatial_semantics import annotate_all
        con, base_boxes, room_id = self._args
        annotate_all(base_boxes)   # idempotente — garante geometry_intent/interaction_policy
        self.sm = sm = build_spatial_model(con, room_id)
        self.cell_in = Polygon([(x * PT_TO_IN, y * PT_TO_IN)
                                for x, y in sm["_geom"]["cell"].exterior.coords])
        self.room = str(sm.get("room_name") or "")
        self._base_blockers = self._blockers_in_cell(base_boxes)
        self.portais, self.dropped_portals = _portal_points(sm, self.cell_in)
        # portal_role: DECLARADO pelo papel arquitetônico da abertura (kind_v5 — porta real vs destino terminal), não
        # inferido pela largura medida (achado 2026-08-12, revisão GPT-Docker).
        self.roles = [("SECONDARY" if _portal_kind(p, sm) in TERMINAL_OPENING_KINDS else "PRIMARY")
                      for p in self.portais]

    def _blockers_in_cell(self, boxes):
        return _blockers([b for b in boxes if _footprint(b).intersection(self.cell_in).area > 1.0])

    def check(self, extra_boxes, *, decide_only: bool = False):
        from core.spatial_semantics import annotate_all
        if not self._ready:
            self._prepare()
            self._ready = True
        annotate_all(extra_boxes)
        cell_in, room = self.cell_in, self.room
        blockers = self._base_blockers + self._blockers_in_cell(extra_boxes)
        if decide_only:
            chair_result = _chair_checks(blockers, cell_in)
            if chair_result[3] is None and not (chair_result[0] and chair_result[1]):
                return {"result": "FAIL", "room": room, "checks": {}, "constraints": [], "decided_by": "cadeiras"}
        occ = unary_union([g for _, g in blockers]) if blockers else None
        free = cell_in.difference(occ.buffer(0.5)) if occ is not None else cell_in

        checks: dict = {}

        # 1) corredor principal — dois thresholds + gargalo herdado do shell
        # (ver docstring do modulo; decisao GPT-Docker 2026-08-12).
        portais = self.portais
        corr_ok, detail = True, []
        # Sem portal medivel o corredor NAO e PASS (FP-054 #380): portal descartado ou ausente bloqueia; portal unico
        # (comodo de passagem unica) e NOT_APPLICABLE explicito. So >= 2 portais sao medidos.
        corr_status, corr_reason = None, None
        if self.dropped_portals:
            corr_status, corr_reason = "BLOCKED_MISSING_INPUT", "PORTAL_WITHOUT_INNER_POINT"
            detail.append({"erro": "portal sem ponto interno no comodo", "descartados": self.dropped_portals})
        elif not portais:
            corr_status, corr_reason = "BLOCKED_MISSING_INPUT", "NO_PORTAL"
            detail.append({"erro": "nenhum portal no comodo"})
        elif len(portais) == 1:
            corr_status, corr_reason = "NOT_APPLICABLE", "SINGLE_PORTAL"
            detail.append({"erro": "menos de 2 portais no comodo"})
        if corr_status is None:
            base_pt = portais[0]   # ancora: primeiro portal (mesmo criterio de sempre)
            for p, portal_role in zip(portais, self.roles):
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

                if decide_only and not ok:
                    return {"result": "FAIL", "room": room, "checks": {}, "constraints": [], "decided_by": "corredor"}
                corr_ok &= ok
                detail.append({"portal": [round(p.x, 1), round(p.y, 1)], "portal_role": portal_role,
                               "conectado": ok, "status": status, "tier": tier,
                               "w_empty_m": w_empty, "w_furnished_m": w_furnished})
            corr_status, corr_reason = ("PASS", "CORRIDOR_CONNECTED") if corr_ok else ("FAIL", "CORRIDOR_BLOCKED")
        checks["corredor_principal"] = {"result": corr_status, "reason_code": corr_reason,
                                        "primary_target_m": PRIMARY_TARGET_M,
                                        "secondary_target_m": SECONDARY_TARGET_M,
                                        "shell_floor_m": IMMUTABLE_SHELL_FLOOR_M,
                                        "portais": detail}

        # 2/3) cadeiras: 0.70 atrás + envelope PUXADA (N/A sem conjunto de jantar — nada a medir nao e PASS)
        behind_ok, pull_ok, cdetail, chairs_na = chair_result if decide_only else _chair_checks(blockers, cell_in)
        if chairs_na:
            behind_st = pull_st = "NOT_APPLICABLE"
        else:
            behind_st, pull_st = ("PASS" if behind_ok else "FAIL"), ("PASS" if pull_ok else "FAIL")
        checks["atras_das_cadeiras"] = {"result": behind_st, "reason_code": chairs_na or "MEASURED",
                                        "min_m": BEHIND_CHAIR_M, "cadeiras": cdetail}
        checks["cadeira_puxada"] = {"result": pull_st, "reason_code": chairs_na or "MEASURED", "recuo_m": PULL_M}

        constraints = [_corridor_constraint(corr_status, corr_reason, detail),
                       *_chair_constraints(behind_st, pull_st, chairs_na, cdetail)]
        result = combine(c["result"] for c in checks.values())
        return {"result": result, "room": room, "checks": checks, "constraints": [c.to_dict() for c in constraints]}


def _corridor_constraint(status, reason, detail) -> ConstraintResult:
    """Corredor como `ConstraintResult`: medido = largura mobiliada do PIOR portal (menor folga sobre o exigido)."""
    if status not in ("PASS", "FAIL"):
        return ConstraintResult("circulation.corridor", status, reason,
                                evidence={"why": detail[0].get("erro", reason) if detail else reason, "detail": detail})
    worst = None
    for p in detail:
        w, tier = p.get("w_furnished_m"), p.get("tier")
        if w is None:
            continue
        need = {"principal": PRIMARY_TARGET_M, "secundaria": SECONDARY_TARGET_M}.get(tier)
        if tier == "shell_estreito":
            need = p["w_empty_m"] - GEOMETRY_TOLERANCE_M
        elif tier == "shell_impossivel":
            w, need = p["w_empty_m"], IMMUTABLE_SHELL_FLOOR_M
        if worst is None or w - need < worst[0] - worst[1]:
            worst = (w, round(need, 4), p)
    return ConstraintResult("circulation.corridor", status, reason, measured=worst[0], threshold=worst[1], units="m",
                            evidence={"portals_measured": sum(1 for p in detail if p.get("w_furnished_m") is not None),
                                      "worst_portal": worst[2]})


def _chair_constraints(behind_st, pull_st, na_reason, cdetail) -> list[ConstraintResult]:
    if na_reason:
        why = {"why": "sem mesa de jantar e cadeiras de jantar identificadas no comodo"}
        return [ConstraintResult("circulation.behind_chairs", "NOT_APPLICABLE", na_reason, evidence=why),
                ConstraintResult("circulation.chair_pull", "NOT_APPLICABLE", na_reason, evidence=why)]
    behind = min(c["livre_atras_m"] for c in cdetail)
    stuck = sum(1 for c in cdetail if not c["puxada_ok"])
    return [ConstraintResult("circulation.behind_chairs", behind_st, "MEASURED", measured=behind,
                             threshold=round(BEHIND_CHAIR_M - 0.25, 4), units="m",
                             evidence={"chairs": len(cdetail), "note": "medido de um ponto 0,25 m atras do centro da cadeira"}),
            ConstraintResult("circulation.chair_pull", pull_st, "MEASURED", measured=float(stuck), threshold=0.0,
                             units="cadeiras_sem_recuo", evidence={"chairs": len(cdetail), "pull_m": PULL_M})]


def _chair_checks(blockers, cell_in):
    """Cadeiras da mesa de jantar: 0,70 m livres atras e cadeira PUXADA cabendo. Devolve (atras_ok, puxada_ok, detalhe,
    motivo_na): `motivo_na` e None quando ha mesa E cadeiras para medir; senao o codigo de por que nao se aplica."""
    mesa = [g for b, g in blockers if str(b.get("module", "")).startswith("Mesa de jantar")]
    mesa_u = unary_union(mesa) if mesa else None
    # Uma cadeira = varias boxes (foot x4 / frame x2 / seat / back). O box
    # kind="seat" ja e o footprint INTEIRO da cadeira (_chair_parts: pernas,
    # frames e encosto ficam contidos nele) — usar ele como representante
    # unico da instancia, sem reconstruir identidade por coordenada/proximidade.
    # Bug pago 2x: round(centroid.x) fundia cadeiras que compartilham X (e
    # partia as giradas 90 graus); clusterizar por buffer de 0.08m fundia as 2
    # cadeiras lado a lado da mesa 1.00x0.65 (centros a 0.50m, assento 0.42m
    # -> gap real 0.08m < 2x0.08) numa "cadeira" so, medida pelo ponto medio.
    cad = {i: [g] for i, (b, g) in enumerate(blockers)
           if str(b.get("module", "")).startswith("Cadeira") and b.get("kind") == "seat"}
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
    na = None if (mesa_u is not None and cad) else ("NO_DINING_TABLE" if mesa_u is None else "NO_DINING_CHAIRS")
    return behind_ok, pull_ok, cdetail, na


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
