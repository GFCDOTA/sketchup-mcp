# Failure Patterns

> Anti-patterns to never repeat. Each entry has a unique ID, a clear
> "do not" rule, and links to the lesson learned that would prevent
> recurrence.

## FP-001 — Opening SketchUp inside a tight dev loop

**Symptom:** 60-90s per loop iteration. Frustrating during debug.
Cache misses every time because each minor edit changes the consensus.

**Root cause:** No cheap gate before SU. No content-based cache.

**Rule:** Never invoke `tools.skp_from_consensus` in a loop. Use
`scripts/smoke/smoke_skp_export.py` which runs cheap gates first
and skips SU when consensus hash hasn't changed.

**See also:** `LL-001`, `LL-008`.

## FP-002 — Forgetting Pillow / matplotlib / scipy in pyproject deps

**Symptom:** PR passes locally on Windows, fails CI on ubuntu with
`ModuleNotFoundError`.

**Root cause:** Phantom transitive dependencies in the dev's local
venv. Especially common with `Pillow` (pulled by matplotlib),
`scipy` (pulled by scikit-image), `requests` (pulled by gh tooling).

**Rule:** When the pipeline imports a package, that package MUST be
in `[project].dependencies` in `pyproject.toml`. Reproduce CI
locally in a fresh venv before opening the PR.

**See also:** `LL-002`.

## FP-003 — Direct push to main

**Symptom:** main breaks; multiple in-flight PRs need to rebase;
CI is now red on the default branch.

**Root cause:** Fast iteration culture without develop branch.

**Rule:** All PRs go to `develop`. Only `develop → main` PRs touch
main. The hook `pre_bash_guard.py` blocks `git push origin main`.

**See also:** `LL-003`.

## FP-004 — `ruff --fix` over the whole repo

**Symptom:** Massive diff with mixed concerns (import order,
unused removals, style). Impossible to review.

**Root cause:** Treating ruff as an autoformatter instead of a linter.

**Rule:** Configure ruff with conservative selects (E, F, I) but
NEVER run `ruff --fix .` or `ruff format`. Cleanup is dedicated,
scoped PRs. The hook `pre_bash_guard.py` blocks repo-wide
autoformat commands.

**See also:** `LL-004`.

## FP-005 — Triplication of geometry in .skp

**Symptom:** Wall_dark1, wall_dark2 materials appear; 99 wall groups
for 33 walls; z-fighting on every wall. Diagnosed in
`docs/diagnostics/2026-05-02_planta_74_skp_inspection.md`.

**Root cause:** `consume_consensus.rb` was being executed multiple
times in the same SketchUp session without `model.entities.clear!`
between runs.

**Rule:** `consume_consensus.rb` always calls `reset_model()` at
the start. Never bypass this. The autorun plugin always closes SU
after a successful save (via `Sketchup.quit` in a 2s timer) so
state can't accumulate.

## FP-006 — Parapets covering walls ("rodapé branco")

**Symptom:** 1.10m colored band running along exterior walls,
covering them as if they were wallpaper.

**Root cause:** `tools/build_vector_consensus.py:_extract_building_outline`
emits soft_barriers from stroked outlines that often coincide with
the building exterior. The `_midpoint_inside_any?` filter only
checked the midpoint with tol_in=0.5, so parallel-offset peitoris
slipped through.

**Rule:** Use 3-pt sampling (p1, midpoint, p2) with tol_in=1.0 inch
in `_segment_overlaps_wall?`. Documented in commit `7fbd531`.
Future PRs that reduce tol_in or revert to single-point sampling
must justify empirically.

## FP-007 — Welcome dialog blocking SU2026 plugin firing

**Symptom:** SU spawns, exits with code 0 or 1 in seconds, no
plugin log written.

**Root cause:** SU2026 trial shows Welcome dialog when launched
without a positional .skp, blocking startup. The autorun plugin
never gets evaluated.

**Rule:** Always pass a positional .skp on the SU command line.
`skp_from_consensus.py` does this automatically: picks most recent
.skp in out_dir as bootstrap. If out_dir is empty, copy a template
from `C:\Program Files\SketchUp\SketchUp 2026\SketchUp\resources\en-US\Templates\`.

**See also:** `LL-009`.

## FP-008 — Mass branch deletion losing uncommitted work

**Symptom:** `git branch -D feat/svg-ingest` would have nuked 80
commits + 1 file with uncommitted changes in another worktree.

**Root cause:** Not checking worktree status before deletion.

**Rule:** Always `git worktree list` and `git -C <path> status`
before deleting any branch checked out in another worktree. Always
write a textual backup of branches to be deleted (name, SHA,
subject, unique commits) outside the repo.

**See also:** `LL-005`.

## FP-009 — Specialist agents granted write permission

**Symptom:** Hard to tell what the agent decided vs what the human
approved. Silent code changes.

**Root cause:** Conflating "find" and "fix" responsibilities.

**Rule:** Specialists are read-only over their scope by default.
Only `docs-maintainer` writes (narrowly, to docs/) and `ci-guardian`
proposes via PR drafts. All other findings are reports/PR comments.

**See also:** `LL-007`.

## FP-010 — Hidden CI deselects masking real regressions

**Symptom:** CI green but actually 3+ tests are silently skipped
because the deselect set is too broad.

**Root cause:** Adding tests to `--deselect` to "make CI green"
without documenting WHY each one is deselected.

**Rule:** Every test in the CI deselect set must be categorized
(HARD_EXTERNAL_DEPS or BASELINE_KNOWN_FAILURES) and listed in a
YAML comment in `.github/workflows/ci.yml` AND in
`docs/repo_hardening_plan.md`. Never deselect to mask a regression
introduced by the current PR.
