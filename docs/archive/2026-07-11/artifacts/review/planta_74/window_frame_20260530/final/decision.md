# Decision — planta_74 RENDER_LEGIBILITY cycle: window caixilho (frame)

Mode: OFFLINE_DATA_ONLY + visual (representation/legibility is inherently a
render-axis judgment; data gate cannot rule on it). Builder does NOT self-accept
— final visual sign-off is the human's (or GPT via Chrome).

## Problem (confirmed visually, evidence-first)
planta_74 windows on the right exterior wall (SUÍTE 01, SUÍTE 02, BANHO 01/02)
rendered as **raw gray voids** in the iso: the aperture is a real through-hole
with peitoril + verga preserved (geometry OK), but the only infill is a thin
mid-thickness glass pane that goes edge-on at the grazing iso angle and
disappears → the opening reads as a hole, not a window.
Verdict: **RENDER_LEGIBILITY_BUG** (not geometry/scale — those are unchanged).

## Why not alpha (superseded experiment)
GLASS_ALPHA=0.72 experiment = **FAIL_PARTIAL**: a thin pane is invisible
edge-on regardless of opacity, and a global glass change made the glazed_balcony
MORE dominant. Reverted, not committed. Legibility needs solid geometry (a
frame), not transparency tuning.

## Patch (minimal, representation-only, gated, reversible)
`ENV['WINDOW_FRAME']` per-build override in `tools/build_plan_shell_skp.rb`
(default OFF → quadrado + every pinned render/test byte-identical; same safe
pattern as PT_TO_M; no fixture mutation). When ON, each window aperture gets a
**caixilho**: 4 solid bars (FRAME_WIDTH 0.06 m, off-white) each in its own
isolated sub-group, pushpulled through the wall reveal (+1.2 cm proud), wrapped
in begin/rescue so a frame failure can never abort the build. Emitted ONLY in
`build_window_aperture_3d` (windows) — the glazed_balcony stays frameless so it
remains visually distinct (porta-vidro vs janela).

NOT touched: walls, perimeter, scale (PT_TO_M=0.0252), opening positions/sizes,
the aperture carve. Frame is purely additive geometry, like the glass pane.

## Result (built WINDOW_FRAME=1 PT_TO_M=0.0252 --force-skp)
- Data: geometry_report → **4 WindowFrame_Group**, 4 WindowGlass_Group,
  1 GlazedBalcony (unframed). All 4 frames emitted (none fell to rescue).
- Gates self-check: plan_shell_exists ✓ · wall_shell_single_group ✓ ·
  floors_separated ✓ · default_material_faces_zero ✓.
- No regression: **pytest 223 passed, 5 skipped** (= baseline; default path
  unchanged).
- PDF anchor: framed windows land exactly where the PDF marks windows
  (SUÍTE 01/02, BANHO) — frames added only on existing PDF-matched openings.

## Verdict (calibrated — no overconfidence)
On the legibility axis: **IMPROVED.** The bedroom/bathroom/right-facade windows
went from raw gray holes → legible framed windows; the balcony stays a distinct
blue glass. This is a render/representation improvement, objectively visible in
`before_after_iso.png`. It is NOT a claim that the whole plan is "faithful"
(scale + this legibility aid are the confirmed fixes so far; open-plan room
warnings remain documented). Final visual acceptance + promotion-to-default is
the human's call.

## Artifacts
`model.skp` · `model_iso.png` · `model_top.png` · `geometry_report.json` ·
`before_after_iso.png` (frame off→on) · `pdf_before_after.png` (PDF‖before‖after).

## Next options (pending human nod — committed behavior / PRs are the user's)
1. Promote WINDOW_FRAME to default-on (would change quadrado canonical render —
   needs sign-off + canonical re-pin).
2. Tune caixilho (color/width) if off-white 0.06 m reads too stark.
3. Keep gated + open a PR with the diff for review.
