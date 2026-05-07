# Current State — 2026-05-07 04:00 UTC

> Per-session snapshot. Update at start of each long session and
> overwrite (not append). For history → `HANDOFF.md` (per-session
> log) or `docs/ops/`.

## Branch

- Working: `feature/ai-bridge-scaffolding` (this session updated
  HANDOFF + CURRENT_STATE + TODO_NEXT with validation cycle)
- Sync target: `develop` (sha `fad28d9`)
- Pending PR (waiting for merge): `feature/smoke-promotes-inspector-v2-gate` (gate G2, commit `2417a20`) → PR #52
- **New branch this session**: `docs/non-stop-autonomy-rule` —
  CLAUDE.md §18 added with DONE IS NOT STOP rule.

## Last objective

Validation cycle confirming the 5-PR queue (PRs #44–#48) on `develop` is
healthy + saving the new "DONE IS NOT STOP" behavioral rule into
cross-project memory and CLAUDE.md. Critério final all green
(see `HANDOFF.md` top entry).

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
