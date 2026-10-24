# FP-055 P0 — grafo de execução real da geração do apartamento (2026-10-23)

Fonte: `python -m tools.navigation.pipeline_audit docs/reports/fp055/p0`, que roda o caminho de geração sob `sys.setprofile`
e registra cada função chamada (`generation_trace.json`). É rastreio dinâmico, não leitura de código.

## Entrypoints que geram o apartamento inteiro
| Entrypoint | Onde grava | Caminho |
|---|---|---|
| `python -m tools.furnish_apartment` → `tools/orchestration/furnish_apartment.py::main` | **`artifacts/planta_74/furnished/` (oficial)** — apaga e regrava | `collect_boxes` → SketchUp + `place_layout_skp.rb` |
| MCP `su_furnish` → `tools/sketchup/jobs.py::furnish` | `runs/` | `collect_boxes` → `place_layout_skp.rb` |

Os dois compartilham **o mesmo** `collect_boxes`. Escritores parciais (cômodo, tema ou variante) também existem e não geram o
apartamento: `tools/rooms/bedroom/capabilities/place_bedroom_skp.py`, `tools/rooms/kitchen/capabilities/bake_theme.py`
(grava em `artifacts/`), `tools/rooms/living/capabilities/ruby/sofa_premium_integrate.rb` (originou o `.skp` com sofá
premium), `tools/furnish_plan.py` (3D Warehouse, legado), `tools/sketchup/furnish/place_layout_skp.py` (só a sala, legado), os
fluxos de gabinete/Shaker da cozinha (`tools/rooms/kitchen/capabilities/*_flow.py`) e o shell (`build_plan_shell_skp.py`).

## O que `collect_boxes` executa
```text
consensus.json
  └─ tools.room_type.classify_rooms                       → 8 cômodos
  └─ tools.rooms.dispatch.get_brain(room_type)            (despacho por TIPO, sem especialista)
       ├─ BEDROOM  bedroom.furnishing.bedroom_designer_boxes → bedroom.designer / layout / layout_decisions (#381)
       │            shared.bed.build_bed, shared.wardrobe.build_wardrobe, circulation_gate.GateSession
       ├─ LIVING   living.furnishing.living_room_boxes → living.planner, interior.planners.living_room_planner,
       │            sofa_class / rack_class / coffee_table_class, circulation_gate.GateSession
       ├─ KITCHEN  kitchen.layout.build_boxes ; depois kitchen.validation.require_kitchen_anchor (BLOQUEIA)
       ├─ BATHROOM bathroom.layout.build_boxes (exporta out["functional_interfaces"] — DESCARTADO) ;
       │            bathroom.validation.unexpected_wet_room_kinds (só LOGA)
       └─ SERVICE  service.layout.build_boxes
  └─ core.spatial_semantics.annotate_all                  (rótulos de intenção; não muda geometria)
  └─ caixas → env LAYOUT_BOXES → SketchUp -RubyStartup tools/sketchup/furnish/place_layout_skp.rb (+ place_layout_geom.rb)
```

## O que NÃO é executado (existe e tem teste)
`tools/rooms/specialists.py` (plan), `specialist_fragments.py`, `capability_catalog.py`, `tools/sketchup/knowledge.py` e as 19
receitas de `references/sketchup/knowledge/`, `tools/rooms/kitchen/functional_interfaces.py`, `tools/validation/functional_clearance.py`,
`core/functional_constraints.py`, todo `tools/rooms/shared/spatial_solver/`, `tools/validation/furniture_overlap_gate.py`,
`tools/validation/room_collisions.py` e `tools/rooms/shared/cabinet/` (gabinete paramétrico e Shaker, L2_PASS só no fluxo de
capacidade da cozinha).

## Depois do SketchUp
`main` roda `flat_white_check` (textura no render) e grava um item de galeria. **Nenhum gate funcional, de colisão ou de parede
roda sobre o modelo construído**, e nada compara o que foi construído com o que foi pedido.
