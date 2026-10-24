# FP-055 P0 — matriz de lacunas de integração (2026-10-23)

Estados (FP-055 §6.7): AVAILABLE → INVOKED → CONSUMED → REFLECTED_IN_MODEL → VALIDATED. Os três primeiros são medidos por
`tools.navigation.pipeline_audit`. REFLECTED/VALIDATED pedem inspeção do `.skp` construído e ficam `NOT_EVALUATED` aqui.
CONSUMED só por regra explícita (`_CONSUMED_RULES`), nunca por import.

## Capacidades do catálogo (18)
| Capacidade | Catálogo | INVOKED | CONSUMED | Lacuna |
|---|---|---|---|---|
| kitchen.layout.galley | L2_PASS | sim | sim | — |
| kitchen.sink-anchor-guard | L1_PASS | sim | sim (bloqueia) | — |
| kitchen.ergonomics.audit | UNTESTED | não | não | fora do fluxo |
| **shared.cabinet.parametric** | **L2_PASS** | **não** | **não** | marcenaria provada no SketchUp não entra no apartamento |
| **kitchen.cabinet.plain-fronts** | **L2_PASS** | **não** | **não** | idem |
| **kitchen.cabinet.shaker-door** | **L2_PASS** | **não** | **não** | idem |
| **shared.cabinet.front.shaker** | **L2_PASS** | **não** | **não** | idem |
| living.layout.boxes | L1_PASS | sim | sim | — |
| living.sofa.class | L1_PASS | sim | sim (transitivo) | — |
| living.sofa.gate | L1_PASS | não | não | gate fora do fluxo |
| bedroom.layout.boxes | L1_PASS | sim | sim | — |
| bedroom.bed.build | L1_PASS | sim | sim (transitivo) | — |
| bedroom.wardrobe.build | L1_PASS | sim | sim (transitivo) | — |
| bedroom.wardrobe.gate | L1_PASS | não | não | gate fora do fluxo |
| bathroom.layout.boxes | L1_PASS | sim | sim | — |
| bathroom.wet-room.guard | L1_PASS | sim | **não** (só loga) | não bloqueia |
| service.layout.boxes | L1_PASS | sim | sim | — |
| circulation.gate | L1_PASS | o módulo roda via `GateSession` dentro dos brains; o símbolo do catálogo `gate` não | — | catálogo aponta outra entrada |

## Componentes da FP-054/F1 e o conhecimento
| Componente | Existe | Executado na geração | Lacuna |
|---|---|---|---|
| Especialistas (9 `specialist.v1.json`, `specialists.plan`) | sim | **não** (0/9) | despacho por `room_type` ignora perfil/allowlist/binding |
| Fragmentos de especialista | sim | não | — |
| Receitas de tutoriais (19) | sim | **não** (0/19) | nenhuma receita seleciona operação no build |
| Interfaces F1C do banheiro | sim | chamado | **descartado**: `collect_boxes` ignora `out["functional_interfaces"]` |
| Interfaces F1C da cozinha | sim | não | — |
| Folga funcional F1B/F1C | sim | não | só relatório separado |
| Solver F2 (problem/engine/candidates/solver/ranking/proposal) | sim | não | nenhuma proposta chega ao builder |
| Proveniência de limiares (`core.functional_constraints`) | sim | não | — |
| `furniture_overlap_gate`, `room_collisions` | sim | não | colisão e parede não bloqueiam a geração |
| `circulation_gate` | sim | **sim** (dentro dos brains) | — |
| `layout_decisions` (decisões aprovadas) | sim | **sim** | só quarto |
| `core.spatial_semantics` | sim | sim | rótulos, não decisão |

## Runtime
| Item | Estado |
|---|---|
| Checkout do MCP (`E:/Claude/apps/sketchup-mcp`, branch `develop`) | `90d4433`, **102 commits atrás** de `origin/develop`, 0 à frente; sujo só com `?? worktrees/` |
| Verificação de identidade do runtime antes de gerar | **não existe** |
| Versão do SketchUp | 26.0.429 (registrada só nos jobs) |

## Defeitos funcionais conhecidos (permanecem no baseline)
Banho 01 vão do box 0,327 · Banho 02 frente do box 0,00, vão 0,00, inalcançável, frente do vaso 0,523 · Lavabo frente da
bancada 0,044, frente do vaso 0,032, vaso inalcançável. A F2C/F2E (#399–#401) mostrou que, com o grau de liberdade declarado,
os três banheiros são INFEASIBLE: corrigir pede decisão do Felipe (vão do box no builder; parede/louça do vaso), não só integração.
