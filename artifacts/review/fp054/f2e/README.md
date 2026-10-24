# FP-054 F2E — proposta somente-leitura por cômodo (2026-10-23)

Gerado por `PT_TO_M=0.0259 python -m tools.validation.f2e_proposal_board <dir>` sobre develop `a8cde14` + as mudanças deste PR
(colisão estrita do solver, orçamento 10 000). Nada aplicado à planta; nenhum SketchUp (sem proposta viável não há o que provar em L2).

| Cômodo | Tipo | 1º da ordem | Violações rígidas que sobram | Posição do ORIGINAL |
|---|---|---|---|---|
| Cozinha r004 | NO_CHANGE_NEEDED | ORIGINAL | — | 1 |
| Banho 01 r005 | CLOSEST_INFEASIBLE | Vaso −0,16 | vão do box 0,327 m | 292 |
| Banho 02 r006 | CLOSEST_INFEASIBLE | Bancada +0,10, Box R270, Vaso +0,20 | vão do box 0,31; alcance do box 0,50; frente do vaso 0,523 | 2 027 |
| Lavabo r007 | CLOSEST_INFEASIBLE | Bancada −0,38, Vaso +0,36 | frente do vaso 0,515 | 684 |

**Achado durante a F2E:** o 1º do Banho 02 com a regra anterior punha o vaso 29% dentro do gabinete suspenso (0,067 m²), abaixo
do FAIL de 30% do gate do builder. Corrigido: para peças do solver qualquer interpenetração 3D > 4 in² é colisão rígida
(`iter_overlap_pairs` ganhou limiares opcionais; padrão do gate inalterado). Os rankings de F2C/F2D já mergeados usavam a regra
antiga — os relatórios deles ficam como retrato datado; os números válidos são estes.

Overlays `<rid>_before_after.png`: desenhados com as MESMAS linhas de avaliação que decidiram o tipo. **O que NÃO é:** solução
aprovada, alteração da planta ou veredito visual (`PENDING_HUMAN`). Destravar os banheiros exige decisão do Felipe (vão do box no
builder; parede/louça do vaso).
