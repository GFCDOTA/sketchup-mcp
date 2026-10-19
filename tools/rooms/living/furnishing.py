"""Brain de sala: placement baseado em paredes, circulação e fidelidade.

Migração literal do corpo de living_room_boxes antes em furnish_apartment.
Preserva layout, geometria, cores, logs e provenance do solver. Não executa
SketchUp; o orquestrador continua único ponto de materialização do .skp.
"""
from __future__ import annotations

import os

from tools.rooms.living.components import _bwg_recolor, _dining_table_rect, _oct_in
from tools.rooms.shared.decor import place_decor_boxes
from tools.rooms.shared.furniture import _chair_parts
from tools.rooms.shared.geometry import _oriented_box


def living_room_boxes(con, room_id):
    """Sala via COMMON SENSE ENGINE (placement solver): o sofa GOLDEN deixa de
    flutuar no centro — fica ANCORADO numa parede de FRENTE pra TV (eixo sofa->rack),
    fora da circulacao; rack de MADEIRA na parede-TV (limpa), mesa de centro + tapete
    no eixo entre os dois. Corrige o veredito do GPT (objeto PASS, placement FAIL):
    o solver rejeita sofa em circulacao / sem eixo pra TV. Fallback: brain antigo."""
    from tools.sofa_builder import build_sofa, place_sofa_boxes
    from interior.planners.living_room_planner import plan_living
    # provenance de decisões de posicionamento (optimizer_consistency_gate) —
    # achado 2026-08-12: toda busca de posição JÁ usa circulation_gate.gate()
    # de verdade (não proxy), mas a decisão morria depois de escolhida; agora
    # fica registrada em out["placement_decisions"] pra auditoria/CI.
    _CANONICAL_GATE_VERSION = "circulation_gate.py::gate/2026-08-12-role-based"
    _placement_decisions = []
    plan = plan_living(con, room_id)
    if not plan.get("plan"):
        # sem parede util no comodo (raríssimo): NAO flutua moveis — sala vazia e
        # honesto, sofa flutuando nao. O degrade do plan_living ja garante plano
        # ANCORADO (WARN) p/ sala apertada; o brain antigo FLUTUANTE foi removido.
        return [], {"result": plan.get("result"), "room_name": plan.get("room_name"),
                    "placement": "no_plan_skip"}
    p = plan["plan"]
    sofa_c = tuple(p["sofa"]["center_in"]); sofa_f = tuple(p["sofa"]["facing"])
    rack_c = tuple(p["tv_rack"]["center_in"]); rack_f = tuple(p["tv_rack"]["facing"])
    width_m = round(p["sofa"]["width_m"], 3)
    # seats adaptados a largura que cabe no nicho (3-lug so se a parede comporta).
    # FASE 1 do laco classe->.skp: a CLASSE escolhe os LUGARES (per_seat na faixa) e o
    # sofa nasce do arquetipo VENEZIA curado pelo Felipe (sofa-ref-02 venezia-slate main:
    # bracos finos + pes de ferro). Substitui a heuristica `3 se w>=2.0 senao 2` que
    # esticava per_seat fora da classe (defeito que a Fase 0 revelou). So a largura e'
    # fixada ao nicho; o resto e' in-class por construcao.
    from tools.sofa_class import derive_living_sofa, sofa_class_gate
    _sofa_spec = derive_living_sofa(width_m)
    parts, _ = build_sofa(_sofa_spec)
    # gate de classe no caminho REAL (Fase 0): agora o sofa nasce in-class, entao isto e'
    # guarda-corpo contra REGRESSAO futura (ex.: mexer no arquetipo). WARN-log, nao aborta.
    _sgate = sofa_class_gate(_sofa_spec, parts)
    if _sgate["result"] != "PASS":
        _why = "; ".join(_sgate["errors"] or _sgate["warnings"]) or "(sem detalhe)"
        print(f"[furnish-apt] sofa_class_gate => {_sgate['result']} (WARN-log, nao aborta): {_why}")
    boxes = place_sofa_boxes(parts, sofa_c, sofa_f)         # sofa de frente pra TV
    for _b in boxes:                                        # cada movel = modulo editavel separado
        _b["module"] = "Sofa"
    # mesa + tapete AGRUPADOS perto do sofa (nao esticados ate o rack); rack na parede-TV
    import math as _m
    fnx, fny = sofa_f
    _fn = _m.hypot(fnx, fny) or 1.0
    fnx, fny = fnx / _fn, fny / _fn
    M2IN = 39.3700787402

    def _ahead(dist_m):                                     # ponto 'dist_m' a frente do sofa
        return (sofa_c[0] + fnx * dist_m * M2IN, sofa_c[1] + fny * dist_m * M2IN)

    # rack na parede-TV: o plan_living ja o posiciona FRENTE-A-FRENTE com o sofa,
    # centrado no nicho (sem a projecao antiga que o empurrava pra boca/corredor).
    # COMPACTO (Felipe: "diminuir o rack; tava tomando o corredor"): largura modesta
    # (~ largura do sofa, teto 1.20m) e raso (0.35), flush na parede — apê pequeno
    # pede movel compacto que nao rouba circulacao.
    from interior.semantics.wall_affordance import wall_affordance
    _aff = wall_affordance(con, room_id)
    _rack_wall_len = next((w["length_m"] for w in _aff["walls"]
                           if w["wall_id"] == p["tv_rack"]["wall_id"]), 1.80)
    # RACK = painel/credenza PLANEJADO ancorado na parede-TV (planned_niche_system, NUNCA cubo proxy).
    # LIVING_ROOM_LAYOUT_FIX_OPTION_A: a FORMA entra SEMPRE (sai do proxy); a cor é neutra no baseline
    # e escura só sob FURNISH_STYLE (a estética black_wood_gold entra numa fase posterior).
    from tools.rack_class import build_rack, derive_rack_spec
    # BLACK_WOOD_GOLD DIRETO (programa apê-inteiro 2026-08-03): a sala nasce
    # estilizada como a cozinha — a estética não depende mais de FURNISH_STYLE.
    _rlen = round(min(1.55, max(1.30, _rack_wall_len - 0.35)), 2)
    _rspec = derive_rack_spec("55", "low_credenza", length=_rlen,
                              body_rgb=(38, 39, 40), front_rgb=(44, 45, 47),
                              feet_rgb=(26, 26, 28))
    _rparts, _ = build_rack(_rspec)
    rfx, rfy = rack_f
    _rn2 = _m.hypot(rfx, rfy) or 1.0
    rfx, rfy = rfx / _rn2, rfy / _rn2
    # rack avança 13cm pra abrir espaço pro PAINEL na parede (medido: 7cm deixava
    # 3cm de invasão — overlap_gate WARN 493cm²; 13cm dá folga de ~3cm)
    _rack_c2 = (rack_c[0] + rfx * 0.13 * M2IN, rack_c[1] + rfy * 0.13 * M2IN)
    _rb = place_sofa_boxes(_rparts, _rack_c2, rack_f)
    for _b in _rb:
        _b["module"] = "Rack TV"
    boxes += _rb
    # PAINEL DE TV em NOGUEIRA (SEMPRE — substitui o proxy gated 'parede_concreto'):
    # é o fundo que faz rack+TV lerem como estar planejado. Fita LED 2700K no topo.
    _pan_w = round(max(1.80, min(_rack_wall_len - 0.10, 2.60)), 2)
    _pan_c = (rack_c[0] - rfx * 0.15 * M2IN, rack_c[1] - rfy * 0.15 * M2IN)
    from shapely.geometry import Polygon
    from shapely.ops import unary_union as _uni
    from core.scale import PT_TO_IN
    from tools.spatial_model import build_spatial_model, wall_footprint

    _sm = build_spatial_model(con, room_id)
    _room_walls = _uni([
        wall_footprint(_sm["_geom"]["walls"][wid], extend_endpoints=True)
        for wid in _sm["_geom"]["room_walls"]
    ])
    _perp = (-rfy, rfx)   # deslocamento AO LONGO da parede-TV, não afastamento.
    _pan_choice = None
    _pan_best_overlap = float("inf")
    _candidate_w = _pan_w
    while _candidate_w >= 2.0 - 1e-8:
        for _shift in (0.0, 0.02, -0.02, 0.04, -0.04, 0.06, -0.06,
                       0.08, -0.08, 0.10, -0.10, 0.14, -0.14, 0.20, -0.20):
            _cc = (_pan_c[0] + _perp[0] * _shift * M2IN,
                   _pan_c[1] + _perp[1] * _shift * M2IN)
            _probe = _oriented_box("painel_tv", _cc, rack_f, _candidate_w, 0.05,
                                   0.0, 2.40, [92, 64, 46], module="Painel TV")
            _shape = Polygon([(x / PT_TO_IN, y / PT_TO_IN) for x, y in _probe["corners"]])
            _intr = _shape.intersection(_room_walls).area
            if _intr < _pan_best_overlap:
                _pan_choice, _pan_best_overlap = (_candidate_w, _cc), _intr
            if _intr < 1e-8:
                break
        if _pan_best_overlap < 1e-8:
            break
        _candidate_w = round(_candidate_w - 0.04, 3)
    if _pan_choice is not None:
        _pan_w, _pan_c = _pan_choice
    if _pan_best_overlap > 1e-8:
        print(f"[furnish-apt] PAINEL_TV_WALL_COLLISION: {_pan_best_overlap:.3f} pt2 "
              f"(sem posicao livre; exige correcao, nao promover)")
    boxes.append(_oriented_box("painel_tv", _pan_c, rack_f, _pan_w, 0.05, 0.0, 2.40,
                               [92, 64, 46], module="Painel TV"))
    boxes.append(_oriented_box("lv_led", (_pan_c[0] + rfx * 0.033 * M2IN, _pan_c[1] + rfy * 0.033 * M2IN),
                               rack_f, _pan_w - 0.20, 0.016, 2.32, 0.02, [255, 250, 232], module="Painel TV"))
    # TV 55" REAL em produção (era só proxy na matriz do juiz): moldura fina +
    # vidro preto profundo — o preto mais escuro do ambiente, montada no painel.
    _tv_c = (_pan_c[0] + rfx * 0.045 * M2IN, _pan_c[1] + rfy * 0.045 * M2IN)
    boxes.append(_oriented_box("tv_frame", _tv_c, rack_f, 1.27, 0.025, 0.735, 0.73, [22, 22, 26], module="TV"))
    boxes.append(_oriented_box("tv_glass", (_tv_c[0] + rfx * 0.014 * M2IN, _tv_c[1] + rfy * 0.014 * M2IN),
                               rack_f, 1.23, 0.012, 0.755, 0.69, [16, 16, 18], module="TV"))
    # cell + helper (SEMPRE — jantar e decor usam o polígono do cômodo)
    from shapely.geometry import Point, Polygon

    from core.scale import PT_TO_IN
    from tools.spatial_model import build_spatial_model
    cell_in = Polygon([(x * PT_TO_IN, y * PT_TO_IN)
                       for x, y in build_spatial_model(con, room_id)["_geom"]["cell"].exterior.coords])
    cen = cell_in.centroid

    def _inside(pt, margin_in=9.0):
        p = Point(pt)
        return cell_in.contains(p) and cell_in.exterior.distance(p) >= margin_in

    # ---- ZONA DE JANTAR (SEMPRE — forma/zona, NÃO estética). Mesa COMPACTA p/ 4 (apê 74m²,
    # nada de trambolho); na maior zona LIVRE longe do estar; NÃO bloqueia porta/passagem
    # (geometry_sanity + overlap conferem). LIVING_ROOM_LAYOUT_FIX_OPTION_A.
    from shapely.ops import unary_union as _uni
    _occ = [Polygon([(c[0], c[1]) for c in _b["corners"]]) for _b in boxes if _b.get("corners")]
    _free = cell_in.buffer(-M2IN * 0.12).difference(_uni([p.buffer(M2IN * 0.32) for p in _occ]))
    if _free.geom_type == "MultiPolygon":
        _free = max(_free.geoms, key=lambda g: g.area)
    if (not _free.is_empty) and _free.area > (2.4 * M2IN * M2IN):
        # P1 do VERDICT 6.5 (Felipe): mesa MENOR e POSIÇÃO ESCOLHIDA PELO GATE
        # — busca candidatos e só aceita onde a circulação PASSA de verdade
        # (90/80cm contínuo por PAPEL do portal + 0.70 atrás + cadeira PUXADA).
        from tools.circulation_gate import gate as _circ_gate
        # 1.00x0.65, 4 lugares (2+2 nos lados COMPRIDOS) — achado 2026-08-12,
        # varredura EXAUSTIVA (grade completa do cômodo, passo 6-8in, overlap
        # real contra sofá/rack, exigindo os 5 portais conectados E folga
        # atrás/puxada de TODA cadeira): nenhuma mesa retangular de 6 lugares
        # (testadas 1.10-1.40m, com/sem cabeceira, 2+2+2 e 3+3) tem posição
        # válida nesse cômodo — sofá (ajustado ao nicho) + rack já ocupam a
        # parede-TV inteira, e 6 cadeiras ao redor de qualquer mesa >=1.0m²
        # sempre fecham pelo menos 1 dos 5 vãos OU deixam alguma cadeira sem
        # 0.70m de folga atrás. 4 lugares em mesa retangular (ratio 1.5, ainda
        # "mesa de jantar" de verdade, não bistrô) É o teto real do apê 74m²
        # pra essa sala combinada sem violar circulação (P1, prioridade sobre
        # contagem de lugares).
        _MW, _MD = 1.00, 0.65
        _CHAIR_GAP = 0.30
        _seat_xs = (-0.25, 0.25)
        _chair_spots = ([(sx, _MD / 2 + _CHAIR_GAP, (0.0, -1.0)) for sx in _seat_xs]
                        + [(sx, -(_MD / 2 + _CHAIR_GAP), (0.0, 1.0)) for sx in _seat_xs])

        def _dining_set(cx, cy):
            out_ = []
            _dtp = _dining_table_rect(w=_MW, d=_MD, top_rgb=(108, 80, 58), leg_rgb=(30, 30, 33))
            for _b in place_sofa_boxes(_dtp, (cx, cy), (0.0, 1.0)):
                _b["module"] = "Mesa de jantar"
                out_.append(_b)
            for _dx, _dy, _cf in _chair_spots:
                _chc = (cx + _dx * M2IN, cy + _dy * M2IN)
                _pt = Point(_chc)
                if cell_in.contains(_pt) and cell_in.exterior.distance(_pt) >= 4:
                    for _b in place_sofa_boxes(_chair_parts(), _chc, _cf):
                        _b["module"] = "Cadeira jantar"
                        out_.append(_b)
            out_.append(_oriented_box("pend_cabo", (cx, cy), (0.0, 1.0), 0.032, 0.032,
                                      2.10, 0.60, [26, 26, 28], module="Pendente"))
            out_.append(_oct_in("pend_cupula", cx, cy, 0.20, 1.85, 0.25, [30, 31, 32], "Pendente"))
            out_.append(_oct_in("pend_bronze", cx, cy, 0.206, 1.842, 0.010, [171, 119, 63], "Pendente"))
            return out_

        # grade no cômodo INTEIRO (não mais radial-do-centroide): achado
        # 2026-08-12 — a busca radial (raio até 1.60m a partir do centroide da
        # zona livre) nunca alcançava as poucas posições que de fato preservam
        # os 5 portais (comprovado por varredura exaustiva com passo de 6-10in +
        # checagem de overlap real contra sofá/rack, que a busca radial também
        # não fazia — só evitava a zona de circulação, não a mobília em si).
        # Métrica: nº de portais desconectados (pesa mais) + nº de categorias
        # FAIL como desempate; primeira posição com 0 (circulação E folga de
        # cadeira) vence.
        _bx0, _by0, _bx1, _by1 = cell_in.bounds
        _occ_now = _uni(_occ) if _occ else None
        from tools.rooms.shared.geometry import door_swing_polygons
        _swings = door_swing_polygons(con)
        _room_door_swings = [
            Polygon([(x * PT_TO_IN, y * PT_TO_IN) for x, y in _swings[o2["id"]].exterior.coords])
            for o2 in con.get("openings", [])
            if o2["id"] in _swings and o2["wall_id"] in _sm["_geom"]["room_walls"]
        ]
        # A grade de 6in acha o layout com circulacao PASS, mas o tampo
        # tangenciava o arco h_o000 (~36 cm2). Uma grade nova de 3in buscava
        # somente candidatos sem intersecao e perdia a faixa viavel, deixando
        # corredor/varanda bloqueados. Resolver PRIMEIRO a circulacao real e
        # refinar LOCALMENTE o candidato com pequeno slide, mantendo ambos gates.
        _best, _best_score, _best_gate_result = None, 999, None
        _n_candidates = 0
        _valid_but_swinging = []

        def _candidate(cx, cy):
            if not _inside((cx, cy), margin_in=20):
                return None
            cand = _dining_set(cx, cy)
            if sum(b.get("kind") == "seat" for b in cand if b.get("module") == "Cadeira jantar") != 2:
                return None
            if _occ_now is not None:
                cand_occ = _uni([Polygon([(v[0], v[1]) for v in b["corners"]])
                                 for b in cand if b.get("corners")])
                if cand_occ.intersection(_occ_now).area > 50:
                    return None
            return cand

        def _swing_hit(cand):
            return any(
                Polygon([tuple(pt) for pt in b["corners"]]).intersection(sw).area > 1e-8
                for b in cand if b.get("module") == "Mesa de jantar" and b.get("corners")
                for sw in _room_door_swings
            )

        for _cx in range(int(_bx0) + 8, int(_bx1) - 8, 6):
            if _best_score == 0:
                break
            for _cy in range(int(_by0) + 8, int(_by1) - 8, 6):
                cand = _candidate(_cx, _cy)
                if cand is None:
                    continue
                _n_candidates += 1
                _g = _circ_gate(con, boxes + cand, room_id)
                if _g["result"] != "PASS":
                    continue
                if _swing_hit(cand):
                    # Guardar layout funcional para o refinamento (maximo 8);
                    # nunca promover este candidato com colisao.
                    if len(_valid_but_swinging) < 8:
                        _valid_but_swinging.append((_cx, _cy))
                    continue
                _best, _best_score, _best_gate_result = cand, 0, "PASS"
                break

        if _best is None:
            # Refinar em passos de 0.5in (~1.27cm) ao redor de cada layout
            # aprovado na circulacao. Pequenos slides sao menos invasivos
            # que trocar a mesa por outra localizacao e perder os portais.
            _shifts = [0.0]
            for d in range(1, 13):
                _shifts.extend((d * 0.5, -d * 0.5))
            _pairs = sorted(
                ((dx, dy) for dx in _shifts for dy in _shifts
                 if (dx or dy) and max(abs(dx), abs(dy)) <= 6.0),
                key=lambda pair: (pair[0] ** 2 + pair[1] ** 2, abs(pair[0]), abs(pair[1]))
            )
            for bx, by in _valid_but_swinging:
                for dx, dy in _pairs:
                    cand = _candidate(bx + dx, by + dy)
                    if cand is None or _swing_hit(cand):
                        continue
                    _n_candidates += 1
                    _g = _circ_gate(con, boxes + cand, room_id)
                    if _g["result"] == "PASS":
                        _best, _best_score, _best_gate_result = cand, 0, "PASS"
                        break
                if _best is not None:
                    break

        if _best is None:
            print("[furnish-apt] circulation_gate: FAIL (WARN — DINING_TABLE_BLOCKED): "
                  "nenhuma posicao preserva corredor+cadeiras+arco; nao inserir mesa inviavel")
        else:
            boxes += _best
            _placement_decisions.append({
                "candidate_id": "mesa_de_jantar",
                "optimizer": "dining_grid_search_v2_door_swing_refine",
                "canonical_gate": _CANONICAL_GATE_VERSION,
                "gate_result": _best_gate_result, "score": _best_score,
                "n_candidates_tried": _n_candidates,
            })

    # almofadas soltas no sofá (decor mínimo, pontuação não frase)
    for _adx, _aang in ((-0.55, 12), (0.55, -12)):
        _af = (fnx * _m.cos(_m.radians(_aang)) - fny * _m.sin(_m.radians(_aang)),
               fnx * _m.sin(_m.radians(_aang)) + fny * _m.cos(_m.radians(_aang)))
        _ac = (sofa_c[0] - fnx * 0.18 * M2IN + (-fny) * _adx * M2IN,
               sofa_c[1] - fny * 0.18 * M2IN + fnx * _adx * M2IN)
        # decorative=True: almofada "jogada" (12°/-12° de propósito, look
        # tossed) — não-axis-aligned por design, não bug de rotação. Achado
        # 2026-08-12 (geometry_sanity.off_axis rejeitava).
        boxes.append(_oriented_box("almofada", _ac, _af, 0.45, 0.14, 0.47, 0.45,
                                   [96, 88, 76], module="Sofa", decorative=True))
    # tapete COM BORDA (campo + moldura 8cm mais escura — deixa de ser laje)
    boxes.append(_oriented_box("rug_border", _ahead(0.70), sofa_f, 1.80, 1.20, 0.0, 0.018, [96, 88, 76], module="Tapete"))
    boxes.append(_oriented_box("rug_field", _ahead(0.70), sofa_f, 1.64, 1.04, 0.0, 0.02, [140, 128, 112], module="Tapete"))
    # MESA DE CENTRO: tampo pedra preta (eco do tampo da cozinha) + pernas metal.
    # Posicionada por ÚLTIMO (depois da mesa de jantar) de propósito — achado
    # 2026-08-12: a conectividade dos portais é uma checagem de conjunto (flood-fill
    # no cômodo inteiro), então a mesa de jantar decide primeiro o "istmo" livre e a
    # mesa de centro busca (2D, gate real) o que ainda sobrou sem fechar o resto.
    from tools.coffee_table_class import CoffeeTableClassSpec, build_coffee_table_v2
    _ct = CoffeeTableClassSpec(style="two_tier", length=0.95, width=0.50, height=0.38, shelf=True,
                               top_rgb=(30, 29, 32), leg_rgb=(26, 26, 28))
    _ctp, _ = build_coffee_table_v2(_ct.validate())
    _perp = (-fny, fnx)

    def _clear_of_circulation(parts, facing, base_dist_m=0.70):
        from tools.circulation_gate import gate as _cgate
        base = _ahead(base_dist_m)
        # overlap real contra a mobília já colocada (sofá/rack/mesa de jantar/
        # etc. — 'boxes' já reflete o que foi decidido até aqui) — achado
        # 2026-08-12: a busca só evitava a zona de circulação, não a mobília em
        # si; um candidato "mais perto" (raio pequeno) podia grudar no sofá
        # (furniture_overlap_gate: Mesa de centro × Sofa, ~48% sobreposto).
        _occ_polys = [Polygon([(c[0], c[1]) for c in _b["corners"]]) for _b in boxes if _b.get("corners")]
        _occ_now = _uni(_occ_polys) if _occ_polys else None
        _best_c, _best_fails = base, None
        _n_tried = 0
        cands = [(0.0, 0.0)] + [(along, side) for r in (0.20, 0.40, 0.60, 0.80)
                                for along, side in ((0, r), (0, -r), (r, 0), (-r, 0),
                                                     (r * 0.7, r * 0.7), (-r * 0.7, r * 0.7),
                                                     (r * 0.7, -r * 0.7), (-r * 0.7, -r * 0.7))]
        for along, side in cands:
            c = (base[0] + fnx * along * M2IN + _perp[0] * side * M2IN,
                 base[1] + fny * along * M2IN + _perp[1] * side * M2IN)
            if not _inside(c, margin_in=int(_ct.width / 2 * M2IN)):
                continue
            _cand = place_sofa_boxes(parts, c, facing)
            for _b in _cand:
                _b["module"] = "Mesa de centro"
            if _occ_now is not None:
                _cand_occ = _uni([Polygon([(cc[0], cc[1]) for cc in _b["corners"]])
                                  for _b in _cand if _b.get("corners")])
                if _cand_occ.intersection(_occ_now).area > 50:   # in^2
                    continue
            _n_tried += 1
            _g = _cgate(con, boxes + _cand, room_id)
            _nf = sum(1 for p in _g["checks"]["corredor_principal"]["portais"]
                     if not p.get("conectado", True))
            if _nf == 0:
                _placement_decisions.append({
                    "candidate_id": "mesa_de_centro", "optimizer": "coffee_table_radial_search_v1",
                    "canonical_gate": _CANONICAL_GATE_VERSION, "gate_result": _g["result"],
                    "score": _nf, "n_candidates_tried": _n_tried,
                })
                return c, True
            if _best_fails is None or _nf < _best_fails:
                _best_c, _best_fails = c, _nf
        _placement_decisions.append({
            "candidate_id": "mesa_de_centro", "optimizer": "coffee_table_radial_search_v1",
            "canonical_gate": _CANONICAL_GATE_VERSION, "gate_result": "OMITTED_NO_VALID_CANDIDATE",
            "score": _best_fails, "n_candidates_tried": _n_tried,
        })
        return _best_c, False

    # sofá+rack (parede-a-parede) já deixam a faixa do portal da varanda no fio
    # da margem (~0.91-0.92m contra o alvo 0.90m) — achado 2026-08-12: QUALQUER
    # objeto plantado nesse "istmo" (na frente do sofá, entre sofá e rack) fecha
    # a conexão pra 0 (erosão é tudo-ou-nada, não degrada aos poucos). Coloca a
    # mesa de centro só se algum candidato preservar os 5 portais conectados;
    # senão pula (sala compacta: melhor sem mesa de centro do que bloqueando a
    # varanda) — mesmo padrão já usado pra mesa de jantar (só entra se couber).
    _ct_center, _ct_ok = _clear_of_circulation(_ctp, sofa_f)
    if _ct_ok:
        _ctb = place_sofa_boxes(_ctp, _ct_center, sofa_f)
        for _b in _ctb:
            _b["module"] = "Mesa de centro"
        boxes += _ctb
    else:
        print("[furnish-apt] circulation_gate: mesa de centro OMITIDA — nenhuma "
              "posição preserva os 5 portais conectados (sala compacta, sofá+rack "
              "já deixam a faixa da varanda no limite)")

    # ---- camada de ESTILO (gated, AESTHETIC — NÃO entra no layout-fix): parede de concreto na
    # parede-TV + decor (planta/quadro/prateleira/trilho). Só sob FURNISH_STYLE.
    style = os.environ.get("FURNISH_STYLE")
    if style in ("industrial", "modern_warm"):

        def _toward_centroid(start, frac0=0.35):
            """Ponto entre start e o centroide, recuado ate ficar DENTRO com margem
            (decor nunca atravessa parede / sai do comodo em L)."""
            frac = frac0
            for _ in range(9):
                pt = (start[0] + (cen.x - start[0]) * frac, start[1] + (cen.y - start[1]) * frac)
                if _inside(pt):
                    return pt
                frac += 0.08
            return (cen.x, cen.y) if _inside((cen.x, cen.y)) else None

        rfx, rfy = rack_f
        _rn = _m.hypot(rfx, rfy) or 1.0
        rfx, rfy = rfx / _rn, rfy / _rn
        # parede de concreto ATRAS do rack (recuada ~0.19m contra o facing = na parede)
        wall_c = (rack_c[0] - rfx * 0.19 * M2IN, rack_c[1] - rfy * 0.19 * M2IN)
        wall_w = round(min(_rack_wall_len, 3.6), 2)
        boxes.append(_oriented_box("parede_concreto", wall_c, rack_f, wall_w, 0.04, 0.0, 2.40,
                                   [165, 162, 158], module="Parede concreto"))
        rperp = (-rfy, rfx)
        plant_c = (rack_c[0] + rperp[0] * 0.50 * M2IN, rack_c[1] + rperp[1] * 0.50 * M2IN)
        if _inside(plant_c, margin_in=2.0):
            boxes += place_decor_boxes("plant_placeholder", plant_c, rack_f, z_lift=0.52,
                                       height=0.55, pot_w=0.16, pot_h=0.10, foliage_w=0.30,
                                       module="Planta")
        art_c = (wall_c[0] + rfx * 0.04 * M2IN, wall_c[1] + rfy * 0.04 * M2IN)
        boxes += place_decor_boxes("wall_art", art_c, rack_f, z_lift=1.15, module="Quadro",
                                   width=0.90, height=0.62)
        perp = (-rfy, rfx)
        shelf_c = (wall_c[0] + perp[0] * 0.45 * M2IN + rfx * 0.14 * M2IN,
                   wall_c[1] + perp[1] * 0.45 * M2IN + rfy * 0.14 * M2IN)
        if _inside(shelf_c, margin_in=4.0):
            boxes += place_decor_boxes("shelf", shelf_c, rack_f, z_lift=1.42, module="Prateleira",
                                       width=0.85, n_planks=2)
        mid = ((sofa_c[0] + rack_c[0]) / 2.0, (sofa_c[1] + rack_c[1]) / 2.0)
        track_face = (-fny, fnx)                 # perp ao facing do sofa -> trilho ao longo do eixo
        boxes += place_decor_boxes("track_light", mid, track_face, z_lift=2.15, module="Trilho de luz",
                                   length=1.5, n_spots=3)

    # LINGUAGEM black_wood_gold SEMPRE (programa apê-inteiro): só cor, layout intacto.
    _bwg_recolor(boxes)

    out = {"result": "OK", "room_name": plan.get("room_name"), "n_placed": len(boxes),
           "placement": "common_sense_solver", "tv_wall": plan.get("tv_wall"),
           "sofa_wall": p["sofa"]["wall_id"], "view_dist_m": p["sofa"]["rule"],
           "placement_decisions": _placement_decisions}
    return boxes, out
