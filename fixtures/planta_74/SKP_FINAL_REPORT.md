# SKP final — 3-verdict honest report (planta_74, post host classifier)

**Date:** 2026-05-11  
**Run:** `runs/smoke/20260511T161305Z/`  
**SKP:** `fixtures/planta_74/skp_final_model.skp` (82,384 bytes)  
**Source annotation:** `fixtures/planta_74/human_openings_annotation.png` (real reviewer)

> Reworked per the 2026-05-11 user mandate: **separate the verdicts.**
> Snap was removed as a silent correction. Each opening is now
> classified into `cut_into_wall` / `existing_gap` / `unhosted` mode;
> shifts > 8 pt WARN, > 15 pt FAIL.

---

## THREE VERDICTS

| Layer | Verdict | Evidence |
|---|---|---|
| 1. `human_openings_extraction` | ✅ **PASS** | 7 green + 4 magenta + 1 orange components extracted from the real annotation PNG → 12 openings. Required counts met (`gate C-H1..C-H4`). |
| 2. `opening_hosting/carving` | ❌ **FAIL** | 11/12 openings = `existing_gap` (drawn, no carve needed). **1/12 = `unhosted`** (h_o005, A.S. door — no wall in the consensus matches the painted position). `gate C-H10 FAIL`, `gate C-H17 FAIL` (hosting summary). |
| 3. `global_skp_visual_fidelity` | ❌ **FAIL** | side-by-side render diverges from PDF: 7 cells vs 11 expected rooms (FP-014 P0 structural ceiling: dividers between A.S./TERRACO SOCIAL/COZINHA/TERRACO TECNICO + SALA ESTAR/SALA JANTAR not present as filled paths). Even with all openings rendered, the floor topology is still 7-cell merged. |

### Cycle verdict: **FAIL** (per user rule: any of the 3 fails → cycle fails)

---

## Per-opening hosting table

```
       id            kind   color    mode             host       shift   carve  drawn  verdict
  h_o000  interior_door   green  existing_gap   gap_w003_w002      4.97   False   True  PASS
  h_o001  interior_door   green  existing_gap   gap_w007_w006      2.34   False   True  PASS  (LAVABO)
  h_o002  interior_door   green  existing_gap   gap_w010_w008      1.88   False   True  PASS  (BANHO 01)
  h_o003  interior_door   green  existing_gap   gap_w024_w027      0.62   False   True  PASS  (SUITE 02 entry vert)
  h_o004  interior_door   green  existing_gap   gap_w012_w011      0.01   False   True  PASS  (SUITE 01 entry)
  h_o005  interior_door   green  UNHOSTED       —                  0.00   False  False  FAIL  (A.S. — wall missing)
  h_o006  interior_door   green  existing_gap   gap_w024_w027      0.48   False   True  PASS  (BANHO 02 west — KEY)
  h_o007         window  magenta  existing_gap   gap_w017_w015      3.04   False   True  PASS  (BANHO 01 east #1)
  h_o008         window  magenta  existing_gap   gap_w018_w017      2.77   False   True  PASS  (BANHO 01 east #2)
  h_o009         window  magenta  existing_gap   gap_w026_w025      4.77   False   True  PASS  (SUITE 02 south)
  h_o010         window  magenta  existing_gap   gap_w030_w029      6.18   False   True  PASS  (BANHO 02 south)
  h_o011  glazed_balcony  orange  existing_gap   gap_w022_w021      3.62   False   True  PASS  (SALA ↔ TERRACO)
```

All `existing_gap` shifts ≤ 6.18 pt — every drawn opening is **well below** the WARN threshold (8 pt) and FAIL threshold (15 pt). The user-paint positions land in honest colinear gaps between wall fragments — exactly the architectural mode where doors and windows live in vector PDFs.

**Key per-user-criterion verifications:**

| User rule | Check | Outcome |
|---|---|---|
| BANHO 02 porta física aberta, sem parede fechando o vão | h_o006: existing_gap between w024 and w027 (both vertical, x=333.4, bracketing y=543.4). The wall is ALREADY OPEN at that position — no carving needed, door leaf renders at center. | ✅ |
| SALA DE ESTAR ↔ TERRACO SOCIAL = porta-balcão (não janela pequena) | h_o011: kind=glazed_balcony ✓ width=78.3pt, mode=existing_gap between w022 and w021 (both horizontal, y=511.4). Renders as glazed_balcony with full glass extending the gap width. | ✅ |
| SUITE 02 sul magenta = janela (não porta-balcão) | h_o009: kind=window ✓ width=20.8pt, mode=existing_gap on south wall of SUITE 02. | ✅ |
| NÃO criar window interna entre SUITE 01 e BANHO 01 | Gate C-H18 (require_absent in region [475, 540, 510, 605]) → 0 windows. | ✅ |
| Porta LAVABO lado correto | h_o001: kind=interior_door, hinge_side="left" (default — Ruby exporter convention). **Reviewer must open SKP and verify swing direction; edit `human_openings_truth.json` `hinge_side` to flip if wrong.** | ⚠️ NEEDS VISUAL VERIFY |
| h_o005 (A.S. door) renderiza | **UNHOSTED — door leaf will NOT render.** The wall between COZINHA and A.S. doesn't exist in the consensus (FP-014 root cause). | ❌ FAIL |

---

## Rooms — 7 cells in SKP (vs 11 expected)

| id | cell name | rooms in cell |
|---|---|---:|
| r000 | A.S. \| TERRACO SOCIAL \| COZINHA \| TERRACO TECNICO | **4 merged** |
| r001 | SUITE 01 | 1 |
| r002 | SALA DE JANTAR \| SALA DE ESTAR | **2 merged** |
| r003 | SUITE 02 | 1 |
| r004 | BANHO 01 | 1 |
| r005 | BANHO 02 | 1 |
| r006 | LAVABO | 1 |

The 4+2 merge is the **structural ceiling** documented in `docs/diagnostics/2026-05-11_wall_candidates_audit.md`. The dividers between these rooms are not drawn as filled paths in `planta_74.pdf` (audit refuted threshold-rejection hypothesis). To split into 11 cells, the protocol needs **human-annotated walls** — a follow-up extension to the human-openings protocol.

---

## Hosting modes — what each mode means in the SKP

- **`cut_into_wall`** (0 openings) — opening center sits inside a continuous wall. consume_consensus.rb's carve step walks the wall axis range and emits sub-walls only outside `[center - half, center + half]`. The wall gets sliced; the door/window renders at the carved gap.
- **`existing_gap`** (11 openings) — opening center sits between two colinear wall fragments. The wall is ALREADY split in the consensus (door arc drew the gap during stage-1 extraction). consume_consensus.rb's carve loop runs but emits no cut because the center is outside any individual wall's axis range; the door/window leaf renders at the center, in the gap. **Visually indistinguishable from `cut_into_wall` — both yield a physical opening with a leaf.**
- **`unhosted`** (1 opening: h_o005 A.S. door) — neither a containing wall nor a bracketing gap matches. consume_consensus.rb's `add_door_leaf` returns nil if `wall_id is null`. Door does NOT render. **This is a FAIL** that the reviewer must resolve.

---

## Gate report (final)

```
verdict: FAIL  pass/warn/fail: 17/0/2  (gates C-H1..C-H18)

PASS:
  C-H1   Total openings = 12 (required 12)
  C-H2   glazed_balcony = 1 (req 1)
  C-H3   interior_door  = 7 (req 7)
  C-H4   window         = 4 (req 4)
  C-H5..C-H9, C-H11..C-H16 — 11 existing_gap openings with shift_pt ≤ 6.18 pt
  C-H18  BANHO_02_west_door require_present interior_door — found 1 in region

FAIL:
  C-H10  h_o005 (interior_door): UNHOSTED — A.S. door has no wall to host
  C-H17  Hosting summary: drawn=11/12, carved=0/12, unhosted=1/12
```

---

## Artifacts (all committed under `fixtures/planta_74/`)

| File | What it shows |
|---|---|
| `human_openings_annotation.png` | The reviewer's source annotation |
| `human_openings_truth.json` | 12 openings extracted, calibrated to PDF coords |
| `human_openings_overlay.png` | PDF + painted blobs + final consensus outlines |
| `human_openings_report.json` | Gate verdict (FAIL 17/0/2) |
| `skp_final_model.skp` | The 82,384-byte SKP (open in SU 2026) |
| `skp_final_preview_top.png` | Top-down render from smoke harness |
| `skp_final_preview_axon.png` | 3D axon from smoke harness |
| `skp_final_axon.png` | render_preflight axon (doll-house, with door swing arcs) |
| `skp_final_side_by_side.png` | **PDF \| axon — visual FAIL is clearest here** |
| `skp_final_door_audit.png` | Top-down with all 12 openings color-coded by kind |
| `skp_final_zooms.png` | **12-panel zoom mosaic — per-opening visual verify** |
| `skp_final_notes.md` | render_preflight 10-point checklist + verdict |
| `SKP_FINAL_REPORT.md` | This file |

---

## Next-step recommendations

In priority order:

1. **(unblocks all of 3-verdict layer 3)** Extend the protocol to accept **human-annotated walls**. Paint solid red lines for the missing dividers (4 between A.S./TERRACO/COZINHA/TECNICO + 1 between SALA ESTAR/JANTAR). Build `tools/extract_human_walls.py` symmetric to openings extraction. Rerun the pipeline; `polygonize_rooms` forms 11 cells. h_o005 becomes hostable.
2. Open `fixtures/planta_74/skp_final_model.skp` in SU 2026 to verify per-opening swing direction (`hinge_side` default is "left"). Edit individual `hinge_side` in `human_openings_truth.json` and rerun apply → SKP.
3. Accept 11/12 openings drawn at honest gap positions for v1; v2 follows after human walls.
