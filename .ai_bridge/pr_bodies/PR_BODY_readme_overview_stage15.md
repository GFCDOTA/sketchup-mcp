# docs(readme,overview): document Stage 1 / 1.5 / 1.6 tools + gates

**Branch**: `docs/readme-overview-stage15-tools` → `develop`
**Commit**: `d62954c`
**Compare URL**: https://github.com/GFCDOTA/sketchup-mcp/compare/develop...docs/readme-overview-stage15-tools

## Summary

- Catches `README.md` and `OVERVIEW.md` up to the current state of
  the repo. Both files were last touched 2026-04-XX and predate the
  entire Stage-1.5 wave (PRs #44–#48): they had ZERO references to
  `coherence_audit`, `micro_truth_gate`, `classify_openings_by_room_context`,
  the Plan Truth Gate, or the new gates' CI wiring.
- Pure additive markdown. No code, no test, no schema, no threshold,
  no Ruby/SU touched.

## What changed

### `OVERVIEW.md`

- §2.8 (Tools auxiliares): adds 4 entries — `classify_openings_by_room_context`,
  `coherence_audit`, `micro_truth_gate`, `skp_inspection_report` —
  each with a one-line description of its stage, schema version,
  and strict-mode behaviour.
- §4.4 (Pipeline vetorial completo): extends the bash recipe with
  the missing Stage 5 (`classify_openings_by_room_context`); bumps
  the expected output to mention `soft_barriers`; updates the
  `--mode replace` line to the current
  `--mode replace --classify-kind --detect-wall-gaps` form.
- §4.4.1 (Validation gates) — new subsection. Three-line recipe
  covering Plan / Coherence / Micro gates with a pointer to
  `quality_gates.yml`.

### `README.md`

- New section "Validation Gates (Stage 1 / 1.5 / 1.6)" inserted
  between "Testes Cobertos" and "Preview / Visualizacao". Same
  three gates, briefly described, with a pointer to the CI
  workflow that runs them in `--strict`.

## What did NOT change

- No code path. No test surface. No schema or threshold. No Ruby
  or SU exporter logic.
- Pre-existing OVERVIEW / README structure preserved; additions
  only — no deletions, no reorderings.

## Validation

- N/A: pure markdown.
- Manually spot-checked file paths against the repo state on `develop`:
  - `tools/coherence_audit.py` ✓
  - `tools/micro_truth_gate.py` ✓
  - `tools/classify_openings_by_room_context.py` ✓
  - `tools/skp_inspection_report.py` ✓
  - `tests/test_planta_74_truth_gate.py` ✓
  - `tests/baselines/planta_74.json` ✓
  - `ground_truth/planta_74_micro.json` ✓
- The `quality_gates.yml` reference assumes the Cycle 10 PR
  (`feature/quality-gates-ci-workflow`) lands. That PR is in
  the same merge wave; if landed first, the link is live the
  moment this PR merges.

## Risks

- None. Worst case a future reader follows the recipe and finds
  slightly stale numbers if a baseline shifts — the gates
  themselves catch that case immediately.

## Rollback

```bash
git push origin --delete docs/readme-overview-stage15-tools
# post-merge:
git revert <merge-sha>
```

## Next steps

After merge:

- If `feature/quality-gates-ci-workflow` was NOT landed first,
  the README link to `quality_gates.yml` is dangling — but only
  for the duration of the gap. Recommend merging that workflow
  PR before this docs PR if doing them sequentially.
- Future Stage 2 / Stage 3 work should add a `## Stage 2` /
  `## Stage 3` subsection in the same area rather than rewriting
  the existing prose.
