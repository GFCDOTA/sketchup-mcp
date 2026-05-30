# Decision — planta_74 fidelity loop cycle (OFFLINE_DATA_ONLY)

Gate: `tools/pdf_overlay_verify.py` (consensus-on-PDF overlay + PDF door-arc
measurement) + `opening_audit.py` + geometry_report. No GPT/Chrome.

## Findings bucketed
| Item | Verdict | Evidence |
|---|---|---|
| **scale** | **SCALE_BUG (CONFIRMED)** | PT_TO_M 0.0352 vs PDF cotas 5.45/2.60/2.40 → ~0.0252 (~1.40× too big) |
| doors width/placement | FALSE_ALARM | 7 PDF arcs vs consensus, ratio 0.98–1.09 |
| external wall / perimeter | FALSE_ALARM | walls land on PDF perimeter (steps incl.) |
| floor leak | FALSE_ALARM | rooms fill within walls; gates floors_separated=✓ |
| blue glass / empty windows | RENDER_LEGIBILITY_BUG | 5 glass elements 0.05–0.09m from openings (placed); render doesn't show them |
| central rooms open | WARN_DOCUMENTED | open-plan (8 cells vs 11 ambients) |
| (geometry layout) | no GEOMETRY_BUG confirmed yet | suspicions verified so far have NOT confirmed a geometric bug |
| INCONCLUSIVE | none | — |

## Chosen (1, highest impact, confirmed): SCALE_BUG
Minimal patch: `ENV['PT_TO_M']` per-build override in `build_plan_shell_skp.rb`
(default UNCHANGED — quadrado keeps 0.0352; no fixture mutation). Built planta_74
`@0.0252`.

## Result (calibrated — no overconfidence)
- Apartment: **17.74×10.51 m → 12.71×7.53 m** (cota 5.45m reproduced). The
  absolute dimensions are now **data-correct** (cota-proven).
- gates_self_check all pass; **pytest 223 passed** (no regression; default scale unchanged).
- **Improved on the SCALE axis only** (data-confirmed). The render looks *subtly*
  different (zoom_extents auto-fits, so layout reads the same). **Representation /
  legibility NOT addressed** → planta_74 still has open issues there. This is a
  partial fix, not acceptance of the whole plan.

## Next item
RENDER_LEGIBILITY track (image/representation, per the hierarchy = audit, needs
visual review, not the data gate): door leaf reads as a full-height panel; glass
not legible in render. Candidate: door = thin leaf + a *legible* 2D swing arc.
Separately: make the scale value sticky per-fixture (build config, not fixture
mutation) so planta_74 builds at 0.0252 by default.
