---
name: gpt-review-gate
description: >-
  GATE obrigatório de GPT_REVIEW (Modo B) para TODA mudança de APARÊNCIA (render/SKP).
  O GPT é o validador; o agente NUNCA autojulga IMPROVED/SAME/WORSE/PASS. Use sempre que
  um render/montagem/SKP muda visualmente e precisa de veredito antes de promover.
---

# GPT_REVIEW — gate de validação visual (Modo B)

> Felipe: "o GPT é o validador, precisa de um STEP de GPT_REVIEW pra ser um gate."
> Regra-raiz: mudança de aparência = veredito do GPT (texto, schema), **nunca** autojulgado.

## Quando dispara (trigger)

Qualquer artefato visual novo/alterado antes de ser promovido/commitado como deliverable:
render V-Ray, montagem, SKP com mudança visível, textura, câmera, iluminação.

## Fluxo (agent-in-the-loop — o round-trip usa a sessão ChatGPT autenticada no Chrome do Felipe)

1. **prepare** — `python tools/gpt_review.py prepare --id <id> --image <png> --context "<o que mudou + pergunta>"`
   Seta o clipboard com a imagem (`setclip.ps1 -STA`), imprime o PROMPT Modo B canônico, grava PENDING no ledger.
   (Render via `tools/render_room.ps1 -ReviewId <id> -ReviewCtx "..."` já chama o prepare automático.)
2. **consult** — colar no thread ChatGPT (Chrome MCP, tab "Veredito minimalista FAIL"): `ctrl+v` a imagem +
   colar o prompt + enviar. Capturar o texto do veredito. Se o GPT começar a gerar IMAGEM, clicar "Parar de
   responder" e re-pedir texto. Limpar o composer (`ctrl+a`+Delete) antes de colar (evita texto stale).
3. **record** — salvar o texto do veredito num .txt e `python tools/gpt_review.py record --id <id>
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

- `tools/gpt_review.py` — prepare / record / show (parser + gate + ledger). Testado: `tools/test_gpt_review.py`.
- Ledger append-only: `artifacts/review/interior/gpt_review_ledger.jsonl`.
- Espelho humano: `artifacts/review/interior/gpt_verdicts.md`.

## Anti-regras

- NÃO pular o gate em mudança visual "óbvia" — o veredito local é comprovadamente não-confiável.
- NÃO promover artefato com gate FAIL.
- NÃO inventar/parafrasear o veredito — registrar o texto **cru** do GPT no ledger (`raw`).
