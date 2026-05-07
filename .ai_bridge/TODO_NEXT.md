# TODO Next — ROI-ordered

> Continuous queue. Top items execute first. Update as items land
> or new ones surface. Stale entries → either compact or move to
> `LESSONS.md`.

## Format

Each entry:
- **Priority** — P0 (blocker) / P1 (high ROI) / P2 (nice) / P3 (deferred)
- **Evidence** — why this matters (file path, log, test, metric)
- **Touchpoints** — files / commands likely involved
- **Validation** — how to know it worked
- **Risk** — what can break

---

## P0 — Six PR-less branches ready (PR bodies under .ai_bridge/pr_bodies/)

User opens PRs manually (memory rule `feedback_pr_manual_preferido.md`).
Recommended merge order to minimize rebase pain:

1. `docs/non-stop-autonomy-rule` (CLAUDE.md only, no conflicts)
2. `docs/suite01-polygon-leakage-investigation` (docs/ only)
3. `feature/rubocop-sketchup-ci` (Gemfile/.rubocop/workflow only)
4. `feature/concave-hull-room-clip-spike` (default-off code change)
5. `docs/ai-bridge-scaffolding-clean` (.ai_bridge/ only)
6. `feature/micro-truth-expand-planta-74-cycle7` (ground_truth + tests)

| Branch | Body file | Compare URL |
|---|---|---|
| `docs/non-stop-autonomy-rule` | `PR_BODY_non_stop_autonomy_rule.md` | https://github.com/GFCDOTA/sketchup-mcp/compare/develop...docs/non-stop-autonomy-rule |
| `docs/suite01-polygon-leakage-investigation` | `PR_BODY_suite01_polygon_diagnostic.md` | https://github.com/GFCDOTA/sketchup-mcp/compare/develop...docs/suite01-polygon-leakage-investigation |
| `feature/rubocop-sketchup-ci` | `PR_BODY_rubocop_ci.md` | https://github.com/GFCDOTA/sketchup-mcp/compare/develop...feature/rubocop-sketchup-ci |
| `feature/concave-hull-room-clip-spike` | `PR_BODY_concave_hull_spike.md` | https://github.com/GFCDOTA/sketchup-mcp/compare/develop...feature/concave-hull-room-clip-spike |
| `docs/ai-bridge-scaffolding-clean` | `PR_BODY_ai_bridge_scaffolding_clean.md` | https://github.com/GFCDOTA/sketchup-mcp/compare/develop...docs/ai-bridge-scaffolding-clean |
| `feature/micro-truth-expand-planta-74-cycle7` | `PR_BODY_cycle7_micro_truth_expand.md` | https://github.com/GFCDOTA/sketchup-mcp/compare/develop...feature/micro-truth-expand-planta-74-cycle7 |

**Branch to delete after `docs/ai-bridge-scaffolding-clean` merges**:
`feature/ai-bridge-scaffolding` (contaminated with PR #52 commit
`2417a20`). Local + remote.

## P0 — Merge in-flight (Stage 1.6)

**Merge PR #52 (smoke gate G2)** — `feature/smoke-promotes-inspector-v2-gate`
- Evidence: PR open, all checks green, no conflicts
- Touchpoints: GitHub PR #52
- Validation: `git pull origin develop && grep "gate_g2" scripts/smoke/smoke_skp_export.py`
- Risk: none (additive, opt-in flag)

## P1 — Cycle 6: wire autorun inspector into gate F

**Goal**: `inspect_report.json` becomes default output of every smoke
run; gate G2 stops SKIPping.
- Evidence: smoke_g2_2026_05_07 run shows G2 SKIP "no inspect_report.json"
- Touchpoints:
  - `tools/skp_from_consensus.py` (launcher) — pass `INSPECT_REPORT` env
    + `CONSENSUS_JSON_FOR_INSPECTION` env to SU launch
  - `tools/autorun_inspector_plugin.rb` — already exists, needs trigger
    wiring
  - `scripts/smoke/smoke_skp_export.py` gate F — write the inspector
    control file before SU launch
- Validation: smoke run produces `inspect_report.json` in out_dir;
  G2 transitions from SKIP → PASS with structural counts
- Risk: SU session adds inspector cost (~1-2 s); negligible

## ✅ Cycle 7 done (2026-05-07) — branch ready, PR pending

`feature/micro-truth-expand-planta-74-cycle7` (commit `d5ce23d`,
pushed). 4 rooms now scored, all 1.0:

- SALA DE ESTAR (unchanged), SUITE 02, BANHO 02, COZINHA
- `tests/test_micro_truth_gate.py::test_real_planta_74_micro_passes`
  now also asserts the four labels are present
- 20/20 micro_truth tests pass; 56/56 across 3 gate test files
- Compare URL:
  https://github.com/GFCDOTA/sketchup-mcp/compare/develop...feature/micro-truth-expand-planta-74-cycle7

Open issue surfaced (deferred):
- COZINHA's only detected adjacency is SUITE 02 (architecturally
  implausible). Restore `expected_adjacent_labels=["A.S."]` once
  the room-context classifier reaches cozinha — likely via Cycle 6.
- SUITE 01 polygon is 69.91 m² (oversized) — diagnostic landed in
  `docs/suite01-polygon-leakage-investigation` branch with FP-012
  + 3 fix paths.

## ✅ SUITE 01 diagnostic done (2026-05-07) — fix is the next ROI

`docs/suite01-polygon-leakage-investigation` (commit `1863abd`).
- Documents FP-012 (convex-hull room clip leaks watershed into
  exterior). Pure documentation per CLAUDE.md §1.
- See `docs/diagnostics/2026-05-07_planta_74_suite01_polygon_leakage.md`
  for symptom + root cause + 3 candidate fix paths.
- Recommended next: spike Option A (alpha-shape via
  `shapely.concave_hull`) behind `--use-concave-hull` flag,
  default off → `feature/concave-hull-room-clip-spike`.

## ✅ Cycle 8 done (2026-05-07) — branch ready, PR pending

`feature/concave-hull-room-clip-spike` (commit `39bfb99`, pushed).
- `_build_interior_mask()` extracted; `--use-concave-hull` flag
  + `--concave-hull-ratio` (default 0.3) added.
- Default OFF → byte-identical behavior on existing baseline.
- Empirical: SUITE 01 = 69.91 → 18.61 m² at ratio 0.30; sum 11
  rooms = 182 → 83 m². ratio=1.0 reproduces convex baseline.
- 4 new unit tests on synthetic L-shape; 519/519 in-scope tests
  still pass (zero regression).
- Diagnostic artifacts: `docs/diagnostics/2026-05-07_planta_74_fp012_spike_results.md`
  + 2 PNG previews (ratio 0.30 + 0.55).
- Compare URL:
  https://github.com/GFCDOTA/sketchup-mcp/compare/develop...feature/concave-hull-room-clip-spike

## P1 — Cycle 8b: promote concave-hull to default

After Cycle 8 lands, open `feature/concave-hull-promote-default`:
- Pick the production ratio (recommend 0.55 for minimum disruption,
  0.30 for closest-to-truth result; sweep table in
  `docs/diagnostics/2026-05-07_planta_74_fp012_spike_results.md`)
- Flip flag default to True (or remove flag entirely)
- Regenerate `tests/baselines/planta_74.json` with new room counts
  / area distributions
- Recalibrate `ground_truth/planta_74_micro.json` ranges (or
  remove specific assertions that no longer hold)
- Regenerate `docs/preview/example_top.png`
- Update CLAUDE.md §10 known-baseline note
- File LL-XXX in `docs/learning/lessons_learned.md`
- Risk: medium. This PR INTENTIONALLY changes baseline numbers,
  needs careful diff review.
- Validation:
  - default-off path → existing 56/56 gate tests still pass
  - flag-on rebuild on planta_74 → SUITE 01 < 50 m² (target ~30)
  - render top preview with flag-on, save in
    `docs/diagnostics/<date>_planta_74_concave_hull_spike.png`
  - micro_truth_gate (with the new c3) → score still 1.0 across 4 rooms
- Risk: medium. shapely 2.0 `concave_hull` accepts a `ratio` between
  0 (most concave) and 1 (convex hull). Wrong ratio could shrink
  the hull *inside* the building. Mitigation: ratio sweep on
  planta_74 logged in PR description; only one chosen value lands.

## ✅ Cycle 9 done (2026-05-07) — branch ready, PR pending

`feature/rubocop-sketchup-ci` (commit `83e175d`, pushed). Pure
infrastructure bootstrap of Ruby lint for `tools/*.rb`:
- `Gemfile.lint` (new, name avoids implying full Ruby application)
- `.rubocop.yml` (new) — TargetRubyVersion 3.2, only Lint +
  Security cops on, all cosmetic categories disabled
- `.github/workflows/rubocop.yml` (new) — paths-filtered to fire
  only when a Ruby file or the lint config itself changes; PR +
  push to main/develop, 5-min timeout, `--format github`
- ZERO Ruby code touched. ZERO Python touched. ZERO test touched.
- rubocop-sketchup gem deferred to a follow-up (needs per-file
  annotations for our autorun-plugin pattern).
- Compare URL:
  https://github.com/GFCDOTA/sketchup-mcp/compare/develop...feature/rubocop-sketchup-ci

Expected first-CI behaviour: may surface real Lint violations on
`tools/*.rb`. Per FP-010, do NOT auto-correct in the same PR;
open `feature/rubocop-cleanup-tools` to address them in a
review-friendly diff.

## P2 — Cycle 9: GitHub Action wiring all 4 gates per PR

**Goal**: every PR runs Plan Truth + Micro Truth + Coherence Audit
strict + Smoke `--inspect-strict`. Block on failure.
- Evidence: each gate works in isolation; not yet tied together in CI
- Touchpoints:
  - `.github/workflows/quality_gates.yml` (new)
  - Reuse existing fixture data from `runs/post_merge_*`
- Validation: PR with intentional regression fails CI before merge
- Risk: SU dependency in CI is heavy; may need to skip the SU step
  in the CI run and only validate the JSON consumers

## P3 — Cycle 10+ (future, not soon)

- Multi-PDF corpus (need 5+ different floor plans to break the
  planta_74-specific tunings)
- DL wall oracle (CubiCasa5K) only after multi-PDF corpus exists
- Web upload UI (PDF in → SKP out) — needs product decision
- C API SKP I/O (defer indefinitely; current Ruby flow works)
