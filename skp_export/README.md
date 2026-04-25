# skp_export — observed_model.json -> .skp 3D bridge

Ruby scaffold that consumes `observed_model.json` (schema 2.1.0) emitted by
the Python pipeline and produces a 3D SketchUp model (`.skp`).

This is a **scaffold** (architecture + entry points). It targets the
SketchUp Ruby API (>= 2021) and must be executed inside SketchUp's Ruby
console or as a SketchUp extension. It cannot run on a vanilla Ruby
interpreter — the `Sketchup`, `Geom::Transformation`, `Geom::Point3d`
constants are SketchUp-only.

## Architecture

```
observed_model.json
        |
        v
  lib/json_parser.rb   -- normalises JSON into in-memory hashes
        |
        v
  lib/units.rb         -- pixel -> meter (DPI 150 -> 0.0066 m/px)
        |
        v
  rebuild_walls.rb     -- build_wall_with_openings: face-with-holes
        |
        v
  apply_openings.rb    -- apply_cut_into_wall + apply_existing_gap
        |
        v
  place_door_component.rb -- place_door_component (real .skp component
                             with scale_x = wall_thickness / 0.19)
        |
        v
  output.skp
```

## V6.1 baseline (recreated from memory)

The previous V6.1 pipeline (now lost from `E:\Sketchup`) validated 7/7
doors using a real SketchUp component:

- Component name: `Porta de 70/80cm.skp`
- Component native bounding box X = 0.19 m
- Walls alvenaria (0.14 m) -> `scale_x = 0.737`
- Walls drywall  (0.075 m) -> `scale_x = 0.395`
- Transformation order: `trn * rot * scale_trn` (scale **first**,
  then rotate, then translate)
- Rotation: -90 deg around X axis to stand the door upright
- Scale call:
  `Geom::Transformation.scaling(ORIGIN, scale_x, 1.0, 1.0)`

If the component file is absent, `place_door_component.rb` falls back
to a parametric procedural door (rectangle face extruded).

## How to run inside SketchUp

1. Copy `Porta de 70/80cm.skp` into a known folder (or leave nil to
   use the parametric fallback).
2. Open SketchUp 2021+.
3. Open Window -> Ruby Console.
4. Run:

   ```ruby
   $RUN_DIR = "E:/Claude/sketchup-mcp/runs/proto/p12_v1_run"
   $DOOR_LIB = "E:/Claude/sketchup-mcp/skp_export/components/Porta de 70_80cm.skp"
   load "E:/Claude/sketchup-mcp/skp_export/main.rb"
   SkpExport.run(run_dir: $RUN_DIR, door_lib: $DOOR_LIB)
   ```

5. Output is written to `<RUN_DIR>/output.skp`.

## Coordinate system

- Source PDF coordinates are in pixels at DPI 150.
- Pipeline `lib/units.rb` converts pixels to metres
  (`PX_TO_M = 0.0254 / 150 = 0.000169 m/px` for true 150 DPI;
  the value used here is configurable — see units.rb).
- SketchUp internal length unit is **inches**. The conversion to inches
  uses `length.m` (i.e. `1.m`), which is the standard idiom.
- Y axis in PDF grows downward. SketchUp Y grows "north". We flip Y
  during conversion so that walls render in the canonical orientation.

## Field handling (schema 2.1.0)

- `walls[]`: each item carries `start`, `end`, `thickness`, `orientation`,
  `confidence`. `thickness` is in source pixels and is converted to metres
  via `units.rb`. Walls with `thickness < 2.5 px` are treated as drywall.
- `openings[]`: `kind` is `door` (others ignored for now). `wall_a` /
  `wall_b` reference `parent_wall_id`. `width` is in pixels.
- `peitoris[]`: optional. `height_m` defaults to 1.10.
- `rooms[]`: not used for geometry; reserved for floor faces in future.
- Optional fields (`hinge_side`, `swing_deg`) are tolerated as `nil`.

## Pendencies

- `hinge_side` (left/right flip) is not honoured yet — uses default.
- `swing_deg` arc geometry is not drawn.
- Furniture / mobiliario placement is out of scope for this scaffold.
- Floors / slabs are not generated.
- Peitoris are placed as low walls; no real window glass component yet.
