# Block false visual PASS without required fidelity evidence

## Scope (read first)

- **This PR does NOT fix geometry.** No detector change, no
  consensus mutation, no SKP exporter touch.
- **This PR blocks improper promotion to `verdict_top_level: PASS`**
  in `tools/verify_fidelities.py` when the seven required visual
  evidence artifacts are missing or incomplete.
- **The current `planta_74` state now correctly fails** under the
  new gate (`top_level: FAIL`, `policy_violation:
  2026-05-14_visual_fidelity_gate_required`,
  `missing_visual_artifacts: 7/7`). The fail is the intended
  consequence of the policy — geometry stays untouched.
- **PR B will implement the real `tools/visual_fidelity_gate.py`**
  with algorithmic checks for the 8 failure conditions + producers
  for the 7 artifacts. PR A only checks artifact presence.

## Summary

Block `verdict_top_level: PASS` from `tools/verify_fidelities.py`
whenever the seven required visual evidence artifacts are missing.
Algorithmic checks for the 8 failure conditions land in **PR B**;
this PR is the **policy + artifact-presence gate** half of the
2026-05-14 Visual Fidelity Gate Protocol.

Also reverts the two 2026-05-13 priors from PR #121 that were
committed under a fictional "Operator confirmed" attribution and
that silently deleted the `MURETA H=0,70M` between TER.SOCIAL and
TER.TECNICO from the prior set.

## What changed

- **`tools/verify_fidelities.py`** — `--require-visual-evidence`
  (opt-in flag, default off → backward compatible) +
  `--visual-evidence-dir` (defaults to parent of
  `--consensus-after`). New report fields: `policy_violation`,
  `policy_reason`, `visual_evidence_required`,
  `visual_evidence_status`, `missing_visual_artifacts`,
  `visual_evidence.per_artifact`, `verdict_top_level_pre_visual_gate`.
  Per-axis verdicts are preserved when the gate forces FAIL.
- **`tools/find_loop_closure_candidates.py`** — reverts the 2
  erroneous priors:
  - `A.S. ↔ TERRACO TECNICO` → `human_soft_barrier(peitoril, 0.65)`
  - `TERRACO SOCIAL ↔ TERRACO TECNICO` →
    `human_soft_barrier(peitoril, 0.80)` (PDF labels
    MURETA H=0,70M between them)
- **`docs/protocols/visual_fidelity_gate_protocol.md`** (NEW) —
  full protocol: 8 failure conditions, 7 required artifacts, gate
  behavior, rollout plan.
- **`CLAUDE.md`** — §10 policy section + §13 entry.
- **`tests/test_verify_fidelities_visual_gate.py`** (NEW, +16 tests).
- **planta_74 fixtures** — re-rendered after the prior revert.

## What did NOT change

- No algorithmic visual gate (PR B scope).
- No schema_version bump; additive fields only.
- No CI workflow change.
- No detector / SKP-exporter / Ruby changes.
- No baselines, no fixtures touched outside planta_74.

## Validation

```
ruff check tools/verify_fidelities.py tests/test_verify_fidelities_visual_gate.py
# All checks passed!

pytest tests/test_verify_fidelities_visual_gate.py
# 16 passed (new visual-gate tests)

pytest tests/test_cockpit_overrides*.py tests/test_apply_overrides*.py \
       tests/test_fidelity_engine*.py tests/test_fidelity_apply_overrides.py \
       tests/test_verify_fidelities_visual_gate.py \
       tests/test_classify_openings_by_room_context.py \
       tests/test_cockpit_render_overlay.py \
       tests/test_consume_consensus_*.py \
       tests/test_rooms_from_seeds_polygonize.py \
       tests/test_smoke_gate_e_fidelity_amended.py
# 273 passed — no regressions on the impacted modules.

# Scenario 1 — backward compatibility (no --require-visual-evidence)
python -m tools.verify_fidelities \
  --consensus-after fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json \
  --candidates fixtures/planta_74/loop_closure_candidates_after_soft_barriers.json \
  --labels runs/vector/labels.json \
  --side-by-side fixtures/planta_74/side_by_side_pdf_vs_skp_FINAL.png \
  --out /tmp/r.json
# verdict_top_level: WARN  (per-axis worst, as before)
# new fields present in report: NONE  (backward compatible ✓)
# top-level keys: ['fidelities', 'schema_version', 'verdict_top_level']

python -m tools.verify_fidelities \
  --consensus-after fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json \
  --candidates fixtures/planta_74/loop_closure_candidates_after_soft_barriers.json \
  --labels runs/vector/labels.json \
  --side-by-side fixtures/planta_74/side_by_side_pdf_vs_skp_FINAL.png \
  --require-visual-evidence \
  --out fixtures/planta_74/fidelity_4axis_report.json
# === Top-level verdict: FAIL ===
#   policy_violation: 2026-05-14_visual_fidelity_gate_required
#   pre-gate top-level (per-axis worst): WARN
#   visual_evidence_status: missing
#   missing artifacts: original_floorplan, skp_render, overlay_pdf_skp,
#                      diff_walls, diff_doors, diff_rooms, mismatches_list
```

The `soft_barrier_fidelity: WARN` (instead of PR #121's PASS) is
the direct consequence of the prior revert: the trio cell
`A.S. | TERRACO SOCIAL | TERRACO TECNICO` is still merged and the
single painted CYAN soft barrier (south peitoril `h_sb000`) does
not close the loops the PDF documents (`MURETA H=0,70M` between
the two terraços + the perimeter peitoril segments the operator
pointed out in the 2026-05-14 dialogue).

Pre-existing failures on develop @ `f01a9ae` (unrelated, verified
via stash): `test_f1_dashboard.py`,
`test_f1_regression.py::test_raster_byte_identical_on_planta_74`,
`test_planta_74_regression.py` (raster), `test_text_filter.py`
(raster).

## Risks

**LOW.** Flag is opt-in. CI and existing callers see no behavior
change. The only fixture flipped to FAIL is `planta_74` — that's
the intended consequence of the policy. Reverting this PR restores
the previous (false-positive) behavior cleanly.

## Rollback

```
gh pr close <this-PR> --repo GFCDOTA/sketchup-mcp --delete-branch
```

## Next step

**PR B — `tools/visual_fidelity_gate.py`**: algorithmic checks for
the 8 failure conditions + producers for the 7 visual artifacts.
Description: "blocks false PASS until visual evidence gate exists."
