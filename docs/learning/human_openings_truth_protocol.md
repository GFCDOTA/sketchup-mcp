# Human openings ground truth protocol

> **When the human paints openings on a planta, the painted blobs are
> ground truth. The pipeline must consume them, not contradict them.**

Established: 2026-05-11, FP-014 P0 cycle wrap-up.
Branch: `feat/human-openings-ground-truth`.

## Why this protocol exists

FP-014 cycles (`docs/diagnostics/2026-05-09_skp_visual_failure_fp014.md`,
`docs/diagnostics/2026-05-11_wall_candidates_audit.md`) established
that the canonical planta_74 SKP misses openings the human reviewer
can see in the PDF. The Ruby exporter is honest passthrough; the
Python pipeline misses peitoris/janelas due to detector limitations
(arc geometry rules, hatching ambiguity, stage-1 wall extraction
gaps). For the human reviewer, those misses are not advisory — they
are the source of truth being violated.

This protocol turns the reviewer's painted annotation into a
machine-readable artifact that the pipeline MUST honor. No more
"detector says 9 openings, you marked 12, let's negotiate" — the
12-mark wins, and the gate fails until the SKP shows all 12.

## Color contract (planta_74)

| Color | RGB hex | Kind | Required count |
|---|---|---|---:|
| GREEN   | `#00ff00` | `interior_door`  | 7 |
| MAGENTA | `#ff00ff` | `window`         | 4 |
| ORANGE  | `#ffa500` | `glazed_balcony` | 1 |

The reviewer paints small solid rectangles (or ellipses) of each
color directly over each opening on a planta render. Pure colors only
— no gradients, no semi-transparency.

## Pipeline (5 commands)

The reviewer drops their annotated PNG at
`fixtures/planta_74/human_openings_annotation.png`, then runs:

```powershell
# 0. Build the consensus first if not already (stages 1-3 of canonical pipeline)
.venv\Scripts\python.exe -m tools.build_vector_consensus planta_74.pdf `
    --out runs/vector/consensus.json --detect-openings
.venv\Scripts\python.exe -m tools.extract_room_labels planta_74.pdf `
    --out runs/vector/labels.json
.venv\Scripts\python.exe -m tools.rooms_from_seeds `
    runs/vector/consensus.json runs/vector/labels.json `
    --out runs/vector/consensus.json --method polygonize

# 1. Extract: image -> machine-readable truth JSON
.venv\Scripts\python.exe -m tools.extract_human_openings `
    fixtures/planta_74/human_openings_annotation.png `
    --consensus runs/vector/consensus.json `
    --out fixtures/planta_74/human_openings_truth.json

# 2. Apply: truth JSON overrides consensus.openings
.venv\Scripts\python.exe -m tools.apply_human_openings `
    --consensus runs/vector/consensus.json `
    --truth fixtures/planta_74/human_openings_truth.json `
    --out runs/vector/consensus_human.json

# 3. Gate: counts + positional constraints
.venv\Scripts\python.exe -m tools.structural_checks_human `
    --consensus runs/vector/consensus_human.json `
    --truth fixtures/planta_74/human_openings_truth.json `
    --strict   # exit non-zero on FAIL

# 4. Visual verification: overlay PDF + truth + final
.venv\Scripts\python.exe -m tools.render_human_openings_overlay `
    --pdf planta_74.pdf `
    --truth fixtures/planta_74/human_openings_truth.json `
    --consensus runs/vector/consensus_human.json `
    --out fixtures/planta_74/human_openings_overlay.png

# 5. SKP export — Ruby exporter consumes the human openings transparently
#    via geometry_origin="human_annotation" (PR #111).
.venv\Scripts\python.exe scripts/smoke/smoke_skp_export.py `
    --consensus runs/vector/consensus_human.json `
    --force-skp
```

## File schema

`fixtures/planta_74/human_openings_truth.schema.json` (JSON Schema
draft-07). Key fields per opening:

```json
{
  "id": "h_o000",
  "kind": "interior_door | window | glazed_balcony",
  "color": "green | magenta | orange",
  "bbox_px": [x0, y0, x1, y1],
  "bbox_pts": [l, b, r, t],
  "center_pts": [cx, cy],
  "orientation": "h | v",
  "wall_id": "w015 | null",
  "wall_dist_pts": 2.3,
  "opening_width_pts": 22.0,
  "required": true
}
```

Plus a top-level `explicit_constraints` array for positional
requirements (require_present / require_absent in a bbox).

## Default explicit constraints (planta_74)

These ride in the truth JSON and the gate enforces each:

| Constraint | Policy | Region (PDF pts) |
|---|---|---|
| `BANHO_02_west_door` | require_present interior_door | `[325, 510, 345, 590]` |
| `SALA_ESTAR_TERRACO_SOCIAL_balcony` | require_present glazed_balcony | `[100, 440, 280, 470]` |
| `SUITE_02_south_window` | require_present window | `[255, 395, 380, 415]` |
| `NO_SUITE_01_BANHO_01_internal_window` | require_absent window | `[475, 540, 510, 605]` |

Reviewer can edit the JSON to add more or shift regions; the gate
re-runs idempotently.

## Verdict semantics

`tools/structural_checks_human` emits one of:

- **PASS**: every required-count met, every constraint satisfied.
- **WARN**: counts met but a constraint flagged advisory (currently
  unused; reserved for "policy=advise" extensions).
- **FAIL**: any required-count short OR any `require_present` missing
  OR any `require_absent` violated. SKP export must NOT proceed under
  the F0 gate.

## Coexistence with detector output

By default, `apply_human_openings --mode replace` wipes detector
openings and writes only human openings. Use `--mode merge` to keep
detector openings that don't collide with human ones (within 25 pt
center distance). For FP-014 P0 the rule is **human wins** — collision
deletes the detector entry.

## Why no auto-detection feedback loop

The human truth is **immutable** during a run. The detector can be
improved later (peitoril classifier, hatch-aware stroke detector,
threshold tuning) and PRs that move the detector closer to the truth
without changing this fixture are welcome. But the gate stays the
same: if the human painted 12 openings, the SKP must render 12.

## Test fixture (committed)

`fixtures/planta_74/SYNTHETIC_*.png` and `SYNTHETIC_*.json` are an
end-to-end smoke artifact generated by
`tools/generate_synthetic_human_annotation.py`. They prove the
extract → apply → gate → overlay path runs PASS (8/0/0 findings) on
synthetic input. They are NOT a substitute for the real reviewer
annotation.

When the real `human_openings_annotation.png` lands, the same five
commands above run unchanged.
