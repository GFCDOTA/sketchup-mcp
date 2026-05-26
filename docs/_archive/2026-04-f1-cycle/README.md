# 2026-04 F1-Cycle Archive

Documents from the F1/dedup cycle (2026-04-21 fix `a11724a` window),
moved here on 2026-05-04 to reduce `docs/` root clutter, and pruned
on 2026-05-26 (PR-after-#180) to drop fully-superseded analyses
without active references.

These are preserved for historical context. They are NOT a current
source of truth. For current state see:

- `CLAUDE.md` (constitution + invariants)
- `docs/PROJECT_STATE.md` (canonical project state)
- `docs/operational_roadmap.md` + `.ai_bridge/TODO_NEXT.md` (roadmap)

## Files (post-2026-05-26 prune)

| File | Original purpose | Why kept |
|---|---|---|
| `F1-DASHBOARD.html` | F1 metric dashboard snapshot | Standalone artifact — independent of any active doc; useful reference for F1-cycle outcome numbers |
| `OVER-POLYGONIZATION-ANALYSIS.md` | Over-polygonization analysis | **Load-bearing** — cited by `tools/repo_health_gate.py` I003 rationale for keeping `analyze_overpoly.py` at root (line 220: `python analyze_overpoly.py`) |
| `SOLUTION-FINAL.md` | F1-cycle final solution writeup | Cited by `docs/PROJECT_STATE.md` §9; the canonical F1 root-cause/fix narrative |
| `SVG-INGEST-INTEGRATION.md` | SVG ingest integration plan | Cited by this index; documents the integration that became `tools/build_vector_consensus.py` |
| `SVG-MAIN-PLAN-ISOLATION.md` | SVG main plan isolation plan | Cited by this index; documents the main-plan isolation algorithm |

## What was removed on 2026-05-26

10 fully-superseded analyses with **zero active references** outside
this archive (only self-refs in the archived siblings):
`ANALYSIS-OVERVIEW.md`, `ANALYSIS.md`, `CAUSA-RAIZ.md`,
`CROSS-PDF-VALIDATION.md`, `DOCS-CONSOLIDATION-TODO.md`,
`OPENINGS-EXPLOSION-AUDIT.md`, `OPENINGS-REFINEMENT.md`,
`ORPHAN-RESIDUAL-AUDIT.md`, `PROMPT-NEXT-CLAUDE.md`,
`VALIDATION-F1-REPORT.md`.

Net effect: -~75 KB of unreferenced F1-cycle prose. Git history
preserves the content; the archive now contains only files actively
cited by code/canonical docs.

## Why this archive exists at all

Per CLAUDE.md §1 hard rule #1 (default-preserve under `docs/`) and §5
(conservative default). Files kept here are still discoverable in
`docs/_archive/` without polluting the canonical `docs/` root. Files
removed in the 2026-05-26 prune lacked any active citation, so the
"discoverable for future work" rationale no longer applied.
