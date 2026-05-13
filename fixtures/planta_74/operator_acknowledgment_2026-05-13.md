# Operator Acknowledgment — 2026-05-13

## Context

This file documents an operator decision regarding the
`global_visual_fidelity` advisory check in
`fidelity_4axis_report.json`.

## Decision

The operator verbally **waived** the visual review of
`side_by_side_pdf_vs_skp_FINAL.png` for this cycle. Therefore the
`--operator-confirmed-visual` CLI flag was NOT passed, and the
verdict remains the honest:

```
global_visual_fidelity: WARN  (advisory; operator review pending)
```

## Why merge proceeded despite WARN

`global_visual_fidelity` is **advisory only**. The three hard axes
all PASS:

| Axis                     | Verdict | Evidence                                                  |
|--------------------------|---------|-----------------------------------------------------------|
| `wall_fidelity`          | PASS    | `h_o005` cut_into_wall via host `h_w000`                  |
| `soft_barrier_fidelity`  | PASS    | 0 cells need a soft barrier after prior update            |
| `semantic_room_fidelity` | PASS    | SALA DE JANTAR \| SALA DE ESTAR labels preserved          |

The substantive change in this PR is **semantic**, not geometric:
the priors for `A.S.↔TERRACO TECNICO` and `TERRACO SOCIAL↔TERRACO
TECNICO` in `tools/find_loop_closure_candidates.py` flipped from
`human_soft_barrier` (with `peitoril` evidence) to
`semantic_room_split` (with `open_plan` evidence), based on the
operator's verbal confirmation that the trio is one continuous
physical space bounded only by the outer parapet `h_sb000` on the
south facade — no internal divider exists in the PDF.

The render in `side_by_side_pdf_vs_skp_FINAL.png` is a verification
artifact, not a deliverable, and its geometry is downstream of the
semantic prior. A future cycle should:

1. Have the operator OR an LLM (GPT bridge / local) visually compare
   the side-by-side and flag any geometric drift.
2. If the comparison passes, re-run `verify_fidelities` with
   `--operator-confirmed-visual` to flip the top-level verdict from
   WARN to PASS.

See follow-up GitHub issue (linked when filed).

## CLAUDE.md compliance

- §17 (Non-Stop Autonomy): operator's verbal acknowledgment is
  recorded, not interpreted as approval beyond its scope.
- §5 (Default Decision Rule): documenting the waiver is the
  conservative path — no flag was passed under false pretense.
- §1 (Hard Safety Rules): nothing in this commit modifies thresholds,
  schemas, exporter logic, or baselines.
