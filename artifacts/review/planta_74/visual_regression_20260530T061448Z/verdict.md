# Visual regression gate — planta_74 (scale_candidate_0.0252_vs_baseline_0.0352)

Generated: 20260530T061448Z

Montage: `artifacts\review\planta_74\visual_regression_20260530T061448Z\montage_pdf_before_after.png`

## Hard FAIL checklist (any True => WORSE)

- [ ] doors disappear or become useless lines
- [ ] gray walls/blocks invade rooms
- [ ] colored floors leak / do not respect walls
- [ ] openings become less legible
- [ ] model is more blocky than the baseline
- [ ] plan is less recognizable vs the PDF

## Verdict (fill by LOOKING — not pytest/counts/exit-0)

VERDICT: <IMPROVED | SAME | WORSE>
REASON: <one line, whole-plan vs PDF>
ACTION: <promote | revert | adjust>  (SAME or WORSE => revert/adjust now)
