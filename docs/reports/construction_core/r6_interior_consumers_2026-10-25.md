# Trilha R6 — mapa de consumidores do pacote `interior/` (2026-10-25)

Issue: #463 (critério 1: mapear consumidores). Gerado por análise estática de `import` (AST) sobre `tools/`, `tests/`, `core/` e `interior/`
em `develop@77493f2`. Nada foi movido: este é o mapa que a R6 exigia antes de mexer.

## Achado principal
O escopo literal da R6 — "lógica de sala fora de `interior/` → `tools/rooms/living/planning/`" — **já está feito para o planejador da sala**:
`interior/planners/living_room_planner.py` tem 32 linhas e é fachada de `tools.rooms.living.planner` (FP-042; `tests/test_fp042_living_planner_ownership.py`
trava a identidade). Os 8 arquivos de `interior/validators/` são fachadas de 22 linhas. O que ainda tem lógica real em `interior/`:
`composer/scene_composer.py` (765 linhas), `planners/placement_brain.py` (171), `semantics/wall_affordance.py` (105), `semantics/room_graph.py` (72)
e os provedores de `renderers/` (26–151).

## Consumidores por arquivo (estático)
| Arquivo em `interior/` | Consumidores fora de `interior/` | Consumidores dentro de `interior/` |
|---|---|---|
| `interior/composer/scene_composer.py` | `tests/test_intent_to_scene.py`, `tests/test_living_sofa_is_approved_premium.py`, `tools/rooms/bathroom/capabilities/estudio_banheiro_scene.py`, `tools/validation/scene_spatial_gate.py` | — |
| `interior/planners/living_room_planner.py` | `tests/test_bed_placement_gate.py`, `tests/test_fp042_living_furnishing_adapter.py`, `tests/test_fp042_living_planner_ownership.py`, `tools/rooms/living/furnishing.py`, `tools/rooms/living/validation/sofa_placement_gate.py` | — |
| `interior/planners/placement_brain.py` | `tests/test_fp042_living_planner_ownership.py`, `tools/rooms/bedroom/validation/bed_placement_gate.py` | — |
| `interior/renderers/enscape_preview_provider.py` | — | `interior/renderers/__init__.py` |
| `interior/renderers/render_provider.py` | `tools/rendering/render_scene_views.py`, `tools/rendering/render_scene_vray.py`, `tools/rooms/living/capabilities/sofa_class_matrix.py` | `interior/renderers/__init__.py`, `interior/renderers/enscape_preview_provider.py`, `interior/renderers/sketchup_basic_provider.py`, `interior/renderers/vray_final_provider.py` |
| `interior/renderers/sketchup_basic_provider.py` | `tools/rendering/render_scene_views.py`, `tools/rendering/render_scene_vray.py`, `tools/rooms/living/capabilities/sofa_class_matrix.py` | `interior/renderers/__init__.py` |
| `interior/renderers/vray_final_provider.py` | — | `interior/renderers/__init__.py` |
| `interior/semantics/room_graph.py` | — | `interior/planners/placement_brain.py`, `interior/semantics/wall_affordance.py` |
| `interior/semantics/wall_affordance.py` | `tools/rooms/living/furnishing.py`, `tools/rooms/living/planner.py`, `tools/rooms/living/validation/sofa_placement_gate.py` | `interior/planners/placement_brain.py` |
| `interior/validators/bed_gate.py` | `tools/validation/validation_report.py` | — |
| `interior/validators/bed_placement_gate.py` | `tests/test_bed_placement_gate.py`, `tools/validation/validation_report.py` | — |
| `interior/validators/furniture_visual_gate.py` | `tools/validation/validation_report.py` | — |
| `interior/validators/nightstand_gate.py` | `tools/validation/validation_report.py` | — |
| `interior/validators/scene_spatial_gate.py` | `tests/test_intent_to_scene.py` | — |
| `interior/validators/sofa_placement_gate.py` | `tests/test_fp042_living_planner_ownership.py`, `tools/validation/validation_report.py` | — |
| `interior/validators/validation_report.py` | — | — |
| `interior/validators/wardrobe_gate.py` | `tools/validation/validation_report.py` | — |

## Destino sugerido por peça (NÃO aplicado; cada um é um PR próprio com ownership + suíte)
| Peça | Dono natural | Observação |
|---|---|---|
| `semantics/wall_affordance.py` | `tools/rooms/living/planning/` | consumida só por sala (planner, furnishing, sofa_placement_gate) e por `room_graph` |
| `planners/placement_brain.py` | `tools/rooms/bedroom/` (planning) | único consumidor de produção: `bedroom/validation/bed_placement_gate.py`; teste `tests/test_bed_placement_gate.py` |
| `composer/scene_composer.py` | `tools/rooms/shared/` (trilha Intent-to-Scene) | consumido por `tools/validation/scene_spatial_gate.py`, `bathroom/capabilities/estudio_banheiro_scene.py` e testes: é transversal, não é de sala |
| `renderers/*` | `tools/rendering/` | consumidos por `tools/rendering/*` e `living/capabilities/sofa_class_matrix.py` |
| `semantics/room_graph.py` | junto de `wall_affordance` | só uso interno |
| `planners/living_room_planner.py`, `validators/*` | permanecem como fachadas | removê-las exige repontar os testes de compatibilidade listados |

Restrições para quem mover: manter as fachadas com a mesma identidade de símbolo (testes FP-042), atualizar `fp042_inventory.v1.json`
(dono do caminho) e o gate de ownership; peças fora dos fechos L2 do catálogo (conferir com `python -m tools.rooms.capability_catalog`).
