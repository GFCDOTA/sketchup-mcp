# ADR-005 — Spec-Driven Development framework

> **Status:** Accepted (2026-05-21) as **Phase 2 (observational)**.
> Promotion to Phase 3 (blocking) is a deliberate per-cycle decision
> documented in this ADR.
> **Author:** Claude session, authorised by Felipe.
> **Related:** ADR-001 (validation cockpit), ADR-002 (room polygon
> overrides), ADR-003 (plan-shell exporter §11 + §12), ADR-004
> (mutation & regression testing policy),
> `docs/protocols/visual_fidelity_gate_protocol.md`,
> `docs/learning/failure_patterns.md`.

---

## 1. Context

The PDF→consensus→SKP pipeline has been hardened over many cycles
via a layered defence:

| Layer | Doc | Enforces |
|---|---|---|
| Unit tests | `tests/test_*.py` | Implementation correctness |
| FP regression catalog | `tests/test_failure_patterns_regression_catalog.py` | Every FP-NNN has ≥ 1 regression test |
| Mutation tests | `tests/test_*_mutation_*.py` | Test discrimination power (ADR-004) |
| Smoke gates | `scripts/smoke/smoke_skp_export.py` | Ordering of cheap-vs-expensive gates (CLAUDE.md §3) |
| Geometry invariants | `tools/build_geometry_invariants_report.py` | Per-group height/material/topology PASS/WARN/FAIL |
| Visual fidelity gate | `docs/protocols/visual_fidelity_gate_protocol.md` | Seven-artifact contract for aggregate score promotion |

What this stack does NOT cover is **architectural truth** —
assertions about what the consensus + SKP SHOULD look like given
the source PDF, independent of which exporter / extractor produced
it.

When a planta is delivered, the architectural truth is information
like:

- A.S., TERRACO SOCIAL and TERRACO TECNICO are distinct ambients
  separated by peitoris.
- Every BANHO / LAVABO must have a door.
- Soft barriers must render as parapets (1.10 m), not full walls
  (2.70 m).
- The DoorLeaf must sit within ~1 m of its host opening center.

These are not implementation contracts; they are **fidelity
contracts** between the pipeline's output and the PDF's intent.
The 2026-05-20 .skb review (Frente 2) surfaced the gap: the
pipeline produced PASS invariants on a `.skp` whose Floor_r001
group merged three architectural rooms into one. The geometry was
"valid"; the FIDELITY was wrong.

This ADR records the framework that closes that gap.

## 2. Decision

Introduce **Spec-Driven Development (SDD)**: a contract layer
where each architectural truth is written as a machine-checked
contract in YAML, evaluated by a standalone harness, and
optionally gated in CI.

The workflow:

```
SPEC  →  HARNESS FAILING  →  FIX  →  BEFORE/AFTER EVIDENCE  →  REGRESSION LOCK
```

1. **SPEC** — author writes the contract in
   `specs/<planta>/<aspect>.spec.yaml`.
2. **HARNESS FAILING** — author runs `python -m tools.spec_harness`
   on the pre-fix consensus + reports. The harness MUST FAIL on the
   new contract; otherwise the rule is broken or the bug isn't
   present in the fixture.
3. **FIX** — implementation lands in a separate PR / commit. Spec
   authorship and fix are deliberately split so the audit trail
   shows the contract existed BEFORE the fix.
4. **BEFORE/AFTER EVIDENCE** — both `spec_harness_report.json`s
   live next to overlay PNGs in `runs/.../evidence/`. The PR body
   references both.
5. **REGRESSION LOCK** — pytest test asserts the contract passes
   on the post-fix fixture (`tests/test_spec_<aspect>.py` pattern).

## 3. Phased rollout

Modelled after the visual-fidelity-gate protocol's three phases.

| Phase | When | What |
|---|---|---|
| **Phase 1** | PR #145 (shipped) | Framework + 4 planta_74 specs (21 contracts) + harness with 14 rule types + 24 tests |
| **Phase 2** | PR #146 (shipped) | Non-blocking CI workflow comments harness verdict on every PR. `continue-on-error: true` on the harness step. Spec coverage report tool |
| **Phase 3** | TBD per cycle | Promote individual contracts from `warn` → `critical` AND/OR flip `continue-on-error: false` on the CI step |
| **Phase 4** | TBD | Multi-planta fixtures via `specs/_shared/` for cross-planta contracts |

Phase 3 promotion is per-contract, not per-workflow. A `critical`
contract that has reliably caught regressions for ≥ 4 weeks can be
promoted to BLOCKING by flipping `continue-on-error` on its own
workflow run; the others remain observational.

## 4. Rule type catalogue

The harness dispatches each contract's `rule.type` to a Python
evaluator in `tools.spec_harness._RULE_DISPATCHERS`. Adding a new
type requires (a) a new dispatcher function, (b) a unit test, and
(c) an entry in
`docs/engineering/harness_engineering.md`. The scaffolder
(`tools/new_spec_contract.py`) and linter (`tools/lint_specs.py`)
discover types from the dispatcher table at runtime, so the three
stay in lock-step automatically.

Shipped rule types (Phase 1+2):

  - `no_merged_room_names`
  - `expected_room_names`
  - `room_area_range`
  - `soft_barriers_protected_count`
  - `soft_barriers_count_range`
  - `soft_barriers_wall_coincident_count`
  - `soft_barrier_height_band`
  - `door_leaf_proximity`
  - `room_has_door`
  - `evidence_pack_present`
  - `fidelity_axis_pass`
  - `fidelity_axes_observe`
  - `invariants_verdict_pass`
  - `openings_min_kind_count`
  - `openings_count_range`

Each captures an aspect of fidelity that previously lived in
operator memory or post-hoc commentary on broken PRs.

## 5. Severity model

| Severity | Build effect | Use case |
|---|---|---|
| `critical` | Harness exits 1 if it fails | Architectural truths that, if violated, mean the pipeline shipped wrong work |
| `warn` | Reported, never breaks build | Suspicious states an operator should review but can ship in the interim |
| `info` | Observational, never breaks | Metrics surfaced in the report (counts, totals) |

**Hand-picked**, not derived. The author of a `critical` contract
must include a written rationale in the `description` field and an
evidence pointer (a PR, an FP-NNN, an ADR).

A contract that emits `skip` (because a required input was not
provided) does NOT satisfy critical accounting. Skip ≠ pass.

## 6. Companion tools

| Tool | Purpose | PR |
|---|---|---|
| `tools/spec_harness.py` | Evaluator + report writer | #145 |
| `tools/spec_coverage_report.py` | FP-NNN ↔ contract id matrix | #146 |
| `tools/lint_specs.py` | Pre-harness YAML + rule-type linter | #148 |
| `tools/new_spec_contract.py` | Idempotent contract scaffolder | #148 |

The four tools deliberately do NOT share a CLI namespace — each is
a separate `python -m tools.<tool>` entry point. The harness has
no opinion about the other tools; the coverage report has no
opinion about the linter; etc. This keeps each tool unit-testable
in isolation and lets contributors adopt one without the others.

## 7. CI integration

`.github/workflows/spec_harness.yml`:

  - Path-filtered trigger (only runs on PRs touching specs,
    fixtures/planta_74, or the relevant pipeline tools).
  - Concurrency control (in-flight runs cancelled on new pushes).
  - Step ordering:
      1. `lint_specs` — HARD-blocking (continue-on-error: false)
      2. `spec_harness` — SOFT-blocking (continue-on-error: true,
         Phase 2 observational)
      3. Upload report as artifact (14-day retention)
      4. Post / update PR comment with de-duplicating marker

Comment de-duplication is by HTML marker (`<!-- spec-harness-bot
-->`) so re-runs update the existing comment instead of stacking.

The existing `ci.yml` workflow is untouched; SDD lives in its own
file by design.

## 8. What this ADR does NOT mandate

- **It does NOT replace tests.** Specs assert fidelity; tests
  assert correctness. Both are needed.
- **It does NOT change the production exporter.** The
  consume_consensus.rb pipeline is untouched (CLAUDE.md §1.4).
- **It does NOT change the schema.** Specs READ consensus +
  reports; they do not modify either (CLAUDE.md §1.3).
- **It does NOT generate fixes.** A contract failure is a flag,
  not a patch.
- **It does NOT integrate with the smoke harness** in Phase 1+2.
  The smoke harness owns gate ordering (CLAUDE.md §3); SDD owns
  fidelity contracts. They run independently. Phase 4 may
  introduce a `--run-spec-harness` opt-in on the smoke harness.

## 9. Forbidden anti-patterns

- **Lowering severity to make a critical contract pass** is
  always wrong. If the rule is too strict, the right fix is either
  to tighten the rule's parameters in the YAML (with documented
  rationale) or to land the implementation fix that makes the
  contract pass legitimately.
- **Adding a `warn` contract instead of writing a regression
  test.** A warn is for "operator should look"; a regression
  test is for "this must not happen again." Use both; they have
  different audiences.
- **Hand-editing `spec_harness_report.json`** to silence a
  failing contract. The report is a generated artifact; mutating
  it is fraud.
- **Skipping `lint_specs` to "save time."** The linter is ~50ms
  and catches the failure modes (unknown rule type, dup id) that
  silently degrade the harness report.

## 10. Outstanding work (post-Phase-2)

Tracked in PR descriptions and `.ai_bridge/TODO_NEXT.md`:

- **Audit decision overrides** — a tool that converts
  `tools/audit_soft_barriers.py` `warn` decisions into a
  `consensus.soft_barriers[].geometry_origin = "human_annotation"`
  override file. Resolves the third critical
  failure on planta_74 (sb004 + h_sb000 as legitimate peitoris).
- **`specs/_shared/`** — cross-planta contracts for plantas other
  than planta_74.
- **Phase 3 promotion** — first contract to flip from `warn` to
  blocking after the cooldown period.
- **Smoke harness wiring** — opt-in `--run-spec-harness` flag.
- **FP → spec auto-link** — populate
  `KNOWN_FP_SPEC_LINKS` from contract `evidence_pointers` instead
  of hand-curating.
- **Pre-commit hook** — pre-commit framework integration calling
  `lint_specs` on `git commit`.

## 11. Reversal

The framework is a pure addition. Reverting the PRs in reverse
order (#149 → #148 → #147 → #146 → #145) removes every trace.

Per-contract reversal: delete the contract entry from the spec
YAML (or set its severity to `info` to keep it as observational
metrics). Per-rule-type reversal: remove the dispatcher entry
from `_RULE_DISPATCHERS`; the linter will flag specs referencing
the now-unknown type.

## 12. Decision log

| Date | Decision |
|---|---|
| 2026-05-20 | Frente 2 (Phase 1) — framework + 4 specs + harness + 24 tests (PR #145) |
| 2026-05-21 | Phase 2 — CI workflow, spec_coverage_report, baseline failures audit (PR #146) |
| 2026-05-21 | Docs foundations — CONTRIBUTING.md + pipeline_overview.md (PR #147) |
| 2026-05-21 | Linter + scaffolder — lint_specs, new_spec_contract (PR #148) |
| 2026-05-21 | Hardening — concurrency, PyYAML pin, README doc map (PR #149) |
| 2026-05-21 | This ADR (PR #150 — proposed) |
| 2026-05-24 | Restored to repo after dead-chain orphan. The Phase-1/2 implementation ended up split across surviving PRs: #145 (framework + harness), #163 (docs foundations from #147 with the SDD stack scrubbed), #166 (linter + scaffolder, supersedes #148), #168 (workflow concurrency + PyYAML pin + README doc map, supersedes #149). PR #146 (the "Phase 2 CI gate + coverage report + baseline failures audit") was auto-closed when its base merged; `tools/spec_coverage_report.py` referenced in §6 + above as "shipped via #146" is NOT in develop yet — tracked as outstanding work. `tools/audit_soft_barriers.py` referenced in §10 line 1 is also pending. The framework decision recorded above stands; the catalogue of shipped tools narrowed to harness/linter/scaffolder. |

Future decisions append here. Each Phase 3 promotion of a contract
gets its own line.
