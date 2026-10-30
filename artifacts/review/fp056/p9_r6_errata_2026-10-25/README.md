# FP-056 — errata e complemento da análise de R6 (2026-10-25)

Issue: #501 (decisão #446). **Errata do retrato `artifacts/review/fp056/p8_r6_alternatives/` (mergeado no PR 547, que não foi reescrito).**
Medido em `develop` com `PT_TO_M=0.0259`, solver F2; nada foi aplicado (nenhum builder, limiar, layout ou `.skp` mudou).

## 1. O que estava errado
O README de `p8_r6_alternatives` dizia que o vão do box é "limitado a 65% da frente (~0,43 m)". Os fatos do builder (`tools/rooms/bathroom/layout.py`):
- `fixw = min(0,48 m; 45% da frente)` é a largura do vidro **fixo**; a folha de correr tem `frente − fixw + 0,05 m` (sobrepõe 5 cm);
- a abertura livre declarada ao solver é `frente − folha = fixw − 0,05 m`. Medido: BANHO 01 (frente 1,024 m) → 0,411 m; BANHO 02 (frente 0,80 m) → 0,31 m;
- como a folha tem de ser ≥ à abertura, **com porta de correr a abertura nunca passa de frente/2** (0,51 m e 0,40 m): o mínimo de 0,60 m é inatingível nesses boxes;
- o "65%" era o teto da minha **variante de teste** (não do builder). As alternativas lá registradas ("vidro fixo 0,30/0,24", "abertura 0,42/0,48") continuam válidas como
  medições, mas sob esse teto de teste; a conclusão "nenhuma alternativa de vão viabiliza os cômodos" **estava incompleta**.

## 2. O que faltava testar: abertura de 0,60 e 0,70 m (porta de abrir/pivotante, sem folha de correr) — `door_opening_alternatives.json`
| Cômodo | Abertura declarada | Status F2 | Violações restantes | Móveis movidos |
|---|---|---|---|---|
| BANHO 01 (r005) | 0,60 m | INFEASIBLE | entrada livre **0,516** × 0,60 | Vaso |
| BANHO 01 (r005) | **0,70 m** | **FEASIBLE** | nenhuma | Vaso |
| BANHO 02 (r006) | 0,60 m | INFEASIBLE | alcance do box 0,499 × 0,60; frente do vaso 0,523 × 0,60 (a entrada deixou de reprovar) | Bancada, Box, Vaso |
| BANHO 02 (r006) | 0,70 m | INFEASIBLE | as mesmas duas | Bancada, Box, Vaso |

## 3. Conclusão corrigida para a decisão #446
- **BANHO 01:** existe alternativa viável **dentro das regras atuais** — box com abertura de **0,70 m** (porta de abrir/pivotante; o solver não modela o arco de giro: exige conferir a área
  de giro no cômodo) e só o Vaso se move. Com 0,60 m declarados a entrada livre fica em 0,516 m (obstáculo/parede), por isso 0,70 m.
- **BANHO 02:** a porta resolve a entrada, mas **alcance (+0,101 m) e frente do vaso (+0,077 m) continuam reprovando**; só viabiliza com mudança geométrica adicional ou com os limiares
  do what-if (alcance 0,49 e frente 0,51; ver `p8_r6_alternatives/whatif_thresholds.json`).
- **LAVABO:** sem box; segue como em `p8` (falta 8,5 cm de frente do vaso).
- A recomendação de "decidir primeiro o Lavabo" fica; acrescenta-se: o **BANHO 01 pode ser desbloqueado pela decisão do modelo de porta do box** (sem relaxar nenhum limiar).

## 4. O que NÃO é
Medição no gêmeo/solver (L1), sem SketchUp e sem modelagem do giro da porta; aparência `PENDING_HUMAN`. Reprodução: `probe_door_opening.py` (`PT_TO_M=0.0259 PYTHONPATH=. python ...`, ~11 min por caso).
