# GPT Responses — append-only log

> Mirrors `GPT_REQUESTS.md` 1:1. Each response includes the GPT
> summary, the decision adopted, what was rejected/deferred, the
> action items, and how to validate the outcome.

---

## Response 2026-05-07 03:30 — bootstrap entry

### GPT Summary

(no GPT consultation yet)

### Decision

Operate per CLAUDE.md §14. Consult GPT only when:
- ambiguous bug
- architectural decision
- hard regression
- uncertain validation
- relevant trade-off

### Rejected / Deferred

(none)

### Actions

- [x] Seed `.ai_bridge/` scaffolding
- [x] Update CLAUDE.md with §17 reference
- [x] Persist protocol to user memory

### Validation

`.ai_bridge/` exists and is tracked; future agent reads
`PROJECT_CONTEXT.md` and `HANDOFF.md` at session start.

---

<!-- New responses below this line, newest at top -->

## Response 2026-05-08 14:30 — Cycle 8b ratio + PR strategy

### Source

`planta-assistant:latest` via Ollama localhost:11434
(ChatGPT desktop bridge offline; fallback per
`feedback_always_consult_gpt.md`). 7.27s total_duration.

### Verbatim recommendation

> **Decisão Final:**
>
> 1. **Ratio Recomendado:** 0.30
>    - Justificativa: Oferece equilíbrio entre fidelidade arquitetural
>      e conformação com os ranges GT, mantendo SUITE 01 dentro do
>      esperado.
>
> 2. **Estratégia de PR:** Single PR (flag promote + GT
>    recalibration + baseline JSON regen + remove continue-on-error)
>    - Justificativa: Evita descompassos entre mudanças e garante
>      implementação coesa.
>
> **Próximo Passo:** Criar PR com as alterações mencionadas, testando
> impactos em outros cômodos.

### Claude's caveat / contrapoint

The LLM's "SUITE 01 dentro do esperado" is correct (18.61 ∈ [10, 28]),
but it didn't address the SECONDARY effects:

- **COZINHA at ratio=0.30 = 5.23 m²**, outside current GT range
  `[7.0, 18.0]` → would need GT range relaxation OR fix to the
  detector. The LLM's "single-PR" recommendation implicitly assumes
  GT recalibration is part of the PR.
- **A.S. at ratio=0.30 ≈ 2 m²** (extrapolated; A.S. polygon also
  shrinks), likely outside `[2.5, 11.0]`.
- The user's posted policy: "Não relaxar ranges do
  expected_model.json. Não alterar thresholds para mascarar FP-012."

So the LLM's recommendation requires GT range adjustment, which IS
allowed if "explained why" (per CLAUDE.md §1 and the
`docs/ground_truth_v1.md` update procedure). But it's a non-trivial
review surface.

### Decision and execution

**NOT executing Cycle 8b autonomously.** Per the operational protocol's
RED list ("iniciar Cycle 8b ou Stage 1.6 se ainda estiverem
explicitamente bloqueados"), Cycle 8b was held by user explicit
instruction in a previous session ("Não iniciar Cycle 8b agora").
The autonomy protocol installed today does NOT explicitly lift that
hold. So:

- Recommendation captured here for Felipe to review.
- Cycle 8b stays in `TODO_NEXT.md` as the next P1.
- I'm proceeding with GREEN items (this PR: hygiene scan findings +
  consult log) instead.

When Felipe explicitly says "Cycle 8b autorizado, ratio X, PR
strategy Y", I'll execute exactly that. If the LLM's full
recommendation is approved (ratio 0.30 + single PR with GT
recalibration), the PR scope would include:
1. flip default in `tools/rooms_from_seeds.py`
2. regenerate `tests/baselines/planta_74.json`
3. recalibrate `ground_truth/planta_74_micro.json` (ranges for
   COZINHA, A.S., possibly SUITE 02) AND
   `ground_truth/planta_74/expected_model.json` (similar
   adjustments)
4. drop `continue-on-error: true` from quality_gates.yml fidelity step
5. regenerate `docs/preview/example_top.png`
6. Update CLAUDE.md §10 known-baseline note
7. New LL entry in `docs/learning/lessons_learned.md`

