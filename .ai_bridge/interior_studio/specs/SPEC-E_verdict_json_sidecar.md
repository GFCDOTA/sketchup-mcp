# SPEC-E — Veredito GPT → JSON sidecar (fim do estado por substring)

- **Sessão:** 2026-06-22 · linha STUDIO · branch `feat/sofa-class-from-reference`
- **Status:** ✅ FECHADO

## Problema (GPT: "maior risco real do core")
`asset_state()` derivava `form_pass`/`ctx_pass` por **substring de markdown**
(`"contexto" in vlow and "pass" in vlow`, `"parou de parecer caixa" in vlow`). Frágil:
o veredito do GPT varia idioma/caixa/frase → um asset aprovado podia travar (ou um
texto ambíguo falsear PASS).

## Goal
Estado deriva de um JSON ESTRUTURADO `{asset, gate, verdict, environment}`; o markdown
vira fallback (compat retro) e espelho humano.

## Implementação (`tools/interior_studio/project_state.py` + `tools/gpt_review.py`)
1. **`save_asset_verdict(asset, gate, verdict, environment, md, subdir)`** — grava
   `artifacts/review/furniture/<asset>/<gate>/gpt_verdict.json` (1 JSON por gate),
   opcional o `.md` espelho. Idempotente. É a API "ao salvar um veredito".
2. **`asset_state` JSON-first**: glob `**/gpt_verdict.json` → `form_pass = ∃ gate~form & PASS`,
   `ctx_pass = ∃ gate~context & PASS`. Sem sidecar → cai no fallback markdown (antigo).
   `build_done`/`vray_done` continuam por file-glob (não eram o problema).
3. **`gpt_review.py record --asset --stage [--environment]`**: ao registrar o veredito no
   ledger, emite TAMBÉM o sidecar estruturado (vereditos futuros já nascem estruturados —
   evita o problema do markdown manual voltar).
4. **Backfill**: o único veredito em disco (`sofa/venezia`, Forma PASS + Contexto PASS) virou
   2 sidecars (`venezia/form`, `venezia/context`). Estado do sofá `vray_ready` ANTES (md) e
   DEPOIS (JSON) — sem regressão.

## Prova
- 4 testes novos em `tests/test_project_state.py`: estado deriva do JSON · FAIL não avança ·
  **JSON vence o markdown** (md diz "contexto pass", JSON FAIL → não vray_ready) · roundtrip
  `save_asset_verdict`. Fallback markdown ainda coberto pelo teste antigo. **24/24 verdes.**
- Backfill verificado: sofa `vray_ready` antes e depois.

## Aceite — status
- [x] Estado deriva do JSON (com fallback markdown).
- [x] `save_asset_verdict` + emissão no `gpt_review record`.
- [x] Testes verdes (24/24).
