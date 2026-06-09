# SKP Visual Review — planta_74 manual validation 2026-05-29

## Change

Manual validation run requested by user post-milestone closure (PRs #197/#198/#199 merged). Goal: exercise the FP-030 Visual Oracle Gate on a fresh build and confirm `planta_74` remains in `WARN_documented` state, with all six axes inspected against the PDF and prior baseline.

This is the **dogfooding of priority #1** from the next-step roadmap ("provar o Visual Oracle numa PR real de builder"). No code changed — only fresh build + side-by-side composition + axis review.

## Canonical input

- **PDF**: `planta_74.pdf` (LIVING GRAND WISH JARDIM, planta de vendas R02, 29/08/23, 74.93 m²)
- **Consensus**: `fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json`
  - SHA256: `e1b1a53d0e8c552c98e316a3e0553dfb0a4cbd282366627445336a6ad4b0f54f`
- **Builder commit**: `bdb8d77` (develop @ start of this validation; same builder as PR #198)
- **SU version**: 2026
- **Baseline**: `artifacts/planta_74/planta_74.skp` (PR #185/#191) + `artifacts/review/planta_74/visual_loop_current/final/` (PR #198 dogfooding)

## Reproduce

```bash
python -m tools.run_skp_visual_review \
  --fixture planta_74 \
  --out artifacts/review/planta_74/manual_validation_20260529_041751 \
  --max-attempts 3

# Side-by-side composite generated ad-hoc with PIL + pypdfium2
# (proper tools/compose_side_by_side.py is follow-up #2)
```

## Loop trace

| # | Verdict | Deterministic findings | Stop reason |
|---|---|---|---|
| `attempt_0` | WARN | 0 | early stop on WARN (no FAIL, no need for further attempts) |

Only 1 attempt was needed — fresh build matches prior baseline.

## Axes — final verdict

| Axis | Verdict | Evidence (specific, source-cited) |
|---|---|---|
| `wall_fidelity` | **PASS** | 35 walls extruded (consensus.walls = 35); `slivers_removed = 0`; `gates_self_check.plan_shell_group_exists` + `wall_shell_is_single_group` both true; top render outline matches PDF footprint in side-by-side composite |
| `door_fidelity` | **PASS** | 7 `DoorLeaf_Group` (== consensus.openings kind=interior_door count); all `bbox_m.min[2] ≈ 0` (no floating doors per heuristic); door swings visible at each opening; iso confirms doors anchored to walls |
| `window_fidelity` | **PASS** | 4 `WindowGlass_Group` (== consensus.openings kind=window count = PR #195 invariant); each `height_m = 1.2` (in [0.9, 1.5] range, peitoril + verga preserved per FP-024); iso shows 4 partial-height apertures in right facade with wall mass above AND below — NO full-height void; 1 `GlazedBalcony_Group` at 2.7m routed via 2D carve (NOT counted as window) |
| `room_fidelity` | **WARN** | 8 `Floor_Group` vs 11 semantic ambients (open-plan, lessons_learned.md #4); two cells fuse documented ambients with no PDF wall trace: r001 (A.S./TERRACO SOCIAL/TERRACO TECNICO) and r002 (SALA DE JANTAR/SALA DE ESTAR). Honest baseline; promotion to PASS requires `semantic_zones` overlay tool |
| `scale_rotation` | **PASS** | Side-by-side comparison: PDF outline ↔ SKP top ↔ SKP iso show identical L-footprint with TERRACO SOCIAL extending south, COZINHA NW corner, SUITE 01 NE, SUITE 02 / BANHOs central; `bbox_m ≈ 17.7m × 10.5m` consistent with PDF 74.93m²; 0° rotation |
| `global_visual` | **PASS** | Apartment is architecturally recognizable; no floating geometry, no orphan glass, no misplaced soft barriers, no obvious wall stubs, no floor leaks; matches FP-030 `good_real_baseline` example |
| `gates_self_check` | **PASS** | 4/4 booleans true: `plan_shell_group_exists`, `wall_shell_is_single_group`, `floors_separated_from_walls`, `default_material_faces_zero` |

## PASS / WARN / FAIL summary

```
PASS:
- wall_fidelity
- door_fidelity
- window_fidelity
- scale_rotation
- global_visual
- gates_self_check (4/4)

WARN:
- room_fidelity: 8 cells vs 11 semantic ambients (open-plan, documented baseline)
- SoftBarrier_Group_7 (sb007): ambiguous without explicit PDF label
- SoftBarrier_Group_1: 0.01m^2 sliver, invisible at render distance, finding-only (no patch — sliver threshold is policy choice)

FAIL:
- none
```

## Soft barrier source-confirmed status

Same as iteration 2 of `visual_loop_current/` (PR #198) — same consensus, same builder:

- `SoftBarrier_Group_5` (sb005) → **PASS** confirmed against PDF label "PEITORIL H=1,10M"
- `SoftBarrier_Group_7` (sb007) → **WARN** (no PDF label, plausible)
- `SoftBarrier_Group_1` → **WARN finding-only** (sliver)

## Improvement claimed

This validation does NOT claim improvement over the baseline. It claims that:

> *"The FP-030 Visual Oracle Gate runner, applied to a fresh `planta_74` build, produces the expected `WARN_documented` verdict with all PASS axes confirmed against PDF, no new FAIL introduced, and a side-by-side composite enabling humanly-verifiable comparison."*

## Improvement proven?

**PASS** — the script executes end-to-end, all 6 artifacts are generated, all heuristics pass, Claude inline review confirms qualitative axes against PDF, and the result is stable vs prior baseline.

## Regressions

`none observed`.

Specifically verified against prior baseline (PR #198 dogfooding):

- All counts (input_walls, openings_carved, window_apertures_3d, slivers_removed, floor_groups) identical
- All group counts in `groups_diagnostic` identical (1 PlanShell, 8 Floor, 4 WindowGlass, 7 DoorLeaf, 1 GlazedBalcony, 7 SoftBarrier)
- All 4 `gates_self_check` still true

## Remaining issues (carried forward from prior cycles)

- **`room_fidelity = WARN`** — open-plan cells r001/r002. Backlog: `semantic_zones` overlay tool. Not a blocker.
- **`SoftBarrier_Group_7`** — needs human annotator confirmation. Documented in `.ai_bridge/HANDOFF.md`.
- **`SoftBarrier_Group_1`** — sliver, not patched (policy choice). Documented.
- **Side-by-side composite** — currently ad-hoc PIL script; proper `tools/compose_side_by_side.py` is follow-up #2.

## Final verdict

**WARN_documented (acceptable, no FAIL)** — equivalent to and corroborating the canonical baseline status.

## Constitution #8 compliance

| Requirement | Status |
|---|---|
| Final `.skp` in `artifacts/review/<plant>/<branch>/final/` | OK — `model.skp` (150.8 KB) |
| `model_top.png` | OK (32.2 KB) |
| `model_iso.png` | OK (140.9 KB) |
| `side_by_side_pdf_vs_skp.png` | OK (245 KB, ad-hoc PIL composition) |
| `geometry_report.json` | OK (27.5 KB) |
| `visual_findings.json` (schema v1) | OK — filled with numeric + qualitative axes + 3 findings/passes |
| `regression_summary.md` | OK (this file) |
| Evidence specific per axis (no "PASS — ok") | OK — every axis has concrete reference to numeric stats or inline render observation |
| `.skp` NOT in `/runs/` only | OK — promoted to `artifacts/review/` |

## Closing note

This is **dogfooding #2** of FP-030 on the canonical baseline. No new spec, no new tool, no new ciclo. Per `slice complete IS valid stop` rule, this run closes the priority #1 follow-up from the milestone roadmap. Next legitimate work is priority #2 (side-by-side composer tool) — **only when explicitly requested**.
