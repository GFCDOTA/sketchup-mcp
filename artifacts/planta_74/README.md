# planta_74 — canonical SKP artifact

Generated SKP for the real apartment (`planta_74.pdf`, 74 m² unit) via
the minimal pipeline.

## Files

| File | Role |
|---|---|
| `planta_74.skp` | The SketchUp deliverable (126 KB, SU 2026 format) |
| `planta_74.skp.metadata.json` | Cache sidecar — consensus SHA256 + build provenance |
| `planta_74_iso.png` | Isometric render (auto from SU `write_image`) |
| `planta_74_top.png` | Top render |
| `side_by_side_pdf_vs_skp.png` | PDF underlay vs SKP top vs SKP iso composite |
| `geometry_report.json` | 4-axis gate self-check + Python stats + SU counts |

## Build provenance

| Field | Value |
|---|---|
| Source consensus | `fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json` |
| Builder | `tools/build_plan_shell_skp.{py,rb}` |
| SketchUp | 2026, `C:\Program Files\SketchUp\SketchUp 2026\` |
| Walls | 35 (20h + 15v, all axis-aligned) |
| Openings | 12 (7 interior_door + 4 window + 1 glazed_balcony) — all `geometry_origin: human_annotation` |
| Rooms | 8 |
| Soft barriers | 9 |
| Shell pieces | 7 (after union+carve+canonicalise) |
| Window apertures (3D) | 4 (peitoril + verga preserved per ADR-007 semantics) |
| Slivers removed | 0 |
| Redundant vertices dropped | 0 |
| Total shell area | 11583.4 pts² |
| SU model bounds | 28 top-level groups, 54 faces, 962 edges |
| Gates self-check | ✅ 4/4 PASS (`plan_shell_group_exists`, `wall_shell_is_single_group`, `floors_separated_from_walls`, `default_material_faces_zero`) |

## Reproduce

```bash
python -m tools.build_plan_shell_skp \
  fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json \
  --out runs/planta_74/model.skp
```

Run requires SU 2026 installed at the default path. With `--mode headless`,
SU is auto-terminated after the marker; default `interactive` leaves SU
running for human inspection.
