# Quadrado Demo — Canonical Micro-Fixture Spec

> **Status:** Active reference. The quadrado is the smallest fixture that
> exercises the full PDF-points → `.skp` build pipeline. Every contract
> test in `tests/` pins against the artifacts described here.

## Canonical paths

| Role | Path |
|---|---|
| Input consensus (with window) | `fixtures/quadrado/consensus_with_window.json` |
| Expected shell polygon | `docs/specs/_assets/quadrado_canonical_shell_polygon.json` |
| Expected geometry report | `docs/specs/_assets/quadrado_canonical_geometry_report.json` |
| Reference 3D render | `docs/specs/_assets/quadrado_canonical_success_render.png` |
| Render helpers | `tools/quadrado/render_view.{py,rb}` |
| Smoke gate | `tests/test_quadrado_canonical_smoke.py` (14 cases) |

## Reproduce from a fresh clone

```bash
pip install -e ".[dev]"

# Build the canonical .skp (requires SketchUp 2026)
python -m tools.build_plan_shell_skp \
  fixtures/quadrado/consensus_with_window.json \
  --out runs/quadrado/quadrado.skp

# Render
python tools/quadrado/render_view.py \
  runs/quadrado/quadrado.skp \
  --out runs/quadrado/render.png

# Validate against the versioned reference
pytest tests/test_quadrado_canonical_smoke.py -v
```

## Geometric ground truth

| Dimension | Value | Notes |
|---|---|---|
| Inner room (consensus declares) | 4.00 m × 4.00 m × 2.70 m | `dimension_mode: inner_clear` |
| Wall thickness | 0.19 m | `wall_thickness_pts: 5.4` × `PT_TO_M = 0.19 / 5.4` |
| Wall height | 2.70 m | hardcoded `WALL_HEIGHT_M` in `build_plan_shell_skp.rb` |
| Inner room (stored in `.skp`) | 3.81 m × 3.81 m × 2.70 m | The builder treats `walls.start/end` as **centerlines** — see §"Known characteristics" |

## Invariants locked by the contract tests

| Test file | Locks |
|---|---|
| `tests/test_quadrado_canonical_smoke.py` | Shell polygon contract: 1 piece, 4 outer + 4 inner vertices, no slivers, no redundant vertices, exactly 1 window aperture (3D), 0 carved openings, total area = 2455.6 pts². |
| `tests/test_wall_shell_canonical.py` | LL-017 / FP-025 — axis-aligned wall input produces axis-aligned output, no stepped notches, no overhanging segments. Quadrado outer ring == 4 canonical-corner vertices. |
| `tests/test_window_aperture_contract.py` | ADR-007 / FP-024 — window routes to 3D post-extrude aperture, NOT 2D full-height carve. Window preserves wall mass above/below. |
| `tests/test_window_aperture_geometry.py` | SKP-level: `WindowGlass_Group` at mid-thickness; `PlanShell_Group` full [0, 2.70 m] height; no `Window_Group_*_sill` / `_lintel` groups (the door-like-void anti-pattern). |
| `tests/test_build_plan_shell.py` | Unit-level: `wall_footprint`, `opening_carve_rect`, `canonicalise_axis_aligned_polygon`, sidecar metadata cache. |

## Known characteristics

### Centerline interpretation despite `dimension_mode: inner_clear`

The builder treats `walls.start/end` as **centerlines** regardless of
the declared `dimension_mode`. The stored inner span is 3.81 m
(centerline-to-centerline minus half-thickness on each side) instead
of the consensus-declared 4.00 m. This is a known builder
characteristic; future work that respects `dimension_mode` literally
should aim for the 4.00 m inner.

### Window vs door semantics (ADR-007 / FP-024)

| `kind_v5` | 2D pre-extrude carve | 3D post-extrude aperture | Wall mass below sill | Wall mass above head |
|---|---|---|---|---|
| `interior_door` | full-height | — | no | no |
| `interior_passage` | full-height | — | no | no |
| `glazed_balcony` (porta-vidro) | full-height | — | no | no |
| `window` | **NEVER** | `build_window_aperture_3d` | **yes (peitoril)** | **yes (verga)** |

### Wall shell canonicalisation (LL-017 / FP-025)

Wall footprints extend by half-thickness at BOTH endpoints. After
`unary_union(wall_footprints)` and `shell.difference(carve_union)`, each
retained polygon passes through `canonicalise_axis_aligned_polygon`,
which drops collinear redundant vertices. Quadrado-healthy result:
outer ring = 4 vertices, inner ring = 4 vertices, `slivers_removed = 0`,
`redundant_vertices_dropped = 0`.

## Output convention — `runs/` vs `artifacts/`

| Path | Tracked? | Purpose |
|---|---|---|
| `runs/<plant>/` | gitignored (scratch) | Working build output — default `--out runs/<plant>/<plant>.skp` lands here |
| `artifacts/<plant>/` | tracked | Promoted canonical deliverable — `<plant>.skp` + renders + report + metadata + README documenting build provenance |

Promote `runs/<plant>/foo.skp` → `artifacts/<plant>/` when the build
passes all contract tests and you want to commit the deliverable for
human review. The quadrado canonical artifacts in this spec live under
`docs/specs/_assets/` instead of `artifacts/` because they are
**reference outputs** (versioned for regression-locking), not promoted
deliverables.
