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

- **Door leaves.** ✅ **DONE in Phase 2** (2026-05-20). Each carved
  interior_door now emits a `DoorLeaf_Group_<id>` with a 30°-swung
  leaf (DOOR_HEIGHT_M = 2.10 m, DOOR_THICK_M = 4 cm, DOOR_RGB
  madeira). Lives as a separate top-level group; never inside
  `PlanShell_Group`.
- **Windows.** ✅ **DONE in Phase 2** (2026-05-20). Each window
  emits a `Window_Group_<id>` containing three sub-groups (sill
  0–0.9 m, glass 0.9–2.1 m with alpha=0.45, lintel 2.1–2.7 m).
- **Glazed balcony (porta-vidro).** ✅ **DONE in Phase 2**
  (2026-05-20). Single full-height glass pane (GlazedBalcony_Group).
- **Passage markers (`wall_gap` origin).** ✅ **DONE in Phase 2**
  (2026-05-20). Thin floor-level rectangle for visibility.
- **Carving by `geometry_origin`.** ✅ **DONE in Phase 2**
  (2026-05-20). `tools/build_plan_shell_skp.py` now respects
  `CARVING_ORIGINS = {svg_arc, svg_segments, human_annotation}` and
  records skipped-by-origin openings separately from
  skipped-by-error openings. `wall_gap` origin → not carved (gap
  already in wall data) + passage marker emitted.
- **Overrides.** This exporter is overrides-blind by design (per
  ADR-001 §3). It consumes whichever JSON the user points at —
  `consensus_model.json` or `amended_observed.json`. The launcher
  does not invoke `apply_overrides`; the caller is responsible.
- **Smoke harness integration — DONE (Phase 3, follow-up PR).**
  `scripts/smoke/smoke_skp_export.py` now accepts
  `--exporter {consume,plan-shell}` (default `consume` keeps
  byte-equivalent CI behaviour). Gate F dispatches to
  `tools.build_plan_shell_skp` when `plan-shell` is chosen; gate E's
  cache key includes the exporter choice + the exporter's source
  file SHAs, so the two exporters never share a cache slot. The
  Python launcher now also honours `--force-skp` and writes a
  sidecar `<out_skp>.metadata.json` (consensus SHA + exporter name)
  so subsequent runs short-circuit when input is unchanged.

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
---

## 8. 2026-05-21 — Floor_r001 split (SB extension + Voronoi)

The Floor_r001 merge identified by manual review of planta_74
(`A.S. | TERRACO SOCIAL | TERRACO TECNICO` collapsed into a single
196-vertex cell; analogous `SALA DE JANTAR | SALA DE ESTAR` case)
is addressed here by two opt-in, layered fixes applied in order.
Both layers default OFF — production callers see byte-equivalent
behaviour. Note: the diagnostic harness referenced inside this
section (`tools/diagnose_room_polygons.py`, `tools/audit_soft_barriers.py`)
is NOT on develop as of this PR; it is tracked in a separate
follow-up. References to those tools below describe the eventual
end-state, not the current repo:

### Layer 1 — Near-miss soft_barrier extension

Implementation in `tools/polygonize_rooms.py`:

  - `extend_near_miss_soft_barriers(walls, soft_barriers, base_cells, t, ...)`
    — public helper that probes each polyline endpoint for a near-miss
    extension up to `gap_tol_pt` (default 8 pt).
  - Safety guards:
      * FP-006 wall-coincidence: SBs whose polyline overlaps a wall
        axis by > 50 % are NEVER extended (they're the noise the
        FP-006 filter exists to reject).
      * Semantic origin: by default only SBs with
        `geometry_origin = "human_annotation"` OR
        `barrier_type ∈ {peitoril, mureta, guarda_corpo, esquadria,
        parapet}` are eligible. Operator can opt out via
        `near_miss_require_semantic=False` (CLI: `--no-semantic-guard`).
      * Deep-interior endpoints (a polyline endpoint sitting inside
        any suspicious cell) are skipped — there's no near-miss to
        recover.
  - Post-extension validation: `_validate_extension_effectiveness`
    re-runs `_polygonize_cells_only` with the candidate-extended SBs
    and accepts the extension only when one of:
      * `cell_count_after > cell_count_before` (a split occurred), OR
      * any baseline suspicious cell's area shrank by ≥ 20 %.
    Rejected candidates are still recorded in the provenance log
    with `applied=False` so the audit trail shows what was tried.

The flag in `polygonize_rooms()` is `extend_near_miss_sbs=False` by
default; downstream callers see byte-equivalent behaviour.

### Layer 2 — Voronoi sub-division of merged-seed cells

Implementation in `tools/rooms_from_seeds.py`:

  - `_voronoi_subdivide_merged_cell(cell_poly, seed_labels)` —
    private helper. Given a cell containing ≥ 2 seed labels,
    computes `shapely.ops.voronoi_diagram` over the seed points
    bounded by the cell polygon, clips each Voronoi region against
    the cell, and returns one sub-polygon per seed.
  - Triggered by `voronoi_subdivide_merged_cells=True` in
    `detect_rooms_polygonize`. Each sub-room carries
    `method="polygonize+voronoi"` and a metadata warning
    `voronoi_sub_split_from_shared_cell` so downstream code can
    distinguish architecturally-derived rooms from Voronoi
    approximations.

### Standalone runner

`tools/apply_room_polygon_fixes.py` chains both layers:

```
python -m tools.apply_room_polygon_fixes \
  fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json \
  --out runs/planta_74_after.json \
  --extend-near-miss-sbs \
  --voronoi-subdivide
```

Writes both the new consensus and a `<out>.fix_provenance.json`
sidecar with `applied_extensions`, `rejected_extensions`,
`voronoi_subdivisions`, and before/after room counts.

### Outcome on planta_74

| Metric | Before | After (voronoi + ext) |
|---|---|---|
| Room count | 8 | **11** |
| Suspicious merges | 3 | 1 (SUITE 01 area outlier — legitimate) |
| r001 name | `A.S. \| TERRACO SOCIAL \| TERRACO TECNICO` | A.S. + TERRACO SOCIAL + TERRACO TECNICO (3 rooms) |
| r002 name | `SALA DE JANTAR \| SALA DE ESTAR` | SALA DE JANTAR + SALA DE ESTAR (2 rooms) |
| Plan-shell `with_floors` invariants | 9 PASS / 0 WARN / 0 FAIL | 12 PASS / 0 WARN / 0 FAIL |
| SB extension applied on planta_74 | n/a | 0 applied / 1 rejected (validator vetoed sb004) |

The SB-extension layer's REJECTED candidate is the honest answer:
on planta_74 the available SB geometry is insufficient for
single-endpoint extension to bisect the 3-way merged cell, even with
gap_tol=8 pt. Voronoi resolves the merge correctly. This falsifies
the hypothesis "SB extension alone fixes Floor_r001" — recorded in
`tests/test_room_polygon_fixes.py::
test_planta_74_sb_extension_alone_does_not_split_r001`.

### What this does NOT do

- Does NOT touch `tools/consume_consensus.rb`.
- Does NOT modify the consensus schema.
- Does NOT promote any soft_barrier `warn` from the audit to `keep`
  (the audit decision lives in `audit_soft_barriers.py` reports and
  remains independent of the SB extension feature).
- Does NOT delete any soft_barrier.
- Does NOT change the smoke harness default.
- Does NOT alter the default plan-shell exporter behaviour — all
  flags are opt-in.

### Limitations

- Voronoi sub-division produces equidistant bisectors, NOT real
  architectural divisors. Areas / bbox of sub-rooms are approximate
  (e.g., the A.S. true area is ≈ 2.5 m² per CLAUDE.md baseline, but
  the Voronoi split gives ≈ 9 m² because A.S. occupies less than
  one-third of the merged cell by physical division — the bisector
  cuts it equally). For accurate areas the operator should paint
  additional CYAN human soft_barriers on the divisors.
- Layer 1 (near-miss extension) is best suited to small adjustments
  (≤ 8 pt ≈ 28 cm at planta_74 scale). Larger gaps need new SBs in
  the source, not extension.
- The semantic-origin guard depends on `geometry_origin` /
  `barrier_type` being populated correctly. V7 extractor SBs without
  these fields are skipped by default — that's intentional but means
  on some PDFs the operator must add the metadata or pass
  `--no-semantic-guard`.

### Reversal

```
git revert <fix commit hash>
```

Or per-call: pass `extend_near_miss_sbs=False` and
`voronoi_subdivide_merged_cells=False` (the defaults). All
production callers without flag changes are unaffected.
