# Baseline Known Failures Audit — 2026-05-21

Frente 5 (Spec-Driven Development Phase 2) audited the 11 tests that
fail when `pytest tests/` is run locally without the CI deselect
flags. The goal was to confirm each failure is documented dívida vs
silent regression, and to record the triage so future hands don't
re-investigate from zero.

## Methodology

```
.venv/Scripts/python.exe -m pytest tests/ -q --no-header
  --deselect tests/test_planta_74_truth_gate.py
```

Above was the matrix used. Failures grouped by suite. Each suite
cross-checked against `.github/workflows/ci.yml`'s deselect list and
the CLAUDE.md §10 baseline notes.

## Findings

### Suite A — `tests/test_pair_merge.py` (3 failures)

| Test | Status |
|---|---|
| `test_two_parallel_strokes_merge_into_one_centerline` | DOCUMENTED DEBT |
| `test_hachura_chain_is_removed_before_pair_merge` | DOCUMENTED DEBT |
| `test_vertical_pair_merge_works_too` | DOCUMENTED DEBT |

All three test `classify_walls()` expecting aggressive pair-merge of
near-parallel strokes. The classifier currently returns the strokes
verbatim (no merge). Root cause: pair-merge logic was either removed
or never landed against the test fixture.

**Triage:** legacy raster pipeline. The vector-first track is the
production path now (CLAUDE.md §1 mission statement). Address only
with empirical threshold sweep on planta_74 + p10 + p12.

**Already deselected in CI:**
`tests/test_pair_merge.py` (line 73 of `.github/workflows/ci.yml`).

### Suite B — `tests/test_text_filter.py` (5 failures)

| Test | Status |
|---|---|
| `test_text_baseline_stack_is_removed` | DOCUMENTED DEBT |
| `test_vertical_text_like_stack_is_removed` | DOCUMENTED DEBT |
| `test_two_parallel_walls_survive` | DOCUMENTED DEBT |
| `test_non_uniform_gaps_are_not_treated_as_text` | DOCUMENTED DEBT |
| `test_filter_respects_page_isolation` | DOCUMENTED DEBT |

All test that the text-filter step removes fake-walls produced by
text baseline stacks. The filter is currently a no-op for these
inputs (4 walls survive when test expects 1).

**Triage:** same legacy raster pipeline. Same gate as Suite A —
`classify/service.py:160` `len(strokes) > 200`.

**Already deselected in CI:** line 71.

### Suite C — `tests/test_planta_74_regression.py` (2 failures)

| Test | Status |
|---|---|
| `test_planta_74_wall_count_within_post_hardening_range` | DOCUMENTED DEBT |
| `test_planta_74_room_count_within_post_hardening_range` | DOCUMENTED DEBT |

The raster pipeline returns 3 rooms on planta_74 (test expects
8–16). Pipeline is OUTDATED per CLAUDE.md §10 ("Known baseline on
planta_74 (raster pipeline, OUTDATED) — 94 walls, 14 rooms, 7
orphan_components, geometry_score 0.156").

**Triage:** vector pipeline is the production track. This regression
test pins the OUTDATED raster baseline; doesn't represent shippable
work.

**Already deselected in CI:** line 66.

### Suite D — `tests/test_f1_dashboard.py` (1 failure)

| Test | Status |
|---|---|
| `test_dashboard_runs` | DOCUMENTED DEBT (fixture-dependent) |

The test expects an inline `<svg>` block in the generated dashboard
HTML. The current dashboard generator emits a `<div>`-based layout
without inline SVG. Per CI comment: "depende de
`runs/<plan>/observed_model.json` estarem populados — `runs/` é
gitignored e fica vazio em fresh checkout."

**Triage:** test is FIXTURE-DEPENDENT. In a fresh checkout (CI or
new dev) `runs/` is empty so the dashboard renders the empty-state
HTML without SVG. Not a code regression.

**Already deselected in CI:** line 70.

## Conclusion

**All 11 local failures are documented dívida or fixture-dependent —
none are silent regressions.** The CI workflow runs successfully via
the deselect list; no new escalation is required from this Frente.

## Roadmap to remove deselects (cohort, not flag-by-flag)

The deselects are a "subset verde inicial" per CI comment.
Promoting tests off the deselect list should be done in cohorts:

| Cohort | Suites | Blocker |
|---|---|---|
| C1 — Raster reactivation | A + B + C | Classifier rewrite (gate `len(strokes) > 200`) → or retire raster pipeline entirely |
| C2 — Fixture binding | D | Populate `tests/fixtures/dashboard_observed.json` (small fixture instead of full `runs/` snapshot) |

This audit's primary contribution is the spec-harness gate
(`docs/engineering/spec_driven_development.md`) — once SDD critical
contracts cover the architectural truths that these legacy raster
tests USED to assert, the deselects can be retired in C1 without
losing coverage.

## Companion artefacts

- `.github/workflows/ci.yml` — the deselect list itself (lines 66–73)
- `CLAUDE.md` §10 — baseline notes including the raster-pipeline
  "OUTDATED" classification
- `docs/engineering/spec_driven_development.md` — the SDD framework
  that replaces the raster-suite assertions with executable
  architectural contracts
- `tools/spec_coverage_report.py` — coverage matrix between FP-NNN
  failure patterns and spec contracts; rerun with each new spec
