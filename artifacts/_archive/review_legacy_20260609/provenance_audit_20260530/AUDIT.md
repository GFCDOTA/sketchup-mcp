# Provenance audit — planta_74 openings vs PDF (FP-031)

Evidence-first, deterministic. Each opening's consensus center drawn on the real
`planta_74.pdf` raster (pdf-points → exact) + per-opening zoom crops
(`runs/planta_74/audit/zoom_*.png`) + geometric nearest-wall check.

## Per-opening table

| ID | consensus type | PDF symbol @ center | wall/room | width | exists in PDF? | placement in build | ACTION |
|----|----|----|----|----|----|----|----|
| o000 | door | door swing arc | top-left | 0.83m | ✅ | OK | **KEEP** |
| o001 | door | door swing arc | LAVABO | 0.64m | ✅ | OK | **KEEP** |
| o002 | door | door swing arc | BANHO 01 | 0.61m | ✅ | OK | **KEEP** |
| o003 | door | door swing arc | w024 | 0.69m | ✅ | OK | **KEEP** |
| o004 | door | door swing arc | w012 | 0.69m | ✅ | OK | **KEEP** |
| o005 | door | door swing arc | A.S./kitchen | 0.89m | ✅ | OK | **KEEP** |
| o006 | door | door swing arc | BANHO 02 | 0.58m | ✅ | OK | **KEEP** |
| o007 | window | small bath window | BANHO 01 S | 0.52m | ✅ (likely) | **WRONG WALL** | REPRESENT_AS_WINDOW @ center |
| o008 | window | **3 glazing lines** | SUÍTE 01 S | 1.48m | ✅ confirmed | **WRONG WALL** | REPRESENT_AS_WINDOW @ center |
| o009 | window | small bath window | BANHO 02 S | 0.52m | ✅ (likely) | **WRONG WALL** | REPRESENT_AS_WINDOW @ center |
| o010 | window | **3 glazing lines** | SUÍTE 02 S | 1.29m | ✅ confirmed | **WRONG WALL** | REPRESENT_AS_WINDOW @ center |
| o011 | window→balcony | **porta-vidro** | SALA→TERRAÇO | 1.97m | ✅ confirmed | OK | **KEEP** (glass, no frame) |

**Zero openings are fabricated in the data** — all 12 exist in the PDF. Nothing to delete from the consensus.

## Root cause of the "invented windows on the wrong wall"

NOT invented data, NOT my frame inventing openings. A **pre-existing builder
placement bug** my frame made visible:

1. The 4 window openings (o007–o010) have **broken host-wall hosting** in the
   consensus: the stored `wall_id` (w018/w026/w030) is geometrically incoherent —
   e.g. o008 center x=433pt but host w018 spans only x=383–404pt and is narrower
   (0.53m) than the window (1.48m). The opening centers sit in **gaps / offsets
   (8–43pt = 0.2–1.1m)** between short wall segments.
2. `build_window_aperture_3d` → `find_wall_face_for_aperture` matched the FIRST
   y-perpendicular face merely spanning the window's x — the **north facade
   (w002, y≈680pt)** — and carved the hole there. The glass (which uses
   `host.start.y`) landed on the right line. Result proven by geometry_report:
   `glass=(…,515.1)` ✅ vs `frame/aperture=(…,669.4)` ❌, constant 669.4 for all 4.

So: hole+frame on a wall the PDF has no window on, real glass left orphan.

## What was done this cycle
- **Reverted** the frame patch.
- **Removed the invented windows**: `find_wall_face_for_aperture` now filters by
  the host wall's perpendicular position → the wrong-wall fallback is killed
  (`window_built=0`; right facade now solid). before/after:
  `runs/planta_74/placement_fix/before_after_removal.png`.
- Doors (o000–o006) + balcony (o011) verified correct — untouched.

## Open decision (premise changed → needs direction, no fixture mutation w/o OK)
The 4 real windows are now UNrepresented. To put them back **at the correct PDF
location** (their opening center, where the glass already correctly sits):
- **A. Panel at opening center** (peitoril+glass+verga via `build_window_panel`,
  no wall-carve). Builder-only, no fixture change. Fills the location.
- **B. Geometry-based host carve** — fix `find_wall_face_for_aperture` to pick the
  nearest correct wall face, keep the 3D-aperture path.
- **C. Fix the consensus** opening→wall_id mapping (needs explicit approval —
  CLAUDE.md hard rule #3: never mutate fixtures without it).
</content>
