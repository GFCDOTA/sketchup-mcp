# Decision — planta_74 window provenance fix (FP-031)

## Problem (user-reported, then proven)
The window-frame patch put framed windows on the wrong wall + left real glass
unframed. Audit proved WHY: the 4 window openings (o007–o010) exist in the PDF
but the consensus `wall_id`/hosting is geometrically broken — centers sit in
wall-segment gaps, host walls don't span them. `find_wall_face_for_aperture`
fell back to the first facade spanning the x-range (north wall, y≈669in) and
carved there → "invented window on the wrong wall"; the glass (host.start.y)
stayed on the right line. Doors (o000–006) + balcony (o011): correct, untouched.

## Fix (builder only, no fixture mutation)
1. **`find_wall_face_for_aperture` now requires the candidate face to belong to
   the HOST wall** (`|face_pos − host.start| ≤ thickness+4in`). It returns nil
   instead of carving a wrong parallel facade.
2. **Window path = aperture-first, panel-fallback.** If the host face is found
   (clean wall → quadrado), carve the 3D see-through aperture (unchanged). If
   not (planta_74's gap-hosted windows), fall back to `build_window_panel`
   (peitoril 0–0.9 / glass 0.9–2.1 / verga 2.1–2.7) AT THE OPENING CENTER —
   the exact spot the glass resolves to and the PDF audit confirmed.

## Verification (data + visual + tests)
- **quadrado** (reference): `WindowGlass_Group=1` (aperture), `Window_Group=0`.
  iso identical to canonical → **see-through window preserved**.
- **planta_74**: `Window_Group=4` at opening centers (dist 0.0–0.1in),
  `WindowGlass(aperture)=0` → all 4 fell back to panel **on the correct wall**.
  Invented wrong-wall windows **gone**.
- Gates green both. **pytest 223 passed, 5 skipped** (= baseline).
- Scale unchanged (PT_TO_M=0.0252 via env, default 0.0352 intact).

## Honest caveats (not overclaiming)
- planta_74 windows are now **panels co-located with the solid south wall** =
  peitoril+glass+verga BANDS at the correct location, not a see-through hole
  (the shell is solid there; the consensus represents these walls as solid). No
  z-fighting seen, but it is a surface representation, not a true aperture.
- The root cause is **broken consensus data** (opening→wall_id). The builder
  now works around it; fixing the fixture itself would need explicit approval
  (CLAUDE.md #3) and is the cleaner long-term fix.
- "Faithful" not claimed — scale + window placement are the confirmed fixes;
  open-plan room warnings remain documented.

## Artifacts
`model.skp` · `model_iso.png` · `model_top.png` · `geometry_report.json` ·
`pdf_before_after_panel.png` (PDF‖invented‖correct) · `before_after_removal.png`
· `quadrado_aperture_preserved.png` · `AUDIT.md` (full provenance table).
</content>
