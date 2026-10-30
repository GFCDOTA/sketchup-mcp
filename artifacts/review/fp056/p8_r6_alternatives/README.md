# FP-056 — alternativas verificadas pelo solver para R6 (banhos e lavabo INFEASIBLE) — 2026-10-24

Issue: #501 (resumo para a decisão em #446). **Nada foi aplicado**: nenhum builder, limiar, layout, `.skp` ou fixture foi alterado.
Medido em `develop@5a42624`, `PT_TO_M=0.0259`, solver F2 (`ip.plan_room`) com `PYTHONPATH=.`, saída só em `runs/`.

## 1. Estado atual (melhor candidato do solver; `baseline_measured.json`)
| Cômodo | Status | Candidatos | Regras reprovadas (medido × mínimo de referência) | Móveis movidos |
|---|---|---|---|---|
| BANHO 01 (r005) | INFEASIBLE | 6724 | entrada do box **0,327 m** × 0,60 (vão declarado do builder: 0,411 m) | Vaso |
| BANHO 02 (r006) | INFEASIBLE | 6724 | entrada **0,310** × 0,60 (declarado 0,310); alcance do box **0,499** × 0,60; frente do vaso **0,523** × 0,60 | Bancada, Box, Vaso |
| LAVABO (r007) | INFEASIBLE | 1681 | frente do vaso **0,515** × 0,60 | Bancada, Vaso |

Os mínimos de 0,60 m vêm de `core/functional_constraints.py` (`reference_minimum`, proveniência `COMFORT_GUIDE`, fontes tier C/D — **não são norma**;
`project_target` também 0,60 com `approval: PENDING_FELIPE`).

## 2. Alternativas no builder do box (vão/vidro fixo) — todas INFEASIBLE (`opening_alternatives.json`)
Vidro fixo 0,36 → 0,30 → 0,24 piora (o vão livre cai para 0,17 e 0,11 m); abertura 0,42 e 0,48 não resolvem: o vão declarado do builder
é limitado a 65% da frente do box (~0,43 m), **abaixo de 0,60 m mesmo sem obstáculo**. Em BANHO 02 com abertura 0,48 o vão livre chega a 0,430 (= declarado) e ainda
reprova por 0,17 m; alcance e frente do vaso não dependem do box. No lavabo não há box: sem efeito. **Conclusão técnica:** nenhuma alternativa de
vão/vidro fixo viabiliza os cômodos; o limite é geométrico (frente do box × mínimo de 0,60).

## 3. What-if de limiar (`whatif_thresholds.json`) — o que o solver faz se o mínimo mudasse
Com `reference_minimum` reduzido **só neste experimento** (em memória, nada gravado), o mesmo solver e as mesmas 6724/1681 candidatas:
| Cômodo | Mínimo testado | Resultado | Layout resultante (móveis movidos) |
|---|---|---|---|
| LAVABO | frente do vaso 0,50 m (medido 0,515) | **FEASIBLE** | Bancada, Vaso |
| BANHO 01 | entrada do box 0,30 m (medido 0,327) | **FEASIBLE** | Vaso |
| BANHO 02 | entrada 0,30 / alcance 0,49 / frente do vaso 0,51 (medidos 0,310 / 0,499 / 0,523) | **FEASIBLE** | Bancada, Box, Vaso |

## 4. Recomendação técnica (sem aplicar) para a #446
- **Menor impacto:** LAVABO. Falta só **8,5 cm** de frente do vaso (0,515 × 0,60) e o solver já acha o melhor arranjo (move Bancada e Vaso). Decisão de
  política do proprietário: aceitar um mínimo de frente do vaso ≤ 0,515 m para esse cômodo (hoje o alvo de projeto 0,60 está `PENDING_FELIPE`), ou
  autorizar uma mudança de louça/parede (arquitetura: fora do alcance do agente).
- **BANHO 02:** três regras, margens de 0,08–0,29 m; a entrada (0,31 × 0,60) é a pior. Sem decisão sobre o box (frente maior ou porta de correr com outro modelo)
  não há arranjo; relaxar três limiares ao mesmo tempo é decisão grande.
- **BANHO 01:** a entrada do box (0,327 × 0,60) está 45% abaixo do mínimo — relaxar o limiar para caber seria aceitar um vão estreito demais; o caminho
  honesto é uma decisão sobre o modelo do box/porta no builder (não sobre o limiar).
- Em todos: o resultado `INFEASIBLE` continua o **correto** até o proprietário decidir; limiares e layouts **não** foram alterados.

## 5. Reprodução e limites
`PT_TO_M=0.0259 PYTHONPATH=. python artifacts/review/fp056/p8_r6_alternatives/probe_whatif.py` (what-if) — a sonda de linha de base é `probe_baseline.py`;
cada cômodo leva 2–10 min. O experimento de abertura/vidro usou uma variação temporária de `_box_front` (não versionada, só os resultados em
`opening_alternatives.json`). É medição no **gêmeo em caixas/solver (L1)**, sem SketchUp; aparência `PENDING_HUMAN`.
