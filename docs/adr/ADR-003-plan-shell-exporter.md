# ADR-003 — `build_plan_shell_skp` (experimental parallel exporter)

> **Status:** Accepted (2026-05-20) as an **experimental, parallel
> exporter**. NOT a replacement for `consume_consensus.rb`.
> **Author:** Claude session, authorised by Felipe.
> **Related:** ADR-001 (overrides surface), ADR-002 (room polygon
> overrides), `docs/protocols/visual_fidelity_gate_protocol.md`,
> `docs/learning/failure_patterns.md` FP-014 (autorun cleanup),
> `tools/consume_consensus.rb` (the production exporter, not touched).
>
> **Scope of this ADR:** introduces a NEW, isolated entry point
> (`tools/build_plan_shell_skp.{py,rb}`) for generating a `.skp` from
> a `consensus_model.json` using a paradigm different from
> `consume_consensus.rb`. The production exporter and all its CI
> integration remain unchanged. This ADR does NOT propose retiring or
> replacing `consume_consensus.rb`; it documents an alternative we are
> evaluating in isolation.

---

## 1. Context

The production exporter `consume_consensus.rb` emits **one
`Sketchup::Group` per wall** (`group.name = wall['id']`). For a real
floor plan like `planta_74` (35 walls, 12 openings, 8 rooms,
9 soft_barriers), this produces:

- 35 wall groups at the top level of the model.
- At every internal corner where two perpendicular walls meet, the
  thickness footprints of those walls **occupy the same cell**. With
  one `Sketchup::Group` per wall, that cell becomes a geometric
  duplicate — the corner is "inside" both groups simultaneously.
  Visually: a faint extra edge at each corner; structurally: a
  micro-pillar of overlap volume.
- Long straight runs of wall composed of multiple consensus segments
  (planta_74 has 13 such colinear runs covering 28 of 35 walls) read
  as a sequence of separate slabs with visible vertical edges
  between them, instead of as a single continuous wall surface.

This was demonstrated end-to-end first on a single-room ring exporter
(`tools/build_room_ring_skp.{py,rb}`, also untracked): one face with a
hole, one `pushpull`, zero corner overlap. The user requested that the
same paradigm be tried at the **whole-plan scale**, without touching
production.

Walls in `planta_74`'s consensus have **endpoint-share ratio = 1.000**
(every endpoint coordinate is unique). They are *centerline segments*,
not a graph-connected wall network. A naive "per-room ring" would
double-count any wall shared between two adjacent rooms — but
planta_74's consensus doesn't have that problem because no walls are
shared (each room's bounding walls are independent segments).

## 2. Decision

Implement a parallel, experimental exporter in two files:

- `tools/build_plan_shell_skp.py` — Python launcher + 2D geometry.
- `tools/build_plan_shell_skp.rb` — SketchUp Ruby builder.

Algorithm (Python phase):

1. **Wall footprints** — for each wall, build the rectangle
   `(centerline ± thickness/2)`. Identical to the corner computation
   in `consume_consensus.rb` lines 67-90 (`add_wall_volume`).
2. **`shapely.unary_union`** of all wall footprints. Corners merge
   into a continuous shell; no manual per-corner reconciliation.
3. **`buffer(eps, join_style=mitre).buffer(-eps, mitre)`** with
   `eps = 0.1 pt` to bridge sub-pixel endpoint mismatches without
   rounding right angles. Mitre joins preserve axis-aligned geometry
   exactly; round joins would replace each corner with a 16-segment
   arc (rejected by initial unit tests).
4. **Subtract opening rectangles** in 2D before extrusion. Each
   opening becomes a rectangle aligned with its host wall's axis
   spanning `opening_width_pts × wall_thickness`. The subtraction
   produces a clean door gap in the shell — no post-extrusion
   boolean operations needed.
5. **Sliver filter** at `MIN_SLIVER_AREA_PTS2 = 0.5 pt²` drops
   numerical-noise polygons from the boolean ops.
6. **Serialise** the resulting `Polygon` / `MultiPolygon` to
   `_shell_polygon.json` (outer ring + holes per piece).

Algorithm (Ruby phase, runs inside SU 2026):

1. **`PlanShell_Group`** — one top-level group containing N
   sub-groups (one per disconnected piece returned from the Python
   phase). For each sub-group: `add_face(outer)`, `add_face(hole)`
   + `erase!` per hole (so SU keeps the hole as a face-with-loops),
   `pushpull(WALL_HEIGHT_IN)`. Each sub-group is its own context, so
   pushpull never accidentally re-extrudes a face from an earlier
   piece — a bug observed and fixed in the first run.
2. **`Floor_Group_<room_id>`** — one group per `consensus.rooms[i]`.
   A single planar face built from `room.polygon_pts` at `z=0`, no
   pushpull. Painted with the corresponding entry of `ROOM_PALETTE`.
   Consensus polygons may contain consecutive duplicate vertices
   (planta_74's `A.S. | TERRACO SOCIAL | TERRACO TECNICO` room has
   196 entries with at least one duplicate); we dedupe at the Ruby
   layer with a 0.001-pt epsilon before `add_face`.
3. **`SoftBarrier_Group_<index>`** — optional. With
   `SOFT_BARRIERS_MODE=groups` (default) each `consensus.soft_barriers[i]`
   becomes a slab at `PARAPET_HEIGHT_M = 1.10 m`, built from the
   bounding rectangle of its polyline. With `SOFT_BARRIERS_MODE=skip`
   the count is recorded in `geometry_report.json` and no group is
   emitted, with the expected fidelity impact noted.

Configuration (mirrors `consume_consensus.rb`):

- `PT_TO_M = 0.19 / 5.4` (calibrated wall-thickness scale)
- `WALL_HEIGHT_M = 2.70`
- `PARAPET_HEIGHT_M = 1.10`
- `WALL_RGB = [78, 78, 78]`, `PARAPET_RGB = [130, 135, 140]`
- `ROOM_PALETTE` (11 entries, copy-paste)

The Ruby phase reads `consensus.rooms[]` and `consensus.soft_barriers[]`
**directly from the input JSON**, not from `_shell_polygon.json`. The
intermediate JSON only carries the shell polygon — the rest of the
consensus is consumed unchanged.

## 3. What this exporter does NOT do (yet)

Out of scope for this first cut, on purpose:

- **Door leaves.** Openings show as gaps in the shell (no panel, no
  hinge, no swing arc). Deferred to a phase-2 PR; this matches the
  user's explicit instruction "door leaves ficam para fase 2, mas os
  vãos das portas NÃO podem ficar para fase 2".
- **Windows.** No three-band (sill / glass / lintel) assembly. The
  opening rectangle subtracts the full wall height. A future phase
  will add the per-`kind_v5` rendering (`interior_door` /
  `interior_passage` / `window` / `glazed_balcony`).
- **Carving by `geometry_origin`.** `consume_consensus.rb` restricts
  carving to `svg_arc | svg_segments | human_annotation` and skips
  `wall_gap` (the source PDF already drew the gap into the wall
  geometry). This exporter carves **every** opening with a valid
  `wall_id`, on the assumption that consensus walls are stored as
  full-length centerlines. For planta_74 (`geometry_origin =
  human_annotation` on all 12 openings) the assumption holds; for
  consensuses with mixed origins it must be revisited before phase
  2 ships.
- **Overrides.** This exporter is overrides-blind by design (per
  ADR-001 §3). It consumes whichever JSON the user points at —
  `consensus_model.json` or `amended_observed.json`. The launcher
  does not invoke `apply_overrides`; the caller is responsible.
- **Smoke harness integration.** Not wired into
  `scripts/smoke/smoke_skp_export.py` gate F yet. This first cut is
  invoked directly: `python -m tools.build_plan_shell_skp ...`.
  Once metrics prove an improvement, a follow-up PR adds it as an
  alternative `--exporter plan-shell` flag on the smoke harness.

## 4. Deviation from `sketchup-specialist.md` invariants

The active `sketchup-specialist.md` invariants assume the
`consume_consensus.rb` paradigm and check, e.g.:

- `wall_groups == count of walls in consensus` — **NOT applicable**:
  the plan_shell exporter produces 1 `PlanShell_Group` containing N
  sub-groups (one per disconnected shell piece), regardless of how
  many walls the consensus has.
- `materials ≈ 13` (1 wall_dark + 1 parapet + 11 rooms) — **same
  spirit, different count**: this exporter creates 1 wall material +
  1 parapet material + N room materials (one per room in consensus).
  For planta_74: 1 + 1 + 8 = 10 materials.
- `wall_overlaps_top20 == []` — **TARGET still 0**, achieved via
  `unary_union` instead of via per-corner manual reconciliation.

Until or unless the plan_shell exporter is promoted to production
(separate ADR, separate PR), the `sketchup-specialist.md` invariants
apply only to `consume_consensus.rb` output. Reviewers of plan_shell
output should use `runs/planta_74_plan_shell/geometry_report.json`
as the source of truth for what the exporter produced.

## 5. Validation gates

The first cut is considered OK only if ALL of the following hold for
`runs/planta_74_plan_shell/model.skp`:

1. `pytest tests/test_build_plan_shell.py` passes (Python phase).
2. `ruff check tools/build_plan_shell_skp.py tests/test_build_plan_shell.py`
   passes.
3. `PlanShell_Group` exists at the top level of the model.
4. Wall geometry lives in a single top-level group (`PlanShell_Group`),
   not 35 independent wall groups.
5. Each opening in the consensus shows as a real gap in the shell
   (the door rectangle was subtracted from the shell footprint).
6. Floors are separate top-level groups from walls
   (`Floor_Group_<room_id>` per room with a valid polygon).
7. `default_material_faces` count is 0 — every face is painted.
8. The SKP bbox is within 5.0 in of the consensus walls bbox
   (matches `inspect_walls_report.rb` tolerance).
9. The 4-axis fidelity report's `wall_fidelity` axis does not
   regress from the production exporter's verdict.
10. The PNG preview (`model_iso.png`) visibly shows fewer corner
    pillars / fewer wall-to-wall artefacts than the equivalent
    rendering from `consume_consensus.rb`.

Gates 1-8 are mechanically checked. Gate 9 requires running
`verify_fidelities.py` against the new `.skp`. Gate 10 is a human
visual check supported by `runs/planta_74_plan_shell/comparison_with_current.{png,md}`.

## 6. Future decisions still open

- **Phase 2 (door leaves, windows, glazed balcony, passage markers).**
  Port the rendering helpers from `consume_consensus.rb`. Separate
  ADR if the rendering diverges materially from the production
  exporter.
- **Promotion to production.** Replace `consume_consensus.rb` with
  `build_plan_shell_skp.rb` as the default exporter behind
  `skp_from_consensus.py`. Requires: full fidelity parity on
  planta_74 + at least one other planta; explicit human approval
  (CLAUDE.md §1.4); migration plan for `inspect_walls_report.rb`
  invariants and CI workflows.
- **Smoke harness alternate exporter.** Add an `--exporter
  {consume,plan-shell}` flag to `scripts/smoke/smoke_skp_export.py`
  with the same gate sequence (A-H) for both. Deferred until phase 2
  has parity.
- **Schema enrichment.** None proposed. The consensus schema is
  untouched. If the plan_shell algorithm needs additional input
  (e.g., explicit room-wall associations, explicit wall snap
  graph), a separate ADR will propose the additive schema change.

## 7. Rollback

```bash
git revert <merge-sha>
```

The change is purely additive — three new files, one new directory
under `runs/` (gitignored), one new ADR. No production code is
modified. Reverting only removes the experimental exporter; the
production pipeline is unaffected because it never used it.
