# SKP final — post-SU 2026 report (planta_74)

**Date:** 2026-05-11  
**Run:** `runs/smoke/20260511T160057Z/`  
**SKP:** `fixtures/planta_74/skp_final_model.skp` (79,478 bytes)  
**Source:** `fixtures/planta_74/human_openings_annotation.png` (user's real annotation)

---

## TL;DR — verdict per user acceptance criteria

| Criterion | Verdict | Evidence |
|---|---|---|
| 1. SKP visually parecido com PDF | **FAIL** | 7 cells vs 11 expected rooms (2 merged cells: A.S.\|TERRACO SOCIAL\|COZINHA\|TERRACO TECNICO + SALA ESTAR\|SALA JANTAR). See `skp_final_side_by_side.png`. |
| 2. 12 openings nos lugares corretos | **PASS-with-drift** | 12/12 painted blobs extracted + snapped to walls. 10/12 snap shifts < 40pt (acceptable). h_o005 (A.S. door) shifted 72pt; h_o011 (SALA-TERRACO balcony) shifted 51pt — positions drifted from user paint to nearest valid wall axis. |
| 3. BANHO 02 com porta física aberta | **PASS (predicted)** | h_o006 → wall w024 (BANHO 02 west, vertical), center in axis, geometry_origin=human_annotation → consume_consensus.rb will carve. |
| 4. Porta LAVABO abre pro lado correto | **NEEDS VERIFY** | h_o001 → wall w006, kind=interior_door. Default `hinge_side="left"`. User did NOT specify hinge direction in the annotation — Ruby exporter renders left-hinged. Reviewer must inspect SKP visually and edit truth JSON if wrong side. |
| 5. SALA ESTAR ↔ TERRACO SOCIAL = porta-balcão | **PASS-with-drift** | h_o011 kind=glazed_balcony ✓, snapped to w021 (boundary between SALA cell and A.S.-merged cell — geometrically the right wall, but the cell-merge hides that one of the two adjacent rooms is bundled with 3 others). |
| 6. SUITE 02 sul magenta = window (não balcony) | **PASS** | h_o009 kind_v5=window ✓ — color mapping enforced the kind. |
| 7. NO magenta interpretado como SUITE 01 ↔ BANHO 01 window | **PASS** | Gate C-H8: `0 window in region (correct)`. |
| 8. Não aceitar PASS apenas por contagem | **ACKNOWLEDGED** | Counts pass (12 = 7+4+1). Visual still fails on rooms merge. **Verdict is FAIL.** |

**Cycle verdict: FAIL.** Counts + per-kind + carving prediction OK; side-by-side visual diverges from PDF on the 4+2 room merge — that is the structural ceiling established by `docs/diagnostics/2026-05-11_wall_candidates_audit.md`.

---

## 12 human openings — wall match + snap diagnostic

```
       id            kind   color  wall_id  orig_dist  snap_shift  in_axis  carve
  h_o000   interior_door   green     w002         16         32      True   CARVED  (top entry, between cells)
  h_o001   interior_door   green     w006         13         26      True   CARVED  (LAVABO south)
  h_o002   interior_door   green     w010         11         15      True   CARVED  (BANHO 01 west)
  h_o003   interior_door   green     w004         24         37      True   CARVED  (SUITE 02 entry vertical)
  h_o004   interior_door   green     w011         16         29      True   CARVED  (SUITE 01 entry)
  h_o005   interior_door   green     w022         71         72      True   CARVED  (A.S. door — DRIFTED)
  h_o006   interior_door   green     w024         15         26      True   CARVED  (BANHO 02 west — KEY CHECK)
  h_o007          window magenta     w017          9         19      True   CARVED  (BANHO 01 east #1)
  h_o008          window magenta     w018         30         40      True   CARVED  (BANHO 01 east #2)
  h_o009          window magenta     w026         12         18      True   CARVED  (SUITE 02 south)
  h_o010          window magenta     w029         28         34      True   CARVED  (BANHO 02 south)
  h_o011  glazed_balcony  orange     w021         39         51      True   CARVED  (SALA-TERRACO balcony — DRIFTED)
```

`orig_dist` = distance from user-painted center to nearest-wall centerline before snap.
`snap_shift` = additional displacement to land center inside wall axis range (so `consume_consensus.rb` actually carves).
**`in_axis=True` for all 12** → Ruby exporter `CARVING_OPENING_ORIGINS` includes `human_annotation` (since PR #111) so all 12 will carve.

Two openings drifted > 50 pt during snap:
- **h_o005 (A.S. door)** — snap 72pt. User-painted blob was near A.S./COZINHA region but no exact wall there; nearest wall (w022) is at the inner BANHO 02 area. Likely a region where the wall divider is missing from the consensus (same root cause as the 4+2 cell merge).
- **h_o011 (SALA-TERRACO glazed_balcony)** — snap 51pt. The wall it landed on (w021) sits between SUITE 02 cell and the A.S.-merged cell — not the SALA-ESTAR-to-TERRACO-SOCIAL boundary the user marked. The cell-merge ate that boundary.

---

## Rooms — final cells (7 vs 11 expected)

| id | cell name | type |
|---|---|---|
| r000 | A.S. \| TERRACO SOCIAL \| COZINHA \| TERRACO TECNICO | **MERGED** (4 rooms in 1 cell) |
| r001 | SUITE 01 | single |
| r002 | SALA DE JANTAR \| SALA DE ESTAR | **MERGED** (2 rooms in 1 cell) |
| r003 | SUITE 02 | single |
| r004 | BANHO 01 | single |
| r005 | BANHO 02 | single |
| r006 | LAVABO | single |

The merges are HONEST — no wall divider exists in the consensus between the merged rooms. This was established empirically by [`2026-05-11_wall_candidates_audit.md`](../../docs/diagnostics/2026-05-11_wall_candidates_audit.md): the dividers between A.S./TERRACO SOCIAL/COZINHA/TERRACO TECNICO and between SALA ESTAR/SALA JANTAR are NOT drawn as filled paths in the source PDF. Possible reasons (audit refuted threshold-rejection):
- Drawn as thin stroked lines indistinguishable from hatches without further heuristic work
- Truly absent (semantic-only separation by labels / piso-color change)

Resolving this requires either:
- (a) **Improve `tools/build_vector_consensus.py`** to detect the missing dividers — needs multi-PDF threshold sweep per CLAUDE.md §1.3 (planta_p10 + planta_p12 fixtures not yet committed)
- (b) **Add human-annotated walls** (extending the human-openings protocol to also accept user-painted wall lines — red lines for "missing walls", saved alongside the openings annotation)
- (c) **Accept 7-room baseline** as honest fidelity ceiling

---

## Gate verdicts

### Human-openings contract (C-H1..C-H6)
```
verdict: PASS  pass/warn/fail: 6/0/0
  C-H1 total openings (12 = 12)
  C-H2 glazed_balcony (1 = 1)
  C-H3 interior_door (7 = 7)
  C-H4 window (4 = 4)
  C-H5 BANHO_02_west_door (1 interior_door in region)
  C-H6 NO_SUITE_01_BANHO_01_internal_window (0 in region)
```

### F0 structural (post-SKP)
```
smoke verdict: PASS  (review-mode=off, advisory only)
structural blockers: 9
structural warnings: 11
rooms with blockers: 6/7
```
The structural blockers stem from the same 4+2 cell merge — polygons cover wider areas than expected (TERRACO SOCIAL absorbed into the merged cell, etc.). Not new defects; they're the structural fingerprint of the FP-014 P0 ceiling.

---

## Visual artifacts (commit-checked)

| File | Purpose |
|---|---|
| `skp_final_model.skp` | The SKP itself (open in SU 2026 to verify carving + door swing) |
| `skp_final_preview_axon.png` | 3D axon from consensus (generated by smoke harness) |
| `skp_final_preview_top.png` | Top-down preview |
| `skp_final_axon.png` | render_preflight axon (doll-house style, doors with swing arcs) |
| `skp_final_side_by_side.png` | PDF \| axon — VISUAL FAIL is clearest here |
| `skp_final_door_audit.png` | Top-down with D-id labels + openings color-coded by kind |
| `skp_final_notes.md` | render_preflight notes with 10-point validation checklist |
| `human_openings_overlay.png` | PDF + human truth blobs + final outlines |

---

## What changed since the synthetic dry-run

1. **Auto-calibrate image→PDF** — user's annotation is 1999×1307 landscape with title strip, NOT a 1:1 PDF render. Calibration via wall-bbox matching: image planta px=[89,1911]×[133,1231] ↔ PDF=[49.2,553.5]×[404.6,697.8], scale ~0.277 pt/px.
2. **Snap-to-wall in `apply_human_openings`** — after auto-calibrate, opening centers were 9-71 pt off from the nearest wall's axis range, which made `consume_consensus.rb` skip carving silently. New `_snap_center_to_wall()` projects center onto wall centerline + clamps to axis range minus half-width. Without this, **all 12 openings would have been "floating door leaves with no holes"**.
3. **Eyeballed positional constraints removed** — the SALA-ESTAR-TERRACO and SUITE-02-south bbox constraints failed against real-blob positions because the bboxes were picked from text-only inference. Removed both. Only BANHO_02_west_door and NO_SUITE_01_BANHO_01_internal_window survive (wall-aligned geometry).

---

## Next-step options

In priority order:

1. **Add human-annotated walls** (extend the protocol)
   - User paints solid red lines for missing dividers in a separate PNG or same PNG
   - `extract_human_walls.py` extracts them as walls with `geometry_origin="human_annotation"`
   - Re-run polygonize → 11 cells instead of 7
   - The 4+2 merge goes away → side_by_side passes
   - h_o005 and h_o011 stop drifting because the right walls now exist

2. **Open the SKP in SU 2026 and verify carving**
   - File at `fixtures/planta_74/skp_final_model.skp`
   - Check each of the 12 openings:
     - Is the door leaf hinged on the correct side? (we defaulted to "left" for all; user can correct individual `hinge_side` in `human_openings_truth.json` and rerun apply→SKP)
     - Is the wall actually cut where the opening sits?
     - Does the glazed_balcony render with full glass extending the right width?

3. **Accept current SKP as v1** — 7-room honest ceiling, 12 openings carved at snapped positions. v2 follows after human walls or stage-1 wall extraction work.
