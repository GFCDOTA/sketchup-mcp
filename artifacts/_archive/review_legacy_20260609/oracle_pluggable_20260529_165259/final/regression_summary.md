# SKP Visual Review — `planta_74`

## Generated: 2026-05-29T16:53:03Z

## Consensus: `fixtures\planta_74\consensus_with_human_walls_and_soft_barriers.json`

## Attempts

| # | Verdict | Findings |
|---|---|---|
| canonical | WARN | 0 findings (artifacts\review\planta_74\oracle_pluggable_20260529_165259\final) |

## Final verdict: **BLOCKED**
> **BLOCKED reason**: --require-oracle was set but oracle status = `unavailable` (bridge unreachable at http://localhost:8765: URLError(ConnectionRefusedError(10061, 'Nenhuma conexão pôde ser feita porque a máquina de destino as recusou ativamente', None, 10061, None))). See `oracle_request_package/` for the request that would have been sent.

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
| SKP generation | FAIL | no .skp produced (or --image-source canonical) |
| Render generation | PASS |  |
| Side-by-side composite | PASS |  |
| Deterministic checks | PASS | 10 checks ran; 0 FAIL finding(s) |
| Visual oracle bridge | WARN | provider unreachable; package written for manual review |
| Human review required | yes | qualitative axes still need human/agent inline OR external review of oracle_request_package |

**Estimated maturity: 45%**

Honest caps:
- without functional visual oracle bridge: max ~70%
- with bridge + bounded positional heuristics: ~80–90%
- 100% is not promised

Oracle status: `unavailable` (bridge unreachable at http://localhost:8765: URLError(ConnectionRefusedError(10061, 'Nenhuma conexão pôde ser feita porque a máquina de destino as recusou ativamente', None, 10061, None)))

## Remaining qualitative review (non-deterministic axes)

Even with all numeric checks PASS, `global_visual` and
`scale_rotation` cannot be fully decided from numbers alone.
If oracle bridge is unavailable, a human or Claude inline must
inspect:

- `artifacts\review\planta_74\oracle_pluggable_20260529_165259\final/model_top.png`
- `artifacts\review\planta_74\oracle_pluggable_20260529_165259\final/model_iso.png`
- `artifacts\review\planta_74\oracle_pluggable_20260529_165259\final/side_by_side_pdf_vs_skp.png`

## Constitution #8 compliance

- SKP: MISSING
- model_top.png: OK
- model_iso.png: OK
- side_by_side_pdf_vs_skp.png: OK
- visual_findings.json: MISSING
- regression_summary.md: OK (this file)
