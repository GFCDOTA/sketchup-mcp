---
name: gpt-auto-consult-gate
description: Use when a real architectural / merge / WARN-carry decision arises and the agent should consult ChatGPT automatically instead of asking the user to copy/paste. Triggers on phrases like "should this PR merge", "oracle disagrees with final", "open new cycle", "BLOCKED by --require-oracle", "friction tax risk", "A/B/C decision", or whenever one of the 9 canonical triggers in LL-024 applies. Do NOT use for typo/doc-only/small-test/clean-merge decisions.
---

# gpt-auto-consult-gate

Skill operacional para o **GPT Auto-Consult Gate** (LL-024).

> Felipe NÃO é canal de copy/paste pra ChatGPT. Quando o agente bate
> em decisão real, ele monta a pergunta, chama o bridge text-only
> e registra Q+A no repo. Sem fingir resposta.

Detalhe completo em
[`docs/specs/LL-024_gpt_auto_consult_gate.md`](../../../docs/specs/LL-024_gpt_auto_consult_gate.md).

## When to invoke

Auto-trigger quando **um dos 9 gatilhos canônicos** aplica:

1. `oracle_verdict_neq_final_verdict` — oracle e final aggregate divergem
2. `oracle_pass_but_known_warnings` — oracle PASS mas baseline WARNs carregam
3. `final_fail_non_obvious_fix` — FAIL sem fix óbvio
4. `a_b_c_decision_with_tradeoff` — chamada multi-path com trade-off real
5. `risk_of_inventing_geometry` — território Hard Rule #1
6. `about_to_open_new_cycle_post_slice` — slice complete, risco de novo ciclo
7. `require_oracle_blocks_backend` — `--require-oracle` BLOQUEOU
8. `big_pr_changes_gate_or_spec` — risco de friction tax
9. `user_requested_consult` — gatilho explícito do user

## When to NOT invoke

- Typo / doc-only trivial
- Teste pequeno e evidente
- Merge de PR pequena e verde
- Limpeza local sem impacto
- Decisão já coberta por regra canônica (constitution, operational_rules)
- Loop que repetiria pergunta já respondida (ler `.ai_bridge/responses/`
  antes)

## Como invocar

```bash
python -m tools.ask_gpt_gate \
  --trigger oracle_pass_but_known_warnings \
  --question "Should PR #206 merge given oracle PASS but 3 known WARNs carry?" \
  --context-file /tmp/ctx.json \
  --repo-state-file /tmp/repo_state.json
```

Saída:
- `.ai_bridge/questions/<UTC>_<trigger>.md`
- `.ai_bridge/responses/<UTC>_<trigger>.md` (se bridge online)

Com `--require-consult`: bloqueia exit code 3 se bridge offline.

## Bridge offline behavior

- Default: status = `GPT_CONSULT_SKIPPED_OFFLINE`. Questão fica
  registrada pro humano forward manual. Não trava o agente.
- Com `--require-consult`: status = `BLOCKED_BRIDGE_OFFLINE`, exit 3.
  Use só quando a decisão **não pode** ser tomada sem GPT input.

## Hard rule

**Não fingir resposta.** Se bridge offline e não require-consult, registra
a questão e segue. Se require-consult, BLOCKED honesto.

## Anti-padrões

- Chamar GPT pra todo commit trivial → ruído + custo
- Chamar GPT em loop sem ler respostas anteriores
- Substituir Visual Oracle (FP-030) por isso — GPT é text-only, decisões
  arquiteturais; não recebe imagens

## Skills relacionadas

- [`skp-visual-self-correction`](../skp-visual-self-correction/SKILL.md) — visual oracle (image-based, separate)
- [`repo-governance`](../repo-governance/SKILL.md) — PR/merge mechanics
- [`multi-agent-handoff`](../multi-agent-handoff/SKILL.md) — quando coordena outro agente
