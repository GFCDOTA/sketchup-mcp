# ADR-004 — Mutation testing policy + failure-pattern regression catalog

> **Status:** Accepted (2026-05-20).
> **Author:** Claude session, requested by Felipe after the
> 2026-05-20 soft_barrier-bbox-as-slab incident.
> **Related:** ADR-003 (plan-shell exporter), CLAUDE.md §1/§2/§16,
> `docs/learning/failure_patterns.md`.

---

## 1. Context

The visual bug on 2026-05-20 — `build_plan_shell_skp.rb` emitting
soft-barriers with footprints up to 80 m² (vs. peitorils that should
sit at ~0.1 m²) — shipped despite the user-pinned 4-axis fidelity
gate and the 24 existing unit tests on the Python phase. The
geometry was wrong, the smoke harness was green, and the failure
only surfaced when a human opened the `.skp` in SketchUp.

That is the failure mode this ADR addresses: **a unit-test suite
that proves the happy path but does not assert what changes when a
careless edit introduces an off-by-half-thickness or a
bounding-box-instead-of-swept-rectangle bug**. Coverage % is not the
right metric; whether a mutation of the source code is detected by
the suite IS.

Felipe's framing: *"tem que ter testes mutantes e regressivos pra
tudo, bugs nessa altura é inadmissivel."*

## 2. Decision

Adopt three layered guardrails for every Python module on the
critical SKP path. Layered, not redundant — each layer catches a
class of bug the others miss.

### Layer A — Pinned-value / mutation tests (hand-rolled)

For every numeric constant, threshold, or RGB triple that affects
geometric output, write a test that:

  - asserts the constant equals its documented value
    (`SNAP_EPS_PTS == 0.1`, etc.), OR
  - mutates the value temporarily and asserts the geometric
    output VISIBLY differs from the baseline.

For every function that does a coordinate transform, off-by-half
calculation, or operator-based mutation (`>`, `<=`, `+`, `-`), write
at least one test that pins the directional sense of the result
(thicker wall ⇒ larger outer bbox, door subtraction ⇒ smaller area).

Lives in `tests/test_<module>_mutation_critical_paths.py`. Each
mutation gets an `MUT-NN` block comment describing the source-code
change it would correspond to.

Why hand-rolled instead of `mutmut`/`mutatest`: both tools fail on
Windows (subprocess invocation bug in mutmut, missing
`__main__.py` in mutatest). The team works on Windows; tooling that
requires WSL is not adopted today. A hand-rolled list of mutations
is also **auditable** — a reviewer can read the file and see which
mutation classes are covered, which is harder with a black-box
mutation tool.

### Layer B — Adversarial-input tests (mutant consensus)

For every exporter that consumes a consensus / amended-observed
JSON, write tests that feed PATHOLOGICAL inputs:

  - unsupported orientation values
  - negative or zero thickness
  - zero-length walls
  - openings without host wall_id
  - openings whose host wall_id refers to a deleted wall
  - openings whose center falls outside the host wall
  - empty walls array
  - duplicate wall ids
  - self-intersecting wall topology
  - room polygons with consecutive duplicate vertices
  - polylines whose bbox is enormous but whose actual path is tiny

For each adversarial input, pin EITHER the exception kind+message
OR the way the result is recorded in `stats["openings_skipped"]` /
similar. Silent acceptance is not allowed.

Lives in `tests/test_<module>_mutant_inputs.py`. Each adversarial
case gets an `M-NN` block comment describing what real-world
upstream-pipeline regression would produce it.

### Layer C — Failure-pattern regression catalog

`docs/learning/failure_patterns.md` collects FP-NNN entries. Each
entry SHOULD point to at least one regression test such that, if
the failure mode returned, the test would fail.

`tests/test_failure_patterns_regression_catalog.py` enforces:

  1. Every `## FP-NNN` heading in `failure_patterns.md` has an
     entry in `KNOWN_FP_REGRESSIONS`.
  2. Every entry has at least one test/file reference.
  3. Every reference exists on disk.
  4. No orphan entries (referenced FP-NN that is not in the .md).
  5. Every entry has a non-empty `reason` field.

This forces an author who lands a new failure pattern to think
about regression coverage BEFORE shipping the doc entry. An entry
without coverage is a TODO disguised as documentation.

## 3. Where the layers apply today

| Module | Layer A | Layer B | Layer C |
|---|---|---|---|
| `tools/build_plan_shell_skp.py` | `test_plan_shell_mutation_critical_paths.py` (16 tests) | `test_plan_shell_mutant_inputs.py` (12 tests) | FP-006, FP-014 in catalog |
| `tools/disarm_sketchup_autoruns.py` | `test_disarm_sketchup_autoruns.py` (6 tests) | covered by main suite | FP-014 in catalog |
| `tools/build_plan_shell_skp.rb` | — (no Ruby mutation tooling); proxy via Layer B (consensus mutants) + Layer C (`test_plan_shell_invariants.py` 16 invariants) | shares Python test_mutant_inputs.py | FP-006 in catalog |
| `tools/consume_consensus.rb` (production) | — | — | FP-005, FP-006 in catalog; structural grep in `skp_fidelity_gate.yml` |
| `tools/skp_from_consensus.py` (production) | `test_skp_from_consensus_skip.py` | — | FP-001, FP-014 in catalog |

Gaps that should be filled in follow-up PRs (one per row, sized
small enough to ship):

  - Layer A for `tools/render_plan_shell_layers.py` (the
    visualisation tool — has no tests today). Low risk because
    it's a diagnostic, but a typo in the projection breaks
    review screenshots.
  - Layer B for `tools/skp_from_consensus.py` — feed it
    pathological consensus JSONs and assert the cache layer +
    bootstrap + control-file logic stays robust.
  - Layer A for the upstream vector-pipeline modules
    (`tools/build_vector_consensus.py`,
    `tools/extract_openings_vector.py`,
    `tools/rooms_from_seeds.py`). Bigger investment; do after the
    next planta lands.

## 4. CI integration

The fidelity gate (`.github/workflows/skp_fidelity_gate.yml`)
already runs every test under `tests/` on PRs that touch the
plan-shell exporter sources. The mutation + mutant-input + catalog
tests pick up `paths`-triggered runs automatically because they
live under `tests/`.

No new CI job. The catalog test serves as the gate: a missing
FP-NN entry, a bad reference, or an undocumented failure pattern
fails CI as a normal pytest assertion.

A future enhancement (NOT in this PR) would add a periodic
`mutmut`-via-WSL job that scans for survived mutants and opens a
GitHub issue per surviving mutation. Deferred until either
mutmut/mutatest fixes their Windows subprocess bug OR a WSL
runner becomes part of the team's flow.

## 5. What this ADR is NOT

  - Not a coverage-percentage policy. We do not gate on
    `coverage.py` percentage — the soft-barrier bug shipped with
    `tests/test_build_plan_shell.py` covering most of the
    critical lines. Coverage is necessary, not sufficient.
  - Not a full mutation-score policy. We do not require a target
    mutation score (e.g. "≥ 90% of mutmut-generated mutants
    killed") because the tooling does not run on Windows. When
    that changes, this ADR gets amended.
  - Not a replacement for the visual fidelity gate
    (`docs/protocols/visual_fidelity_gate_protocol.md`). The 7
    visual evidence artifacts still gate the top-level verdict;
    the mutation/regression suites are an additional pre-screen
    that catches structural bugs before they reach the visual
    review.

## 6. Failure mode this ADR commits to NOT repeating

> Soft-barrier polyline turned into a polyline-bbox slab,
> producing 30-80 m² peitorils that visually buried room floors.
> The 4-axis fidelity gate did not catch it (it scores walls and
> openings, not soft-barrier geometry). The 24 unit tests did not
> catch it (they cover the wall-shell union, not the soft-barrier
> path). A reviewer opened the `.skp` and saw the bug.

Three things failed here:
  1. **No invariant on soft-barrier footprint size.** Added —
     `test_soft_barriers_footprint_below_architectural_ceiling`
     in `test_plan_shell_invariants.py`.
  2. **No adversarial test for the bbox-as-slab class of bug.**
     Added — M-12 note in `test_plan_shell_mutant_inputs.py`
     plus the new invariant.
  3. **No catalog entry forcing the cross-reference.** FP-006
     entry expanded to point at both the new invariant and the
     production exporter's `_segment_overlaps_wall?`.

If a similar class of bug ships from now on, the catalog test
will FAIL on the PR that introduces the failure-pattern entry
without a regression test, OR the invariant test will FAIL on
the PR that introduces the bug itself.

## 7. Rollback

```bash
git revert <merge-sha>
```

Strictly additive: 3 new test files, 1 ADR. Reverting only removes
the new safety net. No production code is touched.
