# Repo Health Report

> **Status:** Generated (do not edit). Produced by `tools/repo_health_gate.py`.
> **Generated:** 2026-05-24T15:07:48+00:00
> **Branch:** chore/repo-governance-anti-forgetting
> **Commit:** e1515b4
> **Base (--base):** (none)

## Summary

| Severity | Count |
|---|---|
| error   | 0  |
| warning | 61 |
| info    | 0 |

## Warnings

| Code | Category | File | Message | Auto-fix? |
|---|---|---|---|---|
| W001 | loose-script-root | `analyze_overpoly.py` | script analyze_overpoly.py lives at repo root. Move under tools/ (active) or tools/legacy/ (historical) when next touched. Don't auto-move — verify references first. | no |
| W001 | loose-script-root | `crop_legend.py` | script crop_legend.py lives at repo root. Move under tools/ (active) or tools/legacy/ (historical) when next touched. Don't auto-move — verify references first. | no |
| W001 | loose-script-root | `make_test_pdf.py` | script make_test_pdf.py lives at repo root. Move under tools/ (active) or tools/legacy/ (historical) when next touched. Don't auto-move — verify references first. | no |
| W001 | loose-script-root | `peek_pdf.py` | script peek_pdf.py lives at repo root. Move under tools/ (active) or tools/legacy/ (historical) when next touched. Don't auto-move — verify references first. | no |
| W001 | loose-script-root | `preprocess_walls.py` | script preprocess_walls.py lives at repo root. Move under tools/ (active) or tools/legacy/ (historical) when next touched. Don't auto-move — verify references first. | no |
| W001 | loose-script-root | `proto_colored.py` | script proto_colored.py lives at repo root. Move under tools/ (active) or tools/legacy/ (historical) when next touched. Don't auto-move — verify references first. | no |
| W001 | loose-script-root | `proto_red.py` | script proto_red.py lives at repo root. Move under tools/ (active) or tools/legacy/ (historical) when next touched. Don't auto-move — verify references first. | no |
| W001 | loose-script-root | `proto_runner.py` | script proto_runner.py lives at repo root. Move under tools/ (active) or tools/legacy/ (historical) when next touched. Don't auto-move — verify references first. | no |
| W001 | loose-script-root | `proto_skel.py` | script proto_skel.py lives at repo root. Move under tools/ (active) or tools/legacy/ (historical) when next touched. Don't auto-move — verify references first. | no |
| W001 | loose-script-root | `proto_v2.py` | script proto_v2.py lives at repo root. Move under tools/ (active) or tools/legacy/ (historical) when next touched. Don't auto-move — verify references first. | no |
| W001 | loose-script-root | `render_debug.py` | script render_debug.py lives at repo root. Move under tools/ (active) or tools/legacy/ (historical) when next touched. Don't auto-move — verify references first. | no |
| W001 | loose-script-root | `render_native.py` | script render_native.py lives at repo root. Move under tools/ (active) or tools/legacy/ (historical) when next touched. Don't auto-move — verify references first. | no |
| W001 | loose-script-root | `render_proto_overlays.py` | script render_proto_overlays.py lives at repo root. Move under tools/ (active) or tools/legacy/ (historical) when next touched. Don't auto-move — verify references first. | no |
| W001 | loose-script-root | `render_semantic.py` | script render_semantic.py lives at repo root. Move under tools/ (active) or tools/legacy/ (historical) when next touched. Don't auto-move — verify references first. | no |
| W001 | loose-script-root | `render_sidebyside.py` | script render_sidebyside.py lives at repo root. Move under tools/ (active) or tools/legacy/ (historical) when next touched. Don't auto-move — verify references first. | no |
| W001 | loose-script-root | `render_with_openings.py` | script render_with_openings.py lives at repo root. Move under tools/ (active) or tools/legacy/ (historical) when next touched. Don't auto-move — verify references first. | no |
| W002 | md-no-status | `docs/SCHEMA-COHERENCE-REPORT.md` | docs/SCHEMA-COHERENCE-REPORT.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched. | no |
| W002 | md-no-status | `docs/SCHEMA-V2.md` | docs/SCHEMA-V2.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched. | no |
| W002 | md-no-status | `docs/SOLUTION.md` | docs/SOLUTION.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched. | no |
| W002 | md-no-status | `docs/agents/agent_operating_model.md` | docs/agents/agent_operating_model.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched. | no |
| W002 | md-no-status | `docs/agents/ci_guardian.md` | docs/agents/ci_guardian.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched. | no |
| W002 | md-no-status | `docs/agents/docs_maintainer.md` | docs/agents/docs_maintainer.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched. | no |
| W002 | md-no-status | `docs/agents/geometry_specialist.md` | docs/agents/geometry_specialist.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched. | no |
| W002 | md-no-status | `docs/agents/openings_specialist.md` | docs/agents/openings_specialist.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched. | no |
| W002 | md-no-status | `docs/agents/performance_specialist.md` | docs/agents/performance_specialist.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched. | no |
| W002 | md-no-status | `docs/agents/repo_auditor.md` | docs/agents/repo_auditor.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched. | no |
| W002 | md-no-status | `docs/agents/sketchup_specialist.md` | docs/agents/sketchup_specialist.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched. | no |
| W002 | md-no-status | `docs/agents/validator_specialist.md` | docs/agents/validator_specialist.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched. | no |
| W002 | md-no-status | `docs/diagnostics/2026-05-09_skp_visual_failure_fp014_gpt_validation.md` | docs/diagnostics/2026-05-09_skp_visual_failure_fp014_gpt_validation.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched. | no |
| W002 | md-no-status | `docs/diagnostics/2026-05-11_wall_audit/planta_74_audit.md` | docs/diagnostics/2026-05-11_wall_audit/planta_74_audit.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched. | no |
| W002 | md-no-status | `docs/diagnostics/2026-05-23_failure_pattern_id_audit.md` | docs/diagnostics/2026-05-23_failure_pattern_id_audit.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched. | no |
| W002 | md-no-status | `docs/diagnostics/2026-05-23_stack_integrity_report.md` | docs/diagnostics/2026-05-23_stack_integrity_report.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched. | no |
| W002 | md-no-status | `docs/git_workflow.md` | docs/git_workflow.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched. | no |
| W002 | md-no-status | `docs/ground_truth_references.md` | docs/ground_truth_references.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched. | no |
| W002 | md-no-status | `docs/ground_truth_v1.md` | docs/ground_truth_v1.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched. | no |
| W002 | md-no-status | `docs/learning/decision_log.md` | docs/learning/decision_log.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched. | no |
| W002 | md-no-status | `docs/learning/failure_patterns.md` | docs/learning/failure_patterns.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched. | no |
| W002 | md-no-status | `docs/learning/human_openings_truth_protocol.md` | docs/learning/human_openings_truth_protocol.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched. | no |
| W002 | md-no-status | `docs/learning/lessons_learned.md` | docs/learning/lessons_learned.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched. | no |
| W002 | md-no-status | `docs/learning/planta_74_clean_compatibility.md` | docs/learning/planta_74_clean_compatibility.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched. | no |
| W002 | md-no-status | `docs/learning/prompt_improvements.md` | docs/learning/prompt_improvements.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched. | no |
| W002 | md-no-status | `docs/learning/prompt_quality_rubric.md` | docs/learning/prompt_quality_rubric.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched. | no |
| W002 | md-no-status | `docs/learning/v5_opening_kind_enrichment.md` | docs/learning/v5_opening_kind_enrichment.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched. | no |
| W002 | md-no-status | `docs/learning/validation_matrix.md` | docs/learning/validation_matrix.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched. | no |
| W002 | md-no-status | `docs/operational_roadmap.md` | docs/operational_roadmap.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched. | no |
| W002 | md-no-status | `docs/ops/repo_hygiene_audit_2026-05-10.md` | docs/ops/repo_hygiene_audit_2026-05-10.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched. | no |
| W002 | md-no-status | `docs/performance/cache_keys.md` | docs/performance/cache_keys.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched. | no |
| W002 | md-no-status | `docs/performance/cache_rollout_plan.md` | docs/performance/cache_rollout_plan.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched. | no |
| W002 | md-no-status | `docs/performance/current_perf_baseline.md` | docs/performance/current_perf_baseline.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched. | no |
| W002 | md-no-status | `docs/performance/skip_unchanged_skp.md` | docs/performance/skip_unchanged_skp.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched. | no |
| W002 | md-no-status | `docs/png_history_protocol.md` | docs/png_history_protocol.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched. | no |
| W002 | md-no-status | `docs/protocols/human_soft_barriers_protocol.md` | docs/protocols/human_soft_barriers_protocol.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched. | no |
| W002 | md-no-status | `docs/tour/matterport_capture_failure_74m2.md` | docs/tour/matterport_capture_failure_74m2.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched. | no |
| W002 | md-no-status | `docs/tour/matterport_photo_inventory_74m2.md` | docs/tour/matterport_photo_inventory_74m2.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched. | no |
| W002 | md-no-status | `docs/tour/matterport_visual_findings_74m2.md` | docs/tour/matterport_visual_findings_74m2.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched. | no |
| W002 | md-no-status | `docs/validation/sketchup_2026_validation.md` | docs/validation/sketchup_2026_validation.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched. | no |
| W002 | md-no-status | `docs/validation/sketchup_smoke_workflow.md` | docs/validation/sketchup_smoke_workflow.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched. | no |
| W002 | md-no-status | `docs/validation/skp_fidelity_2026-05-04.md` | docs/validation/skp_fidelity_2026-05-04.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched. | no |
| W002 | md-no-status | `docs/validation/window_detector.md` | docs/validation/window_detector.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched. | no |
| W002 | md-no-status | `docs/validation_cockpit.md` | docs/validation_cockpit.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched. | no |
| W002 | md-no-status | `docs/validator_protocol.md` | docs/validator_protocol.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched. | no |

## Requires human decision

- [W001] `analyze_overpoly.py` — script analyze_overpoly.py lives at repo root. Move under tools/ (active) or tools/legacy/ (historical) when next touched. Don't auto-move — verify references first.
- [W001] `crop_legend.py` — script crop_legend.py lives at repo root. Move under tools/ (active) or tools/legacy/ (historical) when next touched. Don't auto-move — verify references first.
- [W001] `make_test_pdf.py` — script make_test_pdf.py lives at repo root. Move under tools/ (active) or tools/legacy/ (historical) when next touched. Don't auto-move — verify references first.
- [W001] `peek_pdf.py` — script peek_pdf.py lives at repo root. Move under tools/ (active) or tools/legacy/ (historical) when next touched. Don't auto-move — verify references first.
- [W001] `preprocess_walls.py` — script preprocess_walls.py lives at repo root. Move under tools/ (active) or tools/legacy/ (historical) when next touched. Don't auto-move — verify references first.
- [W001] `proto_colored.py` — script proto_colored.py lives at repo root. Move under tools/ (active) or tools/legacy/ (historical) when next touched. Don't auto-move — verify references first.
- [W001] `proto_red.py` — script proto_red.py lives at repo root. Move under tools/ (active) or tools/legacy/ (historical) when next touched. Don't auto-move — verify references first.
- [W001] `proto_runner.py` — script proto_runner.py lives at repo root. Move under tools/ (active) or tools/legacy/ (historical) when next touched. Don't auto-move — verify references first.
- [W001] `proto_skel.py` — script proto_skel.py lives at repo root. Move under tools/ (active) or tools/legacy/ (historical) when next touched. Don't auto-move — verify references first.
- [W001] `proto_v2.py` — script proto_v2.py lives at repo root. Move under tools/ (active) or tools/legacy/ (historical) when next touched. Don't auto-move — verify references first.
- [W001] `render_debug.py` — script render_debug.py lives at repo root. Move under tools/ (active) or tools/legacy/ (historical) when next touched. Don't auto-move — verify references first.
- [W001] `render_native.py` — script render_native.py lives at repo root. Move under tools/ (active) or tools/legacy/ (historical) when next touched. Don't auto-move — verify references first.
- [W001] `render_proto_overlays.py` — script render_proto_overlays.py lives at repo root. Move under tools/ (active) or tools/legacy/ (historical) when next touched. Don't auto-move — verify references first.
- [W001] `render_semantic.py` — script render_semantic.py lives at repo root. Move under tools/ (active) or tools/legacy/ (historical) when next touched. Don't auto-move — verify references first.
- [W001] `render_sidebyside.py` — script render_sidebyside.py lives at repo root. Move under tools/ (active) or tools/legacy/ (historical) when next touched. Don't auto-move — verify references first.
- [W001] `render_with_openings.py` — script render_with_openings.py lives at repo root. Move under tools/ (active) or tools/legacy/ (historical) when next touched. Don't auto-move — verify references first.
- [W002] `docs/SCHEMA-COHERENCE-REPORT.md` — docs/SCHEMA-COHERENCE-REPORT.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched.
- [W002] `docs/SCHEMA-V2.md` — docs/SCHEMA-V2.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched.
- [W002] `docs/SOLUTION.md` — docs/SOLUTION.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched.
- [W002] `docs/agents/agent_operating_model.md` — docs/agents/agent_operating_model.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched.
- [W002] `docs/agents/ci_guardian.md` — docs/agents/ci_guardian.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched.
- [W002] `docs/agents/docs_maintainer.md` — docs/agents/docs_maintainer.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched.
- [W002] `docs/agents/geometry_specialist.md` — docs/agents/geometry_specialist.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched.
- [W002] `docs/agents/openings_specialist.md` — docs/agents/openings_specialist.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched.
- [W002] `docs/agents/performance_specialist.md` — docs/agents/performance_specialist.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched.
- [W002] `docs/agents/repo_auditor.md` — docs/agents/repo_auditor.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched.
- [W002] `docs/agents/sketchup_specialist.md` — docs/agents/sketchup_specialist.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched.
- [W002] `docs/agents/validator_specialist.md` — docs/agents/validator_specialist.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched.
- [W002] `docs/diagnostics/2026-05-09_skp_visual_failure_fp014_gpt_validation.md` — docs/diagnostics/2026-05-09_skp_visual_failure_fp014_gpt_validation.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched.
- [W002] `docs/diagnostics/2026-05-11_wall_audit/planta_74_audit.md` — docs/diagnostics/2026-05-11_wall_audit/planta_74_audit.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched.
- [W002] `docs/diagnostics/2026-05-23_failure_pattern_id_audit.md` — docs/diagnostics/2026-05-23_failure_pattern_id_audit.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched.
- [W002] `docs/diagnostics/2026-05-23_stack_integrity_report.md` — docs/diagnostics/2026-05-23_stack_integrity_report.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched.
- [W002] `docs/git_workflow.md` — docs/git_workflow.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched.
- [W002] `docs/ground_truth_references.md` — docs/ground_truth_references.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched.
- [W002] `docs/ground_truth_v1.md` — docs/ground_truth_v1.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched.
- [W002] `docs/learning/decision_log.md` — docs/learning/decision_log.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched.
- [W002] `docs/learning/failure_patterns.md` — docs/learning/failure_patterns.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched.
- [W002] `docs/learning/human_openings_truth_protocol.md` — docs/learning/human_openings_truth_protocol.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched.
- [W002] `docs/learning/lessons_learned.md` — docs/learning/lessons_learned.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched.
- [W002] `docs/learning/planta_74_clean_compatibility.md` — docs/learning/planta_74_clean_compatibility.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched.
- [W002] `docs/learning/prompt_improvements.md` — docs/learning/prompt_improvements.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched.
- [W002] `docs/learning/prompt_quality_rubric.md` — docs/learning/prompt_quality_rubric.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched.
- [W002] `docs/learning/v5_opening_kind_enrichment.md` — docs/learning/v5_opening_kind_enrichment.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched.
- [W002] `docs/learning/validation_matrix.md` — docs/learning/validation_matrix.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched.
- [W002] `docs/operational_roadmap.md` — docs/operational_roadmap.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched.
- [W002] `docs/ops/repo_hygiene_audit_2026-05-10.md` — docs/ops/repo_hygiene_audit_2026-05-10.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched.
- [W002] `docs/performance/cache_keys.md` — docs/performance/cache_keys.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched.
- [W002] `docs/performance/cache_rollout_plan.md` — docs/performance/cache_rollout_plan.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched.
- [W002] `docs/performance/current_perf_baseline.md` — docs/performance/current_perf_baseline.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched.
- [W002] `docs/performance/skip_unchanged_skp.md` — docs/performance/skip_unchanged_skp.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched.
- [W002] `docs/png_history_protocol.md` — docs/png_history_protocol.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched.
- [W002] `docs/protocols/human_soft_barriers_protocol.md` — docs/protocols/human_soft_barriers_protocol.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched.
- [W002] `docs/tour/matterport_capture_failure_74m2.md` — docs/tour/matterport_capture_failure_74m2.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched.
- [W002] `docs/tour/matterport_photo_inventory_74m2.md` — docs/tour/matterport_photo_inventory_74m2.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched.
- [W002] `docs/tour/matterport_visual_findings_74m2.md` — docs/tour/matterport_visual_findings_74m2.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched.
- [W002] `docs/validation/sketchup_2026_validation.md` — docs/validation/sketchup_2026_validation.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched.
- [W002] `docs/validation/sketchup_smoke_workflow.md` — docs/validation/sketchup_smoke_workflow.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched.
- [W002] `docs/validation/skp_fidelity_2026-05-04.md` — docs/validation/skp_fidelity_2026-05-04.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched.
- [W002] `docs/validation/window_detector.md` — docs/validation/window_detector.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched.
- [W002] `docs/validation_cockpit.md` — docs/validation_cockpit.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched.
- [W002] `docs/validator_protocol.md` — docs/validator_protocol.md has no `Status:` header (docs/REPO_HYGIENE.md §2). Add Canonical / Active / Archived / Generated / Delete candidate when next touched.

## How to act

- `python tools/repo_health_gate.py --mode audit` (read-only, default).
- `python tools/repo_health_gate.py --mode check --base origin/develop` (CI / PR gate).
- `python tools/repo_health_gate.py --mode fix` (apply the conservative safe-fix list only).
- Manual cleanup: follow `docs/REPO_HYGIENE.md` §3 (don't-delete-blindly protocol).

## References

- [`../REPO_HYGIENE.md`](../../docs/REPO_HYGIENE.md) — policy
- [`../GATES.md`](../../docs/GATES.md) — gate catalogue
- [`../../CLAUDE.md`](../../CLAUDE.md) §15 — manual hygiene loop
