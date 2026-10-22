# Handoff por arquivo — raiz, artifacts, fixtures, references, assets, ops, projects

> Gerado por `python -m tools.navigation.file_audit --out docs/reports/file_audit` em `e0de518`.
> Retrato datado: regenere, não edite. Estados e regras no docstring de `tools/navigation/file_audit.py`.

Contagem: ACTIVE_ENTRYPOINT 2, AGENT_INSTRUCTION 6, CLI_DOC_ONLY 1, CONFIG 27, DOC 2, EVIDENCE_OR_DATA 1129, HISTORICAL 134

| Arquivo | Estado | Por quê | Importado por | Citado por | Último toque | Próximo passo |
|---|---|---|---|---|---|---|
| `.ai_bridge/HANDOFF.md` | AGENT_INSTRUCTION | instrucao do agente |  | 13 | 2026-10-22 | manter (tests/test_claude_assets.py) |
| `.ai_bridge/knowledge/architect.md` | AGENT_INSTRUCTION | instrucao do agente |  | 2 | 2026-06-24 | manter (tests/test_claude_assets.py) |
| `.ai_bridge/learning_patches/LP-SOFA-001.json` | AGENT_INSTRUCTION | instrucao do agente |  | 3 | 2026-06-22 | manter (tests/test_claude_assets.py) |
| `.ai_bridge/lessons/interior-orchestrator.md` | AGENT_INSTRUCTION | instrucao do agente |  | 3 | 2026-06-24 | manter (tests/test_claude_assets.py) |
| `.ai_bridge/reference_packs/sofa_reference_pack_001.json` | AGENT_INSTRUCTION | instrucao do agente |  | 5 | 2026-06-21 | manter (tests/test_claude_assets.py) |
| `.ai_bridge/research/furniture_classes_ergonomics_2026-06-12.json` | AGENT_INSTRUCTION | instrucao do agente |  | 3 | 2026-06-12 | manter (tests/test_claude_assets.py) |
| `.dockerignore` | CONFIG | configuracao/outro |  | 8 | 2026-06-20 | manter |
| `.gitattributes` | CONFIG | configuracao/outro |  | 7 | 2026-09-09 | manter |
| `.github/workflows/ci.yml` | CONFIG | configuracao/outro |  | 10 | 2026-10-21 | manter |
| `.gitignore` | CONFIG | configuracao/outro |  | 20 | 2026-10-22 | manter |
| `.impeccable/config.json` | CONFIG | configuracao/outro |  | 3 | 2026-08-26 | manter |
| `CLAUDE.md` | DOC | documentacao |  | 31 | 2026-05-27 | manter |
| `README.md` | DOC | documentacao |  | 37 | 2026-10-22 | manter |
| `docker-compose.rag.yml` | CONFIG | configuracao/outro |  | 8 | 2026-07-07 | manter |
| `docker-compose.yml` | CONFIG | configuracao/outro |  | 10 | 2026-06-20 | manter |
| `ops/estudio-front/assets/banho01.png` | CONFIG | configuracao/outro |  | 2 | 2026-08-09 | manter |
| `ops/estudio-front/assets/banho02.png` | CONFIG | configuracao/outro |  | 2 | 2026-08-09 | manter |
| `ops/estudio-front/assets/box_ideiaglass_nobre.jpg` | CONFIG | configuracao/outro |  | 2 | 2026-08-09 | manter |
| `ops/estudio-front/assets/chuveiro_deca_flexmax_22.jpg` | CONFIG | configuracao/outro |  | 2 | 2026-08-09 | manter |
| `ops/estudio-front/assets/cuba_deca_slim_L33050.jpg` | CONFIG | configuracao/outro |  | 2 | 2026-08-09 | manter |
| `ops/estudio-front/assets/gabinete_roca_tura.jpg` | CONFIG | configuracao/outro |  | 2 | 2026-08-09 | manter |
| `ops/estudio-front/assets/hero.png` | CONFIG | configuracao/outro |  | 2 | 2026-08-09 | manter |
| `ops/estudio-front/assets/lavabo.png` | CONFIG | configuracao/outro |  | 2 | 2026-08-09 | manter |
| `ops/estudio-front/assets/p21.png` | CONFIG | configuracao/outro |  | 2 | 2026-08-09 | manter |
| `ops/estudio-front/assets/p22.png` | CONFIG | configuracao/outro |  | 2 | 2026-08-09 | manter |
| `ops/estudio-front/assets/p23.png` | CONFIG | configuracao/outro |  | 2 | 2026-08-09 | manter |
| `ops/estudio-front/assets/torneira_deca_level_2880BL.jpg` | CONFIG | configuracao/outro |  | 2 | 2026-08-09 | manter |
| `ops/estudio-front/assets/vaso_roca_gap.jpg` | CONFIG | configuracao/outro |  | 2 | 2026-08-09 | manter |
| `ops/estudio-front/chat_history.json` | CONFIG | configuracao/outro |  | 3 | 2026-08-11 | manter |
| `ops/estudio-front/curadoria/curadoria_20260808_185719.json` | CONFIG | configuracao/outro |  | 2 | 2026-08-09 | manter |
| `ops/estudio-front/index.html` | CONFIG | configuracao/outro |  | 3 | 2026-08-10 | manter |
| `ops/estudio-front/knowledge_ingest.py` | CLI_DOC_ONLY | CLI manual citada so em documentacao (4 doc); nenhum teste/CI a executa | 0 | 4 | 2026-10-19 | dar teste de fumaca (vira ACTIVE) ou arquivar com decisao do Felipe |
| `ops/estudio-front/rag_chat.py` | ACTIVE_ENTRYPOINT | citado por 1 arquivo(s) de codigo/CI/config/skill | 0 | 5 | 2026-10-21 | manter |
| `ops/estudio-front/server.py` | ACTIVE_ENTRYPOINT | citado por 1 arquivo(s) de codigo/CI/config/skill | 0 | 5 | 2026-08-26 | manter |
| `ops/estudio-front/status.json` | CONFIG | configuracao/outro |  | 3 | 2026-08-09 | manter |
| `pyproject.toml` | CONFIG | configuracao/outro |  | 21 | 2026-10-22 | manter |
| `scripts/set_clipboard_image.ps1` | CONFIG | configuracao/outro |  | 9 | 2026-06-10 | manter |
| `uv.lock` | CONFIG | configuracao/outro |  | 11 | 2026-07-11 | manter |

## Evidência e histórico (por diretório)

| Diretório | Estado | Arquivos | Último toque | Regra |
|---|---|---|---|---|
| `.ai_bridge/fidelity/ledger.jsonl/` | HISTORICAL | 1 | 2026-06-08 | nao editar; nova evidencia vai num arquivo novo |
| `.ai_bridge/fidelity/verdicts/` | HISTORICAL | 19 | 2026-06-12 | nao editar; nova evidencia vai num arquivo novo |
| `.ai_bridge/gpt_review/.gitignore/` | HISTORICAL | 1 | 2026-06-22 | nao editar; nova evidencia vai num arquivo novo |
| `.ai_bridge/gpt_review/GPT_REVIEW_BUNDLE.json/` | HISTORICAL | 1 | 2026-06-22 | nao editar; nova evidencia vai num arquivo novo |
| `.ai_bridge/gpt_review/GPT_REVIEW_BUNDLE.md/` | HISTORICAL | 1 | 2026-06-22 | nao editar; nova evidencia vai num arquivo novo |
| `.ai_bridge/questions/20260529T184522Z_oracle_pass_but_known_warnings.md/` | HISTORICAL | 1 | 2026-05-29 | nao editar; nova evidencia vai num arquivo novo |
| `.ai_bridge/questions/20260529T190248Z_oracle_pass_but_known_warnings.md/` | HISTORICAL | 1 | 2026-05-29 | nao editar; nova evidencia vai num arquivo novo |
| `.ai_bridge/questions/20260529T190315Z_oracle_pass_but_known_warnings.md/` | HISTORICAL | 1 | 2026-05-29 | nao editar; nova evidencia vai num arquivo novo |
| `.ai_bridge/questions/20260529T200636Z_a_b_c_decision_with_tradeoff.md/` | HISTORICAL | 1 | 2026-05-29 | nao editar; nova evidencia vai num arquivo novo |
| `.ai_bridge/questions/20260529T201437Z_final_fail_non_obvious_fix.md/` | HISTORICAL | 1 | 2026-05-29 | nao editar; nova evidencia vai num arquivo novo |
| `.ai_bridge/questions/20260529T201947Z_about_to_open_new_cycle_post_slice.md/` | HISTORICAL | 1 | 2026-05-29 | nao editar; nova evidencia vai num arquivo novo |
| `.ai_bridge/responses/20260529T200636Z_a_b_c_decision_with_tradeoff.md/` | HISTORICAL | 1 | 2026-05-29 | nao editar; nova evidencia vai num arquivo novo |
| `.ai_bridge/responses/20260529T201437Z_final_fail_non_obvious_fix.md/` | HISTORICAL | 1 | 2026-05-29 | nao editar; nova evidencia vai num arquivo novo |
| `.ai_bridge/responses/20260529T201947Z_about_to_open_new_cycle_post_slice.md/` | HISTORICAL | 1 | 2026-05-29 | nao editar; nova evidencia vai num arquivo novo |
| `artifacts/_archive/review_legacy_20260609/` | HISTORICAL | 102 | 2026-06-09 | nao editar; nova evidencia vai num arquivo novo |
| `artifacts/correction_loop/planta_74/` | EVIDENCE_OR_DATA | 2 | 2026-07-08 | ler e copiar; nunca escrever no canonico |
| `artifacts/estudio_banheiro/AUDITORIA_P12.md/` | EVIDENCE_OR_DATA | 1 | 2026-08-07 | ler e copiar; nunca escrever no canonico |
| `artifacts/estudio_banheiro/ITERATIONS.md/` | EVIDENCE_OR_DATA | 1 | 2026-08-09 | ler e copiar; nunca escrever no canonico |
| `artifacts/estudio_banheiro/ORCAMENTO_V0.md/` | EVIDENCE_OR_DATA | 1 | 2026-08-08 | ler e copiar; nunca escrever no canonico |
| `artifacts/estudio_banheiro/REFERENCE_KIT_PRODUTOS.md/` | EVIDENCE_OR_DATA | 1 | 2026-08-08 | ler e copiar; nunca escrever no canonico |
| `artifacts/estudio_banheiro/REFERENCE_SPEC.md/` | EVIDENCE_OR_DATA | 1 | 2026-08-05 | ler e copiar; nunca escrever no canonico |
| `artifacts/estudio_banheiro/corner_audit/` | EVIDENCE_OR_DATA | 6 | 2026-08-09 | ler e copiar; nunca escrever no canonico |
| `artifacts/estudio_banheiro/iterations/` | EVIDENCE_OR_DATA | 44 | 2026-08-09 | ler e copiar; nunca escrever no canonico |
| `artifacts/kitchen_research/component_specs.md/` | EVIDENCE_OR_DATA | 1 | 2026-06-19 | ler e copiar; nunca escrever no canonico |
| `artifacts/kitchen_research/design_grammar_spec.json/` | EVIDENCE_OR_DATA | 1 | 2026-06-19 | ler e copiar; nunca escrever no canonico |
| `artifacts/kitchen_research/implementation_plan.md/` | EVIDENCE_OR_DATA | 1 | 2026-06-19 | ler e copiar; nunca escrever no canonico |
| `artifacts/kitchen_research/joinery_tokens.json/` | EVIDENCE_OR_DATA | 1 | 2026-06-19 | ler e copiar; nunca escrever no canonico |
| `artifacts/kitchen_research/reference_board_summary.md/` | EVIDENCE_OR_DATA | 1 | 2026-06-19 | ler e copiar; nunca escrever no canonico |
| `artifacts/kitchen_research/validation_report.md/` | EVIDENCE_OR_DATA | 1 | 2026-06-19 | ler e copiar; nunca escrever no canonico |
| `artifacts/kitchen_research/validation_report_critic.md/` | EVIDENCE_OR_DATA | 1 | 2026-06-19 | ler e copiar; nunca escrever no canonico |
| `artifacts/planta_74/README.md/` | EVIDENCE_OR_DATA | 1 | 2026-06-04 | ler e copiar; nunca escrever no canonico |
| `artifacts/planta_74/design_intent/` | EVIDENCE_OR_DATA | 1 | 2026-06-08 | ler e copiar; nunca escrever no canonico |
| `artifacts/planta_74/furnished/` | EVIDENCE_OR_DATA | 296 | 2026-09-19 | ler e copiar; nunca escrever no canonico |
| `artifacts/planta_74/geometry_report.json/` | EVIDENCE_OR_DATA | 1 | 2026-07-11 | ler e copiar; nunca escrever no canonico |
| `artifacts/planta_74/planta_74.skp/` | EVIDENCE_OR_DATA | 1 | 2026-07-11 | ler e copiar; nunca escrever no canonico |
| `artifacts/planta_74/planta_74.skp.metadata.json/` | EVIDENCE_OR_DATA | 1 | 2026-07-11 | ler e copiar; nunca escrever no canonico |
| `artifacts/planta_74/planta_74_floors_top.png/` | EVIDENCE_OR_DATA | 1 | 2026-06-04 | ler e copiar; nunca escrever no canonico |
| `artifacts/planta_74/planta_74_iso.png/` | EVIDENCE_OR_DATA | 1 | 2026-07-11 | ler e copiar; nunca escrever no canonico |
| `artifacts/planta_74/planta_74_top.png/` | EVIDENCE_OR_DATA | 1 | 2026-07-11 | ler e copiar; nunca escrever no canonico |
| `artifacts/planta_74/planta_74_top.png.proj.json/` | EVIDENCE_OR_DATA | 1 | 2026-07-11 | ler e copiar; nunca escrever no canonico |
| `artifacts/planta_74/regression_summary.md/` | EVIDENCE_OR_DATA | 1 | 2026-06-09 | ler e copiar; nunca escrever no canonico |
| `artifacts/planta_74/side_by_side_pdf_vs_skp.png/` | EVIDENCE_OR_DATA | 1 | 2026-06-09 | ler e copiar; nunca escrever no canonico |
| `artifacts/reference_lab/DECISIONS.md/` | EVIDENCE_OR_DATA | 1 | 2026-06-20 | ler e copiar; nunca escrever no canonico |
| `artifacts/reference_lab/FELIPE_KITCHEN_PREFERENCES.md/` | EVIDENCE_OR_DATA | 1 | 2026-06-19 | ler e copiar; nunca escrever no canonico |
| `artifacts/reference_lab/GOLDEN_SAMPLES.md/` | EVIDENCE_OR_DATA | 1 | 2026-06-20 | ler e copiar; nunca escrever no canonico |
| `artifacts/reference_lab/HOW_TO_USE.md/` | EVIDENCE_OR_DATA | 1 | 2026-06-19 | ler e copiar; nunca escrever no canonico |
| `artifacts/reference_lab/INTERIOR_QUALITY_SYSTEM.md/` | EVIDENCE_OR_DATA | 1 | 2026-06-20 | ler e copiar; nunca escrever no canonico |
| `artifacts/reference_lab/README.md/` | EVIDENCE_OR_DATA | 1 | 2026-06-19 | ler e copiar; nunca escrever no canonico |
| `artifacts/reference_lab/REFERENCE_DB_DESIGN.md/` | EVIDENCE_OR_DATA | 1 | 2026-06-20 | ler e copiar; nunca escrever no canonico |
| `artifacts/reference_lab/analyzed/` | EVIDENCE_OR_DATA | 3 | 2026-06-19 | ler e copiar; nunca escrever no canonico |
| `artifacts/reference_lab/gates/` | EVIDENCE_OR_DATA | 1 | 2026-06-19 | ler e copiar; nunca escrever no canonico |
| `artifacts/reference_lab/inbox/` | EVIDENCE_OR_DATA | 9 | 2026-08-08 | ler e copiar; nunca escrever no canonico |
| `artifacts/reference_lab/kitchen/` | EVIDENCE_OR_DATA | 34 | 2026-06-20 | ler e copiar; nunca escrever no canonico |
| `artifacts/reference_lab/kitchen_dark_walnut/` | EVIDENCE_OR_DATA | 10 | 2026-06-19 | ler e copiar; nunca escrever no canonico |
| `artifacts/reference_lab/kitchen_hotel_boutique/` | EVIDENCE_OR_DATA | 1 | 2026-06-19 | ler e copiar; nunca escrever no canonico |
| `artifacts/reference_lab/living_room/` | EVIDENCE_OR_DATA | 1 | 2026-06-20 | ler e copiar; nunca escrever no canonico |
| `artifacts/reference_lab/renders/` | EVIDENCE_OR_DATA | 2 | 2026-06-19 | ler e copiar; nunca escrever no canonico |
| `artifacts/reference_lab/sofa/` | EVIDENCE_OR_DATA | 2 | 2026-06-22 | ler e copiar; nunca escrever no canonico |
| `artifacts/reference_lab/targets/` | EVIDENCE_OR_DATA | 1 | 2026-10-22 | ler e copiar; nunca escrever no canonico |
| `artifacts/reference_lab/templates/` | EVIDENCE_OR_DATA | 1 | 2026-06-19 | ler e copiar; nunca escrever no canonico |
| `artifacts/reference_lab/themes/` | EVIDENCE_OR_DATA | 4 | 2026-06-20 | ler e copiar; nunca escrever no canonico |
| `artifacts/review/fp043/` | EVIDENCE_OR_DATA | 72 | 2026-10-19 | ler e copiar; nunca escrever no canonico |
| `artifacts/review/fp044/` | EVIDENCE_OR_DATA | 4 | 2026-10-20 | ler e copiar; nunca escrever no canonico |
| `artifacts/review/fp046/` | EVIDENCE_OR_DATA | 67 | 2026-10-21 | ler e copiar; nunca escrever no canonico |
| `artifacts/review/furniture/` | EVIDENCE_OR_DATA | 59 | 2026-10-19 | ler e copiar; nunca escrever no canonico |
| `artifacts/review/interior/` | EVIDENCE_OR_DATA | 14 | 2026-06-17 | ler e copiar; nunca escrever no canonico |
| `artifacts/review/l2_fp042_20261019/` | EVIDENCE_OR_DATA | 95 | 2026-10-19 | ler e copiar; nunca escrever no canonico |
| `artifacts/review/planta_74/` | EVIDENCE_OR_DATA | 81 | 2026-10-19 | ler e copiar; nunca escrever no canonico |
| `artifacts/review/scenes/` | EVIDENCE_OR_DATA | 12 | 2026-06-22 | ler e copiar; nunca escrever no canonico |
| `artifacts/review/sofa_premium/` | EVIDENCE_OR_DATA | 29 | 2026-07-12 | ler e copiar; nunca escrever no canonico |
| `artifacts/review/sofa_program/` | EVIDENCE_OR_DATA | 56 | 2026-10-19 | ler e copiar; nunca escrever no canonico |
| `artifacts/review/vray_pipeline_proof_2026-06/` | EVIDENCE_OR_DATA | 2 | 2026-10-19 | ler e copiar; nunca escrever no canonico |
| `artifacts/variant_sweep/planta_74/` | EVIDENCE_OR_DATA | 10 | 2026-07-08 | ler e copiar; nunca escrever no canonico |
| `assets/catalog/furniture_catalog.json/` | EVIDENCE_OR_DATA | 1 | 2026-06-05 | ler e copiar; nunca escrever no canonico |
| `assets/furniture/sofa/` | EVIDENCE_OR_DATA | 2 | 2026-06-05 | ler e copiar; nunca escrever no canonico |
| `assets/textures/pbr/` | EVIDENCE_OR_DATA | 6 | 2026-06-18 | ler e copiar; nunca escrever no canonico |
| `assets/textures/procedural/` | EVIDENCE_OR_DATA | 36 | 2026-08-07 | ler e copiar; nunca escrever no canonico |
| `assets/textures/sofa_fabric/` | EVIDENCE_OR_DATA | 6 | 2026-10-19 | ler e copiar; nunca escrever no canonico |
| `fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json/` | EVIDENCE_OR_DATA | 1 | 2026-07-11 | ler e copiar; nunca escrever no canonico |
| `fixtures/planta_74/human_openings_annotation.png/` | EVIDENCE_OR_DATA | 1 | 2026-06-05 | ler e copiar; nunca escrever no canonico |
| `fixtures/planta_74/human_soft_barriers_annotation.png/` | EVIDENCE_OR_DATA | 1 | 2026-06-05 | ler e copiar; nunca escrever no canonico |
| `fixtures/planta_74/human_walls_annotation.png/` | EVIDENCE_OR_DATA | 1 | 2026-06-05 | ler e copiar; nunca escrever no canonico |
| `fixtures/planta_74/known_warnings.json/` | EVIDENCE_OR_DATA | 1 | 2026-05-29 | ler e copiar; nunca escrever no canonico |
| `fixtures/planta_74/semantic_zones.json/` | EVIDENCE_OR_DATA | 1 | 2026-07-06 | ler e copiar; nunca escrever no canonico |
| `fixtures/quadrado/consensus_with_window.json/` | EVIDENCE_OR_DATA | 1 | 2026-05-24 | ler e copiar; nunca escrever no canonico |
| `fixtures/scene_intents/living_room_black_wood_gold_boutique.json/` | EVIDENCE_OR_DATA | 1 | 2026-07-11 | ler e copiar; nunca escrever no canonico |
| `fixtures/scene_intents/living_room_modern_warm_minimal.json/` | EVIDENCE_OR_DATA | 1 | 2026-06-11 | ler e copiar; nunca escrever no canonico |
| `fixtures/synthetic_cabinets/fp046_shaker_valid_a.json/` | EVIDENCE_OR_DATA | 1 | 2026-10-21 | ler e copiar; nunca escrever no canonico |
| `fixtures/synthetic_cabinets/holdout_c.json/` | EVIDENCE_OR_DATA | 1 | 2026-10-19 | ler e copiar; nunca escrever no canonico |
| `fixtures/synthetic_cabinets/invalid_impossible.json/` | EVIDENCE_OR_DATA | 1 | 2026-10-19 | ler e copiar; nunca escrever no canonico |
| `fixtures/synthetic_cabinets/invalid_incomplete.json/` | EVIDENCE_OR_DATA | 1 | 2026-10-19 | ler e copiar; nunca escrever no canonico |
| `fixtures/synthetic_cabinets/valid_a_base_600.json/` | EVIDENCE_OR_DATA | 1 | 2026-10-19 | ler e copiar; nunca escrever no canonico |
| `fixtures/synthetic_cabinets/valid_b_tall_900.json/` | EVIDENCE_OR_DATA | 1 | 2026-10-19 | ler e copiar; nunca escrever no canonico |
| `fixtures/synthetic_rooms/bedroom_large_18m2.json/` | EVIDENCE_OR_DATA | 1 | 2026-06-05 | ler e copiar; nunca escrever no canonico |
| `fixtures/synthetic_rooms/bedroom_medium_14m2.json/` | EVIDENCE_OR_DATA | 1 | 2026-06-05 | ler e copiar; nunca escrever no canonico |
| `fixtures/synthetic_rooms/bedroom_medium_14m2_inner_face.json/` | EVIDENCE_OR_DATA | 1 | 2026-10-19 | ler e copiar; nunca escrever no canonico |
| `fixtures/synthetic_rooms/bedroom_small_9m2.json/` | EVIDENCE_OR_DATA | 1 | 2026-06-05 | ler e copiar; nunca escrever no canonico |
| `fixtures/synthetic_rooms/living_large_rect_28m2.json/` | EVIDENCE_OR_DATA | 1 | 2026-06-04 | ler e copiar; nunca escrever no canonico |
| `fixtures/synthetic_rooms/living_long_narrow.json/` | EVIDENCE_OR_DATA | 1 | 2026-06-04 | ler e copiar; nunca escrever no canonico |
| `fixtures/synthetic_rooms/living_medium_rect_18m2.json/` | EVIDENCE_OR_DATA | 1 | 2026-06-04 | ler e copiar; nunca escrever no canonico |
| `fixtures/synthetic_rooms/living_small_rect_10m2.json/` | EVIDENCE_OR_DATA | 1 | 2026-06-04 | ler e copiar; nunca escrever no canonico |
| `fixtures/visual_oracle_examples/README.md/` | EVIDENCE_OR_DATA | 1 | 2026-05-28 | ler e copiar; nunca escrever no canonico |
| `fixtures/visual_oracle_examples/bad_real/` | EVIDENCE_OR_DATA | 14 | 2026-05-28 | ler e copiar; nunca escrever no canonico |
| `fixtures/visual_oracle_examples/bad_synthetic/` | EVIDENCE_OR_DATA | 16 | 2026-05-28 | ler e copiar; nunca escrever no canonico |
| `fixtures/visual_oracle_examples/good_real/` | EVIDENCE_OR_DATA | 6 | 2026-05-28 | ler e copiar; nunca escrever no canonico |
| `fixtures/visual_oracle_examples/good_synthetic/` | EVIDENCE_OR_DATA | 2 | 2026-05-28 | ler e copiar; nunca escrever no canonico |
| `fixtures/visual_oracle_examples/manifest.json/` | EVIDENCE_OR_DATA | 1 | 2026-05-28 | ler e copiar; nunca escrever no canonico |
| `fixtures/visual_oracle_negative/README.md/` | EVIDENCE_OR_DATA | 1 | 2026-05-29 | ler e copiar; nunca escrever no canonico |
| `fixtures/visual_oracle_negative/floating_door/` | EVIDENCE_OR_DATA | 2 | 2026-05-29 | ler e copiar; nunca escrever no canonico |
| `fixtures/visual_oracle_negative/full_height_window/` | EVIDENCE_OR_DATA | 2 | 2026-05-29 | ler e copiar; nunca escrever no canonico |
| `fixtures/visual_oracle_negative/orphan_glass/` | EVIDENCE_OR_DATA | 2 | 2026-05-29 | ler e copiar; nunca escrever no canonico |
| `projects/planta_74/README.md/` | EVIDENCE_OR_DATA | 1 | 2026-10-19 | ler e copiar; nunca escrever no canonico |
| `projects/planta_74/source/` | EVIDENCE_OR_DATA | 1 | 2026-10-19 | ler e copiar; nunca escrever no canonico |
| `references/README.md/` | EVIDENCE_OR_DATA | 1 | 2026-06-19 | ler e copiar; nunca escrever no canonico |
| `references/design_rules/design_rule.schema.json/` | EVIDENCE_OR_DATA | 1 | 2026-06-05 | ler e copiar; nunca escrever no canonico |
| `references/design_rules/felipe_visual_judge_rules.json/` | EVIDENCE_OR_DATA | 1 | 2026-06-22 | ler e copiar; nunca escrever no canonico |
| `references/design_rules/furniture_rule_cards.json/` | EVIDENCE_OR_DATA | 1 | 2026-06-05 | ler e copiar; nunca escrever no canonico |
| `references/eval/retrieval_baseline.json/` | EVIDENCE_OR_DATA | 1 | 2026-07-15 | ler e copiar; nunca escrever no canonico |
| `references/eval/retrieval_golden.jsonl/` | EVIDENCE_OR_DATA | 1 | 2026-07-15 | ler e copiar; nunca escrever no canonico |
| `references/felipe/VERDICT_APE_V1_2026_08_03.md/` | EVIDENCE_OR_DATA | 1 | 2026-08-05 | ler e copiar; nunca escrever no canonico |
| `references/felipe/anti_patterns/` | EVIDENCE_OR_DATA | 1 | 2026-06-21 | ler e copiar; nunca escrever no canonico |
| `references/felipe/approved/` | EVIDENCE_OR_DATA | 3 | 2026-06-24 | ler e copiar; nunca escrever no canonico |
| `references/felipe/verdicts/` | EVIDENCE_OR_DATA | 9 | 2026-08-28 | ler e copiar; nunca escrever no canonico |
| `references/joinery_rules/anti_patterns.md/` | EVIDENCE_OR_DATA | 1 | 2026-06-19 | ler e copiar; nunca escrever no canonico |
| `references/joinery_rules/appliance_niches.md/` | EVIDENCE_OR_DATA | 1 | 2026-06-19 | ler e copiar; nunca escrever no canonico |
| `references/joinery_rules/kitchen_ergonomics.md/` | EVIDENCE_OR_DATA | 1 | 2026-06-19 | ler e copiar; nunca escrever no canonico |
| `references/joinery_rules/premium_details.md/` | EVIDENCE_OR_DATA | 1 | 2026-06-19 | ler e copiar; nunca escrever no canonico |
| `references/materials/lacquer.md/` | EVIDENCE_OR_DATA | 1 | 2026-06-19 | ler e copiar; nunca escrever no canonico |
| `references/materials/metal.md/` | EVIDENCE_OR_DATA | 1 | 2026-06-19 | ler e copiar; nunca escrever no canonico |
| `references/materials/stone.md/` | EVIDENCE_OR_DATA | 1 | 2026-06-19 | ler e copiar; nunca escrever no canonico |
| `references/materials/wood.md/` | EVIDENCE_OR_DATA | 1 | 2026-06-19 | ler e copiar; nunca escrever no canonico |
| `references/palettes/black_wood_gold_industrial_boutique.json/` | EVIDENCE_OR_DATA | 1 | 2026-06-20 | ler e copiar; nunca escrever no canonico |
| `references/palettes/fendi_oak_stone.json/` | EVIDENCE_OR_DATA | 1 | 2026-06-19 | ler e copiar; nunca escrever no canonico |
| `references/palettes/modern_warm.json/` | EVIDENCE_OR_DATA | 1 | 2026-06-19 | ler e copiar; nunca escrever no canonico |
| `references/sketchup/knowledge/` | EVIDENCE_OR_DATA | 2 | 2026-10-21 | ler e copiar; nunca escrever no canonico |
| `references/sofas/audit/` | EVIDENCE_OR_DATA | 9 | 2026-06-10 | ler e copiar; nunca escrever no canonico |
| `references/sofas/gpt_review_log.jsonl/` | EVIDENCE_OR_DATA | 1 | 2026-06-10 | ler e copiar; nunca escrever no canonico |
| `references/sofas/history/` | EVIDENCE_OR_DATA | 1 | 2026-10-19 | ler e copiar; nunca escrever no canonico |
| `references/sofas/raw/` | EVIDENCE_OR_DATA | 2 | 2026-06-10 | ler e copiar; nunca escrever no canonico |
| `references/tokens/coordinated_medium_dark_wood_base.json/` | EVIDENCE_OR_DATA | 1 | 2026-06-19 | ler e copiar; nunca escrever no canonico |
| `references/tokens/coordinated_oak_base.json/` | EVIDENCE_OR_DATA | 1 | 2026-06-19 | ler e copiar; nunca escrever no canonico |
| `references/tokens/dark_stainless_appliance.json/` | EVIDENCE_OR_DATA | 1 | 2026-06-20 | ler e copiar; nunca escrever no canonico |
| `references/tokens/discreet_bronze_hardware.json/` | EVIDENCE_OR_DATA | 1 | 2026-06-20 | ler e copiar; nunca escrever no canonico |
| `references/tokens/hot_tower_niche.json/` | EVIDENCE_OR_DATA | 1 | 2026-06-19 | ler e copiar; nunca escrever no canonico |
| `references/tokens/matte_black_cabinetry.json/` | EVIDENCE_OR_DATA | 1 | 2026-06-20 | ler e copiar; nunca escrever no canonico |
| `references/tokens/planned_fridge_tower.json/` | EVIDENCE_OR_DATA | 1 | 2026-06-19 | ler e copiar; nunca escrever no canonico |
| `references/tokens/premium_shadow_gap.json/` | EVIDENCE_OR_DATA | 1 | 2026-06-19 | ler e copiar; nunca escrever no canonico |
| `references/tokens/reflecta_champagne_led_cabinet.json/` | EVIDENCE_OR_DATA | 1 | 2026-06-19 | ler e copiar; nunca escrever no canonico |
| `references/tokens/subtle_veined_stone.json/` | EVIDENCE_OR_DATA | 1 | 2026-06-19 | ler e copiar; nunca escrever no canonico |
| `references/tokens/under_cabinet_led.json/` | EVIDENCE_OR_DATA | 1 | 2026-06-19 | ler e copiar; nunca escrever no canonico |
| `references/tokens/warm_fendi_upper.json/` | EVIDENCE_OR_DATA | 1 | 2026-06-19 | ler e copiar; nunca escrever no canonico |
