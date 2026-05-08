# docs(diagnostic): SUITE 01 polygon leakage on planta_74 (FP-012)

**Branch**: `docs/suite01-polygon-leakage-investigation` → `develop`
**Commit**: `1863abd`
**Compare URL**: https://github.com/GFCDOTA/sketchup-mcp/compare/develop...docs/suite01-polygon-leakage-investigation

## Summary

- Documents a confirmed geometry bug surfaced during Cycle 7
  (PR `feature/micro-truth-expand-planta-74-cycle7`):
  `SUITE 01` polygon area on `planta_74` = **69.91 m²** in a
  nominal **74 m²** apartment. Sum of all 11 rooms ≈ **182 m²**.
- Root cause located: `cv2.convexHull()` in
  `tools/rooms_from_seeds.py:163-169` over-encloses non-convex
  building footprints, so the watershed assigns the unwalled
  exterior strip to whichever seed is nearest. SUITE 01's seed
  `(434, 610)` is the nearest to that strip → it absorbs ~45 m²
  of exterior area.
- Documentation only. No algorithm change. CLAUDE.md §1 marks
  geometry / topology surfaces as hard-rule guarded — any fix
  must come in a separate dedicated PR with explicit approval.

## What changed

- `docs/diagnostics/2026-05-07_planta_74_suite01_polygon_leakage.md`
  — full diagnostic (symptom, downstream impact, root cause,
  three candidate fix paths, reproduction steps)
- `docs/diagnostics/2026-05-07_planta_74_suite01_polygon_leakage.png`
  — top-down preview rendered today, shows the leakage visually
- `docs/learning/failure_patterns.md` — adds **FP-012** cross-
  referencing the diagnostic; recommends Option A spike behind a
  feature flag (`--use-concave-hull` default off)

## What did NOT change

- `tools/rooms_from_seeds.py` (untouched — that's the §1-guarded
  surface)
- No schema, no thresholds, no Ruby/SU exporter, no test, no CI
- No other source file

## Validation

- N/A: pure documentation / diagnostic. No code path executes
  this content.
- Visual diagnostic re-verified by re-rendering today's preview
  (top mode) against the current `develop` HEAD before saving.
- Numeric measurements cross-checked from two independent
  consensus runs:
  - `runs/feature_room_context_2026_05_06/...` (canonical baseline)
  - `runs/validation_2026-05-07/c3_classified.json` (fresh build)
- `shapely` overlap check confirms SUITE 01 polygon does NOT
  overlap any other room polygon — it claims **unlabelled empty
  area**, which is the diagnostic signature.

## Risks

- None for the codebase. Risk is meta: future maintainers might
  attempt to "fix" SUITE 01 by tightening a generic threshold
  without addressing the convex-hull root cause. The FP-012
  rule in `failure_patterns.md` warns explicitly against silent
  shrink-to-pass workarounds.

## Rollback

```bash
git push origin --delete docs/suite01-polygon-leakage-investigation
# post-merge:
git revert <merge-sha>
```

## Next steps

- Spike Option **A** (alpha-shape / `shapely.concave_hull`) on a
  separate `feature/concave-hull-room-clip` branch behind a
  `--use-concave-hull` flag default off.
- Re-run plan/micro/Ruby gates with the flag enabled and inspect
  whether SUITE 01 area drops near 25–30 m².
- Promote the flag default to `on` only in a single dedicated PR
  that updates `tests/baselines/planta_74.json` and explains
  every count delta.
- File an `LL-XXX` in `docs/learning/lessons_learned.md` after the
  fix lands.
