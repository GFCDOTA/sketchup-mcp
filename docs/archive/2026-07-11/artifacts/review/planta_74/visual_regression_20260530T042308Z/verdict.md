# Visual regression gate — planta_74 (door_flat_swing_patch)

Generated: 20260530T042308Z

Montage: `artifacts/review/planta_74/visual_regression_20260530T042308Z/montage_pdf_before_after.png`

## Hard FAIL checklist (any True => WORSE)

- [x] doors disappear or become useless lines   <-- AFTER: door leaves flattened to ~2cm, effectively invisible
- [ ] gray walls/blocks invade rooms            (unchanged: same in BEFORE and AFTER)
- [ ] colored floors leak / do not respect walls (unchanged)
- [x] openings become less legible              <-- door swing arcs no longer readable in AFTER
- [ ] model is more blocky than the baseline    (~same; walls untouched)
- [x] plan is less recognizable vs the PDF      <-- PDF shows clear door arcs; AFTER shows nothing at doors

## Verdict (filled by LOOKING — not pytest/counts/exit-0)

VERDICT: WORSE
REASON: door-only patch made doors invisible/illegible (hard FAIL) and improved nothing whole-plan; walls/floors/scale unchanged, so AFTER is not more like the PDF than BEFORE.
ACTION: reverted (git checkout tools/build_plan_shell_skp.rb -> DOOR_HEIGHT_M back to 2.10). NOT promoted. The local opening-audit (5/7 doors WARN->PASS, exit 0) was NOT evidence of visual improvement — the whole-plan 3-way gate is.
