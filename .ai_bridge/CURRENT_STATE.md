# Current State — 2026-05-07 05:00 UTC

> Per-session snapshot. Update at start of each long session and
> overwrite (not append). For history → `HANDOFF.md` (per-session
> log) or `docs/ops/`.

## Branch

- Working: `docs/ai-bridge-scaffolding-clean` (this update)
- Sync target: `develop` (sha `fad28d9`)
- Pending PR (waiting for merge): `feature/smoke-promotes-inspector-v2-gate` (gate G2, commit `2417a20`) → PR #52
- **Nine pushed branches with PR bodies ready** (under `.ai_bridge/pr_bodies/`):
  - `docs/non-stop-autonomy-rule` — CLAUDE.md §17 DONE IS NOT STOP rule.
    Compare: https://github.com/GFCDOTA/sketchup-mcp/compare/develop...docs/non-stop-autonomy-rule
  - `feature/micro-truth-expand-planta-74-cycle7` — Cycle 7 ground
    truth expansion (4 rooms now scored 1.0).
    Compare: https://github.com/GFCDOTA/sketchup-mcp/compare/develop...feature/micro-truth-expand-planta-74-cycle7
  - `docs/ai-bridge-scaffolding-clean` — clean replacement of
    `feature/ai-bridge-scaffolding` (cherry-picked off develop).
    Compare: https://github.com/GFCDOTA/sketchup-mcp/compare/develop...docs/ai-bridge-scaffolding-clean
  - `docs/suite01-polygon-leakage-investigation` — diagnostic for
    SUITE 01 oversized polygon (FP-012). Pure docs.
    Compare: https://github.com/GFCDOTA/sketchup-mcp/compare/develop...docs/suite01-polygon-leakage-investigation
  - `feature/concave-hull-room-clip-spike` — Cycle 8 spike
    (FP-012 Option A behind default-off flag).
    Compare: https://github.com/GFCDOTA/sketchup-mcp/compare/develop...feature/concave-hull-room-clip-spike
  - `feature/rubocop-sketchup-ci` — Cycle 9 (RuboCop lint workflow
    bootstrap, infra-only).
    Compare: https://github.com/GFCDOTA/sketchup-mcp/compare/develop...feature/rubocop-sketchup-ci
  - `feature/quality-gates-ci-workflow` — Cycle 10 (Plan/Coherence/
    Micro strict CI workflow, infra-only).
    Compare: https://github.com/GFCDOTA/sketchup-mcp/compare/develop...feature/quality-gates-ci-workflow
  - `docs/readme-overview-stage15-tools` — Cycle 11 (README + OVERVIEW
    catch-up to Stage 1.5 tools, pure docs).
    Compare: https://github.com/GFCDOTA/sketchup-mcp/compare/develop...docs/readme-overview-stage15-tools
  - `feature/ground-truth-v1-fidelity-engine` — Cycle 12 (whole-plant
    golden truth + fidelity engine + 21 unit tests + 2 docs).
    Compare: https://github.com/GFCDOTA/sketchup-mcp/compare/develop...feature/ground-truth-v1-fidelity-engine

Total: **9 PR-able branches** ready (PR bodies all under
`.ai_bridge/pr_bodies/`).

- **Branch to delete** post-merge of `docs/ai-bridge-scaffolding-clean`:
  `feature/ai-bridge-scaffolding` (contaminated with PR #52 commit).

## Last objective

Cycle 10 — Quality Gates CI workflow on
`feature/quality-gates-ci-workflow`. Builds the planta_74 5-stage
pipeline + runs `coherence_audit --strict` and `micro_truth_gate
--strict`. Hard merge blocker on regression. Earlier in this
session chain: Cycles 7, 8, 9 + PR org wave + FP-012 diagnostic +
DONE-IS-NOT-STOP rule + validation cycle.

Earlier in this session: validation of the 5-PR queue (PRs #44–#48)
on `develop` + saving the "DONE IS NOT STOP" rule + Cycle 7
(planta_74_micro 1 → 4 rooms).

Previous session was Stage 1.6: inspector v2 schema 1.0 (PR #49)
→ autonomous-rules in CLAUDE.md (PR #50) → hygiene cycle (PR #51) →
smoke gate G2 consumer (PR #52, in-flight).

## What's in `develop` right now

- 5 PRs from May 6 (PRs #44-#48): caminho A door leaves + caminho B
  room-context classifier + Stage 1 coherence audit + Plan Truth
  Gate + Micro Truth Gate.
- 3 PRs from May 7 (PRs #49-#51): inspector v2 schema 1.0 +
  CLAUDE.md autonomy rules (§14/§15/§16) + first hygiene cycle.

Plus 1 PR in flight: #52 (smoke gate G2, opt-in `--inspect-strict`).

## Three trincos status

- ✅ PDF → SKP determinístico
- ✅ Incerteza auditável
- ✅ Verdade externa mínima (1 cômodo)

## Open problems

| Problem | Severity | Path forward |
|---|---|---|
| Inspector autorun plugin not wired into smoke gate F | Medium | Cycle 6 (planned next) |
| Only 1 room in micro ground truth | Low | Cycle 7 expand to BANHO 02, COZINHA, SUITE 02 |
| RuboCop SketchUp lint not in CI | Low | Cycle 8 |
| Pre-existing `test_f1_dashboard` failure | Documented | Out of scope until dashboard rewrite |

## Active tools

| Tool | Status |
|---|---|
| `tools/coherence_audit.py` | ✓ stable, schema 1.0 |
| `tools/micro_truth_gate.py` | ✓ stable, schema 1.0 |
| `tools/skp_inspection_report.py` | ✓ stable, schema 1.0 |
| `tools/classify_openings_by_room_context.py` | ✓ stable + Stage 1 contract |
| `tools/inspect_walls_report.rb` | ✓ v2 schema (Stage 1.6 PR #49) |
| `tests/test_planta_74_truth_gate.py` | ✓ 15 assertions locked |
| `scripts/smoke/smoke_skp_export.py` | ✓ A-G + G2 (PR #52 pending) + H |

## Tests

Re-validated 2026-05-07 04:00 UTC on `develop` (sha `fad28d9`):

- Plan Truth Gate: **15/15 PASS** in 2.03s
- Full suite: 520 passed / 8 skipped / 17 failed (16 raster pre-existing
  per CLAUDE.md §10 + 1 `test_f1_dashboard` pre-existing).
- 138 tests of files touched by PRs #44–#48 all pass.
- Gate G2 11 tests on PR #52 branch (not re-run this session).
