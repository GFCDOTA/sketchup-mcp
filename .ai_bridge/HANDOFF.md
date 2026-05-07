# Handoff — 2026-05-07 05:00 UTC

> Most recent session's exit state. Next session reads this FIRST
> after `CLAUDE.md`. Append-only is fine but the top entry must
> always be the latest.

## Status — Cycle 8 done (FP-012 spike landed behind flag)

Per the user's stated ROI preference (geometry > infra), the next
cycle attacked SUITE 01. Implemented Option A from FP-012 behind
a default-OFF flag (`--use-concave-hull` + `--concave-hull-ratio`).

- Branch: `feature/concave-hull-room-clip-spike`
- Commit: `39bfb99`
- Compare URL:
  https://github.com/GFCDOTA/sketchup-mcp/compare/develop...feature/concave-hull-room-clip-spike
- PR body: `.ai_bridge/pr_bodies/PR_BODY_concave_hull_spike.md`

Empirical proof on planta_74:
- SUITE 01 drops from **69.91 m² → 18.61 m²** at default ratio 0.30
- Sum 11 rooms drops from **182 m² → 83.3 m²** (closer to nominal 74 m²)
- ratio=1.0 reproduces convex baseline exactly (sanity)

Validation:
- `pytest test_planta_74_truth_gate + coherence + micro + new
  rooms_from_seeds_concave_hull` → **60/60 PASS** in 2.27s
- Full in-scope suite (excluding pre-existing raster + dashboard
  fails) → **519 passed, 8 skipped, 0 failed** — ZERO regression
- 4 new unit tests on synthetic L-shape envelope harden the
  default-off / concave-on / ratio=1.0 / empty-walls paths

Per CLAUDE.md §1 the flag stays default OFF. A future PR
(`feature/concave-hull-promote-default`) is needed to:
- pick the production ratio (recommend 0.55 for minimum disruption,
  0.30 for closest-to-truth result)
- regenerate `tests/baselines/planta_74.json`
- recalibrate `ground_truth/planta_74_micro.json` ranges
- regenerate `docs/preview/example_top.png`
- update CLAUDE.md §10

## Status — Cycle 4 (PR organization + SUITE 01 diagnostic)

After Cycle 7 (ground-truth expansion) landed, the loop selected the
next two highest-ROI items per the user's prompt: (a) prepare clean
PRs for all in-flight branches and (b) investigate the SUITE 01
oversized polygon surfaced during Cycle 7.

**(a) Three clean PRs ready** (compare URLs + bodies under
`.ai_bridge/pr_bodies/`):
- `docs/non-stop-autonomy-rule` — CLAUDE.md §17 (commit `f60d99e`)
- `feature/micro-truth-expand-planta-74-cycle7` — Cycle 7 GT (commit `d5ce23d`)
- `docs/ai-bridge-scaffolding-clean` — replaces stacked branch
  (cherry-picked off develop, commits `2250cdf` `1d57647` `146cab5`
  `a95176e` `13cdeb9` `d6ebdc7`). Original
  `feature/ai-bridge-scaffolding` should be deleted post-merge.

**(b) SUITE 01 diagnostic done** — branch
`docs/suite01-polygon-leakage-investigation`, commit `1863abd`,
documents the bug (sum of all rooms ≈ 182 m² in a 74 m² apartment)
+ root cause (`cv2.convexHull` over-encloses non-convex envelopes
in `tools/rooms_from_seeds.py:163-169`) + 3 candidate fix paths
(alpha-shape / soft-barrier outline / per-room area cap) +
visual artifact + FP-012 entry in `docs/learning/failure_patterns.md`.
Pure documentation — no algorithm change (CLAUDE.md §1 guards the
geometry surface, requires explicit human approval). Compare URL:
https://github.com/GFCDOTA/sketchup-mcp/compare/develop...docs/suite01-polygon-leakage-investigation

## Status — Validation Cycle (earlier in this session)

Validated on `develop` (sha `fad28d9`) that the 5-PR queue from
2026-05-06 (PRs #44–#48) is integrated and healthy. No code change in
this cycle — pure validation + memory/docs updates.

Critério final (all green):

- `pytest tests/test_planta_74_truth_gate.py` → **15/15 PASS** in 2.03s
- `tools.coherence_audit` → emitted `coherence_report.json` schema 1.0
  (openings=11, by_decision={clean:7, debug:4})
- `tools.micro_truth_gate` → emitted `micro_truth_report.json` schema 1.0;
  SALA DE ESTAR matched `r009`, all 5 checks PASS, **score=1.0**
- `scripts/smoke/smoke_skp_export.py` → verdict **PASS**, gates A–G PASS,
  `model.skp` = 70,762 bytes (in 68–74 KB band), walls=33/rooms=11/openings=11
- Test suite: 520 passed / 8 skipped / 17 failed; the 17 fails are all
  pre-existing (16 raster, gate `len(strokes) > 200` doc CLAUDE.md §10;
  + 1 `test_f1_dashboard`). 138 tests of the 5-PR-touched files all pass.

Artifacts under `runs/validation_2026-05-07/` (gitignored, local only).

### New behavioral rule added (cross-project memory)

User saved permanent rule **"DONE IS NOT STOP"**:
escopo concluído ≠ encerrar a sessão. Ao terminar uma task, registrar
em `.ai_bridge/`, atualizar `TODO_NEXT.md`, escolher próximo ROI e
continuar — só parar por bloqueio real. Saved as
`feedback_done_is_not_stop.md` in user MEMORY.md.
This handoff itself is the first application of the rule.

### Cycle 7 done (demonstration of the new rule)

After the validation cycle completed, the rule's "pick next ROI"
loop kicked in. Cycle 7 (`feature/micro-truth-expand-planta-74-cycle7`,
commit `d5ce23d`, single commit, pushed) added SUITE 02 / BANHO 02 /
COZINHA to `ground_truth/planta_74_micro.json`, raising external-truth
coverage from 1 → 4 rooms. Tightened
`tests/test_micro_truth_gate.py::test_real_planta_74_micro_passes` to
also assert all four labels are present. Validation:
- `pytest tests/test_micro_truth_gate.py` → 20/20 PASS
- `pytest tests/test_planta_74_truth_gate.py + coherence + micro` → 56/56
- `tools.micro_truth_gate` against canonical run → overall 1.0,
  4/4 rooms = 1.0
- `tools.micro_truth_gate` against today's c3 → overall 1.0, 4/4 rooms = 1.0

Compare URL: https://github.com/GFCDOTA/sketchup-mcp/compare/develop...feature/micro-truth-expand-planta-74-cycle7

## Status — Previous handoff (Stage 1.6 substantially landed)

- PR #49 inspector v2 schema 1.0 → MERGED (`4cb968f`)
- PR #50 CLAUDE.md autonomy rules (§14/§15/§16) → MERGED (`de8507d`)
- PR #51 hygiene cycle 1 → MERGED (`fad28d9`)
- PR #52 smoke gate G2 (`--inspect-strict`) → OPEN, awaiting merge

Plus session N-1: created `.ai_bridge/` scaffolding on a separate
branch (`feature/ai-bridge-scaffolding`) — still NOT merged as PR.

## Status — Older entries

- PR #49 inspector v2 schema 1.0 → MERGED (`4cb968f`)
- PR #50 CLAUDE.md autonomy rules (§14/§15/§16) → MERGED (`de8507d`)
- PR #51 hygiene cycle 1 → MERGED (`fad28d9`)
- PR #52 smoke gate G2 (`--inspect-strict`) → OPEN, awaiting merge

Plus this session: created `.ai_bridge/` scaffolding on a separate
branch (`feature/ai-bridge-scaffolding`).

## Branch / Commit

- Active branch: `feature/ai-bridge-scaffolding`
- `develop` HEAD: `fad28d9`
- Last own commit: (this PR's first commit when shipped)

## Files Changed

This session (.ai_bridge scaffolding):

- `.ai_bridge/README.md` — protocol overview
- `.ai_bridge/PROJECT_CONTEXT.md` — stable project context (mission,
  pipeline, paths, hard rules, canonical commands, baseline)
- `.ai_bridge/CURRENT_STATE.md` — branch + last objective + open problems
- `.ai_bridge/HANDOFF.md` — this file
- `.ai_bridge/TODO_NEXT.md` — ROI-ordered next-step queue
- `.ai_bridge/GPT_REQUESTS.md`, `GPT_RESPONSES.md`,
  `DECISIONS.md`, `LESSONS.md`,
  `QUESTIONS_FOR_NEXT_AGENT.md` — initial templates +
  current-state seed entries

CLAUDE.md updated with §17 (AI Bridge Protocol) reference pointing
to `.ai_bridge/PROJECT_CONTEXT.md` for full context.

## Validation

- No source code change → no pytest re-run needed for the .md/dir
  scaffolding itself. Validation = `git status` clean before
  committing + ruff is N/A (no .py files in this PR).
- Sister PR #52 (gate G2) was independently validated:
  - 11 G2 tests pass
  - 204 in-scope total
  - E2E smoke PASS, G2 SKIP graceful (no `inspect_report.json`
    in test out_dir, deferred per design)

## Open Problems

1. Inspector autorun plugin still NOT wired into smoke gate F.
   Result: G2 always SKIPs in current smoke flow. Needs Cycle 6.
2. Only 1 room in `ground_truth/planta_74_micro.json`. Needs Cycle 7
   to add BANHO 02 / COZINHA / SUITE 02.
3. PR #52 still open — needs merge before Cycle 6 can build on it.

## Next Best Actions (ROI order, after this validation cycle)

See `TODO_NEXT.md` for full queue. Updated top of stack:

1. **Open PR for `feature/ai-bridge-scaffolding`** (this branch) —
   per "Nunca deixar PR aberto" rule, branches with commits must land
   or be discarded. Branch ready, validated, no source changes.
2. **Open PR for `docs/non-stop-autonomy-rule`** (new branch this
   session) — adds the DONE IS NOT STOP rule as CLAUDE.md §18.
3. Merge PR #52 (gate G2) — Stage 1.6 already in CLAUDE.md §10
4. Cycle 6: wire `autorun_inspector_plugin.rb` into gate F
5. Cycle 7: expand `planta_74_micro.json` ground truth
6. Cycle 8: RuboCop SketchUp lint CI

## Risks

- The stack of consecutive PRs introduces transient mergeability
  gaps when GitHub recomputes after each merge — observed in
  PR #50/#51/#52 (resolved by waiting ~10s + reload). Not blocking,
  just slower than parallel merge.
- `.ai_bridge/` files MUST NOT contain credentials or large logs
  (per protocol §safety). Self-policing required.

## GPT/Agent Notes

- This session did NOT consult GPT (no real bifurcation). User
  approved direction explicitly via the autonomy prompt; per §14
  + memory rule "IAs decidem bifurcações", continued without
  asking.
- `feedback_ai_bridge_protocol.md` added to user MEMORY.md so
  this protocol is loaded into future Claude sessions
  automatically (cross-project memory).
