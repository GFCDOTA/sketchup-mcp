# Grafo de dependências — resumo

> Gerado por `python -m tools.navigation.baseline_inventory --out docs/reports/fp054/f0` em `2556f41`. Retrato datado: regenere, não edite. Grafo completo em `dependency_graph.json`.

Nós: 394 · arestas: 679 · ci_runs 10 · import_lazy 249 · import_top 321 · mcp_calls 19 · ruby_require 16 · runs_ruby 64

## Pacote → pacote (imports Python, arestas entre pacotes distintos)

| De | Para | Imports |
|---|---|---|
| `tools.rooms.living` | `tools.rooms.shared` | 25 |
| `tools.rooms.bedroom` | `tools.rooms.shared` | 17 |
| `tools.rooms.kitchen` | `tools.rooms.shared` | 14 |
| `tools.validation` | `tools.rooms.shared` | 9 |
| `tools.orchestration` | `tools.rooms.shared` | 8 |
| `tools.rooms.living` | `tools.rendering` | 8 |
| `tools.rooms.shared` | `tools.sketchup` | 8 |
| `tools.validation` | `tools.furnish_apartment` | 8 |
| `tools.rooms.kitchen` | `tools.sketchup` | 6 |
| `tools.validation` | `interior.validators` | 6 |
| `tools.interior_studio` | `tools.knowledge` | 5 |
| `tools.mcp_server` | `tools.rooms.living` | 5 |
| `tools.navigation` | `tools.rooms.shared` | 5 |
| `tools.orchestration` | `tools.validation` | 5 |
| `tools.rendering` | `tools.sketchup` | 5 |
| `tools.rooms.bedroom` | `core.scale` | 5 |
| `tools.validation` | `core.scale` | 5 |
| `tools.validation` | `core.spatial_semantics` | 5 |
| `tools.knowledge` | `core.observability` | 4 |
| `tools.orchestration` | `tools.oracle` | 4 |
| `tools.orchestration` | `tools.rooms.living` | 4 |
| `tools.rendering` | `interior.renderers` | 4 |
| `tools.rooms.kitchen` | `core.scale` | 4 |
| `tools.rooms.living` | `core.scale` | 4 |
| `tools.rooms.living` | `tools.spatial_model` | 4 |
| `tools.validation` | `tools.room_type` | 4 |
| `interior.composer` | `tools.rooms.shared` | 3 |
| `ops/estudio-front/rag_chat.py` | `core.observability` | 3 |
| `tools.interior_studio` | `core.observability` | 3 |
| `tools.navigation` | `tools.validation` | 3 |
| `tools.orchestration` | `tools.rendering` | 3 |
| `tools.rendering` | `core.scale` | 3 |
| `tools.rooms.bedroom` | `tools.spatial_model` | 3 |
| `tools.rooms.kitchen` | `tools.validation` | 3 |
| `tools.rooms.living` | `interior.semantics` | 3 |
| `tools.rooms.shared` | `core.scale` | 3 |
| `tools.sketchup` | `core.scale` | 3 |
| `tools.sketchup` | `tools.validation` | 3 |
| `tools.validation` | `core.project_sources` | 3 |
| `tools.validation` | `tools.spatial_model` | 3 |
| `core.observability` | `tools.orchestration` | 2 |
| `interior.planners` | `interior.semantics` | 2 |
| `interior.renderers` | `tools.rooms.shared` | 2 |
| `interior.renderers` | `tools.sketchup` | 2 |
| `interior.semantics` | `tools.spatial_model` | 2 |
| `tools.interior_studio` | `tools.furnish_apartment` | 2 |
| `tools.knowledge` | `tools.oracle` | 2 |
| `tools.knowledge` | `tools.orchestration` | 2 |
| `tools.mcp_server` | `tools.sketchup` | 2 |
| `tools.mcp_server` | `tools.validation` | 2 |
| `tools.navigation` | `tools.rooms.living` | 2 |
| `tools.oracle` | `core.observability` | 2 |
| `tools.oracle` | `core.project_sources` | 2 |
| `tools.oracle` | `tools.rendering` | 2 |
| `tools.orchestration` | `core.observability` | 2 |
| `tools.orchestration` | `tools.claude_bridge` | 2 |
| `tools.orchestration` | `tools.finding_router` | 2 |
| `tools.orchestration` | `tools.furniture_overlap_gate` | 2 |
| `tools.orchestration` | `tools.room_type` | 2 |
| `tools.orchestration` | `tools.rooms.bathroom` | 2 |

## Mais importados (fan-in)

| Módulo | Importado por |
|---|---|
| `core.scale` | 34 |
| `tools.spatial_model` | 20 |
| `tools.rooms.shared.anatomy` | 16 |
| `tools.furnish_apartment` | 15 |
| `tools.rooms.shared.parts` | 15 |
| `tools.rooms.shared.geometry` | 12 |
| `tools.rooms.shared.sofa` | 11 |
| `tools.room_type` | 11 |
| `tools.rendering.render_parts_iso` | 11 |
| `tools.orchestration.correction.jsonl_io` | 8 |
| `tools.rooms.living.capabilities.sofa_class_matrix` | 8 |
| `tools.rooms.living.sofa_class` | 8 |
| `tools.sketchup.process` | 8 |
| `core.observability` | 7 |
| `core.project_sources` | 7 |
| `interior.renderers.render_provider` | 7 |
| `core.spatial_semantics` | 7 |
| `tools.rooms.shared.cabinet.model` | 6 |
| `tools.rooms.shared.materials` | 6 |
| `tools.sketchup.legacy_process` | 6 |
| `tools.rooms.kitchen.anchor_rules` | 6 |
| `core.schemas` | 6 |
| `tools.rooms.shared.cabinet.plan` | 6 |
| `tools.sketchup.shell.build_plan_shell_skp` | 6 |
| `tools.sketchup.batch` | 6 |

## Tools MCP → módulos que chamam

| Tool | Módulos |
|---|---|
| `furniture_class_derive` |  |
| `kitchen_ergonomics_audit` | `tools.rooms.kitchen.validation.ergonomics` |
| `list_capabilities` | `tools.sketchup.jobs`, `tools.sketchup.ops` |
| `promote_canonical` | `tools.orchestration.promote_canonical` |
| `reference_to_grammar` | `tools.knowledge.reference_grammar` |
| `room_gates` | `tools.furniture_overlap_gate`, `tools.validation.style_coherence_gate` |
| `run_deterministic_gates` | `tools.validation.run_deterministic_gates` |
| `skp_inventory` | `tools.claude_bridge.skp_inventory` |
| `su_apply_edits` | `tools.sketchup.jobs` |
| `su_build_shell` | `tools.sketchup.jobs` |
| `su_close` | `tools.sketchup.jobs` |
| `su_furnish` | `tools.sketchup.jobs` |
| `su_inspect` | `tools.sketchup.jobs` |
| `su_open` | `tools.sketchup.jobs` |
| `su_render` | `tools.sketchup.jobs` |
| `su_render_vray` | `tools.sketchup.jobs` |
| `su_status` | `tools.sketchup.jobs` |
| `validate_grammar_spec` | `tools.knowledge.reference_grammar` |
