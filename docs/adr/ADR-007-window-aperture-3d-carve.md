# ADR-007 — Window apertures are 3D post-extrude carves, not 2D full-height carves + 3-band infill

> **Status:** Accepted (2026-05-24).
> **Decider:** Felipe (GFCDOTA) / Claude.
> **Cross-refs:** FP-024 (the bug), LL-016 (the positive rule),
> `docs/specs/quadrado_demo_spec.md` §6.4 (the in-place edit pattern
> this carve adopts), ADR-003 (`build_plan_shell_skp` overall design).

---

## Context

The `build_plan_shell_skp` exporter (Python + Ruby) historically
treated every opening — interior_door, interior_passage, window,
glazed_balcony — uniformly:

1. **Python phase**: subtract a rectangle (width × wall-thickness)
   from the 2D wall shell polygon BEFORE extrusion.
2. **Ruby phase**: extrude the carved shell to `WALL_HEIGHT_IN`
   (full wall height). The 2D-carved region becomes a full-height
   floor-to-ceiling void.
3. **Per-kind post-fill**:
   - `interior_door` → leaf at swing angle inside the void.
   - `interior_passage` → no fill (vão livre).
   - `glazed_balcony` → single full-height glass pane.
   - `window` → three stacked bands inside the void:
     - peitoril (sill) at z ∈ [0, WINDOW_SILL_IN], material PARAPET_RGB
     - vidro (glass) at z ∈ [WINDOW_SILL_IN, WINDOW_HEAD_IN], material GLASS_RGB
     - verga (lintel) at z ∈ [WINDOW_HEAD_IN, WALL_HEIGHT_IN], material LINTEL_RGB

For windows, this produced a wall STRUCTURE consisting of three
separate volumes (sill + glass + lintel) sitting INSIDE a floor-to-
ceiling shaft. Visually and semantically, this reads as "vertical
void with infill," not "wall with window aperture." The wall mass
continuity is **fake** — the sill and lintel are independent volumes
with their own materials, not the wall continuing past the aperture.

This violates the architectural model of a window: a window is a
**wall-hosted partial-height aperture** in an otherwise continuous
wall. The wall stays as wall material below the sill (peitoril /
parapet) AND above the head (verga / lintel). Only the glass band
is structurally distinct.

## Decision

**Windows do NOT undergo the 2D full-height carve.** Instead:

1. **Python phase** (`tools/build_plan_shell_skp.py`): openings whose
   normalised `kind_v5` is in `WINDOW_APERTURE_KINDS = {"window"}`
   are routed to a separate `window_apertures` list. They are **not**
   added to `carve_rects`. The wall shell polygon stays solid at
   the window position.

2. **Ruby phase** (`tools/build_plan_shell_skp.rb`): after extruding
   the solid wall shell, for each entry in the JSON's
   `window_apertures` list, call `build_window_aperture_3d`. That
   function:

   - Locates the PlanShell sub-group containing the host wall.
   - Finds the vertical (lateral) face on the host wall axis whose
     bounds contain the aperture position **AND** span the full
     wall height [0, WALL_HEIGHT_IN].
   - **Reads the face's fixed coordinate (y for horizontal walls,
     x for vertical walls) from the actual model** (LL-014; never
     hardcode — see `docs/specs/quadrado_demo_spec.md` §7.3 on
     float drift).
   - Adds a coplanar rectangle face at the aperture position,
     z ∈ [WINDOW_SILL_IN, WINDOW_HEAD_IN]. SU auto-splits the host
     face into [aperture sub-face] + [perimeter remainder]. The
     remainder is the wall mass that survives: below the sill +
     above the head + flanking the aperture.
   - `pushpull(-real_thickness_in)` drives the aperture sub-face
     through the wall. If the host wall thickness exactly matches
     the pushpull distance, SU merges the moved face with the
     opposite face and creates a real through-hole.
   - Adds a glass face at mid-thickness inside the aperture as a
     separate top-level `WindowGlass_Group_<id>` (lives outside
     the PlanShell_Group so it can be inspected, replaced, or
     toggled without touching the wall).

3. **`glazed_balcony` (porta-vidro) stays on the full-height carve
   path** — it is genuinely a floor-to-ceiling glass panel. Doors
   and passages likewise stay on the full-height carve path.

## Consequences

### Positive

- **Wall mass continuity restored.** The PlanShell_Group bbox now
  spans [0, WALL_HEIGHT_IN] regardless of how many windows the
  plan contains. Parapet and lintel are simply parts of the wall.
- **Visual fidelity.** A window now reads as a window. Quadrado
  fixture before/after evidence in
  `docs/diagnostics/2026-05-24_window_aperture_fix.png`.
- **Cleaner topology.** No `Window_Group_<id>_sill` /
  `Window_Group_<id>_lintel` sub-groups cluttering the report.
  Only `WindowGlass_Group_<id>` per window.
- **Aligns with the in-place edit pattern** documented in the
  quadrado spec §6.4 — the proven method for modifying a baseline
  SKP without rebuilding from scratch.

### Negative / risks

- **3D pushpull merge requires exact thickness match.** If the
  consensus's `wall_thickness_pts` drifts from the actual face-to-
  face distance after extrude, pushpull may leave a thin slab
  remnant inside the wall (see quadrado spec §7.3). Mitigation:
  the new code reads `host_wall['thickness']` and uses it directly,
  staying in PT_TO_IN units — same domain the extrude used. Float
  drift should be < ULP.
- **Build time increases marginally.** Each window now triggers a
  pushpull + glass face add inside the SU model. For planta_74's
  4 windows, this adds ~0.5 s to the build (negligible vs the
  ~8 s SU launch).
- **`build_window_panel` (the legacy 3-band emitter) is now dead
  code for window kinds.** It's preserved in the Ruby source for
  reference / potential reuse on plants where the new path fails;
  the dispatch in main no longer calls it for `kind_v5 == 'window'`.
  Should be deleted in a follow-up cleanup PR.

### Out of scope

- `tools/consume_consensus.rb` (the legacy wall-by-wall exporter)
  has the **same bug** (`add_window_panel` at line 486 emits the
  same 3-band infill). This PR does NOT fix it. The plan-shell
  builder is the production path; `consume_consensus.rb` is
  scheduled for deprecation. A follow-up may mirror the fix.

## Validation gates

Two test files lock the behaviour against regression:

- `tests/test_window_aperture_contract.py` (15 tests) — pure-Python
  contract checks. Windows must NEVER appear in `openings_carved`.
  Doors must NEVER appear in `window_apertures`. The kind sets are
  disjoint. Tests the planta_74 fixture explicitly (4 windows must
  all route to 3D path).
- `tests/test_window_aperture_geometry.py` (9 tests) — SKP/geometry
  invariants. PlanShell_Group must span full wall height.
  WindowGlass_Group must sit at exactly `[WINDOW_SILL_M, WINDOW_HEAD_M]`.
  Legacy `_sill` / `_lintel` group names must NOT appear in the
  geometry report.

The geometry tests **skip cleanly** when the SKP artifact isn't
present (CI-portable), but fail loudly when it IS present and the
window was miscarved.

## Implementation

- Python: `tools/build_plan_shell_skp.py` lines 94-156 (new
  constants + helpers), lines ~215-260 (skip-window-in-carve logic),
  lines ~340-360 (stats fields), lines ~370-385 (JSON output).
- Ruby: `tools/build_plan_shell_skp.rb` lines ~590-720 (new
  `build_window_aperture_3d` function), dispatch change at line
  ~975.
- Tests: `tests/test_window_aperture_contract.py`,
  `tests/test_window_aperture_geometry.py`.
- Memory: `docs/learning/lessons_learned.md` LL-016,
  `docs/learning/failure_patterns.md` FP-024,
  `CLAUDE.md` §10 `Recently fixed` + new §19 rule.

## Last updated

- 2026-05-24 — first version, commit `feature/window-aperture-semantics`.
