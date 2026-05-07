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

## P0 — Four PR-less branches ready (PR bodies under .ai_bridge/pr_bodies/)

User opens PRs manually (memory rule `feedback_pr_manual_preferido.md`).

| Branch | Body file | Compare URL |
|---|---|---|
| `docs/non-stop-autonomy-rule` | `PR_BODY_non_stop_autonomy_rule.md` | https://github.com/GFCDOTA/sketchup-mcp/compare/develop...docs/non-stop-autonomy-rule |
| `feature/micro-truth-expand-planta-74-cycle7` | `PR_BODY_cycle7_micro_truth_expand.md` | https://github.com/GFCDOTA/sketchup-mcp/compare/develop...feature/micro-truth-expand-planta-74-cycle7 |
| `docs/ai-bridge-scaffolding-clean` | `PR_BODY_ai_bridge_scaffolding_clean.md` | https://github.com/GFCDOTA/sketchup-mcp/compare/develop...docs/ai-bridge-scaffolding-clean |
| `docs/suite01-polygon-leakage-investigation` | `PR_BODY_suite01_polygon_diagnostic.md` | https://github.com/GFCDOTA/sketchup-mcp/compare/develop...docs/suite01-polygon-leakage-investigation |

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

## P1 — Cycle 8: SUITE 01 fix spike (Option A from FP-012)

**Goal**: prove Option A reduces SUITE 01 from ~70 m² toward
~25-30 m² without touching the default code path. User stated
preference (2026-05-07): geometric quality > infrastructure (RuboCop).
- Touchpoints:
  - `tools/rooms_from_seeds.py:152-219` — add `use_concave_hull`
    parameter; new branch uses `shapely.concave_hull(MultiPoint, ratio)`
    with a tunable `ratio` (default 0.3) instead of `cv2.convexHull`
  - `tools/rooms_from_seeds.py:259+` (CLI) — add `--use-concave-hull`
    flag default off
  - new test `tests/test_rooms_from_seeds_concave_hull.py` — exercise
    the new branch on a synthetic L-shaped envelope
  - DO NOT update `tests/baselines/planta_74.json` in this PR
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

## Cycle 8 (renamed → Cycle 9): RuboCop SketchUp lint CI

## P2 — Cycle 8: RuboCop SketchUp lint CI

**Goal**: enforce Extension Warehouse compliance + catch dumb Ruby
errors at PR time.
- Evidence: Stage 1.6 plan in PR #49 stack note lists this
- Touchpoints:
  - `Gemfile.dev` (new) — add `rubocop-sketchup`
  - `.rubocop.yml` (new) — `inherit_from: rubocop-sketchup`
  - `.github/workflows/rubocop.yml` (new) — runs on PR
- Validation: PR #N triggers RuboCop check; shows green or specific
  violation
- Risk: initial run may surface dozens of violations; ship with
  `--auto-correct-safe` first commit + manual fixes second

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
