# ci(rubocop): add Ruby lint workflow for tools/*.rb (Cycle 9 spike)

**Branch**: `feature/rubocop-sketchup-ci` → `develop`
**Commit**: `83e175d`
**Compare URL**: https://github.com/GFCDOTA/sketchup-mcp/compare/develop...feature/rubocop-sketchup-ci

## Summary

- Bootstraps a RuboCop GitHub Action over the four Ruby files
  in `tools/`: `autorun_inspector_plugin.rb`, `consume_consensus.rb`,
  `inspect_walls_report.rb`, `su_boot.rb`.
- Pure infrastructure. No Ruby code is touched — this is the wiring
  that lets a future PR react to lint signal.
- Conservative scope per CLAUDE.md §4: only Lint cops enabled
  (parse errors, unreachable code, useless assignments, ambiguous
  operators). Layout / Style / Naming / Metrics disabled.
- `rubocop-sketchup` cop families (deprecations / requirements /
  performance / suggestions) deferred to a follow-up PR.

## What changed

- `Gemfile.lint` (new) — `rubocop ~> 1.65` in `:lint` group.
  Named `.lint` so the repo is not mistaken for a Ruby application
  (it is primarily Python).
- `.rubocop.yml` (new) — TargetRubyVersion 3.2 (matches SU 2026's
  bundled Ruby), Include `tools/**/*.rb`, exclude `.venv/ vendor/
  runs/ patches/archive/`. NewCops disabled so future rubocop
  releases do not surprise-fail the workflow. Lint + Security
  enabled, all cosmetic categories disabled.
- `.github/workflows/rubocop.yml` (new) — runs on PR + push to
  `main`/`develop`, paths-filtered to fire only when a Ruby file
  or the lint config itself changes. Uses `BUNDLE_GEMFILE=Gemfile.lint`
  + `bundle exec rubocop --format github` so violations annotate
  the PR diff inline.

## What did NOT change

- No Ruby code touched. No tests touched. No Python touched.
- No schema, no thresholds, no smoke gates, no consumer behaviour.
- Existing `.github/workflows/ci.yml` and `skp_fidelity_gate.yml`
  unchanged.

## Validation

- YAML files parse cleanly via pyyaml (both `.rubocop.yml` and the
  workflow).
- Workflow style consistent with existing `ci.yml` +
  `skp_fidelity_gate.yml` (unquoted `on:`, ubuntu-latest, 5-min
  timeout, paths filter).
- Local Ruby parse check skipped (no Ruby installed in the
  development env); CI is the first place rubocop actually runs
  against `tools/`. **Expect the first run to surface real Lint
  violations** — that is the whole point of the spike.

## Risks

- **First CI run may be RED with Lint violations.** That is by
  design — see them, then either accept-and-fix in a follow-up
  cleanup PR (per CLAUDE.md §4 "one PR = one idea") or, if a
  cop is genuinely too strict for our autorun-plugin pattern,
  scope it down in `.rubocop.yml`. Per FP-010, do **not**
  `--auto-correct` in the same PR.
- ruby/setup-ruby@v1 with `bundler-cache: true` should keep CI
  minutes near zero on subsequent runs.
- Workflow timeout 5 min — generous for a single-directory lint;
  fail-fast if rubocop hangs.

## Rollback

```bash
git push origin --delete feature/rubocop-sketchup-ci
# post-merge:
git revert <merge-sha>
```

## Next steps

After merge:

1. Watch the first CI run on a Ruby-touching PR. Capture
   violations to `docs/diagnostics/2026-MM-DD_rubocop_baseline.md`.
2. Open `feature/rubocop-cleanup-tools` to address violations
   in a single review-friendly PR. Use targeted cops or
   per-file `# rubocop:disable Lint/SomeCop` only where the
   pattern is intentional (e.g. autorun plugin's
   `Sketchup.add_observer` pattern that may trigger Lint
   warnings).
3. Open `feature/rubocop-sketchup-extras` to add the
   `rubocop-sketchup` gem and incrementally enable
   `SketchUp/Suggestions` + `SketchUp/Performance`. Skip
   `SketchUp/Requirements` (those expect a full extension
   manifest that this repo does not have).

## References

- `.ai_bridge/TODO_NEXT.md` — Cycle 9 (renamed from Cycle 8 RuboCop
  in the 2026-05-07 reshuffle that promoted FP-012 to P1 Cycle 8).
- `docs/learning/failure_patterns.md` — FP-010 (never deselect
  to mask a current-PR regression).
