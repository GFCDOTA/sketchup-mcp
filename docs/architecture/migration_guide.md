# Guia de migração

Para quem procura um arquivo que mudou de lugar, e para quem vai mover um. Mapa geral:
[mapa do repositório](repository_map.md). Decisão e risco de **cada** arquivo: [mapa P0](../specs/fp043_p0_map.v1.json)
(resumo: [FP-043 P0](../specs/FP-043_P0_map.md)).

## Estado

- **Raiz (P2):** `CLAUDE_COGNITIVE_ARCHITECTURE.md`, `HANDOFF.md`, `KICKOFF.md`, `HISTORICO_SOFA.json`,
  `vray_pipeline_proof.png` e `planta_74.pdf` **já foram movidos** (tabela abaixo). O caminho do PDF é resolvido só por
  `core.project_sources.plant_pdf_path`; a raiz só tem arquivos de papel explícito.
- **`tools/` (P4):** nada movido ainda.

Os movimentos de arquivos protegidos estão registrados em
[`fp043_protected_renames.v1.json`](../specs/fp043_protected_renames.v1.json) (conteúdo idêntico, verificado por teste).

## Regras de compatibilidade

1. **O caminho antigo continua funcionando.** Todo `python -m tools.<nome>` e todo `from tools.<nome> import …` documentado
   segue válido: o arquivo antigo vira uma **fachada** que delega à implementação canônica (`compat: facade_at_old_path`
   no mapa). Os módulos que já são fachada (`tools/sofa_builder.py`, `tools/kitchen_layout.py`, …) ficam como estão.
2. **Uma implementação por responsabilidade.** A fachada só delega: sem lógica duplicada e sem cópia divergente.
3. **Script carregado por caminho** (`.rb` em `-RubyStartup`, `ROOT / "tools" / "x.rb"`) **não** vira fachada: antes de
   mover, introduz-se **um** resolvedor de caminho e os chamadores passam a usá-lo (`compat: path_resolver_unico`).
4. **Fixtures e artefatos canônicos ficam onde estão.** A fonte `planta_74.pdf` é a única migração de *caminho* de um
   protegido: bytes e SHA256 idênticos, sem cópia divergente, e só junto de um resolvedor único.
5. **Janela de compatibilidade:** as fachadas **não** são removidas nesta fase. Remover uma exige spec própria, zero
   consumidores no repositório e os externos atualizados (`E:/Claude/.mcp.json`, `harness-app`).
6. **Pontos externos que não mudam de caminho:** `python -m tools.mcp_server.server` e
   `fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json`.

## Para onde cada família vai (resumo; o detalhe por arquivo está no JSON)

| Hoje (direto em `tools/`) | Destino planejado | Fase |
|---|---|---|
| `*_gate.py`, `*_audit.py`, `geometry_sanity`, `run_deterministic_gates`, `repo_health_gate` | `tools/validation/` | P4 |
| `render_*.py`, `compose_side_by_side`, `tweak_vrscene`, `overlay_diff`, `gen_textures`, … | `tools/rendering/` | P4 |
| `furnish_apartment`, `variant_sweep`, `promote_*`, `correction_*`, `fidelity_loop`, … | `tools/orchestration/` | P4 |
| RAG, `project_memory_db`, `reference_db`, `reference_grammar`, `pdf_knowledge/` | `tools/knowledge/` | P4 |
| `ask_gpt_gate`, `oracle_providers`, `run_skp_visual_review`, `negative_dogfood`, … | `tools/oracle/` | P4 |
| `place_layout_skp.*`, `build_plan_shell_skp.*`, `vray_export.rb`, `inspect_skp.rb`, `su_runner_safety` | `tools/sketchup/{furnish,shell,vray,inspect}/` e `runner_safety.py` | P4 |
| `kitchen_*`, `sofa_*`, `render_banho_*`, `place_bedroom_skp`, `make_synthetic_*` | `tools/rooms/<cômodo>/…` | P4 |
| `room_type`, `spatial_model`, `layout_rules`, `shell_parts`, `decor_*` | `tools/rooms/shared/` | P4 |
| `scripts/*sofa*.rb` | `tools/rooms/living/capabilities/` | P4 |
| `HANDOFF.md` (raiz) | `docs/handoffs/2026-08-27_ai_pipeline_inspector_handoff.md` | **feito** (P2) |
| `KICKOFF.md` (raiz) | `docs/handoffs/2026-07-23_kickoff_proxima_sessao.md` | **feito** (P2) |
| `CLAUDE_COGNITIVE_ARCHITECTURE.md` (raiz) | `docs/architecture/agent_architecture.md` | **feito** (P2) |
| `HISTORICO_SOFA.json` (raiz) | `references/sofas/history/HISTORICO_SOFA.json` | **feito** (P2) |
| `vray_pipeline_proof.png` (raiz) | `artifacts/review/vray_pipeline_proof_2026-06/` | **feito** (P2) |
| `planta_74.pdf` (raiz) | `projects/planta_74/source/planta_74.pdf` | **feito** (P2, via `core.project_sources`) |

## P4a — cozinha e compartilhado (feito)

| Antes | Agora | Compatibilidade |
|---|---|---|
| `tools/kitchen_ergonomics.py` | `tools/rooms/kitchen/validation/ergonomics.py` | fachada (import, `-m`, script) |
| `tools/kitchen_wall_regression_gate.py` | `tools/rooms/kitchen/validation/wall_regression.py` | fachada |
| `tools/kitchen_vray.py` | `tools/rooms/kitchen/capabilities/vray.py` | fachada; efeitos colaterais de import viraram `main()` |
| `tools/bake_theme_skp.py` | `tools/rooms/kitchen/capabilities/bake_theme.py` | fachada; `ROOT` corrigido (apontava para `apps/`) |
| `tools/recolor_kitchen_theme.rb`, `tools/render_kitchen_angles.rb` | `tools/rooms/kitchen/capabilities/ruby/` | caminho único, sem stub; referências reescritas |
| `tools/{layout_rules,decor_anatomy_spec,decor_builders,room_type,semantic_zones,shell_parts,spatial_model}.py` | `tools/rooms/shared/` | fachada |
| `tools/rooms/kitchen/validation.py` | `tools/rooms/kitchen/validation/__init__.py` | mesmo import público |

Prova: `tests/test_fp043_p4_migration.py` (fachada só delega; import frio nas duas ordens devolve o mesmo módulo) e saída de
`collect_boxes` da `planta_74` idêntica antes/depois (402 caixas).

## P4b — demais cômodos (feito)

| Antes | Agora | Compatibilidade |
|---|---|---|
| `scripts/{build_sofa_*,sofa_components,sofa_generator,sofa_primitives,sofa_vray_render}.rb` | `tools/rooms/living/capabilities/ruby/sofa_program/` | caminho único (raiz do repo via `__dir__`); referências reescritas |
| `tools/{render_sala_eyelevel,sofa_premium_harness,sofa_premium_integrate}.rb` | `tools/rooms/living/capabilities/ruby/` | caminho único |
| `scripts/sofa_fabric_material.py`, `tools/{make_synthetic_rooms,sofa_class_matrix,sofa_furnish_fase1_compare,sofa_premium_harness,sofa_venezia_*}.py` | `tools/rooms/living/capabilities/` | fachada |
| `tools/layout_candidates.py`, `tools/sofa_gate.py` | `tools/rooms/living/{planning,validation}/` | fachada |
| `tools/{make_synthetic_bedrooms,place_bedroom_skp}.py` | `tools/rooms/bedroom/capabilities/` | fachada |
| `tools/{estudio_banheiro_scene,render_banho_auto,render_banho_vray}.py` | `tools/rooms/bathroom/capabilities/` | fachada |
| `interior/validators/{bed,bed_placement,nightstand,wardrobe}_gate.py` | `tools/rooms/bedroom/validation/` | fachada em `interior/validators/` |
| `interior/validators/sofa_placement_gate.py` | `tools/rooms/living/validation/` | fachada |
| `interior/validators/{scene_spatial,furniture_visual}_gate.py`, `validation_report.py` | `tools/validation/` | fachada |

`service` já tinha o dono único (`tools/rooms/service/layout.py`); `balcony`, `closet` e `home_office` seguem advisory/reuso e
`circulation` validation-only — nenhum builder foi criado.

## Para quem vai mover um arquivo (checklist do PR)

1. `python -m tools.navigation.consumers <caminho>`: leia **todos** os consumidores (código, testes, CI, MCP, config, docs).
2. Revise à mão o que a busca não vê: caminho montado em runtime, `Path(__file__).parents[n]` (a profundidade muda),
   `require_relative` em Ruby, strings em YAML/JSON/PowerShell.
3. Mova a implementação para o destino do mapa; deixe a fachada no caminho antigo (ou o resolvedor, para scripts).
4. Atualize o item no [mapa P0](../specs/fp043_p0_map.v1.json) (`status: done`) e o estado em [repository_map](repository_map.md).
5. Atualize o inventário e os manifestos FP-042 **no mesmo PR**, sem regenerá-los por inteiro.
6. Prove: imports frios em ordens diferentes, `-m` da CLI antiga, `python -m pytest tests/ -m "not planta74_scale"` e
   `PT_TO_M=0.0259 python -m pytest tests/ -m planta74_scale` (processos separados), `python -m tools.mcp_server.smoke`,
   `python -m tools.navigation.p0_map --check` e `python -m tools.navigation.docs_check`.
7. Um PR por intenção: movimentação **não** vai junto de correção de comportamento nem de capacidade nova.

## Para quem adiciona um módulo de cômodo

Siga a convenção da [cozinha](../../tools/rooms/kitchen/README.md): `README.md` primeiro; `specialist.md`,
`specialist.v1.json` e `knowledge/index.v1.json` quando o perfil existir (P5); `capabilities/` só quando houver adapter
comprovado. Não crie pasta vazia: o estado `previsto` do mapa existe para isso.
