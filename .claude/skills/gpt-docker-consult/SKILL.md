---
name: gpt-docker-consult
description: >-
  DORMENTE. Consulta o ChatGPT logado no container GPT-Docker (localhost:8899, contrato /health + /ask) como segunda
  opinião TEXTUAL de uma decisão técnica, via tools.oracle.ask_gpt_gate --bridge-url; degrada para SKIPPED_OFFLINE sem
  bloquear nem fabricar resposta. Use só quando o Felipe pedir a opinião do GPT. Não serve para veredito visual (é do
  Felipe) nem para typo, doc ou teste trivial.
disable-model-invocation: true
---

# gpt-docker-consult

> **Status: DORMENTE (2026-07-27).** Docker Desktop costuma estar parado; não subir o container nem
> consultar sem o Felipe pedir. Decisão técnica = evidência determinística (+ Ollama `:11434` se precisar);
> veredito visual é do Felipe, no chat (decisão de 2026-07-27).

O gate de decisão do sketchup-mcp pode consultar o **ChatGPT logado num Chrome
dentro de um container Docker** — o bridge **GPT-no-Docker** (`ops/gpt-docker/`,
`http://localhost:8899`). Ele expõe o **mesmo contrato** do antigo oráculo `:8765` (removido)
(`GET /health` + `POST /ask` → `{answer}`), então é um **backend drop-in** do
`tools/oracle/ask_gpt_gate.py` via `--bridge-url`.

> Quem responde é o ChatGPT da assinatura do Felipe, rodando no container.

## Quando invocar

Mesmos **9 triggers canônicos de decisão real** (LL-024). Use este backend
quando quiser especificamente a **segunda-opinião do ChatGPT** numa decisão
arquitetural / de merge / WARN-carry.

## Como invocar

```bash
python -m tools.oracle.ask_gpt_gate \
  --trigger user_requested_consult \
  --question "Devo mergear a PR #X dado oracle PASS mas 3 WARNs conhecidos carregam?" \
  --bridge-url http://localhost:8899 \
  --purpose merge_decision
```

- Probe `http://localhost:8899/health`; se online, POST em `/ask` e grava a
  resposta em `.ai_bridge/responses/<UTC>_<trigger>.md`.
- A questão sempre vira arquivo em `.ai_bridge/questions/` (auditável).
- `--purpose`/`--tier` são ignorados pelo GPT-no-Docker (é ChatGPT web, sem
  roteamento de modelo) — mas não quebram; podem ficar pro caso de trocar o
  backend depois.

## Comportamento offline (degrada, não bloqueia)

- Container fora ou ChatGPT deslogado → status `GPT_CONSULT_SKIPPED_OFFLINE`.
  A questão fica registrada; o agente **segue**. (Relogar: noVNC em `:7900`.)
- `--require-consult` força `BLOCKED_BRIDGE_OFFLINE` (exit 3). **Evite** com
  este backend — ele é assistência, não fundação; não deve travar o pipeline.

## Limites e honestidade (importante)

- É **assistência / segunda-opinião**, NÃO um juiz que fecha gate sozinho. O
  veredito de aparência é do Felipe; decisão técnica
  continua ancorada em evidência determinística.
- É **browser-automation da assinatura ChatGPT** — frágil (login/DOM/Cloudflare)
  e **fora dos Termos da OpenAI em escala**. Um bug, rate-limit ou desafio
  "verify you are human" **não pode** travar o build. Por isso: degrada SKIPPED,
  nunca `--require-consult` aqui.
- Para rotina barata, prefira o LLM local (Ollama). Para decisão de produção
  séria, o caminho robusto é a **API oficial** (ver `GPT_REVIEW_REPOS.md` no
  workspace). O GPT-no-Docker é um **fallback de laboratório**.
- Text-only: NÃO substitui o Visual Oracle (FP-030, `skp-visual-self-correction`)
  — este não recebe imagens.

## Skills relacionadas

- [`skp-visual-self-correction`](../skp-visual-self-correction/SKILL.md) — veredito VISUAL (image-based, separado).
- README do bridge, no workspace (fora deste repo): `E:/Claude/ops/gpt-docker/README.md`.
