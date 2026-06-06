"""Regras determinísticas de layout de interiores (feedback loop).

Fonte unica das regras + thresholds do cerebro de layout. `layout_candidates.py`
importa os thresholds daqui (consistencia) e chama `flag_anti_patterns()` pra
registrar, por candidato, quais regras foram violadas (vira `anti_patterns` no
JSON de diagnostico).

Objetivo: os erros que ja vimos viram REGRA, pro cerebro nao repetir.
NAO usa 3D Warehouse, asset real, estilo nem SKP. Felipe 2026-06-04.
"""
from __future__ import annotations

# ---- thresholds (fonte unica; layout_candidates importa daqui) ----
IDEAL_SOFA_TV = (2.6, 3.0)   # m — faixa ideal de distancia sofa<->TV
MIN_SOFA_TV = 2.3            # m — abaixo disso e HARD (sofa em cima da TV)
MAX_SOFA_TV = 4.0            # m — acima disso o sofa fica longe demais
MIN_TV_DEPTH = 2.3          # m — profundidade minima em frente a parede-TV
MIN_DOOR_CLEAR_M = 0.6      # m — folga minima sofa<->porta (alem da circulacao)
PASSAGE_MIN_M = 0.80        # m — corredor livre minimo
FILL_IDEAL = (0.25, 0.45)   # area de moveis / area util
RESPIRO_IDEAL = 0.60        # fracao de area livre alvo

# ---- catalogo de regras (id, kind, statement, anti_pattern, enforced_by) ----
RULES = [
    {"id": "RL-01", "kind": "process", "name": "layout_antes_de_asset",
     "statement": "Resolver o LAYOUT (posicao/funcao) antes de escolher movel real.",
     "anti_pattern": "AP-01: baixar asset e jogar no modelo sem layout (spawner de sofa burro).",
     "enforced_by": "processo (pipeline) + este modulo roda sem 3DW"},
    {"id": "RL-02", "kind": "process", "name": "placeholder_antes_de_3dw",
     "statement": "Validar com PLACEHOLDER (bounding box) antes de tocar no 3D Warehouse.",
     "anti_pattern": "AP-02: gastar download/escala num asset que nem cabe no comodo.",
     "enforced_by": "layout_candidates.py usa boxes; 3DW so depois de OK"},
    {"id": "RL-03", "kind": "soft", "name": "sofa_precisa_parede_focal",
     "statement": "Sofa so se orienta se ha parede focal / TV candidate.",
     "anti_pattern": "AP-03: sofa orientado pra lugar nenhum.",
     "enforced_by": "soft.orientacao_sofa_tv; sem TV candidate -> NO_VALID_LAYOUT"},
    {"id": "RL-04", "kind": "soft", "name": "sofa_nao_flutuante_sem_funcao",
     "statement": "Sofa nao fica solto no meio da sala sem funcao (setorizar/encarar TV).",
     "anti_pattern": "AP-04: sofa flutuante no centro sem encarar nada.",
     "enforced_by": "soft.orientacao_sofa_tv + dist_sofa_tv"},
    {"id": "RL-05", "kind": "soft", "name": "parede_tv_por_profundidade",
     "statement": "Escolher parede-TV por PROFUNDIDADE (sofa->TV plausivel) e qualidade, "
                  "nao so por ser a maior; preferir parede de fundo/borda.",
     "anti_pattern": "AP-05: TV na maior parede cega mesmo sem espaco pro sofa (m014, 0.67 m).",
     "enforced_by": "spatial_model.tv_wall_candidate (score) + soft.parede_tv"},
    {"id": "RL-06", "kind": "soft", "name": "distancia_sofa_tv_plausivel",
     "statement": f"Distancia sofa<->TV no ideal {IDEAL_SOFA_TV} m (aceitavel {MIN_SOFA_TV}-{MAX_SOFA_TV}).",
     "anti_pattern": "AP-06: sofa colado na TV ou longe demais.",
     "enforced_by": "soft.dist_sofa_tv; < MIN_SOFA_TV vira hard"},
    {"id": "RL-07", "kind": "hard", "name": "nao_bloquear_circulacao",
     "statement": "Movel nao invade a circulacao (cozinha->sala->terraco->quartos).",
     "anti_pattern": "AP-07: sofa/rack sobre a zona vermelha de circulacao.",
     "enforced_by": "hard_gates.nao_bloqueia_circulacao"},
    {"id": "RL-08", "kind": "hard", "name": "nao_bloquear_aberturas",
     "statement": "Movel nao bloqueia portas, porta-vidro nem arco de giro.",
     "anti_pattern": "AP-08: sofa em frente a porta / porta-vidro da varanda.",
     "enforced_by": "hard_gates.nao_bloqueia_porta_janela (circulacao inclui aberturas) + soft.sofa_longe_porta"},
    {"id": "RL-09", "kind": "hard", "name": "nao_atravessar_parede",
     "statement": "Movel nao atravessa a massa da parede (so encosta).",
     "anti_pattern": "AP-09: bounding box dentro da parede.",
     "enforced_by": "hard_gates.nao_invade_parede"},
    {"id": "RL-10", "kind": "hard", "name": "passagem_minima",
     "statement": f"Manter corredor livre >= {PASSAGE_MIN_M} m.",
     "anti_pattern": "AP-10: moveis estrangulam a passagem.",
     "enforced_by": "hard_gates.passagem_min_080"},
    {"id": "RL-11", "kind": "process", "name": "ambiguous_explica_incerteza",
     "statement": "Se a parede-TV for AMBIGUOUS, gerar candidatos E explicar a incerteza; nao cravar.",
     "anti_pattern": "AP-11: cravar 'a TV vai aqui' numa sala onde nao da pra ter certeza.",
     "enforced_by": "spatial_model marca confidence=ambiguous; layout usa best_candidate + nota"},
    {"id": "RL-12", "kind": "process", "name": "no_valid_layout_honesto",
     "statement": "Se nenhum candidato passa os hard gates, retornar NO_VALID_LAYOUT; nao forcar sofa.",
     "anti_pattern": "AP-12: forcar um sofa aleatorio so pra ter saida.",
     "enforced_by": "layout_candidates.run() -> NO_VALID_LAYOUT"},
    {"id": "RL-13", "kind": "soft", "name": "proporcao_e_respiro",
     "statement": f"Proporcao moveis/sala em {FILL_IDEAL}; nao sub-mobiliar nem comprimir.",
     "anti_pattern": "AP-13: sala de 21 m2 com 3 pecas (vazia) ou superlotada.",
     "enforced_by": "soft.proporcao + soft.respiro"},
    {"id": "RL-14", "kind": "hard", "name": "dentro_do_comodo",
     "statement": "Movel fica dentro do comodo (nao vaza pra fora/comodo vizinho).",
     "anti_pattern": "AP-14: bounding box fora da celula da sala.",
     "enforced_by": "hard_gates.dentro_do_comodo"},
]

RULE_BY_ID = {r["id"]: r for r in RULES}


def flag_anti_patterns(candidate: dict) -> list[dict]:
    """Dado um candidato (com `hard_gates` + `metrics`), devolve a lista de
    anti-patterns flagrados: {rule_id, name, severity, evidence}."""
    hg = candidate.get("hard_gates", {})
    m = candidate.get("metrics", {})
    flags: list[dict] = []

    def add(rid, severity, evidence):
        r = RULE_BY_ID.get(rid, {})
        flags.append({"rule_id": rid, "name": r.get("name"),
                      "severity": severity, "evidence": evidence})

    # --- hard ---
    if hg.get("nao_invade_parede") is False:
        add("RL-09", "hard", "movel atravessa parede")
    if hg.get("nao_bloqueia_circulacao") is False:
        add("RL-07", "hard", "movel sobre a zona de circulacao")
        add("RL-08", "hard", "pode bloquear porta/porta-vidro/arco de giro")
    if hg.get("dentro_do_comodo") is False:
        add("RL-14", "hard", "movel fora da celula do comodo")
    if hg.get("passagem_min_080") is False:
        add("RL-10", "hard", f"passagem livre < {PASSAGE_MIN_M} m")

    # --- soft ---
    d = m.get("sofa_tv_dist_m")
    if d is not None and not (IDEAL_SOFA_TV[0] <= d <= IDEAL_SOFA_TV[1]):
        sev = "hard" if d < MIN_SOFA_TV else "soft"
        add("RL-06", sev, f"sofa-TV {d} m fora do ideal {IDEAL_SOFA_TV}")
    dm = m.get("sofa_door_min_m")
    if dm is not None and dm < MIN_DOOR_CLEAR_M:
        add("RL-08", "soft", f"sofa a {dm} m de porta (< {MIN_DOOR_CLEAR_M} m)")
    td = m.get("tv_depth_m")
    if td is not None and td < MIN_TV_DEPTH:
        add("RL-05", "soft", f"profundidade {td} m insuficiente p/ sofa->TV")
    if m.get("tv_wall_type") and m["tv_wall_type"] != "border":
        add("RL-05", "soft", "parede-TV interna/divisoria, nao de fundo")
    f = m.get("fill_ratio")
    if f is not None and not (FILL_IDEAL[0] <= f <= FILL_IDEAL[1]):
        add("RL-13", "soft", f"proporcao moveis/sala {f} fora de {FILL_IDEAL}")
    return flags
