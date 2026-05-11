# planta_74 human ground truth — openings annotations

This directory holds the **human-anotated ground truth** for openings
(doors, windows, glazed balconies) on `planta_74.pdf`. The human
annotation is **mandatory** — when present, it overrides any detector
output for openings.

## How to add an annotation

1. Render the planta as a PNG. Any of these work as a base layer:
   - `runs/preflight_apto74_2026_05_10/walls_numbered_for_annotation.png`
     (preferred — already shows wall ids w000..w032)
   - `runs/audit/planta_74_audit_overlay.png`
   - Or render fresh: `python -m tools.render_axon ... --out planta_74.png`

2. Paint annotation blobs on top in **pure** colors:
   - **#00ff00 GREEN** = interior_door (porta interior)
   - **#ff00ff MAGENTA** = window (janela)
   - **#ffa500 ORANGE** = glazed_balcony (porta-balcão)

   Each blob marks where a single opening lives. Shape: a small filled
   rectangle or ellipse covering the opening width is ideal. Pure
   colors only — no gradients, no shadows, no semi-transparency.

3. Save the result as `human_openings_annotation.png` in this directory.

4. Run the extraction:
   ```powershell
   .venv\Scripts\python.exe -m tools.extract_human_openings `
       fixtures/planta_74/human_openings_annotation.png `
       --consensus runs/vector/consensus_model.json `
       --out fixtures/planta_74/human_openings_truth.json
   ```

5. Apply to consensus:
   ```powershell
   .venv\Scripts\python.exe -m tools.apply_human_openings `
       --consensus runs/vector/consensus_model.json `
       --truth fixtures/planta_74/human_openings_truth.json `
       --out runs/vector/consensus_model_with_human_openings.json
   ```

6. Verify with structural_checks (will FAIL if counts/positions are
   wrong):
   ```powershell
   .venv\Scripts\python.exe -m tools.structural_checks `
       --consensus runs/vector/consensus_model_with_human_openings.json `
       --require-human-openings
   ```

7. Render overlay (PDF + human truth + detected openings):
   ```powershell
   .venv\Scripts\python.exe -m tools.render_human_openings_overlay `
       --pdf planta_74.pdf `
       --truth fixtures/planta_74/human_openings_truth.json `
       --consensus runs/vector/consensus_model_with_human_openings.json `
       --out fixtures/planta_74/human_openings_overlay.png
   ```

## Required counts (locked baseline)

| Color  | Kind            | Count |
|--------|-----------------|------:|
| green  | interior_door   |     7 |
| magenta| window          |     4 |
| orange | glazed_balcony  |     1 |
| **TOTAL** |              | **12** |

## Required-position constraints

These constraints are checked by `structural_checks` and FAIL the
gate if violated:

| Constraint | Description |
|---|---|
| `BANHO_02_west_door` | BANHO 02 must have a green door on its west (left) vertical wall, opening inward. Not the legacy w015 match. |
| `SALA_ESTAR_TERRACO_SOCIAL_balcony` | There must be an orange glazed_balcony between SALA DE ESTAR and TERRAÇO SOCIAL. |
| `SUITE_02_south_window` | SUITE 02 south opening is MAGENTA (window), NOT orange. |
| `NO_SUITE_01_BANHO_01_window` | There must NOT be any window between SUITE 01 and BANHO 01. |

The constraints are defined in `human_openings_truth.json` once
extracted (the schema embeds them) and re-validated on every run.

## Schema

See `human_openings_truth.schema.json` for the JSON Schema. Documented
in `docs/learning/human_openings_truth_protocol.md`.
