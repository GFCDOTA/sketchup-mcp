# SKP Visual Review — `planta_74`

## Generated: 2026-06-02T05:14:24Z

## Consensus: `fixtures\planta_74\consensus_with_human_walls_and_soft_barriers.json`

## Attempts

| # | Verdict | Findings |
|---|---|---|
| 0 | WARN | 0 findings (runs\kitchen_fix\attempt_0) |

## Final verdict: **WARN**


## GPT Auto-Consult Gate (LL-024)

| Field | Value |
|---|---|
| mode | `auto` |
| triggered | `no` |
| trigger | `n/a` |
| status | `not_applicable` |
| question_file | `n/a` |
| response_file | `n/a` |
| decision | `unknown` |

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

- input_walls: `20`
- openings_carved: `8`
- window_apertures_3d: `4`
- slivers_removed: `0`
- consensus_kind_counts: `{'interior_door': 7, 'window': 4, 'glazed_balcony': 1}`
- group_counts: `{'PlanShell_Group': 1, 'Floor_Group': 8, 'SoftBarrier_Group': 1, 'DoorLeaf_Group': 7, 'WindowGlass_Group': 4, 'GlazedBalcony_Group': 1}`

## Validator maturity

| Layer | Status | Notes |
|---|---|---|
| SKP generation | PASS |  |
| Render generation | PASS |  |
| Side-by-side composite | PASS |  |
| Deterministic checks | PASS | 10 checks ran; 0 FAIL finding(s) |
| Visual oracle bridge | N/A | --oracle none |
| Human review required | yes | qualitative axes still need human/agent inline OR external review of oracle_request_package |

**Estimated maturity: 55%**

Honest caps:
- without functional visual oracle bridge: max ~70%
- with bridge + bounded positional heuristics: ~80–90%
- 100% is not promised

Oracle status: `n/a` (--oracle none)

## Remaining qualitative review (non-deterministic axes)

Even with all numeric checks PASS, `global_visual` and
`scale_rotation` cannot be fully decided from numbers alone.
If oracle bridge is unavailable, a human or Claude inline must
inspect:

- `runs\kitchen_fix\final/model_top.png`
- `runs\kitchen_fix\final/model_iso.png`
- `runs\kitchen_fix\final/side_by_side_pdf_vs_skp.png`

## Constitution #8 compliance

- SKP: OK
- model_top.png: OK
- model_iso.png: OK
- side_by_side_pdf_vs_skp.png: OK
- visual_findings.json: OK
- regression_summary.md: OK (this file)
