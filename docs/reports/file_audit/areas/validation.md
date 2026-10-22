# Handoff por arquivo — tools/validation/ (gates transversais)

> Gerado por `python -m tools.navigation.file_audit --out docs/reports/file_audit` em `66fd65b`.
> Retrato datado: regenere, não edite. Estados e regras no docstring de `tools/navigation/file_audit.py`.

Contagem: ACTIVE_ENTRYPOINT 6, ACTIVE_IMPORTED 29, CLI_DOC_ONLY 3, PACKAGE_MARKER 1

| Arquivo | Estado | Por quê | Importado por | Citado por | Último toque | Próximo passo |
|---|---|---|---|---|---|---|
| `tools/validation/__init__.py` | PACKAGE_MARKER | pacote sem logica | 0 | 15 | 2026-10-19 | manter |
| `tools/validation/circulation_gate.py` | ACTIVE_IMPORTED | importado por 6 arquivo(s) | 6 | 7 | 2026-10-19 | manter |
| `tools/validation/collision_envelope_gate.py` | ACTIVE_IMPORTED | importado por 1 arquivo(s) | 1 | 8 | 2026-10-20 | manter |
| `tools/validation/diagnose_wall_stubs.py` | ACTIVE_IMPORTED | importado por 1 arquivo(s) | 1 | 8 | 2026-10-20 | manter |
| `tools/validation/door_swing_audit.py` | ACTIVE_IMPORTED | importado por 1 arquivo(s) | 1 | 6 | 2026-10-20 | manter |
| `tools/validation/flat_white_gate.py` | ACTIVE_IMPORTED | importado por 3 arquivo(s) | 3 | 6 | 2026-10-20 | manter |
| `tools/validation/fp044_baseline.py` | ACTIVE_IMPORTED | importado por 2 arquivo(s) | 2 | 4 | 2026-10-19 | manter |
| `tools/validation/furniture_overlap_gate.py` | ACTIVE_ENTRYPOINT | citado por 1 arquivo(s) de codigo/CI/config/skill | 0 | 6 | 2026-10-19 | manter |
| `tools/validation/furniture_visual_gate.py` | ACTIVE_ENTRYPOINT | citado por 2 arquivo(s) de codigo/CI/config/skill | 0 | 4 | 2026-10-20 | manter |
| `tools/validation/furniture_wall_gap.py` | ACTIVE_IMPORTED | importado por 1 arquivo(s) | 1 | 4 | 2026-10-19 | manter |
| `tools/validation/gate_filefetch.py` | ACTIVE_IMPORTED | importado por 1 arquivo(s) | 1 | 4 | 2026-10-19 | manter |
| `tools/validation/gate_util.py` | ACTIVE_IMPORTED | importado por 4 arquivo(s) | 4 | 4 | 2026-10-19 | manter |
| `tools/validation/gate_verdict.py` | ACTIVE_IMPORTED | importado por 2 arquivo(s) | 2 | 5 | 2026-10-19 | manter |
| `tools/validation/generalization_gate.py` | CLI_DOC_ONLY | CLI manual citada so em documentacao (4 doc); nenhum teste/CI a executa | 0 | 4 | 2026-10-19 | dar teste de fumaca (vira ACTIVE) ou arquivar com decisao do Felipe |
| `tools/validation/geometry_sanity.py` | ACTIVE_ENTRYPOINT | citado por 1 arquivo(s) de codigo/CI/config/skill | 0 | 6 | 2026-10-21 | manter |
| `tools/validation/opening_aperture_audit.py` | ACTIVE_IMPORTED | importado por 1 arquivo(s) | 1 | 4 | 2026-10-20 | manter |
| `tools/validation/opening_audit.py` | ACTIVE_ENTRYPOINT | citado por 1 arquivo(s) de codigo/CI/config/skill | 0 | 6 | 2026-10-19 | manter |
| `tools/validation/opening_host_audit.py` | ACTIVE_IMPORTED | importado por 5 arquivo(s) | 5 | 4 | 2026-10-19 | manter |
| `tools/validation/optimizer_consistency_gate.py` | ACTIVE_IMPORTED | importado por 1 arquivo(s) | 1 | 9 | 2026-10-20 | manter |
| `tools/validation/parapet_not_railing_fallback_gate.py` | ACTIVE_IMPORTED | importado por 3 arquivo(s) | 3 | 4 | 2026-10-20 | manter |
| `tools/validation/pdf_height_labels_audit.py` | ACTIVE_IMPORTED | importado por 1 arquivo(s) | 1 | 5 | 2026-10-20 | manter |
| `tools/validation/position_fidelity_gate.py` | ACTIVE_IMPORTED | importado por 3 arquivo(s) | 3 | 4 | 2026-10-20 | manter |
| `tools/validation/railing_exact_match_gate.py` | ACTIVE_IMPORTED | importado por 4 arquivo(s) | 4 | 4 | 2026-10-19 | manter |
| `tools/validation/render_bbox_audit.py` | ACTIVE_IMPORTED | importado por 2 arquivo(s) | 2 | 4 | 2026-10-19 | manter |
| `tools/validation/repo_health_gate.py` | ACTIVE_IMPORTED | importado por 1 arquivo(s) | 1 | 5 | 2026-10-20 | manter |
| `tools/validation/room_collisions.py` | ACTIVE_IMPORTED | importado por 3 arquivo(s) | 3 | 5 | 2026-10-19 | manter |
| `tools/validation/room_regression.py` | ACTIVE_IMPORTED | importado por 4 arquivo(s) | 4 | 3 | 2026-10-21 | manter |
| `tools/validation/room_regression_diff.py` | ACTIVE_IMPORTED | importado por 5 arquivo(s) | 5 | 2 | 2026-10-21 | manter |
| `tools/validation/room_regression_gates.py` | ACTIVE_IMPORTED | importado por 5 arquivo(s) | 5 | 2 | 2026-10-21 | manter |
| `tools/validation/run_deterministic_gates.py` | ACTIVE_IMPORTED | importado por 9 arquivo(s) | 9 | 18 | 2026-10-20 | manter |
| `tools/validation/scale_anchor_gate.py` | ACTIVE_IMPORTED | importado por 4 arquivo(s) | 4 | 4 | 2026-10-19 | manter |
| `tools/validation/scene_spatial_gate.py` | ACTIVE_ENTRYPOINT | citado por 2 arquivo(s) de codigo/CI/config/skill | 0 | 5 | 2026-10-20 | manter |
| `tools/validation/semantic_geometry_contract_gate.py` | ACTIVE_IMPORTED | importado por 1 arquivo(s) | 1 | 8 | 2026-10-20 | manter |
| `tools/validation/soft_barrier_source_audit.py` | ACTIVE_IMPORTED | importado por 2 arquivo(s) | 2 | 4 | 2026-10-19 | manter |
| `tools/validation/style_coherence_gate.py` | ACTIVE_IMPORTED | importado por 1 arquivo(s) | 1 | 6 | 2026-10-20 | manter |
| `tools/validation/validation_report.py` | ACTIVE_ENTRYPOINT | citado por 2 arquivo(s) de codigo/CI/config/skill | 0 | 4 | 2026-10-20 | manter |
| `tools/validation/visual_regression_gate.py` | CLI_DOC_ONLY | CLI manual citada so em documentacao (7 doc); nenhum teste/CI a executa | 0 | 7 | 2026-10-19 | dar teste de fumaca (vira ACTIVE) ou arquivar com decisao do Felipe |
| `tools/validation/wall_exact_match_gate.py` | CLI_DOC_ONLY | CLI manual citada so em documentacao (5 doc); nenhum teste/CI a executa | 0 | 5 | 2026-10-20 | dar teste de fumaca (vira ACTIVE) ou arquivar com decisao do Felipe |
| `tools/validation/wall_overlap_audit.py` | ACTIVE_IMPORTED | importado por 5 arquivo(s) | 5 | 4 | 2026-10-19 | manter |
