# 2026-04 F1-Cycle Archive

Documents from the F1/dedup cycle (2026-04-21 fix `a11724a` window),
moved here on 2026-05-04 to reduce `docs/` root clutter. Pruned in
PR #181 (2026-05-26) and again in PR-after-#182 (2026-05-26) to drop
fully-superseded analyses and output artifacts without active references.

These are preserved for historical context. They are NOT a current
source of truth. For current state see:

- `CLAUDE.md` (constitution + invariants)
- `docs/PROJECT_STATE.md` (canonical project state)
- `docs/operational_roadmap.md` + `.ai_bridge/TODO_NEXT.md` (roadmap)

## Files (post-2026-05-26 prune, 2 entries)

| File | Why kept |
|---|---|
| `OVER-POLYGONIZATION-ANALYSIS.md` | **Load-bearing** — cited by `tools/repo_health_gate.py` I003 rationale for keeping `analyze_overpoly.py` at root (line 220: `python analyze_overpoly.py`) |
| `SOLUTION-FINAL.md` | Cited by `docs/PROJECT_STATE.md` §9 + `OVERVIEW.md` + `patches/archive/README.md`; the canonical F1 root-cause/fix narrative |

## What was removed across the prune waves

**2026-05-26 (PR #181):** 10 fully-superseded analyses with zero
active refs (`ANALYSIS-OVERVIEW.md`, `ANALYSIS.md`, `CAUSA-RAIZ.md`,
`CROSS-PDF-VALIDATION.md`, `DOCS-CONSOLIDATION-TODO.md`,
`OPENINGS-EXPLOSION-AUDIT.md`, `OPENINGS-REFINEMENT.md`,
`ORPHAN-RESIDUAL-AUDIT.md`, `PROMPT-NEXT-CLAUDE.md`,
`VALIDATION-F1-REPORT.md`).

**2026-05-26 (PR-after-#182):** 3 more entries:
`F1-DASHBOARD.html` (49 KB output artifact regenerable via
`scripts/generate_f1_dashboard.py`), `SVG-INGEST-INTEGRATION.md` and
`SVG-MAIN-PLAN-ISOLATION.md` (whose algorithmic content lives in
`tools/build_vector_consensus.py` source + tests).

Git history preserves all removed content; use
`git log --diff-filter=D -- docs/_archive/2026-04-f1-cycle/<file>`
to recover if ever needed.

## Why this archive exists at all

Per CLAUDE.md §1 hard rule #1 (default-preserve under `docs/`) and §5
(conservative default). Files kept here remain discoverable without
polluting the canonical `docs/` root. Files removed in the 2026-05-26
prunes lacked any active citation beyond the archive's own index —
no active code, test, canonical doc, or canonical ADR referenced them.
