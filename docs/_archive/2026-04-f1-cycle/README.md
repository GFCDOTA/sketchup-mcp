# 2026-04 F1-Cycle Archive

Documents from the F1/dedup cycle (2026-04-21 fix `a11724a` window),
moved here on 2026-05-04 to reduce `docs/` root clutter.

These are preserved for historical context. They are NOT a current
source of truth. For current state see:

- `CLAUDE.md` (constitution + invariants)
- `docs/operational_roadmap.md` (operational source of truth)
- `docs/ROADMAP.md` (algorithmic roadmap, with stale-status banner)

## Files

| File | Original purpose |
|---|---|
| `ANALYSIS-OVERVIEW.md` | Cross-document analysis index for the F1 cycle |
| `ANALYSIS.md` | Detailed root-cause analysis from the F1 cycle |
| `CAUSA-RAIZ.md` | Single root-cause writeup |
| `CROSS-PDF-VALIDATION.md` | Cross-PDF validation report |
| `DOCS-CONSOLIDATION-TODO.md` | One-time docs consolidation TODO list |
| `F1-DASHBOARD.html` | F1 metric dashboard snapshot |
| `OPENINGS-EXPLOSION-AUDIT.md` | Audit of openings count explosion |
| `OPENINGS-REFINEMENT.md` | Openings refinement notes |
| `ORPHAN-RESIDUAL-AUDIT.md` | Audit of orphan residual nodes |
| `OVER-POLYGONIZATION-ANALYSIS.md` | Over-polygonization analysis |
| `PROMPT-NEXT-CLAUDE.md` | Hand-off prompt for next Claude session (F1 cycle) |
| `SOLUTION-FINAL.md` | F1-cycle final solution writeup |
| `SVG-INGEST-INTEGRATION.md` | SVG ingest integration plan |
| `SVG-MAIN-PLAN-ISOLATION.md` | SVG main plan isolation plan |
| `VALIDATION-F1-REPORT.md` | F1 validation report |

## Why archived (not deleted)

Per CLAUDE.md §1 hard rule #1 (never delete under `docs/`) and §5
(default decision rule = conservative). Git history preserves either
way, but keeping these discoverable in `docs/_archive/` lets future
work find prior context without polluting the canonical `docs/` root.
