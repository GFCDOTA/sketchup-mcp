# planta_74 — human walls annotation protocol

> **Status:** OPEN. Companion to the human-openings protocol shipped
> in PRs #112–#120. Use this to mark structural walls/divisors that
> `tools/build_vector_consensus` misses (refuted as "missing
> dividers", not threshold rejection — see
> `docs/diagnostics/2026-05-11_wall_candidates_audit.md`).

## Why this exists

The polygonize-based room detection ships 7 cells on planta_74 instead
of the 11 expected, because the dividers between certain rooms do not
appear as filled paths in the PDF — the audit refuted threshold
rejection (the wall extractor behaves correctly on the paths it
sees). Resolution path: the reviewer marks the missing walls in a
color-coded PNG; the pipeline adds them to `consensus.walls` with
`geometry_origin="human_annotation"`; `polygonize_rooms` re-runs and
forms 11 cells.

This is symmetric to the human-openings protocol — same shape, just
walls instead of openings.

## Color contract

| Color | Hex | Meaning |
|---|---|---|
| **BLUE** | `#0000ff` | structural wall (preferred) |
| **PURPLE** | `#8000ff` | structural wall (alternate, accepted) |

**Do NOT use** red / green / magenta / orange — they are reserved for
openings, wall labels, unhosted markers, and merged-cell highlights.

## Workflow

1. Generate the base annotation image:
   ```powershell
   .venv\Scripts\python.exe -m tools.render_human_walls_annotation_base `
       --pdf planta_74.pdf `
       --consensus runs/vector/consensus_human.json `
       --out fixtures/planta_74/human_walls_annotation_base.png
   ```
   This produces a PNG showing the PDF, the existing walls (gray with
   red IDs), the merged cells highlighted in yellow, and each unhosted
   opening marked with a red X.

2. Paint missing walls on top of the base image in **BLUE `#0000ff`**.
   Each blob = one wall. Use solid filled rectangles whose long axis
   IS the wall centerline. Save as
   `fixtures/planta_74/human_walls_annotation.png`.

3. Extract:
   ```powershell
   .venv\Scripts\python.exe -m tools.extract_human_walls `
       fixtures/planta_74/human_walls_annotation.png `
       --consensus runs/vector/consensus_human.json `
       --out fixtures/planta_74/human_walls_truth.json
   ```
   The extractor auto-calibrates image-px ↔ PDF-pt using the existing
   walls (same approach as openings extraction), then runs connected
   components per color, derives each wall's orientation/start/end from
   the bbox, and inherits `thickness` from the consensus (no
   invention).

4. Apply to consensus and rebuild rooms via polygonize:
   ```powershell
   .venv\Scripts\python.exe -m tools.apply_human_walls `
       --consensus runs/vector/consensus_human.json `
       --truth fixtures/planta_74/human_walls_truth.json `
       --out runs/vector/consensus_with_human_walls.json
   ```

5. Verify gates:
   ```powershell
   .venv\Scripts\python.exe -m tools.verify_after_human_walls `
       --consensus-after runs/vector/consensus_with_human_walls.json `
       --consensus-before runs/vector/consensus_human.json `
       --out fixtures/planta_74/after_human_walls_report.json `
       --strict
   ```
   Gates:
   - G-W1: room count ≥ expected_rooms_min (default 10)
   - G-W2: no merged cells remaining
   - G-W3: 0 unhosted human openings (h_o005 must find a wall)
   - G-W4: all 12 human openings re-validated against augmented walls
   - G-W5: global visual fidelity (advisory — reviewer confirms via
           side-by-side)

6. Render the after artifacts:
   ```powershell
   .venv\Scripts\python.exe -m tools.render_human_openings_overlay `
       --pdf planta_74.pdf `
       --truth fixtures/planta_74/human_openings_truth.json `
       --consensus runs/vector/consensus_with_human_walls.json `
       --out fixtures/planta_74/rooms_after_human_walls_overlay.png

   .venv\Scripts\python.exe -m tools.render_preflight `
       runs/vector/consensus_with_human_walls.json `
       --pdf planta_74.pdf `
       --out-fidelity fixtures/planta_74/skp_after_human_walls_axon.png `
       --out-side-by-side fixtures/planta_74/side_by_side_pdf_vs_skp_after_human_walls.png `
       --out-door-audit fixtures/planta_74/door_audit_after_human_walls.png `
       --out-notes fixtures/planta_74/notes_after_human_walls.md
   ```

7. Export final SKP:
   ```powershell
   .venv\Scripts\python.exe scripts/smoke/smoke_skp_export.py `
       --consensus runs/vector/consensus_with_human_walls.json `
       --force-skp
   ```

## Acceptance gates (cycle FAILs unless ALL pass)

| Gate | Meaning |
|---|---|
| `G-W1` room count | ≥ 10 cells (was 7 before walls) |
| `G-W2` merged cells | 0 cells with "X \| Y" name pattern |
| `G-W3` unhosted | 0 openings classified `unhosted` on augmented walls |
| `G-W4` re-host | all 12 human openings re-validate |
| `G-W5` visual side-by-side | operator confirms PDF ↔ SKP match |

## Files written by this pipeline

| Path | Step | What |
|---|---|---|
| `human_walls_annotation_base.png` | 1 | Base image (auto-generated) |
| `human_walls_annotation.png` | 2 | **Reviewer's paint — INPUT** |
| `human_walls_truth.json` | 3 | Extracted walls |
| `consensus_with_human_walls.json` | 4 | Consensus + new walls + rebuilt rooms |
| `after_human_walls_report.json` | 5 | Gate verdict |
| `rooms_after_human_walls_overlay.png` | 6 | PDF + paint + final cells |
| `side_by_side_pdf_vs_skp_after_human_walls.png` | 6 | PDF \| axon final |
| `door_audit_after_human_walls.png` | 6 | Top-down openings |
| `notes_after_human_walls.md` | 6 | 10-point checklist |
| `model.skp` (under `runs/smoke/<ts>/`) | 7 | Final SKP, 80+ KB |

Schema: `fixtures/planta_74/human_walls_truth.schema.json`.

## Notes from the FP-014 P0 cycle

This protocol is the third leg of the human ground-truth approach:

1. **Human openings** (PRs #112–#120) — reviewer paints doors, windows,
   balconies. Pipeline extracts → applies → gate.
2. **Human walls** (this PR) — reviewer paints structural divisors
   that stage-1 wall extraction missed. Pipeline same shape.
3. (Future) **Human soft barriers** — same shape, for peitoris that
   should bound terraços without being load-bearing walls.

The audit in `docs/diagnostics/2026-05-11_wall_candidates_audit.md`
established that the missing dividers between A.S./TERRACO SOCIAL/
COZINHA/TERRACO TECNICO + SALA ESTAR/SALA JANTAR are not drawn as
filled paths in the source PDF. There is no algorithmic fix that
extracts walls that aren't there — human annotation is the
architecturally-correct path.

The annotation is **not synthetic substitution**. The reviewer sees
the PDF, sees the merged cells, and marks where the architect
intended walls to be. The pipeline trusts the reviewer.
