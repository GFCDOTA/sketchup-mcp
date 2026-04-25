# SketchUp Generator Guide — `consume_consensus.rb`

V6.2 adapter that consumes `consensus_model.json` (schema 1.0.0) and emits a
`.skp` with walls, doors, gaps and named room groups.

---

## 1. Running it inside SketchUp

Open the Ruby console (`Window -> Ruby Console`) and run:

```ruby
load "E:/Claude/sketchup-mcp/skp_export/consume_consensus.rb"
Consume.from_consensus(
  "E:/Claude/sketchup-mcp-exp-dedup/runs/final_planta_74/consensus_model.json",
  Sketchup.active_model,
)
```

Dry-run (no SketchUp API needed, plain Ruby):

```bash
ruby -r ./consume_consensus.rb -e \
  'Consume.dry_run("E:/Claude/sketchup-mcp-exp-dedup/runs/final_planta_74/consensus_model.json")'
```

Returns `{walls:, doors:, gaps:, rooms:}` summary; wraps everything in
`start_operation/commit_operation` so undo is one step.

## 2. Schema — `consensus_model.json`

Canonical reference:
`E:/Claude/sketchup-mcp-exp-dedup/runs/final_planta_74/consensus_model.json`

```jsonc
{
  "metadata": { "schema_version": "1.0.0",
                "coordinate_space": "pdf_points",
                "page_bounds": [w_pt, h_pt] },
  "walls":    [{ "wall_id", "start":[x,y], "end":[x,y],
                 "angle_deg", "confidence", "sources":[...] }],
  "openings": [{ "opening_id", "center":[x,y], "chord_pt",
                 "kind":"door|window", "geometry_origin":"svg_arc|pipeline_gap",
                 "confidence", "hinge_side", "swing_deg",
                 "room_a", "room_b" }],
  "rooms":    [{ "room_id", "polygon":[[x,y],...], "area",
                 "label_qwen":"Suite 01", "sources":[...] }]
}
```

Walls have **no thickness/parent_wall_id** — each entry is already a split
segment. Openings have **no host wall_a/wall_b** — host inferred via
nearest-segment lookup.

## 3. Coordinate conversion

PDF points -> metres -> SketchUp internal inches:

- `PT_TO_M = 0.000352778` (1pt = 1/72in)
- `1m = 39.37in`
- Ruby shorthand: `Numeric#pt` and `Numeric#m` go straight to internal inches.

```ruby
Geom::Point3d.new(x_pt.pt, y_pt.pt, 0)   # from pdf points
Geom::Point3d.new(x_m.m,   y_m.m,   0)   # from metres
```

## 4. Category mapping

| Source                                                       | Action                                                                  |
| ------------------------------------------------------------ | ----------------------------------------------------------------------- |
| `walls[]`                                                    | rect (length x 0.14m alvenaria) + `pushpull(2.70m)`, group `Wall_<id>`  |
| `openings` `geometry_origin="svg_arc"` AND `confidence>=0.5` | `PlaceDoorComponent.place_door` (V6.1 real component, scale_x=t/0.19)   |
| `openings` `geometry_origin="pipeline_gap"`                  | carve void in host wall, no door component                              |
| `openings` `kind="window"`                                   | IfcWindow scaffold — rect cut + painted frame (currently same as gap)   |
| `rooms` w/ `label_qwen`                                      | floor face Group named `Room_<label>` (spaces -> `_`)                   |
| `furniture` w/ `center_pdf_pt`                               | 3D Warehouse component if mapped, else placeholder cube `0.5x0.5x0.5 m` |

Low-confidence `svg_arc` openings (<0.5) are skipped with a `warn`.

## 5. Known limitations

- **PT_TO_M scale** assumes PDF is at 1:1 publication scale. Real planta
  needs calibration via dimension OCR (cota "3.40") — slated for V6.3.
- **`hinge_side` flip** is procedural and sometimes mirrors. The arc geometry
  is not rebuilt in Ruby yet (V6.2 final).
- **Furniture without `center_pdf_pt`** (Qwen-only labels) falls back to the
  centroide of its parent room.
- **Wall thickness** hardcoded to 0.14m alvenaria; drywall (0.075m) detection
  not wired.

## 6. Visual debug

- Fusion dashboard: `http://localhost:<port>/fusion/expdedup/final_planta_74`
- 3D viewer (post-build): `http://localhost:<port>/3d/expdedup/final_planta_74`

Dashboard overlays the consensus walls/openings on the rendered PDF so you
can spot drift before committing the SKP.

## 7. TODO — V6.3

- [ ] Scale calibration via dimension OCR (read cota `3.40m`, solve PT_TO_M)
- [ ] Swing-arc geometry in Ruby (`add_arc` + sweep) instead of static folha
- [ ] Replace cube placeholders with real 3D Warehouse furniture components
- [ ] Window IfcWindow with proper frame/glass material instead of bare gap
- [ ] Drywall vs alvenaria classifier feeding `thickness_m` per wall
