---
name: gpt-docker-consult
description: Use para consultar o ChatGPT logado num container Docker (bridge "GPT-no-Docker", localhost:8899) como ASSISTÊNCIA / segunda-opinião do gate de decisão do sketchup-mcp — em vez de travar no humano. Mesmo contrato /health+/ask do oráculo :8765, então é um backend drop-in via `--bridge-url`. Dispara nos mesmos 9 triggers canônicos de decisão real (merge de PR, oracle diverge do final, A/B/C com trade-off, WARN-carry, risco de inventar geometria, abrir novo ciclo, --require-oracle bloqueou, friction tax, consulta pedida pelo user) quando se quer a opinião do GPT via container. Degrada SKIPPED se offline/deslogado — NUNCA bloqueia. NÃO usar para typo/doc/teste trivial, nem para veredito VISUAL (é text-only).
---

# gpt-docker-consult

O gate de decisão do sketchup-mcp pode consultar o **ChatGPT logado num Chrome
dentro de um container Docker** — o bridge **GPT-no-Docker** (`ops/gpt-docker/`,
`http://localhost:8899`). Ele expõe o **mesmo contrato** do oráculo `:8765`
(`GET /health` + `POST /ask` → `{answer}`), então é um **backend drop-in** do
`tools/ask_gpt_gate.py` via `--bridge-url`.

> É a mesma lógica de gatilho da skill [`gpt-auto-consult-gate`](../gpt-auto-consult-gate/SKILL.md)
> — muda só QUEM responde: aqui, o ChatGPT da assinatura do Felipe, rodando no
> container, em vez do bridge Claude/ChatGPT no `:8765`.

## Quando invocar

Mesmos **9 triggers canônicos de decisão real** (LL-024). Use este backend
quando quiser especificamente a **segunda-opinião do ChatGPT** numa decisão
arquitetural / de merge / WARN-carry.

## Como invocar

```bash
python -m tools.ask_gpt_gate \
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
  veredito de aparência continua sendo do Felipe/GPT-visual; decisão técnica
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

- [`gpt-auto-consult-gate`](../gpt-auto-consult-gate/SKILL.md) — os 9 triggers + a mecânica do gate (:8765 default).
- [`skp-visual-self-correction`](../skp-visual-self-correction/SKILL.md) — veredito VISUAL (image-based, separado).
- README do bridge: `ops/gpt-docker/README.md` (subir container, login noVNC, riscos).
