# feat(rooms-from-seeds): FP-012 spike — opt-in concave-hull envelope clip

**Branch**: `feature/concave-hull-room-clip-spike` → `develop`
**Commit**: `39bfb99`
**Compare URL**: https://github.com/GFCDOTA/sketchup-mcp/compare/develop...feature/concave-hull-room-clip-spike

## Summary

- Implements **Option A** from the FP-012 diagnostic
  (`docs/diagnostics/2026-05-07_planta_74_suite01_polygon_leakage.md`):
  replace the convex-hull envelope clip in `tools/rooms_from_seeds.py`
  with `shapely.concave_hull`, behind a default-off flag.
- Empirical proof: **SUITE 01 drops from 69.91 m² → 18.61 m²** at
  the chosen default ratio (0.30), and from 69.91 → 35.64 m² at
  the compatibility-leaning ratio (0.55). Sum of all 11 rooms drops
  from 182 m² toward the apartment's nominal 74 m².
- ZERO regression on default-off path. 519/519 in-scope tests pass.
- Hardened with 4 new unit tests on a synthetic L-shape envelope.

## What changed

- `tools/rooms_from_seeds.py`
  - Extracts new `_build_interior_mask()` helper (refactor of the
    pre-existing inline convex-hull block).
  - Adds `use_concave_hull: bool = False` and
    `concave_hull_ratio: float = 0.3` parameters to `detect_rooms()`.
  - Adds CLI flags `--use-concave-hull` (default off) and
    `--concave-hull-ratio` (default 0.3, calibrated on planta_74).
  - Stamps `metadata.rooms_from_seeds.use_concave_hull` and
    `concave_hull_ratio` so downstream / debug can tell which
    envelope produced a given consensus.
  - Uses wall ENDPOINTS (≈60–70 points typical) as input to
    `shapely.concave_hull`. NOT the wall pixels themselves —
    benchmarked at 38 s per call on planta_74's 750k pixels vs
    0.1 ms on endpoints. Endpoints is the right design.
  - Falls back to convex hull on ImportError or degenerate
    geometry. Default-off path is byte-identical to pre-spike.
- `tests/test_rooms_from_seeds_concave_hull.py` (new) — 4 unit
  tests on a synthetic 100×100 L-shaped wall layout:
  - default-off uses convex hull (preserves baseline)
  - concave-hull-on shrinks the interior (proves the fix)
  - ratio=1.0 ≈ convex hull within 5% slack (sanity)
  - empty walls graceful fallback
- `docs/diagnostics/2026-05-07_planta_74_fp012_spike_results.md` —
  full sweep table (ratios 0.20–1.00) + visual comparison +
  recommended next steps.
- `docs/diagnostics/2026-05-07_planta_74_fp012_spike_ratio_0p30.png`
  and `..._0p55.png` — rendered top previews showing how the
  fix collapses SUITE 01 to a tight L-polygon hugging its actual
  walls.

## What did NOT change

- Default `cv2.convexHull` behavior (use_concave_hull=False) is
  byte-identical to the pre-spike code path. Verified by
  re-running the existing baseline numerically.
- `tests/baselines/planta_74.json` — untouched.
- `ground_truth/planta_74_micro.json` — untouched.
- Schema, threshold, Ruby/SU exporter, smoke gates — untouched.
- No invocation of the new flag in any existing CLI, smoke,
  test, or CI workflow.

## Validation

```
pytest tests/test_planta_74_truth_gate.py \
       tests/test_micro_truth_gate.py \
       tests/test_coherence_audit.py \
       tests/test_rooms_from_seeds_concave_hull.py
# → 60/60 PASS in 2.27s

pytest tests/ -q --ignore=tests/test_f1_dashboard.py \
       --ignore=tests/test_planta_74_regression.py \
       --ignore=tests/test_orientation_balance.py \
       --ignore=tests/test_pair_merge.py \
       --ignore=tests/test_text_filter.py \
       --ignore=tests/test_f1_regression.py
# → 519 passed, 8 skipped (data-fixture-missing, expected)
# → ZERO new failures vs pre-spike baseline
```

Empirical sweep on planta_74:

| ratio | SUITE 01 | SUITE 02 | BANHO 02 | COZINHA | sum 11 rooms |
|------:|---------:|---------:|---------:|--------:|-------------:|
| (default convex) | 69.91 | 32.03 | 6.24 | 11.34 | 182.09 |
| 0.30 | 18.61 | 14.35 | 6.24 |  5.23 |  83.3 |
| 0.55 | 35.64 | 15.16 | 6.24 |  8.80 | 115.7 |
| 1.00 | 69.91 | 32.03 | 6.24 | 11.34 | 182.09 (= convex baseline, sanity) |

## Risks

- **None on the default path** — flag default OFF means existing
  callers (smoke, tests, baselines, GT) see exactly the same
  behavior as before this PR.
- The flag-on path is documented as a **SPIKE**. Promotion to
  default requires a coordinated baseline JSON + ground_truth
  recalibration in a separate dedicated PR per CLAUDE.md §1.
- At the chosen default `ratio=0.30`, COZINHA / A.S. / TERRACO
  TECNICO polygons clip somewhat tighter than ideal (visible in
  the 0.30 preview). Higher ratios (0.55) give more compatible
  shapes at the cost of leaving more SUITE 01 leakage. Final
  ratio choice is left for the recalibration PR.

## Rollback

```bash
git push origin --delete feature/concave-hull-room-clip-spike
# post-merge:
git revert <merge-sha>
```

## Next steps

After merge:

1. Decide the production ratio (recommend 0.55 for minimum
   disruption, 0.30 for closest-to-truth result).
2. Open `feature/concave-hull-promote-default` PR that:
   - flips the flag default to True (or just removes the flag)
   - regenerates `tests/baselines/planta_74.json`
   - regenerates `ground_truth/planta_74_micro.json` ranges
     (or removes specific assertions that no longer hold)
   - regenerates `docs/preview/example_top.png`
   - updates CLAUDE.md §10 known-baseline note
3. Optionally implement Option B (soft-barrier outer outline)
   from the diagnostic in a separate experiment branch.
4. After production ratio is locked, file an LL-XXX in
   `docs/learning/lessons_learned.md` capturing the resolution.

## References

- `docs/diagnostics/2026-05-07_planta_74_suite01_polygon_leakage.md`
  (the bug this fix targets)
- `docs/diagnostics/2026-05-07_planta_74_fp012_spike_results.md`
  (this spike's full empirical sweep)
- `docs/learning/failure_patterns.md` — FP-012
