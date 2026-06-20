# SKP Visual Review — `planta_74`

## Generated: 2026-05-29T04:38:57Z

## Consensus: `fixtures\planta_74\consensus_with_human_walls_and_soft_barriers.json`

## Attempts

| # | Verdict | Findings |
|---|---|---|
| 0 | WARN | 0 findings (artifacts\review\planta_74\visual_oracle_bridge_20260529_maturity2\attempt_0) |

## Final verdict: **WARN**

## Axes (last attempt)

| Axis | Verdict | Evidence |
|---|---|---|
| `wall_fidelity` | PASS | No deterministic finding produced for this axis. |
| `door_fidelity` | PASS | No deterministic finding produced for this axis. |
| `window_fidelity` | PASS | No deterministic finding produced for this axis. |
| `room_fidelity` | PASS | No deterministic finding produced for this axis. |
| `scale_rotation` | WARN | Numeric heuristics cannot decide this axis; needs human/agent or oracle inline review of render PNGs and side-by-side composite. |
| `global_visual` | WARN | Numeric heuristics cannot decide this axis; needs human/agent or oracle inline review of render PNGs and side-by-side composite. |

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
| SKP generation | PASS |  |
| Render generation | PASS |  |
| Side-by-side composite | PASS |  |
| Deterministic checks | PASS | 10 checks ran; 0 FAIL finding(s) |
| Visual oracle bridge | WARN | bridge unreachable; deterministic-only mode |
| Human review required | yes | qualitative axes (global_visual, scale_rotation) still need human/agent inline review |

**Estimated maturity: 60%**

Honest caps:
- without functional visual oracle bridge: max ~70%
- with bridge + bounded positional heuristics: ~80–90%
- 100% is not promised

Oracle status: `unavailable` (bridge unreachable at http://localhost:8765)

## Remaining qualitative review (non-deterministic axes)

Even with all numeric checks PASS, `global_visual` and
`scale_rotation` cannot be fully decided from numbers alone.
If oracle bridge is unavailable, a human or Claude inline must
inspect:

- `artifacts\review\planta_74\visual_oracle_bridge_20260529_maturity2\final/model_top.png`
- `artifacts\review\planta_74\visual_oracle_bridge_20260529_maturity2\final/model_iso.png`
- `artifacts\review\planta_74\visual_oracle_bridge_20260529_maturity2\final/side_by_side_pdf_vs_skp.png`

## Constitution #8 compliance

- SKP: OK
- model_top.png: OK
- model_iso.png: OK
- side_by_side_pdf_vs_skp.png: OK
- visual_findings.json: OK
- regression_summary.md: OK (this file)
