# Scale experiment — EVIDENCE ONLY (no visual judgment)

Status: **AWAITING_GPT_VISUAL_REVIEW_CHROME**

Claude did NOT classify IMPROVED/SAME/WORSE. The .skp is in /runs/ (scratch),
NOT promoted, NOT committed as canonical, no PR. Builder reverted to baseline
(git clean). Only PT_TO_M was changed temporarily; door height stayed baseline
(2.10 m), so this isolates the SCALE effect.

## Scales
- current builder PT_TO_M = 0.19/5.4 = **0.03519 m/pt** (baseline)
- candidate PT_TO_M = **0.0252 m/pt** (from PDF cotas 5.45 / 2.60 / 2.40; see
  artifacts/review/planta_74/scale_anchor_candidate_report.md)
- ratio 0.715 -> baseline is ~1.40x too big

## Measured apartment (PlanShell bbox, deterministic — not a visual claim)
- baseline (0.0352): **17.74 x 10.51 m**
- scale_candidate (0.0252): **12.71 x 7.53 m**

## Technical note (NOT a verdict — to focus the visual review)
The renders use SketchUp `zoom_extents` (auto-fit to viewport). A UNIFORM scale
change therefore does NOT change the plan layout or relative wall-thickness in
the render — those scale together. What it DOES change is the proportion of the
FIXED-height elements relative to the now-smaller footprint:
- wall height 2.70 m and door height 2.10 m are absolute (meters), so at the
  candidate scale they read TALLER relative to the rooms (e.g. a 5 m room ->
  ~3.6 m at candidate, so a 2.70 m wall goes from ~54% to ~75% of room width).
So compare BEFORE vs AFTER for **ceiling-height-to-room proportion / overall
"too flat vs realistic"**, not for a different floor-plan shape.

## Artifacts for GPT visual review (via Chrome only)
- PDF ground truth: runs/planta_74/pdf_plan_region.png
- baseline FAIL (0.0352): runs/planta_74/before_top.png , runs/planta_74/before_iso.png
- scale_candidate (0.0252): runs/planta_74/scale_candidate/model_top.png , model_iso.png , model.skp
- montage PDF x baseline x scale_candidate: artifacts/review/planta_74/visual_regression_20260530T061448Z/montage_pdf_before_after.png

## When Chrome connects
Send the montage to GPT web; ask IMPROVED / SAME / WORSE (candidate vs baseline,
vs the PDF as a whole). IMPROVED -> prepare small patch/PR (mark PASS parcial if
the whole still FAILs). SAME/WORSE -> discard candidate scale, keep this as
evidence, do not promote.
