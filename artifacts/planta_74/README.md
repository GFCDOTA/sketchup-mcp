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

## Room fidelity baseline — 8 cells, 11 semantic ambients (WARN)

The consensus emits **8 closed-cell room polygons** but the source
planta de vendas carries **11 semantic ambients**. Two cells merge
multiple ambients because the PDF doesn't draw walls between them
(open-plan layout):

| Cell | Polygon represents | Why merged |
|---|---|---|
| `r001` | `A.S. \| TERRACO SOCIAL \| TERRACO TECNICO` | No wall traces between these 3 ambients in the PDF — divided only by peitoril/grade in the source drawing |
| `r002` | `SALA DE JANTAR \| SALA DE ESTAR` | Open-plan; no full-height wall separates them in the PDF |
| `r000`, `r003`–`r007` | `SUITE 01`, `SUITE 02`, `COZINHA`, `BANHO 01`, `BANHO 02`, `LAVABO` | 1:1 mapping |

This is the **honest geometric output** — the polygonize step only
closes cells where wall geometry exists. Inventing split walls to
hit "11 rooms" would violate the no-fabrication rule. The semantic
ambients are preserved in the `name` field with `|` as the merge
separator.

**Fidelity verdict:** `room_fidelity = WARN` (not FAIL). The geometry
matches the PDF honestly; only the semantic granularity is below the
planta-de-vendas labelling.

**Promotion path** (future): a `semantic_zones` overlay computed
from human-painted PNG annotations (cyan blobs for peitoril,
etc.) could split the merged cells into the full 11 ambients
without forging wall geometry. Tracked as a future cycle — not a
blocker for the canonical SKP deliverable.

## Reproduce

```bash
python -m tools.build_plan_shell_skp \
  fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json \
  --out runs/planta_74/model.skp
```

Run requires SU 2026 installed at the default path. With `--mode headless`,
SU is auto-terminated after the marker; default `interactive` leaves SU
running for human inspection.
