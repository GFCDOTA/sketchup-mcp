# sketchup-mcp (minimal)

Generate a SketchUp `.skp` floor plan from a JSON consensus describing
walls + openings + rooms.

## Quickstart

```bash
# Install dev deps
pip install -e ".[dev]"

# Run the contract tests (Python-only, no SketchUp needed)
python -m pytest tests/ -v

# Generate the quadrado canonical SKP (requires SketchUp 2026)
python -m tools.build_plan_shell_skp \
  fixtures/quadrado/consensus_with_window.json \
  --out runs/quadrado/quadrado.skp

# Generate the planta_74 SKP
python -m tools.build_plan_shell_skp \
  fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json \
  --out runs/planta_74/model.skp
```

## Pipeline

```
consensus.json (PDF-points coords)
   │
   ▼
[Python] build_shell_polygon
   - merge wall footprints (shapely.unary_union)
   - canonicalise corners (no notches / no slivers)
   - 2D carve full-height openings (doors, passages, porta-vidro)
   - emit window apertures separately for 3D post-extrude carve
   │
   ▼
_shell_polygon.json
   │
   ▼
[Ruby/SU] build_plan_shell_skp.rb (autorun plugin)
   - extrude wall shell to ceiling height
   - 3D carve windows preserving peitoril + verga
   - add separate floor + window-glass groups
   │
   ▼
model.skp + model_iso.png + model_top.png + geometry_report.json
```

## What's in the repo

```
tools/
  build_plan_shell_skp.py    # Python entry + 2D shell geometry
  build_plan_shell_skp.rb    # Ruby/SketchUp 3D builder
  su_runner_safety.py        # SU runtime mode helper (CLI / env)
  disarm_sketchup_autoruns.py # Clean orphan autorun files
  quadrado/render_view.{py,rb} # Render helper for SKP

fixtures/
  quadrado/                  # Canonical micro-fixtures (3 variants)
  planta_74/                 # Real apartment consensus (35 walls)

tests/
  test_quadrado_canonical_smoke.py
  test_wall_shell_canonical.py
  test_window_aperture_contract.py
  test_window_aperture_geometry.py
  test_build_plan_shell.py

docs/specs/
  quadrado_demo_spec.md      # Canonical reference spec
  _assets/                   # Expected shell + report + render

planta_74.pdf / planta_74_clean.pdf  # Source PDFs
```

## Consensus schema (informal)

```json
{
  "wall_thickness_pts": 5.4,
  "walls": [
    {"id": "w_bottom", "start": [100, 100], "end": [213.684, 100],
     "thickness": 5.4, "orientation": "h"}
  ],
  "rooms": [
    {"id": "r_main", "name": "QUADRADO",
     "polygon_pts": [[102.7,102.7], [210.984,102.7],
                     [210.984,210.984], [102.7,210.984]]}
  ],
  "openings": [
    {"id": "win_south", "wall_id": "w_bottom",
     "kind_v5": "window", "center": [156.842, 100.0],
     "opening_width_pts": 30.0, "geometry_origin": "svg_segments"}
  ],
  "soft_barriers": []
}
```

`kind_v5` routing:
- `interior_door` / `interior_passage` / `glazed_balcony` → 2D
  full-height carve
- `window` → 3D post-extrude aperture (preserves peitoril/verga)

`geometry_origin` controls whether to carve:
- `svg_arc` / `svg_segments` / `human_annotation` → carve
- `wall_gap` → leave alone (gap already in wall data)

## Requirements

- Python 3.11+
- SketchUp 2026 at `C:\Program Files\SketchUp\SketchUp 2026\` (Windows)
- `shapely`, `pypdfium2`, `Pillow` (auto-installed via `pip install -e ".[dev]"`)

## License

Proprietary.
