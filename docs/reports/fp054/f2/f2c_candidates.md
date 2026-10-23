# FP-054 F2C — geração de alternativas e estados do solver (2026-10-23)

## O que o solver pode mexer (DOF declarado pelo especialista do banheiro — PROPOSTA, `PENDING_FELIPE`)
- vaso e lavatório: deslizar ao longo da parede de apoio, −0,40…+0,40 m, passo 0,02 m (41 posições);
- box: girar em torno do próprio centro 0/90/180/270° (a reflexão simples foi testada e não resolve o Banho 02);
- cozinha: nada (bancada ancorada no ponto hidráulico do PDF) — só diagnóstico.

Busca **exaustiva** sobre essa discretização (sem SciPy/OR-Tools): exata **só no grid declarado**; nada é dito fora dele.
Avaliação com o motor F2B, peças na vizinhança do cômodo (célula + 1 m; equivalência com a lista completa testada).

## Resultado na planta real (espaço inteiro avaliado)
| Cômodo | Candidatos | Estado | Melhor alternativa | O que sobra | Por quê não há solução no DOF |
|---|---|---|---|---|---|
| Cozinha r004 | 1 | FEASIBLE (ORIGINAL) | — | nada | — |
| Banho 01 r005 | 6 724 | INFEASIBLE | ORIGINAL | vão do box 0,327 / 0,60 m (WALL) | vão é do modelo da porta do box (folha 0,61 > fixo 0,46); giros fazem o box invadir parede. Pede parâmetro do builder |
| Banho 02 r006 | 6 724 | INFEASIBLE | Box R270 + Vaso +0,10 | vão do box 0,31; alcance do box 0,499 (gargalo); frente do vaso 0,523 (parede oposta) | o giro tira a porta do box da parede, mas a frente do vaso é limitada pela profundidade do cômodo em todos os 6 724 |
| Lavabo r007 | 1 681 | INFEASIBLE | Bancada −0,32 + Vaso +0,36 | frente do vaso 0,515 / 0,60 m (WALL) | separar as peças resolve o conflito mútuo e o alcance; resta a profundidade do cômodo |

Nenhuma alternativa foi aplicada à planta. INFEASIBLE vale para esses graus de liberdade e esse passo; as saídas reais são
decisões do Felipe: parâmetro do vão do box (r005/r006), trocar a louça de parede ou outra louça (r006/r007).

## Testes (`tests/test_fp054_f2c_candidates.py`, sintéticos)
Enumeração determinística começando no ORIGINAL; deslize que libera obstáculo → FEASIBLE só para o lado livre; aplicar não muta a
entrada e mantém a parede de apoio; giro gira a normal; armário corrido → INFEASIBLE (espaço inteiro); orçamento esgotado →
UNKNOWN; entrada inválida não enumera; peça com `profile_world` é recusada (nunca meio movida); vizinhança.
