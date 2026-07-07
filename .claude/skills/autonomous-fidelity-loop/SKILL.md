---
name: autonomous-fidelity-loop
description: Use quando o Felipe quer a sessão trabalhando a fidelidade de uma planta (planta_74 etc.) de forma CONTÍNUA e autônoma, em ciclos auto-ritmados, imprimindo um LOG de status por ciclo (PROGREDINDO/PATINANDO/BLOCKED), auto-corrigindo o que os detectores DETERMINÍSTICOS pegam, registrando lições, e parando só em RED / patinagem / NEEDS-HUMAN / backlog esgotado. Dispara em "não pare", "loop contínuo", "fidelity loop", "deixa rodando sozinho", "trabalha sozinho na planta", ou pedido de feedback de progresso ao vivo. NÃO usar pra tarefa pontual nem doc/typo.
---

# Autonomous Fidelity Loop

**O motor agora é código, não prosa** (FP-033): `tools/correction_loop.py` é a
máquina de estados que detecta → classifica → conserta → re-checa sozinha. Esta
skill virou o **protocolo humano de supervisão** — como acionar o motor, ler o
que ele produziu e decidir o próximo passo. Não re-executar o ciclo à mão.

## As 3 peças do motor

1. **`tools/correction_loop.py`** — o laço. Estados: `CLEAN` / `STALL` /
   `NEEDS_FELIPE` / `PENDING_VISION` / `MAX_CYCLES` / `RED`; exit 0 = limpo,
   1 = STALL/RED, 3 = enfileirado (visão/humano — **não é falha**).
   ```
   python -m tools.correction_loop --fixture planta_74 --out runs/loop_x [--max-cycles N] [--dry-run]
   ```
2. **`tools/vision_queue_consumer.py`** — drena `<out>/vision_requests.jsonl`
   pelo olho FP-032 (`POST /ask-vision` no `:8765`) e escreve
   `vision_confirmed.jsonl`, que o loop re-injeta no próximo ciclo. Degrada
   honesto: sem render → `BLOCKED_NEEDS_RENDER`; bridge offline/incompatível →
   `BLOCKED_NEEDS_FP032` (fila intacta, ZERO achado fabricado). FAIL do oráculo
   só permanece FAIL com dogfood `DISCRIMINATED` do backend (paridade FP-032).
3. **NOC `kind:"correction_cycle"`** — 1 task = 1 ciclo em worktree isolado off
   `origin/develop` via `noc_dispatcher` (ver `NOC_DISPATCHER.md`). Mudança de
   consensus → `VISUAL_REVIEW_QUEUED`; só evidência → `COMMITTED`. Nunca main.

## Protocolo de supervisão (o que VOCÊ faz)

Por rodada, leia — nesta ordem — e aja pela tabela:

- `<out>/loop_result.json` (estado, ciclos, fixes, filas)
- `<out>/consumer_result.json` (o que o olho consumiu/bloqueou)
- `.ai_bridge/noc/actions.jsonl` (ledger — status por task)

| estado | ação |
|---|---|
| `CLEAN` | backlog fechado — **parar é o certo**, não inventar ciclo. |
| `PENDING_VISION` | rodar `vision_queue_consumer` (ou aguardar bridge subir) e enfileirar task nova de ciclo. |
| `NEEDS_FELIPE` | revisar `<out>/visual_review_queue.jsonl` com o Felipe (Chrome, vs PDF). Nunca autojulgar. |
| `STALL` / `RED` | investigar a causa raiz; **não** re-tentar em loop (patinagem detectada é feature). |
| `MAX_CYCLES` | avaliar se vale nova task com teto maior — decisão explícita, não default. |
| `BLOCKED_NEEDS_FP032` (consumer) | bridge `:8765` fora/sem `/ask-vision` — pedido fica na fila; não fabricar achado. |

Log por rodada (mantido do protocolo original): 1 linha
`[ciclo N] estado=<X> fixes=<n> felipe_q=<n> vision_q=<n> | PROGREDINDO/PATINANDO/BLOCKED | aprendi: <1 frase ou —>`.

## Invariantes (não furar — RED)

- **Aparência NUNCA auto**: findings de aparência roteiam `NEEDS_FELIPE` /
  `VISUAL_REVIEW_QUEUED` por construção (router + `_appearance_changed`). O
  veredito visual final é exclusivo do Felipe (Chrome-only).
- **Zero achado fabricado**: sem FP-032 disponível o pedido FICA na fila; o
  loop nunca inventa finding visual.
- **Fixtures pinadas intocáveis**: o loop trabalha em CÓPIA; promover
  `consensus_candidate.json` pra `fixtures/` é gate humano (Hard Rule #3).
- **Heartbeat best-effort**: `:8765` offline nunca trava um ciclo.
- Develop-first; commit por slice; `--mode headless` proibido em dev local.

## Limites honestos (dizer ao Felipe, não fingir)

- "Aprender" = lição em arquivo + reler — não é rede neural aprendendo.
- "Perceber a planta errada" = o que os detectores determinísticos medem + o
  que o olho FP-032 **confirma discriminado**; o julgamento final é humano.
- "Não parar" = não parar à toa; `CLEAN`/`STALL` são paradas corretas —
  continuar sem ROI é patinar.
