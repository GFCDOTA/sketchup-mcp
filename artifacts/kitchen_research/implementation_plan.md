# Implementation Plan — Kitchen r004 (planta_74)

**Package title:** Coordinate the two-tone palette (warm the oak base into the fendi family) — kill the builder-grade bicolor.

**Role:** ORCHESTRATOR synthesis. SPEC ONLY. The serial applier (orchestrator) makes the edits below.
**Mandate guardrails respected:** kitchen-only; pia/parede/porta NOT moved; layout stays LINEAR (no U/L); zero geometry/measure change → all 12 gates PASS by construction; no `.skp`/`.rb` geometry edited by this package.

---

## Why THIS package (single, highest visual ROI)

CRITIC verdict = WARN. The form/integration already reads planned (fridge column, modulation, embedded cooktop/sink, plinth). The CRITIC's **priority-1 defect #1** is the loudest thing the eye hits and the one the **flat render can actually show**: a simultaneous big jump in BOTH value and chroma between the medium-saturated oak base `[171,140,100]` and the warm-fendi uppers `[224,215,199]`. That two-material clash is the signature of a store builder-grade kit, not coordinated joinery.

This is the right pick because it is:
- **Flat-render visible** — pure color reads in flat SU shading (no V-Ray needed to see it). The biggest ROI per the rule "prioritize what the flat-render can show (color/form/joint)".
- **Pure data** — touches only the `_KC` color dict in `kitchen_layout.py` (the brain's palette table), no geometry, no footprint, no measure. Every gate (kitchen_validation, geometry_sanity, furniture_overlap_gate, kitchen_ergonomics) is untouched because no box position/size changes.
- **Smallest safe diff** — a handful of RGB triples.

The CRITIC's **priority-1 defect #2** (aereo→fridge-column gap / diagonal stub) is GEOMETRY — it edits the box layout in `kitchen_layout.py:363-378` (the `aereo_fridge`/`filler` arrangement) and would require re-running the overlap + validation gates. That is OUTSIDE this package's mandate. It is the right NEXT package but must be done as a geometry change with the gates re-run; flagged in "orchestrator_followup" below, NOT applied here.

---

## Concrete edits (orchestrator applies SERIAL)

All edits are in **one file**: `E:/Claude/apps/sketchup-mcp/tools/kitchen_layout.py`, in the `_KC` color dict (lines 57-72). They are data-only.

### Edit 1 — warm + lighten the oak base into the fendi family (CRITIC priority-1 #1)
- **File:** `tools/kitchen_layout.py`
- **Line 58:** change
  `"corpo": [171, 140, 100], "porta": [176, 145, 104], "gaveta": [176, 145, 104],`
  to
  `"corpo": [191, 167, 137], "porta": [195, 171, 141], "gaveta": [195, 171, 141],`
- **Why:** Dessaturate ~15% and lighten ~18% so the base lands in the same warm-neutral family as the fendi uppers `[224,215,199]`. Result = ONE tonal step (warmer/darker base → lighter upper), a coordinated palette, instead of two materials fighting. Keep `corpo_sup`/`porta_sup`/`filler` (the uppers) EXACTLY as they are — the CRITIC said uppers are fine. The proud ~30-point value gap base↔upper is what we WANT (reads as a deliberate two-tone), it's the chroma war we're killing.

### Edit 2 — protect the signature niche accent from going muddy (consequence of Edit 1)
- **File:** `tools/kitchen_layout.py`
- **Line 62:** change
  `"niche_wood": [162, 130, 90],`
  to
  `"niche_wood": [138, 104, 66],`
- **Why:** The open niche bay (`upper_niche` token) is the signature element that breaks the off-white upper run. Its current wood `[162,130,90]` was chosen to contrast against the OLD darker base. After Edit 1 the base becomes `[191,167,137]` — only ~25 points darker than the old niche wood, so the accent would flatten into "just another warm panel". Push the niche wood DARKER/richer so it stays the deliberate dark-wood focal accent against the now-coordinated lighter cabinetry. This keeps the two-tone hierarchy: light fendi uppers → mid warm base → dark wood accent (niche). Pure recolor of one existing role; geometry untouched.

### Edit 3 (optional, same package) — soften the board/decor wood to track the new base
- **File:** `tools/kitchen_layout.py`
- **Line 70:** in `"board": [176, 145, 104], ...` change ONLY the board value to
  `"board": [150, 116, 78],`
- **Why:** The cutting board on the counter was matched to the OLD base `[176,145,104]`; after Edit 1 it would read identical to the new base and disappear. A slightly darker warm wood keeps it as a distinct prop. Low ROI but trivial and consistent; orchestrator may skip if minimizing diff.

**Net diff:** 3 lines, RGB-only, all in the `_KC` dict. No box, no position, no measure, no module count, no `.rb`.

---

## Verification the orchestrator MUST run after applying (proves the gates still PASS)

```
cd /e/Claude/apps/sketchup-mcp
PT_TO_M=0.0259 .venv/Scripts/python.exe -m tools.kitchen_validation r004
PT_TO_M=0.0259 .venv/Scripts/python.exe -m tools.geometry_sanity r004
PT_TO_M=0.0259 .venv/Scripts/python.exe -m tools.furniture_overlap_gate r004
PT_TO_M=0.0259 .venv/Scripts/python.exe -m tools.kitchen_ergonomics r004
```
Expected: all 4 PASS, IDENTICAL to baseline (no geometry changed, so they cannot move). If any gate's numbers shift, the orchestrator edited the wrong thing — revert.

Then regenerate the flat .skp + flat render and put it side-by-side with the PDF for the **GPT visual verdict** (the agent NEVER self-judges IMPROVED/SAME/WORSE — gpt-review-gate). The expected read: base and uppers now look like coordinated joinery (one warm family, one tonal step), the niche bay still pops as the dark-wood accent. That is the flat-visible payoff of this package.

---

## What this package deliberately does NOT touch (so the orchestrator knows the boundary)

- **No geometry.** The aereo→fridge gap, the backsplash break, and the aereo-module-alignment (CRITIC priority-1 #2 and priority-2 #3/#4) are all geometry edits to `kitchen_layout.py` box layout and are OUT of this package. They need the overlap/validation gates re-run and a fresh visual verdict — separate serial packages.
- **No `.skp`/`.rb`.** vray_export.rb is correct as-is for the kitchen (see v_ray_followup note 1 — the kc_* keys are ALREADY in the tex_map at lines 25-26, contrary to one stale agent note; do NOT re-add them).

---

## v_ray_followup (only V-Ray can show these — NOT in this flat package)

1. **kc_* textures already wired — do NOT touch.** `tools/vray_export.rb:25-26` ALREADY maps `ph_kc_corpo/porta/gaveta/niche_wood/board → wood_medium.png` and `ph_kc_tampo/backsplash → stone_counter.png`. The BUILDER_SPECS note claiming these keys are "missing from tex_map" is STALE — verified by reading the file. Re-adding them is a no-op at best, a duplicate-key risk at worst. Skip.
   - One real consequence for Edit 1: after warming the oak base in the brain, the V-Ray render swaps the solid color for `wood_medium.png` (a darker `[150,108,70]`-based grain). The flat render shows the new coordinated color; the V-Ray render shows wood grain. Confirm in V-Ray that `wood_medium.png` still reads coordinated against the fendi uppers — if the textured base looks too dark vs the warmer flat color, the followup is to lighten `wood_medium`'s base in `gen_textures.py:159` toward the new `[191,167,137]` family. Flat first; V-Ray tune second.
2. **Veined stone backsplash (premium read).** The CRITIC priority-2 "pelado backsplash" + BUILDER_SPECS `stone_veined.png` proposal: add a directional book-match `stone_veined()` to `gen_textures.py` and point `ph_kc_tampo/backsplash` at it. Veins are a V-Ray texture thing — invisible in flat. Real ROI but lives entirely in V-Ray. Watch UV orientation (transpose the linspace axis if veins render vertical). Deferred.
3. **Inox reflection / LED glow / stone sheen.** Per the task brief, the inox fridge reflection, the 2700K LED strip emission, and the stone sheen only appear under V-Ray (emissive + reflective BRDF). Flat render shows them as solid color only. No flat action; these are the V-Ray pass payoff.
4. **Dark wood for the niche bay under V-Ray.** After Edit 2 darkens `niche_wood` in the brain, the V-Ray followup (BUILDER_SPECS) is to point `ph_kc_niche_wood → wood_dark.png` (instead of wood_medium) so the signature bay gets a distinct dark grain, not just a darker solid. Material-only, no gate risk, but it's a vray_export.rb edit → orchestrator's V-Ray pass, not this flat package.
