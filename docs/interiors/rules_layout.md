# Regras de layout de interiores (feedback loop)

> Fonte de verdade executável: [`tools/layout_rules.py`](../../tools/layout_rules.py).
> Este doc é a versão legível; o código é o que de fato roda no score.
> Aplicadas por [`tools/layout_candidates.py`](../../tools/layout_candidates.py).
> Escopo: **layout** (posição/função de móvel placeholder). **Sem 3D Warehouse,
> sem asset real, sem estilo, sem SKP.**

## Por que existem

O sistema começou como um "spawner de sofá burro" — baixava um asset e jogava
no centro do cômodo. Cada erro que o Felipe vetou virou **regra determinística**
aqui, pro cérebro não repetir. As regras são a memória dura do feedback loop.

Cada regra tem:
- **kind**: `hard` (reprova o candidato), `soft` (penaliza/ranqueia) ou
  `process` (disciplina de pipeline, não checável no score).
- **anti_pattern**: o erro concreto que ela previne (ver
  [`anti_patterns.md`](anti_patterns.md)).
- **enforced_by**: onde no código a regra mora.

## Catálogo

| ID | kind | regra | anti-pattern que previne |
|----|------|-------|--------------------------|
| RL-01 | process | Resolver o **layout** (posição/função) antes de escolher móvel real. | AP-01: baixar asset e jogar no modelo sem layout. |
| RL-02 | process | Validar com **placeholder** (bounding box) antes de tocar no 3DW. | AP-02: gastar download/escala num asset que nem cabe. |
| RL-03 | soft | Sofá só se orienta se há **parede focal / TV candidate**. | AP-03: sofá orientado pra lugar nenhum. |
| RL-04 | soft | Sofá **não fica solto** no meio sem função (setorizar/encarar TV). | AP-04: sofá flutuante no centro sem encarar nada. |
| RL-05 | soft | Parede-TV por **profundidade** e qualidade (preferir borda/fundo), não por ser a maior. | AP-05: TV na maior parede cega sem espaço pro sofá. |
| RL-06 | soft | Distância sofá↔TV no ideal **2.6–3.0 m** (aceitável 2.3–4.0). < 2.3 m vira **hard**. | AP-06: sofá colado na TV ou longe demais. |
| RL-07 | hard | **Não bloquear a circulação** (cozinha→sala→terraço→quartos). | AP-07: sofá/rack sobre a zona vermelha. |
| RL-08 | hard | **Não bloquear aberturas**: portas, porta-vidro, arco de giro. | AP-08: sofá em frente à porta da varanda. |
| RL-09 | hard | **Não atravessar a parede** (só encostar). | AP-09: bounding box dentro da parede. |
| RL-10 | hard | Manter **passagem livre ≥ 0.80 m**. | AP-10: móveis estrangulam o corredor. |
| RL-11 | process | Se a parede-TV for **AMBIGUOUS**, gerar candidatos **e explicar** a incerteza; não cravar. | AP-11: cravar "a TV vai aqui" sem ter certeza. |
| RL-12 | process | Se nenhum candidato passa os hard gates, retornar **NO_VALID_LAYOUT**; não forçar sofá. | AP-12: forçar sofá aleatório só pra ter saída. |
| RL-13 | soft | Proporção móveis/sala em **0.25–0.45**; não sub-mobiliar nem comprimir. | AP-13: sala vazia (3 peças) ou superlotada. |
| RL-14 | hard | Móvel fica **dentro do cômodo** (não vaza pra fora/vizinho). | AP-14: bounding box fora da célula da sala. |

## Mapeamento das 10 regras pedidas → IDs

O Felipe listou 10 regras; abaixo o de-para com o catálogo:

1. Não sofá solto no meio sem função → **RL-04**.
2. Não orientar sofá sem parede focal/TV candidate → **RL-03**.
3. Não bloquear circulação cozinha→sala→terraço→quartos → **RL-07**.
4. Não bloquear portas, porta-vidro ou arcos de giro → **RL-08**.
5. Não sofá/rack atravessando zonas vermelhas → **RL-07** + **RL-09**.
6. Não escolher TV wall só por ser a maior; precisa profundidade plausível → **RL-05** (+ **RL-06**).
7. Se TV wall AMBIGUOUS, gerar candidatos e explicar incerteza → **RL-11**.
8. Se nenhum layout passa hard gates, NO_VALID_LAYOUT, não forçar → **RL-12**.
9. Layout primeiro, asset depois → **RL-01**.
10. Placeholder primeiro, 3DW só depois de layout validado → **RL-02**.

## Como uma regra "dispara" (rastro no output)

Cada candidato avaliado carrega `anti_patterns: [{rule_id, name, severity,
evidence}]`. O JSON top-level agrega em `anti_patterns_flagged` (contagem por
regra). O CLI imprime `! RL-XX [sev] nome: evidência` por candidato e o PNG
mostra `regras: RL-05, RL-06, ...` no título de cada subplot.

Exemplo real (sala `r002`, parede-TV `m013` AMBIGUOUS):

```
REGRAS DISPARADAS (feedback loop):
  RL-05 [soft] parede_tv_por_profundidade x3
  RL-06 [soft] distancia_sofa_tv_plausivel x3
  RL-13 [soft] proporcao_e_respiro x3
```

Os 3 candidatos são válidos (passam os hard gates), mas todos carregam a mesma
ressalva honesta: a TV cai numa parede interna (não de fundo), a distância
sofá-TV foge um pouco do ideal e a sala fica sub-mobiliada — exatamente o tipo
de coisa que a gente quer ver **antes** de gastar um download do 3DW.

## Thresholds (fonte única em `layout_rules.py`)

| constante | valor | regra |
|-----------|-------|-------|
| `IDEAL_SOFA_TV` | (2.6, 3.0) m | RL-06 |
| `MIN_SOFA_TV` / `MAX_SOFA_TV` | 2.3 / 4.0 m | RL-06 |
| `MIN_TV_DEPTH` | 2.3 m | RL-05 |
| `MIN_DOOR_CLEAR_M` | 0.6 m | RL-08 |
| `PASSAGE_MIN_M` | 0.80 m | RL-10 |
| `FILL_IDEAL` | (0.25, 0.45) | RL-13 |
| `RESPIRO_IDEAL` | 0.60 | RL-13 |

`layout_candidates.py` importa esses valores daqui — não duplica.

## Prova

[`tests/test_layout_rules.py`](../../tests/test_layout_rules.py) (8 testes):
catálogo cobre RL-01..RL-14; hard gates mapeiam ≥3 anti-patterns; sofá-TV curto
é hard; candidato limpo = zero flags; run real emite `anti_patterns` no JSON;
AMBIGUOUS é explicado, não cravado.
