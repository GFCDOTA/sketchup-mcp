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

## P4c-1 — executor SketchUp (feito)

| Antes | Agora | Compatibilidade |
|---|---|---|
| `tools/build_plan_shell_skp.{py,rb}` | `tools/sketchup/shell/` | `.py` com fachada; `.rb` caminho único |
| `tools/{place_layout_skp.py,place_layout_skp.rb,place_layout_geom.rb,build_furniture_skp.rb,furnish_plan.rb}` | `tools/sketchup/furnish/` | `place_layout_skp.py` e `.rb` caminho único (mapa `path_resolver_unico`); `furnish_apartment` importa do novo |
| `tools/{inspect_skp,screenshot_camera,skp_editability_report}.rb` | `tools/sketchup/inspect/` | caminho único |
| `tools/vray_export.rb` | `tools/sketchup/vray/` | caminho único |
| `tools/disarm_sketchup_autoruns.py`, `tools/su_runner_safety.py` | `tools/sketchup/{disarm_autoruns,runner_safety}.py` | fachada |

L2 no SketchUp 26 (processo próprio): `su_build_shell` da planta_74 reproduz o `geometry_report` canônico (só caminhos diferem) com todos os
gates PASS; `su_furnish` materializa 402 caixas; a bateria MCP de 38 chamadas (inspect/apply_edits/render/close) tem veredito
idêntico ao baseline, salvo `N25` (muda por causa do porte do V-Ray, #285) e `N06` (uma saída transitória do SketchUp que não se
repetiu em 2 reexecuções).

## P4c-2 — validação transversal (feito)

| Antes | Agora | Compatibilidade |
|---|---|---|
| 28 gates/auditorias em `tools/` (`*_gate.py`, `*_audit.py`, `gate_*`, `geometry_sanity`, `run_deterministic_gates`, `repo_health_gate`, `furniture_wall_gap`, `diagnose_wall_stubs`, `render_bbox_audit`) e `scripts/generalization_gate.py` | `tools/validation/` | fachada (import, `-m`, script) |

Os 8 módulos de governança de `tools/rooms/` (`inventory_gate`, `ownership_audit`, …) **ficam** onde estão: o mapa classifica `tools/rooms/` como
`retain` e o CI os chama por esse caminho; mover seria mudança de política, não de responsabilidade comprovada (registrado como exceção
nomeada, não esquecimento).

## P4c-3 — renderização, orquestração, conhecimento, oráculo e estúdio (feito)

| Antes | Agora | Compatibilidade |
|---|---|---|
| `render_*`, `auto_camera`, `batch_theme_render`, `compose_side_by_side`, `crop_render`, `gen_textures`, `material_review`, `overlay_diff`, `pdf_overlay_verify`, `theme_palette`, `tweak_vrscene` | `tools/rendering/` | fachada |
| `material_review.rb`, `render_room.ps1` | `tools/rendering/{ruby/,}` | caminho único |
| `furnish_apartment`, `fidelity_loop`, `promote_artifact`, `promote_canonical`, `regenerate_consensus`, `variant_axes`, `variant_sweep` | `tools/orchestration/` | fachada |
| `correction_*`, `finding_router`, `jsonl_io`, `vision_queue_consumer` | `tools/orchestration/correction/` | fachada |
| `corpus_to_rag`, `furniture_reference_analyzer`, `project_memory_db`, `rag_*`, `reference_db`, `reference_grammar`, `retrieval_eval`, `taste_writeback` | `tools/knowledge/` | fachada; `README_project_memory.md` ganha ponteiro |
| `ask_gpt_gate`, `consult_tier`, `gpt_*`, `human_verdict`, `negative_dogfood`, `ollama_bridge`, `oracle_providers`, `run_skp_visual_review`, `scripts/make_gpt_review_sheet.py` | `tools/oracle/` | fachada; o veredito visual continua só do Felipe |
| `curator`, `interior_quality_scorecard`, `studio_log` | `tools/interior_studio/` | fachada |

L2: `material_review.rb` no caminho novo gera os 4 proofs **byte-idênticos** (SHA-256) aos do caminho antigo, sobre o mesmo `.skp` mobiliado.

## P4d — pastas inteiras (feito)

| Antes | Agora | Compatibilidade |
|---|---|---|
| `tools/pdf_knowledge/` | `tools/knowledge/pdf/` | CLIs `*.py` com fachada no caminho antigo; README e manifesto-modelo movidos (README antigo vira ponteiro); `.gitignore` cobre o novo `output/` |
| `tools/prompts/` | `tools/oracle/prompts/` | caminho único (referências reescritas); `tools/prompts/README.md` é ponteiro |
| `tools/quadrado/` | `tools/rendering/quadrado/` | `render_view.py` com fachada; `render_view.rb` com stub no caminho antigo |

**Congelados por decisão (D-002…D-005):** `tools/furnish_plan.py` (+`.rb` já movido), `tools/trace_view.py` e `scripts/set_clipboard_image.ps1`
seguem onde estão até a decisão do Felipe — ver [decisões abertas](../specs/FP-043_open_decisions.md).

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

## FP-044 / F2 — programa do sofá sai da raiz

| Antes | Depois | Observação |
|---|---|---|
| `configs/sofa_*.json` | `tools/rooms/living/capabilities/ruby/sofa_program/configs/` | o Ruby resolve por `__dir__`; `ENV['SOFA_*']` continua mandando |
| `textures/fabric_*_{albedo,bump}.png` | `assets/textures/sofa_fabric/` | mesmo blob; spec V-Ray e gerador de tecido repontados |
| `renders/check`, `renders/sofa_eval`, `renders/sofa_vray` (histórico versionado) | `artifacts/review/sofa_program/` | evidência; mesmo blob; `check/` e `sofa_vray/` ganharam `README.md` só de proveniência (padrão D-006) |
| caminhos antigos citados em `references/sofas/*.jsonl` | sem mudança | log histórico: **não** é reescrito; vale a tabela acima para achar o arquivo hoje |
| saída **nova** dos geradores do sofá (`renders/…`) | `runs/sofa_program/…` (scratch, ignorado pelo git) | o Ruby não grava mais em pasta versionada |
| `scripts/{generalization_gate,make_gpt_review_sheet,sofa_fabric_material}.py` | `python -m tools.validation.generalization_gate`, `python -m tools.oracle.make_gpt_review_sheet`, `python -m tools.rooms.living.capabilities.sofa_fabric_material` | fachadas removidas (sem consumidores restantes) |

## FP-044 / F3 — contratos perto do uso

| Antes | Depois | Observação |
|---|---|---|
| `schemas/*.schema.json` (9) | `core/schemas/` | mesmo blob (exceto a descrição de `judged_variant`, que citava o caminho antigo); quem lê usa `from core.schemas import schema_path, load` — nada de `ROOT / "schemas" / …` |
| `capability_catalog.py`, `specialists.py` (`root / "schemas/…"`) | `schema_path(nome, root)` | o parâmetro `root` continua valendo (testes em diretório temporário) |
| `interior/schemas/` | sem mudança | outro conjunto (intents de cena); não referencia os contratos movidos |
