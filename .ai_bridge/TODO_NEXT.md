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

## P0 — Open PRs for in-flight branches (rule: never leave PR-less branches dangling)

**Open PR for `feature/ai-bridge-scaffolding`** — BLOCKED by stacking
- Status: branch is stacked on PR #52's gate G2 commit (`2417a20`), so a
  PR against `develop` would include gate G2 changes too — violates
  "one PR = one idea" (§4). Resolution options:
  1. Wait for PR #52 to merge into `develop`, then ai-bridge naturally
     becomes clean (preferred — minimal risk).
  2. Rebase ai-bridge onto `develop` and force-push, dropping the G2
     commit (allowed for feature branches; requires care).
  3. Cherry-pick the two .ai_bridge commits (`8b467ed` + `f26984e`)
     onto a new fresh branch off `develop` and open PR from there.
- Evidence: `git log develop..feature/ai-bridge-scaffolding` shows 3
  commits including `2417a20` (gate G2).
- Validation: chosen path produces a PR with only .ai_bridge/ files in diff.
- Risk: low (rebase / cherry-pick on a feature branch).

**Open PR for `docs/non-stop-autonomy-rule`** — CLAUDE.md §17
- Status: branch pushed 2026-05-07 04:00 UTC. Single commit `f60d99e`.
- Compare URL:
  https://github.com/GFCDOTA/sketchup-mcp/compare/develop...docs/non-stop-autonomy-rule
- Touchpoints: CLAUDE.md only (+83 lines, no source change)
- Validation: ruff/pytest N/A (markdown only); no schema, threshold,
  Ruby/SU change → §1/§2/§3 not invoked.
- Risk: none

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
- SUITE 01 polygon is 69.91 m² (oversized; absorbs neighbouring
  rooms). Likely contributing to BANHO 02's spurious adjacencies.
  File a separate bug to investigate `rooms_from_seeds` for SUITE 01.

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
