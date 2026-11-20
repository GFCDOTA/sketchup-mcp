# Índice das SPECs do sketchup-mcp

As SPECs saíram deste repositório e moram em **`Plan2Space/engineering-specs`** (privado), pasta `sketchup-mcp/`,
conforme o contrato de ownership v2 do `claude-engineering-skills`. Editar SPEC = PR lá, nunca aqui.

SHA: `40b76f9ce10ab7e9a51e2a1e03495a9cd1ba2b72`

Link de uma SPEC: `https://github.com/Plan2Space/engineering-specs/blob/<SHA>/<caminho em engineering-specs>`.
Em código: `tools.validation.spec_index.url("docs/specs/FP-030_visual_oracle_gate.md")`.

Copiadas byte a byte do `develop` `7ea99daeafda2d0a553d3fc4781a581a73d45d47`. As duas SPECs da FP-062 nunca chegaram ao `develop`: vieram byte a byte dos branches
preservados dos PRs #677 (`e25253b0`) e #674 (`18736dd2`), fechados sem merge. Ficaram aqui porque o código lê esses
arquivos e eles não são SPEC: `docs/specs/*.json`, `docs/specs/_assets/`, `docs/specs/FP-SOFA-PREMIUM/*.json`,
`interior/class_specs/__init__.py`.

Os checadores de caminho (`tools.validation.spec_index.resolves`) aceitam um caminho antigo **só se ele estiver nesta
tabela**. Por isso relatório e handoff históricos continuam válidos sem reescrita, e caminho inventado continua falhando.

| Caminho antigo | Caminho em engineering-specs |
|---|---|
| `.claude/specs/autonomous_planta_prep.md` | `sketchup-mcp/claude-specs/autonomous_planta_prep.md` |
| `.claude/specs/fidelity_gate.md` | `sketchup-mcp/claude-specs/fidelity_gate.md` |
| `.claude/specs/gate_framework_and_audit.md` | `sketchup-mcp/claude-specs/gate_framework_and_audit.md` |
| `.claude/specs/generalize_any_plant.md` | `sketchup-mcp/claude-specs/generalize_any_plant.md` |
| `.claude/specs/generalize_builder_constants.md` | `sketchup-mcp/claude-specs/generalize_builder_constants.md` |
| `.claude/specs/interior_common_sense.md` | `sketchup-mcp/claude-specs/interior_common_sense.md` |
| `.claude/specs/perfect_reference_strategy.md` | `sketchup-mcp/claude-specs/perfect_reference_strategy.md` |
| `.claude/specs/product_goal.md` | `sketchup-mcp/claude-specs/product_goal.md` |
| `.claude/specs/repository_hygiene.md` | `sketchup-mcp/claude-specs/repository_hygiene.md` |
| `.claude/specs/room_furnishing_method.md` | `sketchup-mcp/claude-specs/room_furnishing_method.md` |
| `.claude/specs/sdd_and_harness_engineering.md` | `sketchup-mcp/claude-specs/sdd_and_harness_engineering.md` |
| `.claude/specs/skp_artifact_layout.md` | `sketchup-mcp/claude-specs/skp_artifact_layout.md` |
| `.claude/specs/skp_proof_of_progress_gate.md` | `sketchup-mcp/claude-specs/skp_proof_of_progress_gate.md` |
| `.claude/specs/templates/artifact_contract_template.md` | `templates/artifact_contract_template.md` |
| `.claude/specs/templates/feature_spec_template.md` | `templates/feature_spec_template.md` |
| `.claude/specs/templates/fidelity_spec_template.md` | `templates/fidelity_spec_template.md` |
| `.claude/specs/templates/regression_summary_template.md` | `templates/regression_summary_template.md` |
| `docs/specs/AI_PIPELINE_INSPECTOR.md` | `sketchup-mcp/docs-specs/AI_PIPELINE_INSPECTOR.md` |
| `docs/specs/FP-026_residual_wall_stub_elimination.md` | `sketchup-mcp/docs-specs/FP-026_residual_wall_stub_elimination.md` |
| `docs/specs/FP-030_visual_oracle_gate.md` | `sketchup-mcp/docs-specs/FP-030_visual_oracle_gate.md` |
| `docs/specs/FP-031_furniture_class_to_furnish_loop.md` | `sketchup-mcp/docs-specs/FP-031_furniture_class_to_furnish_loop.md` |
| `docs/specs/FP-032_vision_acl.md` | `sketchup-mcp/docs-specs/FP-032_vision_acl.md` |
| `docs/specs/FP-033_closed_correction_loop.md` | `sketchup-mcp/docs-specs/FP-033_closed_correction_loop.md` |
| `docs/specs/FP-034_judged_variant_sweep.md` | `sketchup-mcp/docs-specs/FP-034_judged_variant_sweep.md` |
| `docs/specs/FP-035_rag_design_retrieval.md` | `sketchup-mcp/docs-specs/FP-035_rag_design_retrieval.md` |
| `docs/specs/FP-036_material_de_verdade.md` | `sketchup-mcp/docs-specs/FP-036_material_de_verdade.md` |
| `docs/specs/FP-037_module_aware_material_attribution.md` | `sketchup-mcp/docs-specs/FP-037_module_aware_material_attribution.md` |
| `docs/specs/FP-038_room_detail_visual_review_camera.md` | `sketchup-mcp/docs-specs/FP-038_room_detail_visual_review_camera.md` |
| `docs/specs/FP-039_honest_visual_fingerprint_v2.md` | `sketchup-mcp/docs-specs/FP-039_honest_visual_fingerprint_v2.md` |
| `docs/specs/FP-040_bridge_hardening.md` | `sketchup-mcp/docs-specs/FP-040_bridge_hardening.md` |
| `docs/specs/FP-041_room_knowledge_expansion.md` | `sketchup-mcp/docs-specs/FP-041_room_knowledge_expansion.md` |
| `docs/specs/FP-041_runtime_room_modularization.md` | `sketchup-mcp/docs-specs/FP-041_runtime_room_modularization.md` |
| `docs/specs/FP-041_video_knowledge_consultation.md` | `sketchup-mcp/docs-specs/FP-041_video_knowledge_consultation.md` |
| `docs/specs/FP-042_P1_owner_dependency_audit.md` | `sketchup-mcp/docs-specs/FP-042_P1_owner_dependency_audit.md` |
| `docs/specs/FP-042_all_reference_provenance.md` | `sketchup-mcp/docs-specs/FP-042_all_reference_provenance.md` |
| `docs/specs/FP-042_asset_provenance.md` | `sketchup-mcp/docs-specs/FP-042_asset_provenance.md` |
| `docs/specs/FP-042_automated_closure.md` | `sketchup-mcp/docs-specs/FP-042_automated_closure.md` |
| `docs/specs/FP-042_exhaustive_modularization.md` | `sketchup-mcp/docs-specs/FP-042_exhaustive_modularization.md` |
| `docs/specs/FP-042_final_validation.md` | `sketchup-mcp/docs-specs/FP-042_final_validation.md` |
| `docs/specs/FP-043_P0_map.md` | `sketchup-mcp/docs-specs/FP-043_P0_map.md` |
| `docs/specs/FP-043_open_decisions.md` | `sketchup-mcp/docs-specs/FP-043_open_decisions.md` |
| `docs/specs/FP-043_remaining_execution_P3_P8.md` | `sketchup-mcp/docs-specs/FP-043_remaining_execution_P3_P8.md` |
| `docs/specs/FP-043_repository_navigation_and_room_specialists.md` | `sketchup-mcp/docs-specs/FP-043_repository_navigation_and_room_specialists.md` |
| `docs/specs/FP-044_root_and_tools_consolidation.md` | `sketchup-mcp/docs-specs/FP-044_root_and_tools_consolidation.md` |
| `docs/specs/FP-045_specialists_knowledge_and_room_modularization.md` | `sketchup-mcp/docs-specs/FP-045_specialists_knowledge_and_room_modularization.md` |
| `docs/specs/FP-046_shaker_parametric_cabinet_specialist.md` | `sketchup-mcp/docs-specs/FP-046_shaker_parametric_cabinet_specialist.md` |
| `docs/specs/FP-047_room_geometry_visual_regression_contract.md` | `sketchup-mcp/docs-specs/FP-047_room_geometry_visual_regression_contract.md` |
| `docs/specs/FP-048_shared_geometry_capabilities_and_coordinate_contract.md` | `sketchup-mcp/docs-specs/FP-048_shared_geometry_capabilities_and_coordinate_contract.md` |
| `docs/specs/FP-049_composable_wardrobe_end_to_end_assembly.md` | `sketchup-mcp/docs-specs/FP-049_composable_wardrobe_end_to_end_assembly.md` |
| `docs/specs/FP-050_kitchen_wall_placement_pilot.md` | `sketchup-mcp/docs-specs/FP-050_kitchen_wall_placement_pilot.md` |
| `docs/specs/FP-051_incremental_learning_furniture_composition.md` | `sketchup-mcp/docs-specs/FP-051_incremental_learning_furniture_composition.md` |
| `docs/specs/FP-052_reference_truth_and_component_learning.md` | `sketchup-mcp/docs-specs/FP-052_reference_truth_and_component_learning.md` |
| `docs/specs/FP-053_demo_first_golden_components_and_reuse.md` | `sketchup-mcp/docs-specs/FP-053_demo_first_golden_components_and_reuse.md` |
| `docs/specs/FP-054-F0_baseline_inventory.md` | `sketchup-mcp/docs-specs/FP-054-F0_baseline_inventory.md` |
| `docs/specs/FP-054-F1B_functional_clearance.md` | `sketchup-mcp/docs-specs/FP-054-F1B_functional_clearance.md` |
| `docs/specs/FP-054-F1C_semantic_interfaces.md` | `sketchup-mcp/docs-specs/FP-054-F1C_semantic_interfaces.md` |
| `docs/specs/FP-054-F1_geometry_correctness.md` | `sketchup-mcp/docs-specs/FP-054-F1_geometry_correctness.md` |
| `docs/specs/FP-054-F2_layout_solver.md` | `sketchup-mcp/docs-specs/FP-054-F2_layout_solver.md` |
| `docs/specs/FP-054-F2_spatial_solver.md` | `sketchup-mcp/docs-specs/FP-054-F2_spatial_solver.md` |
| `docs/specs/FP-054-F3_modularization_dsa.md` | `sketchup-mcp/docs-specs/FP-054-F3_modularization_dsa.md` |
| `docs/specs/FP-054-F4_real_sketchup.md` | `sketchup-mcp/docs-specs/FP-054-F4_real_sketchup.md` |
| `docs/specs/FP-054-F5_rollout_governance.md` | `sketchup-mcp/docs-specs/FP-054-F5_rollout_governance.md` |
| `docs/specs/FP-054_kickoff.md` | `sketchup-mcp/docs-specs/FP-054_kickoff.md` |
| `docs/specs/FP-054_spatial_core_reliability_program.md` | `sketchup-mcp/docs-specs/FP-054_spatial_core_reliability_program.md` |
| `docs/specs/FP-055_intelligent_pipeline_recovery.md` | `sketchup-mcp/docs-specs/FP-055_intelligent_pipeline_recovery.md` |
| `docs/specs/FP-056_usable_space_support_barriers.md` | `sketchup-mcp/docs-specs/FP-056_usable_space_support_barriers.md` |
| `docs/specs/FP-057_P8_executor_rollout.md` | `sketchup-mcp/docs-specs/FP-057_P8_executor_rollout.md` |
| `docs/specs/FP-057_autonomous_engineering_orchestration.md` | `sketchup-mcp/docs-specs/FP-057_autonomous_engineering_orchestration.md` |
| `docs/specs/FP-058_agent_control_bar.md` | `sketchup-mcp/docs-specs/FP-058_agent_control_bar.md` |
| `docs/specs/FP-059_autonomous_development_loop.md` | `sketchup-mcp/docs-specs/FP-059_autonomous_development_loop.md` |
| `docs/specs/FP-060_event_driven_agent_orchestration.md` | `sketchup-mcp/docs-specs/FP-060_event_driven_agent_orchestration.md` |
| `docs/specs/FP-SOFA-PREMIUM/CLAUDE_EXECUTION_PROMPT.md` | `sketchup-mcp/docs-specs/FP-SOFA-PREMIUM/CLAUDE_EXECUTION_PROMPT.md` |
| `docs/specs/FP-SOFA-PREMIUM/FP-SOFA-PREMIUM-SPEC.md` | `sketchup-mcp/docs-specs/FP-SOFA-PREMIUM/FP-SOFA-PREMIUM-SPEC.md` |
| `docs/specs/FP-SOFA-PREMIUM/GPT_CHANGE_GATE.md` | `sketchup-mcp/docs-specs/FP-SOFA-PREMIUM/GPT_CHANGE_GATE.md` |
| `docs/specs/LL-024_gpt_auto_consult_gate.md` | `sketchup-mcp/docs-specs/LL-024_gpt_auto_consult_gate.md` |
| `docs/specs/brain_muscle.md` | `sketchup-mcp/docs-specs/brain_muscle.md` |
| `docs/specs/construction_core_microphases.md` | `sketchup-mcp/docs-specs/construction_core_microphases.md` |
| `docs/specs/geometry_sanity_gate.md` | `sketchup-mcp/docs-specs/geometry_sanity_gate.md` |
| `docs/specs/quadrado_demo_spec.md` | `sketchup-mcp/docs-specs/quadrado_demo_spec.md` |
| `interior/class_specs/ARMCHAIR_CLASS_SPEC.md` | `sketchup-mcp/class-specs/ARMCHAIR_CLASS_SPEC.md` |
| `interior/class_specs/BED_CLASS_SPEC.md` | `sketchup-mcp/class-specs/BED_CLASS_SPEC.md` |
| `interior/class_specs/SOFA_CLASS_SPEC.md` | `sketchup-mcp/class-specs/SOFA_CLASS_SPEC.md` |
| `docs/specs/FP-062_MIGRATION_EXECUTION_PLAN.md` | `sketchup-mcp/docs-specs/FP-062_MIGRATION_EXECUTION_PLAN.md` |
| `docs/specs/FP-062_plan2space_architecture_reset.md` | `sketchup-mcp/docs-specs/FP-062_plan2space_architecture_reset.md` |
