# SKP final — 3-verdict honest report (planta_74, segment classifier)

**Date:** 2026-05-11 (cycle 4 — segment-based host classifier)  
**Run:** `runs/smoke/20260511T162327Z/`  
**SKP:** `fixtures/planta_74/skp_final_model.skp` (82,378 bytes)  
**Source annotation:** `fixtures/planta_74/human_openings_annotation.png`

> Reworked per user mandate 2026-05-11: separate three verdicts, no
> silent snap, host based on the painted SEGMENT (full bbox), not the
> center alone. Tolerance is evidence-justified:
> `cross_tol = thickness * 1.5` = wall half-width (0.5) + paint
> precision allowance (1.0) ≈ gate WARN threshold (8 pt). Above 8 pt
> shift the gate WARNs; above 15 pt FAILs. No `> 15 pt` snaps are
> applied silently.

---

## THREE VERDICTS

| Layer | Verdict | Evidence |
|---|---|---|
| 1. `human_openings_extraction` | ✅ **PASS** | 7 green + 4 magenta + 1 orange components extracted from the real PNG → 12 openings. Gate C-H1..C-H4 PASS. |
| 2. `opening_hosting/carving` | ❌ **FAIL** | 11/12 = `existing_gap` (drawn, shifts 0.01–6.18 pt — all ≤ 8 pt WARN gate). **1/12 = `unhosted`** (h_o005 A.S. door). Gate C-H10 FAIL + C-H17 hosting-summary FAIL. |
| 3. `global_skp_visual_fidelity` | ❌ **FAIL** | 7 cells vs 11 expected rooms (FP-014 P0 structural ceiling). 2 merged cells: A.S.\|TERRACO SOCIAL\|COZINHA\|TERRACO TECNICO + SALA ESTAR\|SALA JANTAR. The dividers do not exist as filled paths in the PDF (refuted by `2026-05-11_wall_candidates_audit.md`). |

### Cycle verdict: **FAIL** (any FAIL → fail per user rule)

---

## Per-opening table (mandatory columns)

```
       id            kind    color  bbox_px (l,b,r,t)             orient  nearest_wall  nearest_gap        mode             host  shift  drawn carved  verdict    failure_reason
  h_o000  interior_door    green   ( 402, 207, 521, 227)         h    w003          gap_w003_w002      existing_gap      w003     4.97   True  False  PASS       —
  h_o001  interior_door    green   ( 865, 393, 957, 414)         h    w007          gap_w007_w006      existing_gap      w007     2.34   True  False  PASS       —
  h_o002  interior_door    green   (1704, 420,1792, 442)         h    w010          gap_w010_w008      existing_gap      w010     1.88   True  False  PASS       —
  h_o003  interior_door    green   (1104, 422,1123, 525)         v    w024          gap_w024_w027      existing_gap      w024     0.62   True  False  PASS       —
  h_o004  interior_door    green   ( 993, 537,1092, 558)         h    w012          gap_w012_w011      existing_gap      w012     0.01   True  False  PASS       —
  h_o005  interior_door    green   ( 230, 566, 358, 581)         h    w012(*)       (none usable)      UNHOSTED          —        0.00   False False  FAIL       A) wall_missing_in_consensus
  h_o006  interior_door    green   (1104, 569,1124, 655)         v    w024          gap_w024_w027      existing_gap      w024     0.48   True  False  PASS       —
  h_o007         window  magenta   (1722, 778,1797, 803)         h    w018          gap_w018_w017      existing_gap      w018     3.04   True  False  PASS       —
  h_o008         window  magenta   (1371, 780,1583, 803)         h    w018          gap_w018_w017      existing_gap      w018     2.77   True  False  PASS       —
  h_o009         window  magenta   (1156, 903,1231, 927)         h    w026          gap_w026_w025      existing_gap      w026     4.77   True  False  PASS       —
  h_o010         window  magenta   ( 887, 999,1072,1024)         h    w030          gap_w029_w030      existing_gap      w030     6.18   True  False  PASS       —
  h_o011 glazed_balcony   orange   ( 402, 806, 685, 829)         h    w022          gap_w022_w021      existing_gap      w022     3.62   True  False  PASS       —
```

(*) h_o005 has no usable nearest wall: closest same-orientation wall is w012 at cross_diff 6.93 pt BUT axis_overlap = 0 (wall sits at x=[232, 297] while opening segment is at x=[86, 134] — 100 pt west of any wall in the same y-band).

11/12 PASS, 1/12 FAIL.

---

## Unhosted diagnosis (h_o005 A.S. door)

**Cause classification: A) wall_missing_in_consensus**

Evidence from `fixtures/planta_74/unhosted_nearest_candidates.json`:

```
opening h_o005: interior_door at PDF (105.9, 580.2)
opening segment: h, x ∈ [86, 134], cross_y = 580

3 nearest same-orientation walls:
  w022  axis=[124.9, 132.2]  cross=511.4  cross_diff= 68.78  axis_overlap=0.00
  w003  axis=[124.9, 132.2]  cross=680.4  cross_diff=100.17  axis_overlap=0.00
  w012  axis=[231.7, 297.2]  cross=587.1  cross_diff=  6.93  axis_overlap=0.00

3 nearest colinear-gap pairs:
  gap_w021_w022  axis=[132.2, 214.2]  width= 82.0pt  cross_diff= 68.78  seg_overlap=0.00
  gap_w002_w003  axis=[132.2, 167.6]  width= 35.4pt  cross_diff=100.17  seg_overlap=0.00
  gap_w011_w012  axis=[297.2, 328.8]  width= 31.6pt  cross_diff=  6.93  seg_overlap=0.00
```

**Why A (wall_missing) and not the alternatives:**

- **B (gap_missing_because_wall_fragmentation)** — there ARE no fragmented walls in this region; the nearest wall in the same y-band is w012 at x=231, 100 pt east of the painted segment.
- **C (host_algorithm_bug_center_only)** — the segment classifier was tested above; bbox segment x=[86, 134] still finds no axis overlap with any wall.
- **D (calibration_drift)** — for drift to explain this, the painted segment would need to be 100 pt off horizontally. Drift on planta_74 is ≤ 7 pt (see h_o010, the worst case).
- **E (human_annotation_off_wall)** — the user clearly painted the door between A.S. and COZINHA. The annotation is correct; the wall they painted across just isn't in the consensus.
- **F (unsupported_border)** — door type is `interior_door`, fully supported.

The COZINHA↔A.S. divider is one of the 4 missing dividers in the merged cell A.S.\|TERRACO SOCIAL\|COZINHA\|TERRACO TECNICO. Refer to `docs/diagnostics/2026-05-11_wall_candidates_audit.md` for the audit that established this is a stage-1 wall extraction gap, NOT a threshold issue.

---

## Hosting modes — geometric verification

```
host_summary:
  cut_into_wall: 0   (no opening sits inside a continuous wall — planta_74 walls are short fragments split by door arcs)
  existing_gap: 11   (all 11 hosted openings live in colinear gaps; gap_id encodes the bracket pair)
  unhosted:      1   (h_o005)
```

Per-opening hosting evidence (existing_gap matches):

```
h_o000  evidence: seg_overlap_pts=119.0  seg_overlap_frac=1.00  gap_width=145.0
h_o001  evidence: seg_overlap_pts= 92.0  seg_overlap_frac=1.00  gap_width= 90.0
h_o002  evidence: seg_overlap_pts= 88.0  seg_overlap_frac=1.00  gap_width=120.0
h_o003  evidence: seg_overlap_pts=103.0  seg_overlap_frac=1.00  gap_width= 36.6
h_o004  evidence: seg_overlap_pts= 99.0  seg_overlap_frac=1.00  gap_width= 31.6
h_o006  evidence: seg_overlap_pts= 86.0  seg_overlap_frac=1.00  gap_width= 48.4
h_o007  evidence: seg_overlap_pts= 75.0  seg_overlap_frac=1.00  gap_width=143.0
h_o008  evidence: seg_overlap_pts=212.0  seg_overlap_frac=1.00  gap_width=143.0
h_o009  evidence: seg_overlap_pts= 75.0  seg_overlap_frac=1.00  gap_width= 23.6
h_o010  evidence: seg_overlap_pts=185.0  seg_overlap_frac=1.00  gap_width= 54.7
h_o011  evidence: seg_overlap_pts=283.0  seg_overlap_frac=1.00  gap_width= 82.0
```

Every existing_gap match has `seg_overlap_frac = 1.0` — the opening segment lies entirely within the gap between the colinear walls. No partial matches, no chute.

---

## User acceptance criteria — per-criterion check

| Criterion | Verdict | Evidence |
|---|---|---|
| 12 openings nos lugares corretos | 11/12 PASS, 1/12 FAIL | shifts ≤ 6.18 pt for hosted; h_o005 unhosted = A) wall_missing |
| BANHO 02 porta física aberta, sem parede fechando o vão | ✅ PASS | h_o006: existing_gap between w024 and w027 (vertical, x=333.4, bracketing y=543.4); wall ALREADY open at that position; door leaf renders at center |
| Porta LAVABO lado correto | ⚠️ NEEDS VERIFY | h_o001 hinge_side="left" default; reviewer must open SKP and flip if wrong |
| SALA ESTAR ↔ TERRACO SOCIAL = porta-balcão | ✅ PASS | h_o011 kind=glazed_balcony, mode=existing_gap, seg_overlap=283 pt = full balcony width, shift=3.62 pt |
| SUITE 02 sul magenta = window (NOT balcony) | ✅ PASS | h_o009 kind_v5=window, painted color=magenta |
| NO SUITE 01 ↔ BANHO 01 internal window | ✅ PASS | C-H18 require_absent in [475, 540, 510, 605] → 0 windows |
| h_o005 (A.S.) renderiza | ❌ FAIL | UNHOSTED — door leaf will NOT render; wall missing |

---

## Rooms in SKP (7 cells)

| id | cell name | merged |
|---|---|:---:|
| r000 | A.S. \| TERRACO SOCIAL \| COZINHA \| TERRACO TECNICO | 4 rooms |
| r001 | SUITE 01 | — |
| r002 | SALA DE JANTAR \| SALA DE ESTAR | 2 rooms |
| r003 | SUITE 02 | — |
| r004 | BANHO 01 | — |
| r005 | BANHO 02 | — |
| r006 | LAVABO | — |

The 4+2 merge is the **structural ceiling** — root cause analyzed in `docs/diagnostics/2026-05-11_wall_candidates_audit.md`. Resolving this requires the **human-annotated walls** protocol extension (companion future PR).

---

## Artifacts (committed under `fixtures/planta_74/`)

| File | What it shows |
|---|---|
| `human_openings_annotation.png` | Reviewer's source annotation |
| `human_openings_truth.json` | 12 openings extracted + calibrated |
| `human_openings_overlay.png` | PDF + paint + final consensus |
| `human_openings_report.json` | Gate verdict (FAIL 17/0/2) |
| `unhosted_nearest_candidates.json` | h_o005's 3 nearest walls + 3 nearest gaps + scores |
| `unhosted_debug_overlay.png` | PDF with the unhosted opening highlighted + connector lines |
| `skp_final_model.skp` | 82,378-byte SKP (open in SU 2026) |
| `skp_final_preview_top.png` | Top-down from smoke harness |
| `skp_final_preview_axon.png` | 3D axon from smoke harness |
| `skp_final_axon.png` | render_preflight axon (doll-house) |
| `skp_final_side_by_side.png` | **PDF \| axon — visual FAIL clearest** |
| `skp_final_door_audit.png` | Top-down + 12 openings color-coded |
| `skp_final_zooms.png` | **12-panel zoom mosaic — per-opening verify** |
| `skp_final_notes.md` | render_preflight 10-point checklist |
| `SKP_FINAL_REPORT.md` | This report |

---

## Next-step recommendations

In priority order:

1. **Extend protocol to accept `human_walls`** — reviewer paints solid red lines for the 4 missing dividers in cell00 (A.S./TERRACO SOCIAL/COZINHA/TERRACO TECNICO splitters) + 1 between SALA ESTAR/JANTAR. New `tools/extract_human_walls.py` symmetric to openings. After applying, `polygonize_rooms` forms 11 cells, h_o005 finds a host, side-by-side matches the PDF.
2. **Open `skp_final_model.skp` in SU 2026** — verify per-opening swing direction (`hinge_side` default "left"). Edit individual `hinge_side` in truth JSON and rerun.
3. **Accept 11/12 + 1 unhosted as v1** — verdict stays FAIL until step 1 ships.
