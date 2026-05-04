# Operational Roadmap

> Where the project is going operationally (CI, agents, perf, cache,
> tooling). Complements `docs/ROADMAP.md` (the algorithmic roadmap
> from 2026-04-21).
>
> The `/afk-maintain` slash command picks the safest task from "Now"
> each cycle. Items move down (Now → Next → Later) as they complete.

## Now (in flight or next up)

### Tooling / SketchUp gates
- [ ] **`validate/sketchup-2026-export`** — Run the smoke harness
  end-to-end against `runs/vector/consensus_model.json`, document the
  result in `docs/validation/sketchup_2026_validation.md`. Now
  unblocked: `scripts/smoke/smoke_skp_export.py` shipped via PR
  `tooling/sketchup-smoke-gates`.

### Performance
- [ ] **`perf/capture-real-baseline`** — Run `bench_pipeline.py`
  against planta_74 with `--runs 3 --warmup 1`. Write
  `docs/performance/current_perf_baseline.md`.

### Cache (infra only)
- [ ] **`perf/cache-infrastructure`** — `packages/cache/` with
  `cache_key()`, `cache_get()`, `cache_set()`, `cache_path()`. Tests
  for determinism + atomic write. **No callers in pipeline yet.**

### Auditor v2
- [ ] **`agents/repo-auditor-v2`** — Add NEW/RESOLVED/PERSISTING
  delta tracking to `agents/auditor/run_audit.py`. Read previous
  report from `reports/repo_audit_<timestamp>.md` if any exists.

## Next (after Now)

- [ ] **`perf/skip-unchanged-skp`** — Promote the cache marker from
  `smoke_skp_export.py` to a reusable helper in `packages/cache/`.
- [ ] **`perf/cache-raster-stage`** — First real cache callsite.
  Implement only after baseline confirms raster is the bottleneck.
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
9. PR (this) `tooling: add SketchUp smoke gates harness`
