# Decision — planta_74 fidelity loop run (OFFLINE_DATA_ONLY)

Mode: `OFFLINE_DATA_ONLY` (no GPT/Chrome). Verifier = deterministic PDF overlay
+ PDF door-arc measurement (`tools/pdf_overlay_verify.py`) + `opening_audit.py`.

## The 5 visual suspicions, resolved against the PDF (ground truth)

| Suspicion | Verdict | Evidence |
|---|---|---|
| doors too big / panels | **FALSE_ALARM** | 7 PDF door-arcs vs consensus widths: ratio 0.98–1.09. h_o000=1.16m & h_o005=1.25m are genuinely wide doors in the PDF. |
| external right wall chamfered | **FALSE_ALARM** | consensus walls overlay exactly on the PDF perimeter (steps included); all 35 walls axis-aligned. |
| floor/color leaking | **FALSE_ALARM** | consensus room polygons fill WITHIN the walls on the overlay; gates floors_separated=✓. |
| blue glass / windows empty | **GEOMETRY_OK_RENDER_LEGIBILITY_BUG** | 5 glass elements 0.05–0.09m from their opening centers (placed); render does not communicate the thin/transparent glass. |
| central rooms not closed | **WARN_DOCUMENTED** | known_warnings open-plan (8 cells vs 11 ambients). |

**Headline: the planta_74 GEOMETRY/LAYOUT is FAITHFUL to the PDF.** The visual
"block model" impression is **representation + scale**, not layout bugs.

## CONFIRMED_BUG (1) — and the fix
**SCALE.** Builder PT_TO_M = 0.19/5.4 = 0.03519 assumes a 0.19 m wall. planta_74's
real scale (3 PDF cotas 5.45 / 2.60 / 2.40) = **~0.0252 m/pt** → builder is ~1.40x
too big (186 m² bbox vs ~95 m²). The overlay proves the consensus is faithful in
pdf-points, so the error is purely the pt->m anchor.

Fix applied (safe, reversible, no fixture mutation):
- Added `ENV['PT_TO_M']` override in `build_plan_shell_skp.rb` — **default
  unchanged** (quadrado etc. keep 0.0352); per-build override only.
- Built planta_74 with `PT_TO_M=0.0252` → PlanShell **12.71 x 7.53 m** (was
  17.74 x 10.51), cota 5.45m reproduced (212.5pt×0.0252=5.36m), **all gates pass**,
  **pytest 223 passed** (no regression).

## Status
- **Geometry/layout fidelity: PASS** (overlay-proven).
- **Scale: CONFIRMED_BUG → fix mechanism landed** (per-build env override; correct
  value 0.0252 demonstrated in /runs/, NOT committed as default).
- **Representation: still FAIL** — door leaf full-height-solid (reads as panel),
  glass legibility, soft-barrier solidity. These are NOT geometry; separate track,
  need visual iteration (the flat-door attempt was WORSE — reverted).
- Scale "looks" subtle in render (zoom_extents auto-fits); the fidelity gain is
  CORRECT ABSOLUTE DIMENSIONS (cota-proven), not render prettiness.

## Next minimal (recommended, not yet done)
Representation track: door = thin leaf + a *legible* 2D swing arc on the floor
(not full-height solid, not invisible) — to be judged with before/after vs PDF.
