# SKP Fidelity Snapshot — 2026-05-04

> Empirical proof that the consume_consensus.rb fixes (D1 reset_model, D2
> parapet painting) actually eliminate the four whiteness defects
> documented in `runs/vector/inspect_report_summary.md` (2026-05-02).
>
> Companion regression tests: `tests/test_consume_consensus_regression.py`
> (skp/fidelity-return-pass branch) — pin the fixes at source level.

## Pipeline run

```
consensus:    runs/vector/consensus_with_openings.json (33 walls / 11 rooms / 12 openings / 8 soft_barriers)
SU exe:       C:/Program Files/SketchUp/SketchUp 2026/SketchUp/SketchUp.exe
out_dir:      runs/skp_current_20260504T215920Z/
smoke verdict: PASS (gates A-G all green)
duration:     ~15s end-to-end
```

Reproduction:

```bash
.venv/Scripts/python.exe scripts/smoke/smoke_skp_export.py \
    --consensus runs/vector/consensus_with_openings.json \
    --out-dir runs/skp_current_<timestamp> \
    --force-skp --timeout 180
```

Then trigger the inspector by writing
`~/AppData/Roaming/SketchUp/SketchUp 2026/SketchUp/Plugins/autorun_inspector_control.txt`
with three lines (skp path, report.json output path, script path) and
launching SU with the .skp positional. The plugin auto-runs
`tools/inspect_walls_report.rb` 5 s after boot.

## Before / after metrics

Source: `runs/vector/inspect_report_summary.md` (stale, 2026-05-02)
versus `runs/skp_current_20260504T215920Z/inspect_report.json`
(fresh, 2026-05-04).

| Metric | Stale 2026-05-02 | Fresh 2026-05-04 | Delta | Defect addressed |
|---|---:|---:|---:|---|
| `default_faces_count` | **1140** (61% of total) | **0** | **-100%** | D1+D2+D3+D4 (all whiteness) |
| `materials` count | **57** | **13** | **-77%** | D1 (no `wall_dark1/2`) + D4 (no `Sree_*`) |
| `wall_overlaps_top20` count | **3** auto-overlaps | **0** | **-100%** | D1 (triplication kill) |
| Top-level groups | **100** (99 walls = 33×3 + 1) | **64** (33w + 11r + 12o + 8p) | **-36%** | D1 (no triplication) |
| Total faces (all) | **1855** | **395** | **-79%** | D1 (3× geometry) + D4 (Sree 87) |
| `ComponentInstances` | **1** (Sree) | **0** | **-100%** | D4 (template figure removed) |
| Layers | **1** (Layer0 only) | **4** (walls, parapets, rooms, Layer0) | +3 | structural debug-friendliness |

Materials inventory now is exactly the expected canonical set:

```
wall_dark   [78,78,78]
parapet     [130,135,140]
room_r000   [253,226,192]
room_r001   [200,230,201]
room_r002   [187,222,251]
room_r003   [248,187,208]
room_r004   [220,237,200]
room_r005   [255,224,178]
room_r006   [209,196,233]
room_r007   [179,229,252]
room_r008   [255,249,196]
room_r009   [245,224,208]
room_r010   [207,216,220]
```

13 materials = 1 wall + 1 parapet + 11 rooms. No `wall_dark1`/`wall_dark2`
(triplication renames), no `Sree_*` (template figure).

## Visual artifact

`runs/skp_current_20260504T215920Z/sidebyside_pdf_vs_skp.png` — three
panels:

1. PDF planta_74 (real CAD with dimensions and labels)
2. Consensus top render of the post-fix .skp (matplotlib via
   `tools/render_axon.py`, smoke harness gate D)
3. Axon extruded view of the post-fix .skp (same renderer)

All eleven rooms present and labeled, twelve openings positioned, eight
parapets along terraço perimeter painted with `parapet` material (not
default-white). No visible triplication artifacts on walls.

## Defect status after this run

| Defect | Pre-fix symptom | 2026-05-04 status |
|---|---|---|
| D1 — Triplication | `wall_dark1/2`, 99 wall groups, 3 auto-overlaps, z-fighting white seams | **CLEARED** (groups=64, materials=13, overlaps=0) |
| D2 — Parapet white faces | 994 default-white faces (583 sides + 411 tops) | **CLEARED** (default_faces_count=0) |
| D3 — Floor whitespace | 146 default-white floor faces | **CLEARED** in current consensus (default_faces_count=0); track polygonize coverage in future runs |
| D4 — Sree template figure | 1 ComponentInstance + 17 `Sree_*` materials + 87 faces | **CLEARED** (components=0, no Sree_* materials) |

D1, D2, D4 stay cleared as long as the source-level invariants pinned by
`tests/test_consume_consensus_regression.py` hold (test on
skp/fidelity-return-pass branch). D3 may resurface if the polygonize
input changes (different planta with rooms that don't tile cleanly); a
metric extractor planned in a follow-up Track B PR will surface
default_faces_count drift before it becomes visible.

## Cross-links

- Pre-fix diagnostic: `runs/vector/inspect_report_summary.md`
- Smoke harness contract: `docs/validation/sketchup_smoke_workflow.md`
- Source-level guards: `tests/test_consume_consensus_regression.py`
- Pipeline invariants: `CLAUDE.md` §2 (must not invent rooms/walls)
- SU-as-last-gate rule: `CLAUDE.md` §3
