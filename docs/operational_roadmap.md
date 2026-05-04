# Operational Roadmap

> Where the project is going operationally (CI, agents, perf, cache,
> tooling). Complements `docs/ROADMAP.md` (the algorithmic roadmap
> from 2026-04-21).
>
> The `/afk-maintain` slash command picks the safest task from "Now"
> each cycle. Items move down (Now → Next → Later) as they complete.

## Now (in flight or next up)

### Cache (infra only)
- [ ] **`perf/cache-infrastructure`** — `packages/cache/` with
  `cache_key()`, `cache_get()`, `cache_set()`, `cache_path()`. Tests
  for determinism + atomic write. **No callers in pipeline yet.**

## Next (after Now)

- [ ] **`perf/cache-raster-stage`** — First real cache callsite.
  Now LOWER priority: the baseline confirmed SketchUp is the
  bottleneck (91 % of wall-clock), not raster. Reconsider after
  smoke harness usage shows whether `rooms_from_seeds` (495 ms)
  becomes a bottleneck during dev iteration.
- [ ] **`chore/ruff-f821-cleanup`** — Add
  `from __future__ import annotations` to 3 oracle scripts. Zeroes 5 F821s.
- [ ] **`refactor/render-scripts-compat`** — Move `render_*.py` from
  root to `scripts/render/` with compat wrappers.

## Later

- [ ] **`refactor/move-tools-to-packages`** — Split `tools/` per
  category. See `docs/architecture/target_repo_architecture.md`.
- [ ] **`refactor/extract-apps`** — Extract apps to `apps/`.
- [ ] **`refactor/extract-packages`** — Move libs to `packages/`.
- [ ] **`feature/window-detector`** — Detect windows in
  `tools/extract_openings_vector.py`.
- [ ] **`feature/skp-carve-openings`** — Modify `consume_consensus.rb`
  to actually carve openings. Touches Ruby.
- [ ] **`chore/runs-archive`** — Move old runs to `runs/_archive/`.
- [ ] **`chore/patches-applied-archive`** — Move applied patches.
- [ ] **`agents/repo-auditor-workflow`** — Cron weekly audit upload.

## Human decision required (do NOT auto-execute)

- [ ] **`fix/strokes-gate-200`** — `classify/service.py:160` — algorithm.
- [ ] **`feature/cubicasa-oracle`** — `patches/archive/08-*` — torch dep.
- [ ] **`feature/afplan-extractor`** — `patches/archive/09-*` — alt extractor.
- [ ] **`feature/lsd-reconnect`** — `patches/archive/07-*` — scipy.
- [ ] **`schema/v3-changes`** — schema migration plan needed.
- [ ] **`pipeline/threshold-changes`** — empirical sweep mandatory.
- [ ] **`runs/historical-cleanup`** — beyond archive.
- [ ] **`patches/historical-cleanup`** — `archive/07-09` HIGH risk.

## Process

1. `/repo-audit` to see state.
2. Pick smallest item from "Now" not blocking another in-flight branch.
3. If "Now" empty, pick from "Next".
4. NEVER touch "Human decision required" without explicit approval.
5. Always branch from `develop`. PR to `develop`. Never to `main` direct.
6. Move items between buckets as state changes.

## Recently shipped

1. PR #1 `chore: add repo hardening baseline and CI`
2. PR #2 `fix(ci): use actions/setup-python before setup-uv@v3`
3. PR #3 `docs: define target architecture and specialist agents`
4. PR #4 `perf: add pipeline benchmark baseline script`
5. PR #5 `agents: add read-only repo auditor`
6. PR #6 `docs: define content-addressed cache rollout plan`
7. PR #7 `agents: add operational memory and guardrails`
8. PR #8 `Promote develop to main` (initial promotion under develop-first)
9. PR #9 `tooling: add SketchUp smoke gates harness`
10. PR #10 `validate: SketchUp 2026 end-to-end smoke run`
11. PR #11 `Promote develop to main` (drains PRs #9 + #10)
12. PR #12 `perf: capture real pipeline baseline (+ bench fixes)`
13. PR #13 `Promote develop to main` (drains PR #12)
14. PR #14 `perf: skip SketchUp export when consensus is unchanged`
15. PR #15 `Promote develop to main` (drains PR #14)
16. PR #16 `agents: repo-auditor v2 with NEW/RESOLVED/PERSISTING delta`
17. PR #17 `Promote develop to main` (drains PR #16)
18. PR (this) `ci: run cheap SketchUp smoke gates without launching SketchUp`
