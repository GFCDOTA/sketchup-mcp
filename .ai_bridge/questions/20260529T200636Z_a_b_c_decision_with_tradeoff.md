# GPT Auto-Consult — a_b_c_decision_with_tradeoff

## Timestamp

2026-05-29T20:06:36Z

## Bridge status

ONLINE — bridge /health returned 200; body={"status":"ok","window_found":true}

## Prompt sent (or that would have been sent)

---

# GPT Auto-Consult Gate — context-driven question

## Trigger

`a_b_c_decision_with_tradeoff`

## Context

```json
{
  "loop": "Autonomous SKP Work Loop with GPT Peer Review",
  "repo_state": {
    "branch": "develop",
    "head": "030a42d (PR #208 LL-024 auto-trigger GPT consult)",
    "planta_74": "WARN_documented (ollama_vision oracle PASS + 3 known warnings carried)",
    "open_prs": "none",
    "tests": "~139 passed / 5 skipped (pre-#203..208 snapshot)"
  },
  "constraints": [
    "No fresh SketchUp build available/reliable -> slices must work from EXISTING planta_74.pdf + artifacts/planta_74/*.png + geometry_report.json + consensus.json",
    "Hard Rule #1: never invent walls/rooms/openings (consensus is source of truth)",
    "No FP-031 auto-fix without a real new FAIL",
    "Smallest useful slice; no cosmetic work; must advance REAL .skp fidelity discrimination",
    "ChatGPT bridge is ONLINE; GPT consult required (do not accept SKIPPED_OFFLINE)"
  ],
  "known_oracle_weakness": "ollama_vision returns PASS readily. We proved FAIL only on SYNTHETIC negative fixtures, NOT a real defect on the real planta_74 render. side_by_side is qualitative-only (no quantitative delta).",
  "candidates": {
    "A_overlay_diff": "Geometric overlay/diff PDF-vs-SKP-top -> quantitative delta metric replacing qualitative side-by-side. Roadmap #2 (~80% maturity). Larger scope: raster registration + diff metric + threshold policy.",
    "B_positional_detectors": "Add positional deterministic detector(s) to the 10-check suite (e.g. misplaced_soft_barrier via bbox-vs-wall-path; door/window centroid-inside-wall sanity). Roadmap #3. Sliceable to ONE detector. Pure geometry_report+consensus, no SU. Adds real FAIL-catching power.",
    "C_negative_dogfood_real": "Feed a deliberately-corrupted REAL planta_74 render through ollama_vision oracle + GPT to PROVE the oracle catches a real visual defect (closes the 'is the oracle actually discriminative on the real fixture?' question). Validation, not a new feature."
  },
  "question_focus": "Which single candidate is the highest-ROI FIRST slice, and what is its minimal version?"
}
```

## Question

Pick the single highest-ROI FIRST slice among candidates A, B, C (see context). Priorities: prove/raise REAL fidelity-discrimination of the visual oracle on the real planta_74 fixture; smallest useful slice; no inventing geometry; no auto-fix without a real FAIL; no fresh SketchUp build. State the chosen letter and its minimal first version. In your 'Suggested next action', START with 'CHOICE: <letter>'.

## Answer format

Respond with a short structured answer:

- **Verdict**: GO / NO-GO / MORE-INFO
- **Reasoning**: 2-4 sentences
- **Risks**: bullets, what could go wrong
- **Suggested next action**: 1-2 lines

No markdown fences around your response. No marketing fluff.
