# feat(ground-truth): v1 schema + planta_74 expected_model + fidelity engine

**Branch**: `feature/ground-truth-v1-fidelity-engine` → `develop`
**Commits**: `c5aa0f6` (initial v1, 7 files +1734) + `dac81ed`
(adendo: `tools/fidelity/synth_from_expected.py` +
`tests/test_fidelity_engine_round_trip.py`, +323 lines, 4 new tests)
**Compare URL**: https://github.com/GFCDOTA/sketchup-mcp/compare/develop...feature/ground-truth-v1-fidelity-engine

> **Adendo (NAO PARE mode)**: round-trip guard tests added. Pattern:
> `expected → synthesize_observed(expected) → compare(...)` MUST
> return `global_fidelity == 1.0`. Catches engine bugs (not pipeline
> bugs). Surfaced + fixed two bugs in the synthesizer during
> authoring. 25/25 tests PASS now (4 round-trip + 21 existing).

## Summary

- Implements the **"minimum ground truth that already blocks real
  regression"** answer to the GT design prompt.
- Distinct from the three pre-existing layers
  (`tests/test_planta_74_truth_gate.py` self-pin,
  `tools/coherence_audit.py` uncertainty,
  `tools/micro_truth_gate.py` per-room subset) — fills the
  whole-plant **golden-truth** gap.
- Today's run on `develop` produces `global_fidelity=0.69` with
  **3 hard_fails that surface exactly the bugs we know about**
  (FP-012 SUITE 01 / SUITE 02 areas, adjacency f1 below 0.60).
  When `feature/concave-hull-room-clip-spike` and Cycle 6 land,
  all 3 should clear and global_fidelity should jump to ~0.95.
- 21 unit tests cover every scoring path; full gate suite stays
  green (77/77 across the four gate test files).

## What changed (additive only — 7 new files, 1734 lines)

- `ground_truth/schema/expected_model.schema.json` — JSON Schema
  draft 2020-12, version `1.0`. Required: `plan_id`, `unit`,
  `rooms[]`. Optional but covered: `global_bbox`, `expected_counts`
  with per-axis tolerance, `openings[]` (kind + connects),
  `adjacency[]` (a/b/via/kind), `manual_confidence` per row.
- `ground_truth/planta_74/expected_model.json` — 11 rooms, 8
  openings, 8 adjacency edges. Areas calibrated against detected
  output + architectural priors for a 74 m² Brazilian apartment
  with 2 suites + 1 lavabo.
- `tools/fidelity/compare_generated_to_expected.py` — engine v1.
  CLI emits `fidelity_report.json` (+ optional `fidelity_scorecard.md`).
  Default exit 0; `--strict` flips to non-zero on any hard_fail.
- `tools/fidelity/__init__.py` — package marker; intentionally
  thin to avoid runpy double-import warning.
- `tests/test_fidelity_engine.py` — 21 tests on synthetic 2-room
  fixtures.
- `docs/ground_truth_v1.md` — protocol + how-to-edit + how-to-read
  the report + today's snapshot.
- `docs/ground_truth_references.md` — public datasets survey
  (CubiCasa5K / FloorPlanCAD / Structured3D classified as
  benchmark-only; Google Images + 3D Warehouse explicitly
  rejected as ground truth).

## What did NOT change

- **No existing source code or test touched.** No bump on any
  pre-existing schema. No threshold change in
  classify/topology/openings/Ruby/SU. No CI workflow change.
- No mutation of inputs (verified by `test_compare_does_not_mutate_inputs`).

## Metrics in v1

- **counts**: rooms / openings / walls count_delta vs expected,
  per-axis tolerance
- **global_bbox_drift**: width/height % drift vs expected
- **room metrics** (per row): label match, polygon_closed,
  area_in_range, with severity gated by `manual_confidence`
  (high = hard_fail, medium/low = warning)
- **adjacency**: precision / recall / f1 via
  `openings.evidence.room_left/right`
- **opening_kind_distribution**: histogram diff (informational v1)

Aggregation:
- `room_score`, `count_score`, `adjacency_score`, `bbox_score`
  (each 0..1 or null when not applicable)
- `global_fidelity` = mean of available scores, **capped at 0.69
  whenever any hard_fail is present** (per the prompt's directive)
- `hard_fails[]` / `warnings[]` / `suggested_fixes[]` /
  `would_block_strict[]`

## Hard-fail vs warning policy

Hard-fail (caps global_fidelity, blocks `--strict`):
- `room_count_delta` outside tolerance
- `room_label_match_ratio < 0.7`
- `adjacency_f1 < 0.6` (when adjacency asserted)
- Any room with `manual_confidence: high` failing `area_in_range`
  or missing entirely

Warning (surfaces but does not cap):
- `opening_count_delta` outside tolerance
- `global_bbox` drift > tolerance %
- Low/medium-confidence room failing `area_in_range`
- `0.6 ≤ adjacency_f1 < 0.8`

## Validation

```
pytest tests/test_fidelity_engine.py            # 21/21 PASS in 0.54s
pytest test_planta_74_truth_gate.py             #
       test_micro_truth_gate.py                 #
       test_coherence_audit.py                  #
       test_fidelity_engine.py                  # 77/77 PASS in 6.48s

python -m tools.fidelity.compare_generated_to_expected \
       runs/validation_2026-05-07/c3_classified.json \
       --expected ground_truth/planta_74/expected_model.json \
       --out /tmp/fidelity_report.json
# [fidelity] global=0.69 hard_fails=3 warnings=0
# would-block: [SUITE 01 area, SUITE 02 area, adjacency_f1=0.42]
```

`jsonschema` also validates `expected_model.json` against the v1
schema (no draft conformance issues).

## Risks

- v1 ranges intentionally generous on first commit. A future
  detector retune may push areas in or out of range; in either
  case the gate fires and the procedure in
  `docs/ground_truth_v1.md` says: open a feature branch, edit the
  range, document the move in the PR body. **Never auto-relax**.
- Adjacency is materialized via `openings.evidence.room_left/right`.
  Open passages with no discrete opening object are a known v1
  gap (medium-confidence entries acknowledge this).
- v1 does NOT check polygon shape (only area + closure) — the
  rectangular SALA pretending to be triangular passes if its
  area lands in range. **Polygon IoU is v2.**

## Rollback

```bash
git push origin --delete feature/ground-truth-v1-fidelity-engine
# post-merge:
git revert <merge-sha>
```

## Next steps (post-merge)

1. Wire `tools.fidelity.compare_generated_to_expected --strict`
   into `.github/workflows/quality_gates.yml` (paired with the
   `feature/quality-gates-ci-workflow` PR; small addendum once
   both are on develop).
2. Promote `feature/concave-hull-room-clip-spike` to default
   (Cycle 8b). When that lands, the SUITE 01 / SUITE 02 hard_fails
   here clear automatically.
3. Author `expected_model.json` for one more plant once a second
   PDF lands in the corpus. Three plants is the floor for "metric
   distribution stable".
4. v2 candidates listed in `docs/ground_truth_v1.md`.

## References

- `docs/ground_truth_v1.md` — protocol
- `docs/ground_truth_references.md` — datasets survey
- `docs/diagnostics/2026-05-07_planta_74_suite01_polygon_leakage.md`
  — FP-012, the bug v1 currently surfaces
- `tests/test_fidelity_engine.py` — 21 unit tests
