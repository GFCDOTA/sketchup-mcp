# FP-046 / P5 — promoção da porta Shaker: prova L2 refeita no commit da promoção

**Decisão D46-09 (opção C), Felipe, 2026-10-21.** O trecho **03:13–04:29** do vídeo `yt-cabinet-tips-2021` ("10 Tips for Modeling CABINETS in
SketchUp!") confirmou os 4 itens do checklist: frente como peça separada; **painel central em rebaixo dentro de moldura (estilo Shaker)**;
perfil interno por Offset e extrusão negativa controlada; gap geométrico real. A revisão está registrada na fonte
(`references/sketchup/knowledge/video_recipes.v1.json` → `sources[yt-cabinet-tips-2021].human_review`: quem, quando, trecho, o que confirmou).
Nenhuma fonte, locator ou evidência foi criada: o binding passou a citar também a recipe que o catálogo **já** atribuía a esse trecho.

**O que a promoção significa:** `bind.kitchen.shaker` → `kitchen.cabinet.shaker-door` (e `shared.cabinet.front.shaker`) está registrada, na allowlist
da cozinha, e `specialists.plan` devolve `PLAN_READY_NOT_EXECUTED` quando o pedido traz as medidas da porta.
**O que NÃO significa:** aprovação visual. `visual = NOT_REVIEWED` / `PENDING_HUMAN` — só o Felipe aprova a aparência. Nada mudou no veio
(`NOT_SUPPORTED`) nem em ferragem/gaveta.

| | |
|---|---|
| Código sob prova | commit `7820f74`, árvore **limpa** (`dirty: false` nos 3 `summary`) |
| SketchUp | 26.0.429 (Windows 11), `interactive`; **29 + 4 + 3 PIDs** (+ render e job interrompido do rerun liso), todos fechados por PID; nenhum SketchUp alheio tocado |
| Por que refazer | o `inspect_shaker` mudou na P4 e o `cabinet_flow.run_request` ganhou a recusa de Shaker: a regra R-18 não aceita prova velha sobre símbolo alterado |
| Reprodução | `l2_matrix.py` (P3), `l2_promoted.py` (esta pasta) e `artifacts/review/fp043/p7_kitchen_cabinet/l2_p7.py` — ver cabeçalhos |

## 1. Matriz sintética da P3 — `p3_matrix_*` (10 casos, 10 PASS)
Igual à P3, agora no commit da promoção: 1 porta a 0°/90°/30° (erro máx. 4,6e-7 m; 53 checks), 2 portas no mesmo gabinete (54), reexecução
idempotente (51), `make_unique` local (52), `propagate` explícito (50), material local, e 2 negativos no Ruby real (pai ausente; pai com outra assinatura).
Evidência da capability `shared.cabinet.front.shaker`.

## 2. Cozinha REAL pelo fluxo sem contorno — `kitchen_*` (12 verificações, 12 PASS)
`shaker_flow.run_request` (sem nenhum argumento de contorno) numa **cópia** do `.skp` mobiliado da planta_74:
- **positivo:** `DONE_L2_VERIFIED`; especialista `PLAN_READY_NOT_EXECUTED`; 8 gates PASS (pai + composição final); 50 checks do modelo reaberto, erro máx. 3,6e-15 m;
  `non_cabinet_fingerprint` antes = depois (`751a56d4…`); `knowledge` do trace mostra a fonte inspecionada **com a revisão humana**;
- idempotência (`ALREADY_DONE`, 0 SketchUp);
- **7 negativos, 0 PIDs, sem diretório de saída:** sem o bloco `shaker` (`BLOCKED_INPUT_INCOMPLETE`); pose fora da cozinha e espessura de moldura ≠ frente
  (`BLOCKED_PLAN_REFUSED`); "remover a parede" (`BLOCKED_ARCHITECTURE_CHANGE`); texto que não pede Shaker mas traz o bloco (`BLOCKED_TECHNIQUE_UNRESOLVED`);
  `source_verified=true` numa fonte sem revisão humana (`BLOCKED_KNOWLEDGE_EVIDENCE`); **o fluxo de frentes lisas recusa o pedido de Shaker**
  (`BLOCKED_CAPABILITY_MISMATCH`) em vez de construir um gabinete liso;
- FP-047 `strict_identity`: 0 deltas nas caixas planejadas, `introduced = 0`; **preexistente** (não introduzido): `CIRC|r000|corredor_principal` (SUITE 01, #351);
- canônicos byte a byte idênticos; **nenhum scratch** deixado dentro de `artifacts/`.
Evidência da capability `kitchen.cabinet.shaker-door`.

## 3. Rerun do fluxo de frentes lisas (P7) — `plain_fronts_*`
Como o `cabinet_flow.run_request` mudou (a recusa de Shaker), o L2 da P7 foi **refeito sem alterar o script**: `DONE_L2_VERIFIED`, 42 checks, erro máx. 3,6e-15 m,
canônico idêntico, job interrompido de verdade (`SU_EXITED`, sem resultado). Mudança de comportamento esperada nos negativos: o pedido "armário com porta Shaker" agora
dá `BLOCKED_INPUT_INCOMPLETE` (faltam as medidas da porta), não mais `BLOCKED_CAPABILITY_MISSING`. A prova original da P7 (`fp043/p7_kitchen_cabinet`) **não foi reescrita**:
o catálogo agora aponta o `run_request` para este rerun e mantém a P7 como evidência dos demais símbolos.

## Limites que o PASS não cobre
- **Aparência (L3): `PENDING_HUMAN`.** Nenhuma imagem foi julgada; valores da porta (50/50/16 mm, painel 6 mm, recuo 4 mm) são do pedido de teste, não decisão de design.
- A fonte sustenta a **técnica** (painel rebaixado dentro de moldura, Offset + extrusão negativa, gap real) em 76 s de um vídeo; não sustenta proporções, ferragem nem fabricação.
- Uma posição de gabinete (a do P7) e uma porta por pedido (duas portas = dois pedidos em sequência); sem regressão visual dos demais cômodos além do `strict_identity` das caixas planejadas.
- A circulação da SUITE 01 reprova antes e depois (preexistente); esta prova não a corrige nem a esconde.
- Veio da madeira: `NOT_SUPPORTED`.
