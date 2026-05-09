# Dogfood — override-aware flow end-to-end (2026-05-09)

> First end-to-end exercise of the cockpit + smoke override-aware
> stack on a real consensus. Confirms the contract works, surfaces
> 3 UX gaps (one fixed in-flight, two queued for follow-up).

## Workspace

- **Run dir:** `runs/_dogfood_e2e_2026_05_09/`
- **Source consensus:** copied from
  `runs/feature_room_context_2026_05_06/consensus_with_room_context.json`
  (the canonical pre-Cycle-8b planta_74 baseline, with FP-012 leakage
  still present in SUITE 01 + SUITE 02 — useful realistic failure mode)
- **Expected model:** `ground_truth/planta_74/expected_model.json`
- **Consensus sha256 (BEFORE):**
  `64b57dc34bb9c01d1bceeacb36607c0da3e9f0d01956ba5baa31af14606cbd0a`
- **Consensus sha256 (AFTER all 3 overrides + 4 gates):**
  `64b57dc34bb9c01d1bceeacb36607c0da3e9f0d01956ba5baa31af14606cbd0a`

✅ **Invariant proved**: ADR-001 §2.10.1 — originals are immutable.

## Felipe's 10-step checklist — results

| # | Step | Result |
|---|---|---|
| 1 | Run cockpit (locally) | ✅ Headless via `cockpit.overrides` API. Same code paths as the Streamlit Review tab — Slice 2's `save_override(...)` is the hot path. |
| 2 | Pick a real run | ✅ planta_74 baseline (11 rooms, 33 walls, 11 openings, fidelity=0.69, 3 hard_fails) |
| 3 | Create at least one override | ✅ **3 overrides created** — `reject_element` on opening `o003` (debug-decision, conf=0.631), `mark_suspect` (severity=high) on room `r004` (SUITE 01, FP-012 leaker), `opening_kind_override` on `o010` (interior_door → window) |
| 4 | review_overrides.json with audit_trail | ✅ All 3 overrides + 3 audit `create` entries with actor=`human:dogfood`, timestamps, signatures. Schema = `review_overrides_v1`. |
| 5 | Gate E2 generates amended_observed.json | ✅ `_overrides_metadata.overrides_applied_count = 3`, `dropped = 0`. opening `o010` shows `_kind_v5_original=interior_door`, `kind_v5=window`, `source=manual`. room `r004` shows `_suspect={severity: high, tag: fp012_convex_hull_leakage}`. opening `o003` dropped from amended (10 openings vs original 11). |
| 6 | Gate E3 generates fidelity_report_amended.json | ✅ Both `global_fidelity` (post=0.69) and `global_fidelity_pre_override` (pre=0.69) emitted per ADR §2.10.5. Sub-scores include both `sub_scores` and `sub_scores_pre_override` (see "Honest delta" below). |
| 7 | Gate F0 prefers amended | ✅ Smoke report shows `using_amended_fidelity: True` in pre_skp_review_report.json. F0 used the E3 output. |
| 8 | All 4 fields in pre_skp_review_report.json | ✅ `fidelity_score=0.69`, `fidelity_score_pre_override=0.69`, `fidelity_delta=0.0`, `using_amended_fidelity=True` (all present, all correct shape) |
| 9 | Consensus / canonical original NOT altered | ✅ sha256 byte-identical before/after (proven above) |
| 10 | Report screenshots/artifacts + UX gaps | This document. |

## Artifacts (all under `runs/_dogfood_e2e_2026_05_09/`)

```
consensus_with_room_context.json     58,845 bytes  ← input, untouched
fidelity_report.json                 10,994 bytes  ← raw fidelity baseline
review_overrides.json                 4,655 bytes  ← human's 3 overrides + audit
_smoke_out/
  amended_observed.json              58,028 bytes  ← gate E2 output
  fidelity_report_amended.json       11,549 bytes  ← gate E3 output (pre + post)
  pre_skp_review_report.json            393 bytes  ← gate F0 verdict
  proposed_actions.json               3,193 bytes  ← gate F0pa (6 advisory actions)
  preview_axon.png                  289,149 bytes  ← gate D
  preview_top.png                    83,838 bytes  ← gate D
  sketchup_smoke_report.{json,md}              ← gate H summary
```

Visual proof of the amended observation rendered through the cockpit's
SVG renderer:
`docs/diagnostics/2026-05-09_dogfood_amended_overlay.svg` (15 KB,
inline-renderable on GitHub).

## Honest delta — what the overrides actually did

The cockpit-displayed `global_fidelity` rounded both pre and post to
0.69. But the **sub-scores tell the real story** (verified by
`fidelity_report_amended.json`):

| sub-score | pre-override | post-override | Δ |
|---|---|---|---|
| `room_score` | 0.7500 | 0.7500 | +0.0000 |
| `count_score` | 1.0000 | 1.0000 | +0.0000 |
| `bbox_score` | 1.0000 | 1.0000 | +0.0000 |
| **`adjacency_score`** | **0.4210** | **0.3330** | **-0.0880** |

`hard_fails` count is the same (3) but the underlying numbers are
different — adjacency_f1 went from 0.42 (raw) to 0.33 (amended)
because:
- `reject_element` on o003 dropped the opening that connected one
  expected adjacency edge
- `opening_kind_override` o010 → window broke another expected
  `interior_door` edge

**The overrides made adjacency WORSE.** This is honest reporting in
action — ADR §2.10.5's "fidelity is never silently masked" property:
the human's overrides produced a measurable score change, the change
went the wrong way, and the system surfaces it both via
`global_fidelity_pre_override` and the per-sub-score breakdown.

The cockpit reviewer would see this and choose to NOT promote these
overrides — exactly the feedback loop the contract was designed to
enable.

## UX gaps discovered

### Gap #1 — `tools.*` lazy imports fail when smoke is invoked as a script — **FIXED IN-FLIGHT**

**Symptom:** First smoke run failed at gate E2 with
`failed to import tools.apply_overrides: No module named 'tools'`.
This blocks E2, E3, AND F0pa — every Slice 5/13b/13 path that lazy-imports `tools.X`.

**Cause:** `python scripts/smoke/smoke_skp_export.py` only adds the
script's directory (`scripts/smoke/`) to `sys.path`. The repo root
isn't there, so `from tools.apply_overrides import apply_overrides`
fails. Tests pass (pytest sets the path) but the real CLI doesn't.

**Fix:** Added a `sys.path.insert(0, str(REPO_ROOT))` bootstrap at
the top of `scripts/smoke/smoke_skp_export.py`, mirroring the
cockpit/app.py pattern from PR #68 (`f11e13c`). One commit, six
lines, fully self-contained.

**Status:** Applied in this dogfood session, will ship as a small PR
together with this report.

### Gap #2 — v1 override types don't address area / polygon issues

**Symptom:** The most common real failure mode on `planta_74` is
"room polygon area out of expected range" (FP-012 SUITE 01 = 69.91 m²
vs expected `[10, 28]`). The 7 v1 override types
(`opening_kind_override`, `opening_connects_override`,
`room_label_override`, `mark_suspect`, `reject_element`,
`approve_element`, `block_skp_export`) have no way to **adjust a room
polygon** or **scope down its area**.

The reviewer's only option to address SUITE 01 is `reject_element`
on the entire room — which drops it from amended_observed
entirely and probably HURTS fidelity more than it helps (because
`count_score` then drops).

**Severity:** Medium. The contract works; it just doesn't cover the
common failure mode.

**Mitigation options (queued, not in this dogfood):**
- Add `room_polygon_override` (new override type — needs ADR-002)
- Add `expand_room_polygon` / `shrink_room_polygon` proposed_actions
  (already specified in ADR-001 §2.6 but the producer doesn't emit
  them yet)
- Document that v1 is intentionally minimal; encourage upstream
  detector fixes (Cycle 8b promoted concave-hull as the better fix
  for FP-012)

### Gap #3 — `global_fidelity` rounded to 2 decimals hides sub-score movement

**Symptom:** Cockpit + smoke both display `fidelity_score = 0.69`
and `fidelity_score_pre_override = 0.69`, computing `Δ = 0.00`. The
underlying sub-score `adjacency_score` actually moved -0.088. The
rounding hides the movement.

**Severity:** Low–Medium. The data is honest (both sub-scores AND
unrounded scores live in `fidelity_report_amended.json`), but the
human-facing display under-reports.

**Mitigation options (queued):**
- Display global_fidelity with 4 decimals when `Δ` would round to
  zero
- Surface a "sub-score Δ" mini-table in the cockpit Pre-SKP Review
  pane when `using_amended_fidelity=True`
- Add a `sub_scores_delta` field to `pre_skp_review_v1` (additive)

## What did NOT change

- `consensus_with_room_context.json` byte-identical (sha256 verified)
- Detector code (gates A–D, fidelity engine when not in apply
  mode) untouched
- Ruby/SU exporter never invoked (`--skip-skp` set)
- `ground_truth/` files read-only
- No threshold / baseline / schema change

## Conclusion

The override-aware end-to-end loop **works as specified** through
all 9 cockpit + smoke layers (Slice 2 → 5a → 5b → 5c → Slice
4-extra). Gap #1 (sys.path bootstrap) was a real blocker fixed
in-flight. Gaps #2 and #3 are documented for follow-up — both
honest about the cost (override expressiveness limited to 7 types;
display rounds aggressively) without hiding the underlying truth
(everything is in the JSON for an auditor).

The detector path is **provably overrides-blind** (consensus
sha256 unchanged across the entire dogfood). The contract from
ADR-001 §2.10 holds end-to-end on real data.
