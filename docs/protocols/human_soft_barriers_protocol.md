# Human Soft Barriers Protocol

> Counterpart of the [human walls protocol](./human_walls_protocol.md)
> for **peitorils, guarda-corpos, esquadrias, parapetos** — low
> physical barriers that bound a room visually but should NOT be
> rendered as full-height masonry walls in the SKP.
>
> Created 2026-05-12 per user mandate:
>
> > "Human_wall azul só deve representar parede/drywall/alvenaria
> > real. Se a célula só não fecha porque falta soft_barrier,
> > criar protocolo human_soft_barrier, não pedir pintura azul."

## When to use this instead of `human_walls`

Run `tools/find_loop_closure_candidates.py` after applying any human
walls. The resulting `loop_closure_candidates.json` classifies each
remaining merged-cell room-pair into one of:

| candidate_type | meaning | action |
|---|---|---|
| `human_wall` (`should_user_paint=True`) | a real masonry/drywall is missing | paint BLUE in `human_walls_annotation.png` |
| `human_soft_barrier` | a peitoril / guarda-corpo / esquadria / parapet is missing | paint CYAN in `human_soft_barriers_annotation.png` (this protocol) |
| `semantic_room_split` | open plan, no physical divider | accept the merge (do not paint) |
| `already_explained` | painted wall covers it / existing opening covers it | no action |

If `verify_after_human_walls` returns verdict=`WARN` with
`G-WC2 = WARN` and the report lists `softbarrier_cells`, that's
exactly when this protocol applies.

## Color contract

```
CYAN    #00ffff   →  peitoril (default barrier_type)
```

Same paint rules as walls:

* each blob = one barrier (axis-aligned filled rectangle)
* aspect ratio long/short ≥ 2 picks orientation
* L/T-shaped blobs auto-decompose via morphological opening (same
  trick as `extract_human_walls`)
* legend swatches reject automatically (`MIN_BLOB_AREA_PX = 1500`)

Painting outside the planta region is ignored (auto-calibrated via
wall bbox).

## Pipeline

```powershell
# 1. annotate — paint CYAN strokes on the base image used for walls
#    (same base; soft-barriers are an additional pass)
#    save to: fixtures/planta_74/human_soft_barriers_annotation.png

# 2. extract
.venv\Scripts\python.exe -m tools.extract_human_soft_barriers `
  --image     fixtures\planta_74\human_soft_barriers_annotation.png `
  --consensus runs\vector\consensus_with_human_walls.json `
  --out       fixtures\planta_74\human_soft_barriers_truth.json

# 3. apply (re-runs polygonize with the original labels so cells split
#    where the new barriers form closed loops)
.venv\Scripts\python.exe -m tools.apply_human_soft_barriers `
  --consensus runs\vector\consensus_with_human_walls.json `
  --truth     fixtures\planta_74\human_soft_barriers_truth.json `
  --labels    runs\vector\labels.json `
  --out       runs\vector\consensus_with_human_soft_barriers.json

# 4. re-verify cell closure honesty
.venv\Scripts\python.exe -m tools.verify_after_human_walls `
  --consensus-after  runs\vector\consensus_with_human_soft_barriers.json `
  --consensus-before runs\vector\consensus_human.json `
  --candidates       fixtures\planta_74\loop_closure_candidates_after_walls.json `
  --out              fixtures\planta_74\after_human_soft_barriers_report.json
```

## Schema (output of `extract_human_soft_barriers`)

```json
{
  "schema_version": "1.0",
  "source_image": "fixtures/planta_74/human_soft_barriers_annotation.png",
  "soft_barriers": [
    {
      "id": "h_sb000",
      "color": "cyan",
      "barrier_type": "peitoril",
      "orientation": "h",
      "polyline_pts": [[x0, y0], [x1, y1]],
      "height_m": 1.10,
      "bbox_px": [x0_px, y0_px, x1_px, y1_px],
      "bbox_pts": [x0_pt, y0_pt, x1_pt, y1_pt],
      "geometry_origin": "human_annotation"
    }
  ]
}
```

## Default heights per barrier_type

| barrier_type | height (m) | source |
|---|---|---|
| `peitoril` | 1.10 | PEITORIL H=1,10M label on planta_74 |
| `guarda_corpo` | 1.10 | same |
| `esquadria` | 2.10 | porta-balcão height |
| `parapet` | 0.70 | mureta divisória inter-terraço |

Override with `--barrier-type` on the CLI for the entire annotation
pass, or extend `DEFAULT_BARRIER_COLORS` in
`tools/extract_human_soft_barriers.py` to map additional colors to
specific barrier types.

## Why this works architecturally

`tools/polygonize_rooms.py` already consumes
`consensus.soft_barriers` as splitting geometry (added in PR #112).
A 2-point polyline whose two endpoints connect to existing walls
closes the cell exactly the same way a wall would, but the rendered
SKP treats it as a low bounded line at the specified `height_m`
rather than as a full-height wall — preserving the architectural
honesty the user mandated.

## Companion documents

* [`tools/extract_human_walls.py`](../../tools/extract_human_walls.py) + [`tools/apply_human_walls.py`](../../tools/apply_human_walls.py) — masonry / drywall walls (BLUE)
* [`docs/learning/human_openings_truth_protocol.md`](../learning/human_openings_truth_protocol.md) — doors / windows / glazed balconies (GREEN / MAGENTA / ORANGE)
