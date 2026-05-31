# GPT Auto-Consult — final_fail_non_obvious_fix

## Timestamp

2026-05-29T20:14:37Z

## Bridge status

ONLINE — bridge /health returned 200; body={"status":"ok","window_found":true}

## Prompt sent (or that would have been sent)

---

# GPT Auto-Consult Gate — context-driven question

## Trigger

`final_fail_non_obvious_fix`

## Context

```json
{
  "situation": "Negative dogfood on the REAL planta_74 render. Erased a top exterior wall segment (rect 400,92,740,122 filled with background gray) -> a missing-wall gap. Ran ollama_vision (qwen2.5vl:7b) on clean vs corrupted TOP render ONLY (single image, empty context).",
  "result": "NOT_DISCRIMINATED at top_level: clean=FAIL, corrupted=FAIL",
  "key_observations": [
    "CLEAN (good baseline) render returned FAIL with hallucinated wall_stub findings, and cited evidence_image 'model_iso.png' even though ONLY the top render was sent (the model never saw an iso). So it confabulates.",
    "In the FULL pipeline (top+iso+side_by_side + geometry_report context) the SAME oracle returns PASS for planta_74 (3 runs). So single-image + empty-context makes it over-pessimistic/unstable -> the clean baseline saturated at FAIL, leaving no room for the corruption to make it worse.",
    "The CORRUPTED render DID produce defect-localized findings the clean did not: 'top center ... not fully enclosed, visible gaps' (full_height_window_void) and a 'missing_wall_continuation' finding. So it arguably noticed the erased top wall, but top_level saturated at FAIL on both."
  ],
  "candidate_refinements": {
    "A_full_input_parity": "Mirror the real pipeline input: send top+iso+side_by_side + geometry context for BOTH runs; corrupt ONLY the top render. Likely un-saturates the clean baseline back to PASS, giving the corruption a chance to drag top_level down. Most faithful to the production path.",
    "B_finding_level_metric": "Keep single image but change the discrimination metric from top_level to finding-level: 'corrupted produces a NEW missing-wall/gap finding localized to the corrupted region that clean does not'. The data suggests this would register as DISCRIMINATED.",
    "C_accept_and_document": "Accept as-is: the single-image probe already shows the oracle is unstable/over-pessimistic (FAILs the clean baseline, hallucinates an unseen image). Document this oracle-robustness limitation and stop the slice."
  },
  "constraints": [
    "smallest useful slice",
    "no inventing geometry",
    "no fresh SketchUp build",
    "no FP-031 auto-fix",
    "be honest, do not fabricate a verdict"
  ],
  "question_focus": "Most rigorous yet smallest refinement to make this a CONCLUSIVE real-fixture discrimination test."
}
```

## Question

The negative dogfood was NOT_DISCRIMINATED because the oracle saturates at FAIL on a single top render (it even FAILs the clean good baseline and hallucinates an unseen iso image), while in the full pipeline it returns PASS. Pick the most rigorous yet SMALLEST refinement (A full-input parity, B finding-level metric, C accept+document, or a combo) to make this a conclusive real-fixture discrimination test. Start 'Suggested next action' with 'CHOICE: <letter(s)>'.

## Answer format

Respond with a short structured answer:

- **Verdict**: GO / NO-GO / MORE-INFO
- **Reasoning**: 2-4 sentences
- **Risks**: bullets, what could go wrong
- **Suggested next action**: 1-2 lines

No markdown fences around your response. No marketing fluff.
