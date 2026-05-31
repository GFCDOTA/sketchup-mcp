# SKP Visual Review — `planta_74`

## Generated: 2026-05-29T18:46:55Z

## Consensus: `fixtures\planta_74\consensus_with_human_walls_and_soft_barriers.json`

## Attempts

| # | Verdict | Findings |
|---|---|---|
| canonical | WARN_documented | 0 findings (artifacts\review\planta_74\oracle_backend_20260529_184609\final) |

## Final verdict: **WARN_documented**


## Verdict aggregation

- **oracle_verdict**: `PASS`
- **deterministic_verdict**: `PASS`
- **carried_known_warnings_verdict**: `WARN_documented`
- **final_verdict = worst(oracle, deterministic, carried_known_warnings)** = `WARN_documented`

> The visual oracle provider is working, but its PASS does
> not override known architectural WARNs. The canonical
> `planta_74` status remains the aggregate above.

### Known warnings carried for this fixture

- room_fidelity: 8 cells vs 11 semantic ambients, open-plan documented
- wall_fidelity: SoftBarrier_Group_7 / sb007: plausible architectural element wrapping BANHO 02 perimeter, but no explicit PEITORIL/MURETA label in PDF
- wall_fidelity: SoftBarrier_Group_1: 0.01 m^2 sliver (19cm x 4cm), not visible at render distance, policy choice
## Axes (last attempt)

| Axis | Verdict | Evidence |
|---|---|---|
| `wall_fidelity` | WARN | All walls appear to be correctly represented. | Downgraded by known_warnings_carried for this fixture. |
| `door_fidelity` | PASS | Doors are correctly represented and aligned. |
| `window_fidelity` | PASS | Windows are correctly represented and aligned. |
| `room_fidelity` | WARN | Rooms are correctly represented and aligned. | Downgraded by known_warnings_carried for this fixture. |
| `scale_rotation` | PASS | The model is correctly scaled and oriented. |
| `global_visual` | PASS | The overall visual representation is accurate and consistent with the PDF floor plan. |

## Input summary (last attempt)

- input_walls: `35`
- openings_carved: `8`
- window_apertures_3d: `4`
- slivers_removed: `0`
- consensus_kind_counts: `{'interior_door': 7, 'window': 4, 'glazed_balcony': 1}`
- group_counts: `{'PlanShell_Group': 1, 'Floor_Group': 8, 'SoftBarrier_Group': 7, 'DoorLeaf_Group': 7, 'WindowGlass_Group': 4, 'GlazedBalcony_Group': 1}`

## Validator maturity

| Layer | Status | Notes |
|---|---|---|
| SKP generation | FAIL | no .skp produced (or --image-source canonical) |
| Render generation | PASS |  |
| Side-by-side composite | PASS |  |
| Deterministic checks | PASS | 10 checks ran; 0 FAIL finding(s) |
| Visual oracle bridge | PASS | provider returned normalized v1 findings |
| Human review required | no | oracle bridge + deterministic checks cover decision |

**Estimated maturity: 65%**

Honest caps:
- without functional visual oracle bridge: max ~70%
- with bridge + bounded positional heuristics: ~80–90%
- 100% is not promised

Oracle status: `ok` (ollama qwen2.5vl:7b returned valid visual_findings.v1)

## Remaining qualitative review (non-deterministic axes)

Even with all numeric checks PASS, `global_visual` and
`scale_rotation` cannot be fully decided from numbers alone.
If oracle bridge is unavailable, a human or Claude inline must
inspect:

- `artifacts\review\planta_74\oracle_backend_20260529_184609\final/model_top.png`
- `artifacts\review\planta_74\oracle_backend_20260529_184609\final/model_iso.png`
- `artifacts\review\planta_74\oracle_backend_20260529_184609\final/side_by_side_pdf_vs_skp.png`

## Constitution #8 compliance

- SKP: MISSING
- model_top.png: OK
- model_iso.png: OK
- side_by_side_pdf_vs_skp.png: OK
- visual_findings.json: OK
- regression_summary.md: OK (this file)
