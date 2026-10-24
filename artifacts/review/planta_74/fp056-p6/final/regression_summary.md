# FP-056 P6 — planta_74 gerada no SketchUp real (regression_summary, 2026-10-24)

Commit sob prova `a0be0516…`; evidência completa em `artifacts/review/fp056/p6/README.md`. `visual = PENDING_HUMAN`.

| Eixo | Medida | Evidência |
|---|---|---|
| Geração | `.skp` salvo e reaberto em outro processo (SketchUp 26.0.429) | `summary.json` |
| Proposta × construído | todos os módulos planejados são grupos, ≤ 5 mm | caso `every_planned_module_is_a_group_within_5mm` |
| Arquitetura | paredes construídas = consensus (20/20) | caso `built_walls_match_consensus` |
| Defeitos físicos | 34 → 29; 0 novos, 0 piores; 4 resolvidos por posição, 1 sumiu com a peça | `regression.json`, `defects_after.json` |
| Programa | **FAIL**: A.S. sem bancada gourmet e banqueta (circulação; decisão AS-1 pendente) | `regression.json` |
| Canônicos | SHA-256 idênticos antes/depois | `summary.json` |

Renders: `model_top_after.png`, `model_iso_after.png`. Aparência não aprovada.
