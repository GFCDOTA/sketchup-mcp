# Fidelity Scorecard — planta_74

- generated_at: `2026-05-08T15:47:56.022037+00:00`
- expected: `ground_truth\planta_74\expected_model.json`
- observed: `runs\cycle8b\before\c3.json`
- global_fidelity: **0.69**

## Sub-scores

- room_score: 0.75
- count_score: 1.0
- adjacency_score: 0.421
- bbox_score: 1.0

## Hard fails

- hard_fail:area_in_range:SUITE 01 actual=69.905
- hard_fail:area_in_range:SUITE 02 actual=32.028
- hard_fail:adjacency_f1=0.42<0.60

## Warnings

_(none)_

## Suggested fixes

- tighten or promote tools.rooms_from_seeds --use-concave-hull (FP-012); recalibrate expected_area_m2_range only after the algorithm flips
- verify tools.classify_openings_by_room_context: openings.evidence.room_left/right are how adjacency is materialized today
