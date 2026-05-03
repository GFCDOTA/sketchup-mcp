# Decision Log

> Architectural and operational decisions, with date and rationale.
> Append-only. Each entry is `DL-NNN`.

## DL-001 — Two pipeline tracks (raster + vector) coexist

**Date:** 2026-04-21 (codified 2026-05-03)
**Decision:** Keep both raster (`extract/`/`classify/`/`topology/`)
and vector (`tools/build_vector_consensus.py` + friends) pipelines
in the repo simultaneously, rather than deprecating one.
**Rationale:** Raster is more general (works on scanned plans);
vector is much cleaner for vectorial PDFs (planta_74). Different
PDFs need different paths.
**Trade-off:** Maintenance cost of two paths. Mitigated by both
producing the same `consensus_model.json` schema.

## DL-002 — Develop-first git flow

**Date:** 2026-05-03
**Decision:** Switch from "PR direct to main" to "PR to develop, then
develop to main".
**Rationale:** Allow batching multiple validated features before
promoting to release. Reduce risk of CI breakage on main affecting
in-flight PRs.
**Implementation:** `docs/git_workflow.md`, `CLAUDE.md` §0.
**Hook enforcement:** `.claude/hooks/pre_bash_guard.py` blocks
`git push origin main` and direct commits on main/develop.

## DL-003 — Constitution lives in CLAUDE.md, not in chat

**Date:** 2026-05-03
**Decision:** Move all persistent rules from session prompts to
`CLAUDE.md` and `.claude/agents/*.md`.
**Rationale:** Context compaction can lose chat-only rules.
CLAUDE.md is reloaded automatically each session.
**Implementation:** `CLAUDE.md` rewritten as constitution; 9
specialist agents created in `.claude/agents/`; 6 slash commands
in `.claude/commands/`; defensive hook in `.claude/hooks/`.

## DL-004 — Specialist agents are read-only by default

**Date:** 2026-05-03
**Decision:** Only `docs-maintainer` and `ci-guardian` get write
permissions, both narrowly scoped (docs/, .github/workflows/ via
PR draft only). All other agents (auditor, geometry, openings,
sketchup, performance, validator, agent-coordinator) are read-only,
output reports under `reports/` and PR comments only.
**Rationale:** Avoid silent code changes. Make the human → agent
boundary visible.
**Implementation:** Each agent's `.claude/agents/<name>.md` file
has explicit allow/deny lists.

## DL-005 — SketchUp is the last gate

**Date:** 2026-05-03
**Decision:** Never invoke SU in tight loops. Cheap gates
(JSON validation, preview PNG, hash compare) come first.
**Rationale:** SU spawn costs 5-90s. Iterating on a fix shouldn't
require a coffee break.
**Implementation (planned):** `scripts/smoke/smoke_skp_export.py`
will enforce gates A→H. Tracked as `tooling/sketchup-smoke-gates`
in `docs/operational_roadmap.md`. The hash-based skip cache will
live in `runs/smoke/<run>/_skp_cache.json` once the script lands.

## DL-006 — Content-addressed cache for the pipeline

**Date:** 2026-05-03 (designed; not implemented)
**Decision:** When implementing pipeline cache, use SHA256 of
inputs + parameters + stage code as the cache key.
**Rationale:** Path-based cache breaks on rename/copy/edit-without-rename.
Content-based cache is correct by construction.
**Trade-off:** Hash cost (negligible for PDF < 50 MB).
**Implementation:** Specified in
`docs/performance/cache_design.md` and
`docs/performance/cache_keys.md`. Sequenced in
`docs/performance/cache_rollout_plan.md` (13 PRs, opt-in first).
**Status:** Documented only. PR 1 (infrastructure without callers)
to be opened in `perf/cache-infrastructure` branch.

## DL-007 — Ruff conservative selects, no autofix

**Date:** 2026-05-03
**Decision:** Configure ruff with `select = ["E", "F", "I"]` only.
No `--fix`, no `format`. Run as informational in CI
(`continue-on-error: true`) until baseline (144 violations) is
cleaned in dedicated PRs.
**Rationale:** Mass autofix produces unreviewable diffs. Cleanup
should be a deliberate, scoped activity.
**Implementation:** `pyproject.toml [tool.ruff]`, hooks block
`ruff --fix .` and `ruff format`.

## DL-008 — patches/archive/* are HIGH risk

**Date:** 2026-05-03
**Decision:** Never apply `patches/archive/07-*` (LSD reconnect),
`patches/archive/08-*` (CubiCasa DL), or `patches/archive/09-*`
(AFPlan). They introduce major dep chains and core algorithm
changes.
**Rationale:** Each was reviewed but never validated empirically.
Applying without a dedicated PR plan would be irresponsible.
**Implementation:** Documented in `CLAUDE.md` §11. Hook blocks
deletes/moves under `patches/archive/`.

## DL-009 — `runs/`, `patches/`, `docs/` are protected from deletion

**Date:** 2026-05-03
**Decision:** No mass deletes from these directories without
explicit user authorization.
**Rationale:** They contain historical baselines, diagnostics, and
WIP that aren't reproducible from code.
**Implementation:** `.gitignore` already ignores `runs/` content
(only specific .md files tracked). Hook blocks
`rm -rf {runs,patches,docs}` and PowerShell equivalent.

## DL-010 — One-PR-one-idea

**Date:** 2026-05-03
**Decision:** Never mix refactor + functional fix + performance
optimization in a single PR.
**Rationale:** Each kind of change has different review criteria
and rollback strategy. Mixing them makes diff impossible to
properly review.
**Implementation:** Codified in `CLAUDE.md` §1 rule #9 and in
`/prepare-pr` slash command.
