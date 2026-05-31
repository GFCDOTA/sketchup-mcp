# planta_74 consensus regeneration — VISUAL_REVIEW (promotion decision = Felipe)

FP-031 #28. Gate :8765 verdict = approach **B** (merge collinear walls + re-host
openings). Produced autonomously; **promotion to the canonical fixture is held
for your visual sign-off** (the render appearance changes).

## What changed (deterministic, machine-checked — NOT a visual self-judgement)
- `tools/regenerate_consensus.py`: collinear wall fragments merged
  (**35 → 19 walls**, duplicate h_w001≈w020 absorbed); every opening re-hosted to
  its nearest merged wall.
- Detectors on the regenerated consensus:
  - `opening_host_audit`: 9/12 FAIL → **PASS (0/12)**
  - `wall_overlap_audit`: 1 → **PASS (0)**
- Rebuilt SKP from the regenerated consensus (PT_TO_M=0.0252, deterministic cam):
  - windows: **panel-fallback ×4 → 3D APERTURE ×4** (`WindowGlass_Group`=4,
    `Window_Group`=0). The continuous merged wall lets `find_wall_face_for_aperture`
    find the solid face, so windows carve as **see-through apertures** (quadrado
    paradigm) instead of opaque surface panels.
  - gates_self_check: all ✓ · `overlay_diff` wall-presence: **PASS** (all 19 walls
    in-frame & present, sidecar_exact).

## Evidence
- `before_after_regen.png` — ANTES (raw 35-wall, panel windows) ‖ DEPOIS (regen
  19-wall, aperture windows), same deterministic camera.
- `model_iso.png` / `model_top.png` / `model.skp` / `geometry_report.json`
- `consensus_regenerated.json` — the candidate (NOT promoted).

## The decision is yours (VISUAL_REVIEW) — I did NOT auto-declare "improved"
Deterministically the regen is sound (detectors + gates + overlay all PASS, no
wall missing, no opening filled). What a machine can't certify is whether the
see-through windows land where the PDF actually has windows and read correctly —
that's the visual judgement.

**To promote** (only on your OK): replace
`fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json` with this
candidate (re-pin the smoke suite), then rebuild the canonical artifact. I left
the pinned fixture untouched.

Reject / tweak: say so and I adjust `bridge_gap` / merge tolerance and regenerate.
</content>
