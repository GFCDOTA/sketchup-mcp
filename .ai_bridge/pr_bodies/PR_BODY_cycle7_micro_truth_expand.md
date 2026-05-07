# feat(ground-truth): Cycle 7 — expand planta_74_micro to 4 rooms

**Branch**: `feature/micro-truth-expand-planta-74-cycle7` → `develop`
**Commit**: `d5ce23d`
**Compare URL**: https://github.com/GFCDOTA/sketchup-mcp/compare/develop...feature/micro-truth-expand-planta-74-cycle7

## Summary

- Raises external-truth coverage of `planta_74` from **1 → 4 rooms**
  (SALA DE ESTAR + SUITE 02 + BANHO 02 + COZINHA), the planned
  Cycle 7 from `.ai_bridge/TODO_NEXT.md`.
- Tightens `tests/test_micro_truth_gate.py::test_real_planta_74_micro_passes`
  to also assert that all four labels are audited (catches a
  regression where a room is silently dropped from the ground truth).
- All four rooms score **1.0** on both the canonical run and a
  freshly-built consensus from today's pipeline.

## What changed

- `ground_truth/planta_74_micro.json`
  - `SALA DE ESTAR` (unchanged — already validated in PR #48)
  - `SUITE 02` — area range [15, 40] m², openings [2, 6], asserts
    `BANHO 02` adjacency (master-bath invariant)
  - `BANHO 02` — area range [3, 12] m², openings [1, 4], asserts
    `SUITE 02` adjacency
  - `COZINHA` — area range [7, 18] m², openings [1, 4],
    `expected_adjacent_labels` intentionally **omitted** (see Risks)
  - `description` field rewritten + `notes` per room calibrated
    against today's pipeline run with explicit numeric anchors
- `tests/test_micro_truth_gate.py` — `test_real_planta_74_micro_passes`
  now asserts `audited_labels == {SALA, SUITE 02, BANHO 02, COZINHA}`
  in addition to the pre-existing `r["score"] >= 0.8`

## What did NOT change

- `tools/micro_truth_gate.py` — algorithm, scoring, schema all
  unchanged. Pure data + test additions.
- No source change to detector / classifier / Ruby / SketchUp.
- No schema bump (`schema_version` stays at `1.0` for both
  ground_truth and report).
- No threshold change in `classify/`, `topology/`, `openings/`.

## Validation

```
pytest tests/test_micro_truth_gate.py -v          # 20/20 PASS
pytest tests/test_planta_74_truth_gate.py \
       tests/test_coherence_audit.py \
       tests/test_micro_truth_gate.py -q          # 56/56 PASS

python -m tools.micro_truth_gate \
  runs/feature_room_context_2026_05_06/consensus_with_room_context.json \
  --ground-truth ground_truth/planta_74_micro.json \
  --out runs/.../micro_truth_report.json
# → [micro-truth] score=1.0 rooms=4 fired=0
# → 4/4 rooms each at 1.0; overall_score=1.0
```

Calibration anchors recorded in the JSON `notes`:
- SUITE 02: 32.03 m² / 28pt polygon / 4 openings touching
- BANHO 02:  6.24 m² / 14pt polygon / 3 openings touching
- COZINHA:  11.34 m² / 14pt polygon / 1 opening touching
- SALA DE ESTAR: 10.75 m² (unchanged from PR #48 baseline)

## Risks

1. **COZINHA has no required adjacency** — the only opening detected
   for COZINHA classifies the wall_left/wall_right as `[SUITE 02]`,
   which is architecturally implausible. Asserting
   `expected_adjacent_labels=["A.S."]` (architecturally correct) would
   fail today. Deferred until the room-context classifier reaches
   cozinha (likely Cycle 6, downstream).
2. **BANHO 02 spurious adjacencies** — detector reports `[LAVABO,
   SUITE 01, SUITE 02]`. Only `SUITE 02` is asserted; the other two
   appear to come from the **SUITE 01 polygon being oversized
   (69.91 m²)** — surfaced as a separate item in `.ai_bridge/TODO_NEXT.md`
   to investigate `rooms_from_seeds` for SUITE 01.
3. Detector retunes that move SUITE 02 outside [15, 40] m² or
   BANHO 02 outside [3, 12] m² will fire the gate. By design — the
   gate IS the regression detector.

## Rollback

```bash
git push origin --delete feature/micro-truth-expand-planta-74-cycle7
# post-merge:
git revert <merge-sha>
```

## Next steps

- Stack-clean PR for `.ai_bridge/` scaffolding (currently blocked by
  PR #52 entanglement; Opção B = cherry-pick onto fresh branch).
- Investigate the SUITE 01 oversized-polygon bug surfaced above.
- Then Cycle 6 (autorun inspector wiring) or Cycle 8 (RuboCop CI).
