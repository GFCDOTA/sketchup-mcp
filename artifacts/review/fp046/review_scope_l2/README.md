# FP-046 — follow-up do #357: a `human_review` precisa cobrir a recipe do pedido (L2 refeito)

**Defeito (meu, introduzido na promoção #354):** `shaker_flow.run_request` só conferia que a fonte citada tinha *alguma* `human_review`. A revisão do Felipe
(2026-10-21) cobre **uma** recipe e **um** trecho — `cabinet.front-gaps-and-profiles`, 03:13–04:29 de `yt-cabinet-tips-2021`. Um `source_verified=true` para
outra recipe do mesmo vídeo (ex.: `cabinet.countertop-separate-and-bevel`, 07:09–08:53) passaria e construiria a porta.

**Correção:** `source_verified=true` só passa se `human_review.recipe_id == origin_context.recipe_id`; senão `BLOCKED_KNOWLEDGE_EVIDENCE` antes do SketchUp,
dizendo qual recipe a revisão cobre. `source_verified=false` continua permitido (a fonte nunca é presumida verificada). Teste vermelho→verde em
`tests/test_fp046_kitchen_shaker.py` (3 outras recipes do mesmo vídeo; o vermelho foi visto na versão antiga do fluxo, que chegou até o SketchUp (o duplo de teste); qualquer reversão do símbolo também invalida a prova pelo digest, R-18).

**Por que L2 de novo:** o símbolo `run_request` mudou → a regra R-18 revoga a prova (`EVIDENCE_STALE`). O commit da correção revoga a evidência no catálogo
(`kitchen.cabinet.shaker-door` → `L1_PASS`); o commit seguinte a restaura apontando para esta pasta.

| | |
|---|---|
| Código sob prova | commit `4023b78`, árvore **limpa** (`dirty: false`) |
| SketchUp | 26.0.429 (Windows 11), `interactive`; 4 PIDs, todos fechados por PID; nenhum SketchUp alheio tocado; nenhum processo restante |
| Reprodução | `PT_TO_M=0.0259 PYTHONPATH=. python artifacts/review/fp046/review_scope_l2/l2_review_scope.py <saida em runs/> <cópia do .skp mobiliado> artifacts/review/fp046/promotion_l2/request.json` |

## Resultado — 13 verificações, 13 PASS (`kitchen_summary.json`)
- **positivo:** `DONE_L2_VERIFIED` na cozinha real (cópia do `.skp` mobiliado); 8 gates PASS (pai + composição); 50 checks do modelo reaberto, erro máx. 3,6e-15 m;
  `non_cabinet_fingerprint` antes = depois (`751a56d4…`); `source_verified: true` com a recipe **coberta** pela revisão;
- idempotência (`ALREADY_DONE`, 0 SketchUp);
- **8 negativos, 0 PIDs, sem diretório de saída** — os 7 de antes + **o novo:** `source_verified=true` para `cabinet.countertop-separate-and-bevel` da mesma fonte
  → `BLOCKED_KNOWLEDGE_EVIDENCE`; e o fluxo de frentes lisas continua recusando Shaker (`BLOCKED_CAPABILITY_MISMATCH`);
- FP-047 `strict_identity`: 0 deltas, `introduced = 0`; **preexistente** (não introduzido): `CIRC|r000|corredor_principal` (SUITE 01, #351);
- canônicos byte a byte idênticos; nenhum scratch dentro de `artifacts/`.

## O que NÃO é
Não é veredito visual: `visual = NOT_REVIEWED` / `PENDING_HUMAN` (o pacote L3 segue aguardando o Felipe). Não toca `plan_kitchen_shaker`, `plan_shaker_door` nem
o Ruby; o `promotion_l2/` fica como registro histórico da promoção (#354), sem reescrita.
