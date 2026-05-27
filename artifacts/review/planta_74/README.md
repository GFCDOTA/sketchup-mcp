# planta_74 — FP-026 wall-stub review artifacts

Human-facing review artifacts for the FP-026 (Residual Wall Stub
Elimination) verdict on the `planta_74` canonical build.

| File | Role |
|---|---|
| `planta_74_stub_review.skp` | Reviewable SKP — the deliverable from the current builder |
| `model_top_stub_review.png` | Top render |
| `model_iso_stub_review.png` | Isometric render |
| `wall_stub_debug_overlay.png` | 5-panel staged diagnostic (raw → junction-aware → union → carve → candidates) |
| `wall_stub_report.json` | Per-candidate classification + verdict (FP-026 schema v1) |

## Verdict (2026-05-27)

```
total_candidates: 14
FAIL: 0
WARN: 0
PASS: 14
```

All 14 stub-shaped pieces detected by the FP-026 heuristic have
consensus centerline support (classified as `valid_wall_return`).
No residual caps or overhanging stubs remain after the PR #192
junction-aware extension landed.

## Observed but deferred — stair-step edges from thickness variance

The consensus declares 3 walls (`w000`, `w025`, `w026`) at thickness
**5.52 pt** while the other 32 walls are at **5.40 pt**. The 0.12 pt
difference produces visible stair-step joggles at junctions where
walls of different thicknesses meet. These are NOT residual stubs —
they faithfully reflect the consensus input. Resolving them would
require either:

1. Editing the consensus to normalise thicknesses (input change —
   needs human review against the source PDF measurements);
2. A separate stair-step canonicalisation pass that snaps wall
   thicknesses to a common value at junctions (cosmetic — would
   modify wall offset geometry).

Neither is in scope for FP-026 (which targets unsupported residuals).
Tracked as observation; not blocking the SKP deliverable.

## Reproduce

```bash
python -m tools.build_plan_shell_skp \
  fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json \
  --out runs/planta_74/planta_74.skp

python -m tools.diagnose_wall_stubs \
  fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json \
  --plant planta_74 --pdf planta_74.pdf

python -m pytest tests/test_wall_stub_canonicalization.py -v
```
