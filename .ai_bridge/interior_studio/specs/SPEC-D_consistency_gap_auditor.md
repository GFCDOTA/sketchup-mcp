# SPEC-D — Consistency/Gap Auditor (worker que PROPÕE, nunca muta)

- **Sessão:** 2026-06-22 · linha STUDIO · branch `feat/sofa-class-from-reference`
- **Status:** ✅ FECHADO
- GPT: "ouro" — o único worker local autônomo que paga (propõe, não muta).

## Goal
Worker offline que lê os sinais reais (project_state · packs · gpt_verdict · proposals) e
gera `proposal` tipo `consistency_gap` (requires_approval, NUNCA muta) → aparece no dash p/ aprovar.

## Decisão — DETERMINÍSTICO (não LLM)
Os exemplos de gap do handoff são todos **checks determinísticos**. Filosofia do projeto:
gate determinístico = verdade, LLM = consultivo. Auditor determinístico é mais robusto e
testável; LLM só serviria pra frasear (firula aqui). `tools/interior_studio/auditor.py`.

## Checks
- **C1 duplicate_main** — pack com >1 referência ⭐ principal.
- **C2 no_json_verdict** — asset em estado avançado (vray_ready/approved/learned) sem
  `gpt_verdict.json` (apoiado em markdown frágil) [tie SPEC-E].
- **C3 competing_program** — cômodo com programa aprovado E proposta pendente.
- **C4 stale_program** — programa APROVADO que o gate do Arquiteto (SPEC-C) corrigiria.
- **C5 buggy_pending_program** — proposta PENDENTE que o gate corrigiria (gerada antes do SPEC-C).

`audit()` puro (sem efeito); `audit_and_save()` salva os gaps não-resolvidos como pending,
remove pending obsoletos (gap que sumiu), NUNCA toca approved/rejected. + `proposals.delete()`.

## Dash
- Ação `audit` em `_proposal_action` → roda `audit_and_save`.
- Seção **🔍 Auditor de Consistência** (botão "rodar auditoria" + cards de gap por severidade +
  aceitar/ignorar, reusa `/api/proposal`).

## Prova
- 6 testes em `tests/test_auditor.py` (duplicate_main · estado avançado sem json · sidecar
  resolve · programa aprovado viola gate · pending viola gate · audit_and_save salva+limpa stale).
- **Live no repo real: 3 gaps REAIS** — as proposals pendentes da sessão anterior (pré-SPEC-C):
  suíte sem `cama`, cozinha com `banheiro_*`, banheiro sem `vaso`. Salvos como pending.
- **Dash (Chrome): seção renderiza os 3 cards, 0 erro de console.**

## Aceite — status
- [x] Propostas de gap reais aparecem no dash pra aprovar.
- [x] Worker propõe, nunca muta. Testes verdes (6/6).
