# FP-030 — Visual Oracle Gate

## Status

MVP delivered in `feat/fp-030-visual-oracle-gate` (2026-05-28).
Skill `skp-visual-self-correction` operacionaliza o loop.

## Problem

Geometry reports can pass while the generated SKP is visually
wrong: floating doors, orphan glass panels, misplaced soft
barriers, wall stubs, missing wall continuations, or floor
leaks may be obvious to a human but invisible to existing
gates. The user should not be the visual regression detector.

The fidelity-review of `planta_74` on 2026-05-27 (post PR #194)
proved the gap: all 4 `gates_self_check` passed `true` AND
the user still raised a visual hypothesis ("extra windows") that
required a fresh build + manual count check to dismiss.

## Rule

```text
No SKP, no progress.
No visual proof, no progress.
The user is not the visual regression detector.
```

Per Constitution #8 (in `.claude/constitution.md`), any
SKP-affecting PR must commit a final `.skp` + renders +
`regression_summary.md` under `artifacts/review/<plant>/<branch_or_pr>/final/`.
FP-030 extends Constitution #8 by **enforcing visual evidence**
via heuristic checks + structured findings JSON.

## Scope

Applies to any change affecting:

- SKP generation (`tools/build_plan_shell_skp.{py,rb}`)
- Walls / wall shell / canonicalisation
- Openings (doors, windows, glazed_balcony, kind_v5 routing)
- Rooms / floors / soft barriers
- Fidelity / geometry reports
- Renderer (Ruby `write_image`)
- Artifact policy (paths, naming, sidecar)
- Consensus-to-SKP builder logic

Same path triggers as Constitution #8 — see
`.claude/specs/skp_proof_of_progress_gate.md` § "Quando aplica".

## Required artifacts

```
artifacts/review/<fixture>/<run_id>/final/
├── model.skp                       ← deliverable
├── model_top.png                   ← render top
├── model_iso.png                   ← render iso
├── side_by_side_pdf_vs_skp.png     ← if generated
├── geometry_report.json            ← stats + gates_self_check
├── visual_findings.json            ← v1 schema (this PR)
└── regression_summary.md           ← veredito + evidência
```

`visual_findings.json` schema at `schemas/visual_findings.schema.json`.

## Blocking visual findings (hard FAIL)

The deterministic heuristics in `tools/run_skp_visual_review.py`
hard-FAIL the build if any of these are detected:

| Type | Detection |
|---|---|
| `gates_self_check_fail` | Any boolean in `geometry_report.gates_self_check` is `false` |
| `window_count_mismatch` | `window_apertures_3d` != count of `kind_v5=="window"` in consensus |
| `floating_door` | `DoorLeaf_Group.bbox_m.min[2]` > 0.05m (door off floor) |
| `orphan_glass_panel` | `WindowGlass_Group_<id>` with no matching `id` in `consensus.openings` of kind=window |
| `bad_window_aperture` | `WindowGlass_Group.height_m` outside [0.9, 1.5]m range |
| `floor_leak` | `floor_groups.present == false` OR `count == 0` |

Other classes (taught by synthetic examples) are not yet
auto-detected but are part of the manifest taxonomy:

- `wall_stub` (FP-026 has its own diagnostic tool)
- `misplaced_soft_barrier`
- `unsupported_parapet`
- `missing_wall_continuation`
- `misplaced_window`
- `global_visual_fail` (umbrella)

## Review axes

```text
wall_fidelity
door_fidelity
window_fidelity
room_fidelity
scale_rotation        ← qualitative, needs human/agent inline
global_visual         ← qualitative, needs human/agent inline
```

Qualitative axes default to **WARN: needs_human_or_agent_inline_review**
when no numeric finding is produced.

## Loop

Up to 3 correction attempts:

```text
attempt_0 = baseline
attempt_1 = fix highest-ROI FAIL (if source-supported)
attempt_2 = second fix if needed
attempt_3 = final attempt if needed
```

**MVP**: the script (`tools/run_skp_visual_review.py`) **does
not auto-fix**. It stops on first FAIL and reports proposed
fixes; a human or downstream agent must apply the fix and rerun.
Auto-fix is a follow-up.

Stop early on:
- PASS verdict
- WARN verdict (acceptable if WARN reasons are documented as
  expected, e.g. open-plan cells for planta_74)
- BLOCKED (SU unavailable, consensus missing, etc.) — written
  to `regression_summary.md` with next command

## Example policy — 5 confidence tiers

Each example in `fixtures/visual_oracle_examples/manifest.json`
carries a `confidence_tier` controlling **how it can train the
oracle**:

| Tier | Use | Can train hard FAIL? |
|---|---|---|
| `good_real_baseline` | Strong PASS reference from current canonical artifact | n/a (positive) |
| `bad_real_confirmed` | Strong FAIL example, defect clearly localised and NOT coinciding with legitimate geometry | ✅ yes |
| `bad_real_ambiguous` | Real screenshot with annotations that MAY include false-positive regions (e.g. door jambs marked as wall stubs) | ❌ no — WARN only |
| `good_synthetic_teaching` | Didactic positive diagram | n/a (positive) |
| `bad_synthetic_teaching` | Didactic negative diagram for a single category | ✅ yes (with caveat: synthetic, not golden absolute) |

**Confidence weighting** (oracle decision logic):

1. `bad_real_confirmed` = strong weight; localised, unambiguous
2. `good_real_baseline` = strong weight; canonical positive
3. `bad_real_ambiguous` = WARN-only, **never** hard FAIL
4. `bad_synthetic_teaching` = didactic; learns category but not
   absolute ground truth
5. `good_synthetic_teaching` = didactic positive

**Rule**: a real bad example may teach the oracle but must NOT
teach a false positive as FAIL. The `bad_wall_stubs_*` images
carry red circles over both real residual stubs AND legitimate
door jambs / window mullions; classified as `bad_real_ambiguous`
they contribute WARN only.

### Disambiguating `bad_wall_stubs_*`

When the oracle inspects a region flagged by these examples, it
must cross-check the FP-026 detector
(`tools/diagnose_wall_stubs.py`) before issuing a FAIL. Each
ambiguous example carries an `ambiguous_or_false_positive_regions`
list in its `.expected.json` enumerating likely false positives:

- `"possible door jamb"` — legitimate wall framing a door
- `"possible window mullion"` — legitimate wall around a window aperture
- `"possible valid opening detail"` — opening reveal / jamb shadow

### Current example inventory

- **4 PASS** (3 `good_real_baseline` from current canonical + 1 `good_synthetic_teaching`)
- **2 `bad_real_confirmed`** (`bad_orphan_glass_parapet_*`)
- **5 `bad_real_ambiguous`** (`bad_current_*_suspicious`, `bad_suspicious_openings_iso`, `bad_wall_stubs_*`)
- **8 `bad_synthetic_teaching`** (each negative class)

Total: 19 examples.

## Schema (`visual_findings.v1`)

See `schemas/visual_findings.schema.json`. Required fields:

- `schema_version` (const `"visual_findings.v1"`)
- `fixture`, `attempt`, `top_level_verdict`
- `axes` (object with 6 review axes)
- `findings` (array; each finding has id, severity, axis,
  type, location, evidence_image, evidence)

## Tooling

- `tools/run_skp_visual_review.py` — MVP runner
- `tools/prompts/visual_oracle_reviewer.md` — prompt for downstream
  vision agent
- `tests/test_visual_oracle_contract.py` — schema + manifest contract
- `.claude/skills/skp-visual-self-correction/SKILL.md` — operational skill

## Encaixe operacional

Categoria 5 (user-requested milestone) + 3 (failing gate
protection) do `memory/operational_rules.md`.

## Follow-ups (not in this PR)

1. Auto-fix loop (script applies source-supported fixes between
   attempts). Requires a fix taxonomy and safe-edit policies.
2. Side-by-side composite generator
   (`tools/compose_side_by_side.py`) — currently external.
3. Vision API integration for qualitative axes (optional).
4. Wider negative class coverage:
   `misplaced_soft_barrier`, `unsupported_parapet`,
   `missing_wall_continuation` need positional heuristics that
   compare bbox vs wall paths.

## Related

- Constitution: [`.claude/constitution.md`](../../.claude/constitution.md) §1, §2, §8
- [`.claude/specs/skp_proof_of_progress_gate.md`](../../.claude/specs/skp_proof_of_progress_gate.md)
- [`.claude/skills/skp-visual-self-correction/SKILL.md`](../../.claude/skills/skp-visual-self-correction/SKILL.md)
- [`fixtures/visual_oracle_examples/manifest.json`](../../fixtures/visual_oracle_examples/manifest.json)
- [`schemas/visual_findings.schema.json`](../../schemas/visual_findings.schema.json)
