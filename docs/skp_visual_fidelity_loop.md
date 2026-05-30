# SKP Visual Fidelity Loop (canonical)

Operating contract for validating/correcting a generated `.skp` against its
source PDF. Default mode: **`OFFLINE_DATA_ONLY`** (no GPT/Chrome dependency).

## Validation hierarchy (cheapest + most reliable first)

1. **MANDATORY TECHNICAL GATE = data/geometry/overlay vs PDF.**
   PDF and `consensus.json` are both in pdf-points → overlaying consensus on the
   PDF raster is an *exact, deterministic* comparison (no calibration, no
   hallucination, ~1-2 s, no SketchUp, no GPU). This is the authoritative
   correctness check. Tools: `tools/pdf_overlay_verify.py` (walls/rooms/openings
   on PDF + PDF door-arc measurement), `tools/opening_audit.py`, the deterministic
   heuristics in `run_skp_visual_review.py`, `geometry_report.json`.
2. **Image/render = representation/legibility AUDIT, not a fidelity judge.**
   A render can look bad with correct geometry, or look fine with wrong geometry
   (e.g. zoom_extents auto-fit hides scale). Use renders to generate *leads*
   ("looks wrong"), never as the verdict. Empirically unreliable (overconfident).
3. **Code = a correction tool, not proof of fidelity.** Reading code finds logic
   bugs; it does not prove the plan matches the PDF.
4. **GPT / human = optional escalation, not a default dependency.** Use only when
   the overlay/data is INCONCLUSIVE, or the problem is purely visual/legibility.

## Anti-overconfidence rule
Never claim "the geometry is faithful." Say: **"the suspicions verified so far
have not confirmed a geometric bug; current problems appear to be scale /
representation / legibility."** A visual lead the data cannot disprove stays
**INCONCLUSIVE / NEEDS_PDF_OVERLAY**, never silently dismissed.

## Verdict taxonomy
`GEOMETRY_BUG` · `SCALE_BUG` · `RENDER_LEGIBILITY_BUG` · `FALSE_ALARM` ·
`INCONCLUSIVE` · `NEEDS_PDF_OVERLAY` · `GEOMETRY_OK_RENDER_LEGIBILITY_BUG` ·
`WARN_DOCUMENTED` · `PASS` · `FAIL`. Only a CONFIRMED bug
(`GEOMETRY_BUG`/`SCALE_BUG`/`RENDER_LEGIBILITY_BUG`) becomes a patch.

## Loop
1. (Re)generate the top-down PDF↔consensus overlay = the gate.
2. Run the gate on the fixture; bucket every finding into the taxonomy.
3. Pick **one** confirmed item of highest impact.
4. Apply the **minimal** patch (Builder does not approve its own result).
5. Regenerate `.skp` + top + iso + `pdf_vs_skp` + `before_after`.
6. **Acceptance requires PDF×SKP + before/after + no regression — a pretty iso
   render is NOT acceptance.** Save the `.skp` as a versioned human artifact.
7. Report: confirmed / fixed / before-after / improved-or-not / next item.

## Output (`artifacts/review/<plant>/<ts>/`)
`candidate.skp` · `top.png` · `iso.png` · `pdf_vs_skp.png` · `before_after.png` ·
`critic_report.md` (leads) · `verification_report.json` (verdicts+evidence) ·
`patch_plan.md` · `decision.md`. Mode marker: `OFFLINE_DATA_ONLY` / `CHROME_GPT`
/ `API_GPT`.

## Roles (same Claude may play all, but reports stay separated)
Builder (alters code/SKP, never self-approves) · Visual review (leads only) ·
Data Verifier (confirms/kills each lead in data — read-only) · Gate (decision).
Escalate to a 2nd agent / GPT-vision only on the triggers above. Never use
ChatGPT Desktop/computer-use (steals the screen). `/ask` text-only is for textual
decisions, never image judgment.
