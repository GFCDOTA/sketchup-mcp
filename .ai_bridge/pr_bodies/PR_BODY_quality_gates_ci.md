# ci(quality-gates): add strict-mode workflow for Plan/Coherence/Micro

**Branch**: `feature/quality-gates-ci-workflow` → `develop`
**Commits**: `c5b5342` (initial workflow with 3 strict gates) +
`a73be99` (adendo: hashFiles-guarded Fidelity Engine v1 step,
auto-skip until GT branch lands)
**Compare URL**: https://github.com/GFCDOTA/sketchup-mcp/compare/develop...feature/quality-gates-ci-workflow

> **Adendo (NAO PARE mode)**: adds the Fidelity Engine v1 step
> guarded by `hashFiles('tools/fidelity/__init__.py',
> 'ground_truth/planta_74/expected_model.json') != ''`. Step is
> SKIPPED gracefully until `feature/ground-truth-v1-fidelity-engine`
> lands on develop, then runs automatically with `--strict`. Removes
> the cross-branch sequencing dependency between this PR and the
> GT v1 PR — they can land in either order.

## Summary

- Bootstraps a dedicated CI workflow that builds the planta_74
  vector pipeline end-to-end and then runs the three Stage-1.5
  quality gates in `--strict` mode.
- Hard merge blocker on regression — distinct from `ci.yml`'s
  informational subset.
- Pure infrastructure. No code, no test, no fixture touched.

## What changed

- `.github/workflows/quality_gates.yml` (new)
  - Triggers on PR, push to `main`/`develop`, manual dispatch.
  - Builds `c0 -> c1 -> c2 -> c3` from `planta_74.pdf` (5-stage
    vector pipeline, ~5–10 s on this PDF).
  - Runs `tests/test_planta_74_truth_gate.py` in isolation so a
    failure surfaces as a dedicated, named CI status rather than
    being buried in the larger pytest job.
  - Runs `tools.coherence_audit --strict` on the freshly-built
    consensus. Exits non-zero on any
    `assumptions.strict_blockers` condition (drops, asks,
    floating doors).
  - Runs `tools.micro_truth_gate --strict` against the same
    consensus + the canonical
    `ground_truth/planta_74_micro.json`. Exits non-zero if any
    room fails its checks.
  - Uploads `runs/_ci_quality_gates/` (the full pipeline output
    + both audit reports) as an artifact for 14 days on both
    success AND failure, for diffability across PRs.

## What did NOT change

- No Python code touched. No Ruby code touched. No tests touched.
- `ci.yml`, `skp_fidelity_gate.yml`, `rubocop.yml` unchanged.
- `tools/coherence_audit.py`, `tools/micro_truth_gate.py`,
  `tools/build_vector_consensus.py`, `tools/rooms_from_seeds.py`
  — untouched.
- No schema, no thresholds, no Ruby/SU exporter, no smoke gates.

## Validation

```
# YAML parse
python -c "import yaml; yaml.safe_load(open('.github/workflows/quality_gates.yml'))"
# OK

# Strict gates against today's c3:
python -m tools.coherence_audit \
       runs/validation_2026-05-07/c3_classified.json \
       --out-dir /tmp --strict
# [coherence-audit] openings=11 by_decision={'clean': 7, 'debug': 4}
# exit 0

python -m tools.micro_truth_gate \
       runs/validation_2026-05-07/c3_classified.json \
       --ground-truth ground_truth/planta_74_micro.json \
       --out /tmp/mt.json --strict
# [micro-truth] score=1.0 rooms=1 fired=0
# exit 0
```

Both `--strict` commands exit 0 against the current canonical
output. Workflow style consistent with the existing `ci.yml` +
`rubocop.yml` (paths-filtered or unconditional triggers, ubuntu-
latest, generous timeouts, `actions/upload-artifact@v4`).

## Risks

- **First CI run is the first time the workflow exercises its
  full path.** If pyrubicon, shapely, opencv-headless, or
  pypdfium2 misbehaves on ubuntu CI in any way the locally-
  validated equivalent did not surface, the workflow flags it.
  Mitigation: full pipeline takes ~10 s; quick to iterate on.
- `ground_truth/planta_74_micro.json` currently has only 1
  room (SALA DE ESTAR). Until the Cycle 7 expansion PR merges,
  `--strict` checks 1 room. After Cycle 7 merges this workflow
  will check all 4 rooms automatically — no follow-up needed.
- Any upstream change that flips a count in
  `tests/baselines/planta_74.json` → Plan Truth Gate fails →
  this workflow becomes RED → blocks merge. By design.

## Rollback

```bash
git push origin --delete feature/quality-gates-ci-workflow
# post-merge:
git revert <merge-sha>
```

## Next steps

After merge:

1. The next PR that touches `tools/build_vector_consensus.py`,
   `rooms_from_seeds.py`, `extract_openings_vector.py`, or
   `classify_openings_by_room_context.py` becomes the first
   real-world test of the strict workflow.
2. Once the Cycle 8 spike (`feature/concave-hull-room-clip-spike`)
   AND the Cycle 8b promote-default PR land, this workflow
   automatically validates the new geometry pipeline.
3. Optional Cycle 11: add a `--inspect-strict` smoke step
   (Stage 1.6, gate G2) once PR #52 lands. Excluded from this
   PR because Stage 1.6 is out-of-scope per the user's session
   directive.

## References

- `.ai_bridge/TODO_NEXT.md` — "Cycle 9 GitHub Action wiring all 4
  gates per PR" (renamed Cycle 10 in the 2026-05-07 reshuffle).
- `docs/learning/failure_patterns.md` — FP-010 (never deselect to
  mask a current-PR regression).
