# Visual Fidelity Gate Protocol — 2026-05-14

> **Status:** Active policy as of 2026-05-14.
> Applies to every fidelity report produced by `tools/verify_fidelities.py`
> when `--require-visual-evidence` is set.

## Motivation

The 4-axis fidelity engine (`wall_fidelity`, `soft_barrier_fidelity`,
`semantic_room_fidelity`, `global_visual_fidelity`) can produce a
`verdict_top_level: PASS` whose hard axes are PASS purely on
intra-consensus self-consistency:

- `wall_fidelity` counts how many `human_wall` priors were honored.
- `soft_barrier_fidelity` counts how many `human_soft_barrier`
  priors were honored.
- `semantic_room_fidelity` counts label preservation in merged cells.
- `global_visual_fidelity` is advisory only.

None of these axes compares the consensus against the **source PDF**.
Two PRs in the planta_74 cycle (#121 on 2026-05-13 and the post-PR
inspection on 2026-05-14) confirmed this is unsafe: a `PASS` was
produced for a consensus whose `MURETA H=0,70M` (visible in the
PDF as a labeled barrier) is silently missing, and whose exterior
parapet wraps only one of the three perimeter edges the PDF
documents.

> **Aggregate-score PASS without visual evidence is unacceptable.**
>
> An axis can be PASS, but the top-level verdict cannot be PASS
> until the seven visual evidence artifacts described below exist
> on disk and the eight failure conditions are absent.

## The eight failure conditions (each ≥ 1 = FAIL)

A future `tools/visual_fidelity_gate.py` (PR B) implements algorithmic
checks for each. Until that tool ships, the gate runs in
**artifact-presence mode**: the top-level verdict cannot be PASS
without the artifacts.

| # | Condition |
|---|---|
| 1 | Door drawn without a real opening in its host wall. |
| 2 | Door crossing the wall (no carve) or displaced from the gap. |
| 3 | Door swing / orientation diverges from the PDF arc. |
| 4 | A room with a non-closed polygon. |
| 5 | A room polygon bleeding outside the building outline. |
| 6 | An exterior wall / esquadria / peitoril that is invented or has the wrong height. |
| 7 | Bathroom / lavabo / A.S. / terraço with the wrong adjacency. |
| 8 | A room rendered as a bounding box / block instead of real geometry. |

## The seven required visual evidence artifacts

When `--require-visual-evidence` is set, all seven must exist
on disk for the top-level verdict to clear `FAIL` by policy. Each
artifact has a canonical filename pattern. The flag
`--visual-evidence-dir <dir>` overrides the lookup root (defaults
to the parent of `--consensus-after`).

| key | required path under `<visual-evidence-dir>` |
|---|---|
| `original_floorplan` | `original_floorplan.png` (PDF rendered to PNG, full page) |
| `skp_render` | `skp_render.png` (axon of the SKP, no PDF) |
| `overlay_pdf_skp` | `overlay_pdf_skp.png` (PDF and SKP superimposed on a shared frame) |
| `diff_walls` | `diff_walls.png` (walls present in PDF but absent in SKP + walls in SKP but absent in PDF) |
| `diff_doors` | `diff_doors.png` (per-door pass/fail badge: present / missing / displaced / swing-wrong) |
| `diff_rooms` | `diff_rooms.png` (per-room polygon overlay vs expected) |
| `mismatches_list` | `mismatches_list.md` (markdown checklist of every failure-condition hit, with room/wall/opening IDs) |

> **Presence is necessary, not sufficient.** PR B introduces
> algorithmic checks that interrogate each artifact (e.g. compare
> the door pixel diff against a threshold, parse the markdown for
> open items, run shapely on each room polygon). PR A only checks
> that the artifacts exist.

## Gate behavior

`tools/verify_fidelities.py --require-visual-evidence`:

1. Compute the four axes as before (unchanged).
2. Inspect `<visual-evidence-dir>` for the seven artifacts.
3. Tag each artifact `present` / `missing` / `incomplete`.
   In PR A's artifact-presence mode, `present` simply means the
   file exists and is > 0 bytes. PR B refines `incomplete` based
   on per-artifact checks.
4. If all seven are `present`:
   - Top-level verdict uses the worst-axis rule (unchanged).
5. Otherwise:
   - Top-level verdict is forced to `FAIL`.
   - `policy_violation: 2026-05-14_visual_fidelity_gate_required`.
   - `visual_evidence_required: true`.
   - `visual_evidence_status: missing` (none present) or
     `incomplete` (some present).
   - `missing_visual_artifacts: [<keys>]`.
   - Per-axis verdicts are **preserved** (so a reader can still
     see which axes individually pass). Only the top-level is
     downgraded.

`tools/verify_fidelities.py` **without** the flag remains
byte-equivalent to the prior contract (no behavior change in CI
or any existing caller).

## Rollout

- 2026-05-14 — PR A ships the artifact-presence gate behind
  `--require-visual-evidence` (default off → backward compatible).
- PR B — `tools/visual_fidelity_gate.py` ships the eight algorithmic
  checks + the seven artifact producers. PR B flips `incomplete`
  from "unused in PR A" to a real verdict driven by the checks.
- A subsequent CI cycle promotes `--require-visual-evidence`
  from opt-in flag to default (after PR B has dogfooded
  successfully on planta_74).

## Honesty principle

Aggregate scores cover the cases the engine knows how to score.
A score that is PASS without ever having compared the consensus
to the PDF is **not honest**. The gate's job is to refuse to
emit a PASS the operator could mistake for visual fidelity, and
to make the missing evidence visible by name.

## Related

- `tools/verify_fidelities.py` (this PR adds the flag)
- `tools/visual_fidelity_gate.py` (PR B will land)
- `fixtures/planta_74/fidelity_4axis_report.json`
- `fixtures/planta_74/operator_acknowledgment_2026-05-13.md` (the
  former WARN-with-waiver that this policy supersedes)
- `CLAUDE.md` §10 (carries the operational rule)
