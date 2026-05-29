# GPT response — final_fail_non_obvious_fix

## Timestamp

2026-05-29T20:15:09Z

## Question file

`E:\Claude\sketchup-mcp\.ai_bridge\questions\20260529T201437Z_final_fail_non_obvious_fix.md`

## Raw response

---

* **Verdict**: GO
* **Reasoning**: Use **A+B**, with A as the primary test and B as a predeclared secondary metric. Full-input parity is the only rigorous path because it mirrors the production oracle conditions where clean `planta_74` is known to PASS; finding-level comparison then prevents top-level saturation from hiding a localized real defect. C alone is honest but inconclusive, and B alone is weaker because it keeps the broken single-image setup.
* **Risks**:

  * Full context may make the oracle too forgiving and still miss the corrupted wall.
  * Finding-level matching may become subjective unless region/type criteria are fixed before running.
  * Corrupting only the top render while side-by-side/geometry remain clean may confuse the model.
  * If clean still FAILs under full-input parity, the oracle path is not stable enough for this test.
* **Suggested next action**: CHOICE: A+B — rerun clean vs corrupted using the exact production inputs: top+iso+side_by_side+geometry context, corrupting only top render, with primary criterion `clean PASS/WARN + corrupted FAIL/WARN_worse`.
  Secondary criterion: corrupted must introduce a new localized missing-wall/gap finding overlapping the erased rectangle, absent from clean; otherwise mark NOT_CONCLUSIVE, not PASS.

## Decision taken

_To be filled by the agent or operator after acting on the response._
