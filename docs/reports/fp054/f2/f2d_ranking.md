# FP-054 F2D — ordenação lexicográfica e estabilidade (2026-10-23)

`tools/rooms/shared/spatial_solver/ranking.py`. **Sem soma ponderada**: cada critério só desempata o anterior.
1 viável antes de inviável · 2 menos violações rígidas · 3 menos regras abaixo do alvo de projeto · 4 maior margem mínima sobre o
mínimo de referência · 5 maior margem somada · 6 menor intervenção (objetos movidos, deslocamento, giros) · 7 id do candidato.
Cada posição traz a explicação ("fica atrás da anterior pelo critério X"). Entre inviáveis a ordem diz só **"o mais próximo"**.

Decisão explícita: conforto (4/5) vem antes de deslocamento (6) — no sintético, deslizar 0,34 m vence 0,24 m por deixar mais
frente livre. Inverter é trocar dois critérios; fica como proposta para o Felipe.

## Planta real (espaço completo de F2C)
| Cômodo | Estado | 1º da ordem | Violações que sobram | Posição do ORIGINAL |
|---|---|---|---|---|
| Cozinha | FEASIBLE | ORIGINAL (margem 0,188 m) | — | 1 |
| Banho 01 | INFEASIBLE | Vaso −0,16 | vão do box 0,327 / 0,60 m | 369 |
| Banho 02 | INFEASIBLE | Box R270 + Vaso +0,26 | vão do box 0,31; alcance do box 0,499; frente do vaso 0,523 | 2 638 |
| Lavabo | INFEASIBLE | Bancada −0,38 + Vaso +0,36 | frente do vaso 0,515 / 0,60 m | 684 |

Os "1º" dos banheiros **não são soluções** — continuam reprovando regra rígida; mostram até onde o DOF declarado chega.

## Estabilidade (`tests/test_fp054_f2d_ranking.py`)
Violação rígida nunca perde por margem; menos violações primeiro; regra abaixo do alvo antes da margem; empate → menor
intervenção → id; margem ausente vai para o fim; ordem independente da ordem de entrada (5 embaralhamentos semeados); solve
sintético reproduzível byte a byte.
