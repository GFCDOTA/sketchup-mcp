# Spec-Driven Development (SDD) for sketchup-mcp

> Loaded automatically every Claude Code session when a planta-fidelity
> change is in scope. Treat as the contract layer between an
> architectural truth and the pipeline that approximates it.

## Why

The pipeline `PDF → consensus_model → SKP` has many moving parts:
extractor heuristics, polygonize tolerances, watershed seeds, soft-
barrier rasterisation, Ruby exporter materials, plan-shell unions,
camera setup, screenshot rendering. When something is visually wrong
in the final SKP, the failure usually has 3+ candidate causes:

  - the extractor misread the PDF;
  - the consensus has a merged / merged-seed cell;
  - the exporter buffer width is too thin;
  - a Ruby material is missing and the floor renders default-grey;
  - the camera is wrong and a real bug is masked.

"Visual fix" loops — adjust a constant, regenerate, eyeball — produce
fragile geometry: the visual symptom goes away, but the underlying
contract (what SHOULD be true) was never written down. The next time
the same area changes for an unrelated reason, the regression goes
unnoticed because there was nothing to assert.

**SDD inverts the loop.** Before you touch geometry, write the spec.
Before you ship the spec, ship a harness assertion. The fix is only
done when:

  1. the spec entry exists in `specs/<planta>/<aspect>.spec.yaml`;
  2. the harness FAILS on the pre-fix state;
  3. the harness PASSES on the post-fix state;
  4. before/after evidence is recorded in `runs/.../evidence/`;
  5. the spec is locked as a regression test.

This is the same pattern the failure-patterns catalog enforces (FP-NNN
must have a regression test) — extended one level up, from
implementation bugs to architectural contracts.

## What a spec is

A spec is a small **YAML** document describing one aspect of fidelity
on one planta. Each spec lives in `specs/<planta_id>/<aspect>.spec.yaml`
and is a list of named contracts. Each contract has a `severity`
(critical, warn, info) and a machine-readable rule body.

```yaml
# specs/planta_74/rooms.spec.yaml (excerpt)
schema_version: "1.0.0"
target: planta_74
contracts:
  - id: rooms-no-merged-as-tt
    severity: critical
    description: >
      A.S., TERRACO SOCIAL and TERRACO TECNICO must NOT be co-located
      in a single room polygon. They are distinct architectural
      ambients in the source PDF.
    rule:
      type: no_merged_room_names
      forbidden_substrings:
        - "A.S. | TERRACO"
        - "TERRACO SOCIAL | TERRACO TECNICO"
```

The harness (`tools/spec_harness.py`) reads each spec, executes its
rule against a consensus + reports bundle, and emits a per-contract
verdict (`pass | warn | fail`) into `spec_harness_report.json`.

## Contract severity

- **`critical`** — the fix must land before the change ships. Harness
  exits 1 if any critical contract fails. Use sparingly: a critical
  contract is the architectural equivalent of an assertion. Pick rules
  that, if violated, mean the pipeline is producing wrong work, not
  merely sub-optimal.
- **`warn`** — surfaced in the report and CI log, but does NOT exit 1.
  Use for "this is suspicious; an operator should look but we can ship
  without resolving today." Trending too many warns is its own signal.
- **`info`** — observational, never fails. Use for metrics you want
  visible in the report (room counts, total areas, etc.).

## Workflow

```
SPEC  →  HARNESS FAILING  →  FIX  →  BEFORE/AFTER EVIDENCE  →  REGRESSION LOCK
```

Step-by-step:

1. **Write the spec.** Add a new contract to the relevant
   `specs/<planta>/<aspect>.spec.yaml`. Severity should be honest —
   if you're not willing to block a PR on the contract, it's not
   critical.
2. **Run the harness against the pre-fix consensus.** Confirm the
   harness FAILS on the contract you just added. If it passes, the
   rule is broken OR the bug isn't actually present in this fixture;
   resolve before continuing.
3. **Implement the fix** in a separate branch / commit / PR. Do NOT
   bundle spec authorship and fix in the same change — separation
   keeps the audit trail clean.
4. **Generate before/after evidence.** Run the harness on both the
   pre-fix and post-fix consensus + reports. Save both
   `spec_harness_report.json`s next to overlay PNGs in
   `runs/.../evidence/`. The PR body must reference both reports.
5. **Lock as regression.** Add a pytest test that loads the spec and
   asserts the contract passes on the post-fix fixture
   (`tests/test_spec_<aspect>.py` style). If the contract ever
   regresses, the test fires.

## How to add a new spec or contract

1. Decide WHICH planta the contract applies to. Most contracts will be
   `planta_74`-scoped initially. Multi-planta contracts live in
   `specs/_shared/`.
2. Pick the right aspect file: `rooms`, `openings`, `soft_barriers`,
   `fidelity`. Add a new aspect file only when an existing one would
   exceed ~25 contracts.
3. Choose a `rule.type` from the supported list in
   `harness_engineering.md`. If no rule type fits, add a new one to
   `tools/spec_harness.py` with a unit test, then use it.
4. Default to `warn` unless you can defend `critical`. Critical
   contracts must include a written rationale in the
   `description` field and a link to evidence (a PR, a failure
   pattern, an ADR) showing why this can't ship broken.
5. PR. The PR body should include the result of running the harness
   on the current main branch (proves the contract has the intended
   discrimination power).

## What SDD does NOT do

- **It doesn't replace tests.** Specs assert FIDELITY (the consensus +
  SKP match an external truth). Tests assert IMPLEMENTATION
  correctness (the code behaves as documented). Both are needed.
  The catalog test in `tests/test_failure_patterns_regression_catalog.py`
  is the bridge: every FP must have at least one implementation test.
- **It doesn't auto-generate fixes.** A spec failure is a flag, not a
  patch. The fix is still your responsibility.
- **It doesn't block the smoke harness.** Specs run via the
  `tools/spec_harness.py` entry point. The smoke harness
  (`scripts/smoke/smoke_skp_export.py`) is unchanged; integration
  into smoke gates is a follow-up decision per spec.
- **It doesn't change the production exporter** or any pipeline tool.
  SDD is read-only on the existing code surface.

## File layout summary

```
docs/engineering/
  spec_driven_development.md     ← this file
  harness_engineering.md         ← the harness internals

specs/
  planta_74/
    rooms.spec.yaml
    openings.spec.yaml
    soft_barriers.spec.yaml
    fidelity.spec.yaml
  _shared/                       ← multi-planta contracts (future)

tools/
  spec_harness.py                ← evaluator (exit 0/1)

tests/
  test_spec_harness.py           ← framework tests
  test_spec_<aspect>.py          ← spec-locked regression tests
```

## Pointers

- `docs/engineering/harness_engineering.md` — how the harness works
  internally, supported rule types, how to add a new rule type.
- `docs/protocols/visual_fidelity_gate_protocol.md` — companion
  protocol for visual-evidence gates that already use a 7-artifact
  contract.
- `docs/learning/failure_patterns.md` — every FP-NNN entry that
  describes an architectural failure (FP-006, FP-012, FP-015, FP-016)
  is a candidate for SDD coverage. Convert them incrementally.
- `tests/test_failure_patterns_regression_catalog.py` — the parallel
  enforcement for implementation tests. SDD is the same idea applied
  to architectural truth.
