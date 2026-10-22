---
name: gpt-review-gate
description: >-
  LEGADO. Fluxo antigo de GPT_REVIEW (prepare → consult → record em tools/oracle/gpt_review.py) que pedia veredito
  visual ao ChatGPT. Substituído em 2026-07-27: o veredito visual é do Felipe, direto no chat. Use só se o Felipe
  pedir explicitamente uma revisão pelo GPT, ou para ler o ledger histórico
  artifacts/review/interior/gpt_review_ledger.jsonl.
disable-model-invocation: true
---

# GPT_REVIEW — gate de validação visual (Modo B) — LEGADO

> **Status: substituído em 2026-07-27.** O veredito visual é do Felipe, direto no chat; a evidência fica
> `PENDING_HUMAN` até ele responder. Este fluxo só roda se ele pedir uma revisão pelo GPT. O código
> (`tools/oracle/gpt_review.py`) e o ledger seguem válidos como histórico. Texto abaixo = padrão antigo.

> Felipe: "o GPT é o validador, precisa de um STEP de GPT_REVIEW pra ser um gate."
> Regra-raiz: mudança de aparência = veredito do GPT (texto, schema), **nunca** autojulgado.

## Quando dispara (trigger)

Qualquer artefato visual novo/alterado antes de ser promovido/commitado como deliverable:
render V-Ray, montagem, SKP com mudança visível, textura, câmera, iluminação.

## Fluxo (agent-in-the-loop — o round-trip usa a sessão ChatGPT autenticada no Chrome do Felipe)

1. **prepare** — `python -m tools.oracle.gpt_review prepare --id <id> --image <png> --context "<o que mudou + pergunta>"`
   Seta o clipboard com a imagem (`setclip.ps1 -STA`), imprime o PROMPT Modo B canônico, grava PENDING no ledger.
   (Render via `tools/rendering/render_room.ps1 -ReviewId <id> -ReviewCtx "..."` já chama o prepare automático.)
2. **consult** — colar no thread ChatGPT (Chrome MCP, tab "Veredito minimalista FAIL"): `ctrl+v` a imagem +
   colar o prompt + enviar. Capturar o texto do veredito. Se o GPT começar a gerar IMAGEM, clicar "Parar de
   responder" e re-pedir texto. Limpar o composer (`ctrl+a`+Delete) antes de colar (evita texto stale).
3. **record** — salvar o texto do veredito num .txt e `python -m tools.oracle.gpt_review record --id <id>
   --verdict-file <txt> --image <png>`. Parseia o schema → ledger JSONL + espelho em `gpt_verdicts.md` →
   decide o GATE.

## Decisão do gate (saída do `record`, código de saída 0=promove / 1=bloqueia)

- **PASS** → promove o artefato.
- **WARN** → promove, mas registra o(s) eixo(s) WARN como **backlog** (não bloqueia).
- **FAIL** (VERDICT=FAIL **ou qualquer dimensão=FAIL**) → **BLOQUEIA promoção**; corrigir e re-rodar o gate.

## Schema Modo B (canônico)

`VERDICT: PASS|WARN|FAIL // PREMIUM_REALISM: // MATERIALS: // LIGHTING: // CAMERA: //
FURNITURE_DETAIL: // TOP_3_ISSUES: 1) 2) 3) // NEXT_ACTION:` (dimensões configuráveis via `--dims`).
Prompt sempre força: SÓ TEXTO, SEM IMAGEM, SEM REDESENHAR.

## Artefatos

- `tools/oracle/gpt_review.py` — prepare / record / show (parser + gate + ledger). Testado: `tests/test_gpt_review.py`.
- Ledger append-only: `artifacts/review/interior/gpt_review_ledger.jsonl`.
- Espelho humano: `artifacts/review/interior/gpt_verdicts.md`.

## Anti-regras

- NÃO pular o gate em mudança visual "óbvia" — o veredito local é comprovadamente não-confiável.
- NÃO promover artefato com gate FAIL.
- NÃO inventar/parafrasear o veredito — registrar o texto **cru** do GPT no ledger (`raw`).
