# FP-046 / P4 — porta Shaker na cozinha REAL da planta_74 (L2, pré-promoção)

**O que está provado:** o adapter opt-in da cozinha (`capabilities/shaker.py`) e o fluxo de pré-promoção (`capabilities/shaker_flow.py`)
levam um pedido de gabinete + porta Shaker, na cozinha real, por **gates antes do job** → gabinete-pai numa cópia → Shaker aplicada
→ salvo → **reaberto em outro processo** → inspecionado e verificado; o resto do apartamento fica como estava.
**O que NÃO está provado / NÃO aconteceu:** promoção ao catálogo (o binding `bind.kitchen.shaker` segue **sem capability**, D46-09),
qualidade estética (L3 = `PENDING_HUMAN`), posição "boa" de projeto, ferragem/gaveta, veio (`NOT_SUPPORTED`).

| | |
|---|---|
| Código sob prova | commit `34d5cf6a`, árvore **limpa** (`dirty: false` em [`summary.json`](summary.json)) |
| SketchUp | 26.0.429 (Windows 11), `interactive`; **4 PIDs** (baseline, pai, Shaker, reabertura), todos fechados por PID; nenhum SketchUp alheio tocado |
| Base | **cópia** de `artifacts/planta_74/furnished/planta_74_furnished.skp`; os 3 canônicos (dois `.skp` + consensus) ficaram **byte a byte idênticos** (`canonical_before == canonical_after`) |
| Pedido | [`request.json`](request.json): o pedido do P7 (480×545×780 mm, pose 2,25 m / 15,90 m / 0°, frente 16 mm) + porta `50/50/16 mm`, painel 6 mm, recuo 4 mm. **Medidas escolhidas por quem pediu a prova** (origem `user_request`), não decisão de design da cozinha |
| Reprodução | `PT_TO_M=0.0259 PYTHONPATH=. python artifacts/review/fp046/p4_kitchen_shaker_l2/l2_p4.py <saida> <base_mobiliado.skp> request.json` (saída fora de `fixtures/` e `artifacts/`) |

## Resultado (8 verificações, 8 PASS)

| Caso | O que prova |
|---|---|
| `positive_kitchen_shaker` | estado `PREPROMOTION_L2_VERIFIED` (**nunca** `DONE_L2_VERIFIED`), `promotion: NOT_PROMOTED`. Trace: `request → project_room → consensus_requirements → knowledge → specialist_plan (BLOCKED) → prepromotion (ACK) → plan_validation → allowlist (PREPROMOTION) → baseline_inspect → job_parent → job_shaker → reopen_inspection → kitchen_anchor_after → evidence`. **8 gates PASS** (pai: âncora, arquitetura, mobília, circulação; composição final: os mesmos 4). 50 checks do modelo reaberto, erro máx. de vértice 3,6e-15 m, recuo medido no modelo = pedido. `non_cabinet_fingerprint` antes = depois (`751a56d4…`, o mesmo do P7) |
| `same_key_already_done` | mesma chave de idempotência: `ALREADY_DONE`, nenhum SketchUp |
| `default_blocked_capability_missing` | **sem** `prepromotion_ack`, o fluxo para em `BLOCKED_CAPABILITY_MISSING` antes de qualquer SketchUp e não cria diretório de saída |
| `pose_outside_kitchen_refused_before_job` | gabinete fora da cozinha ⇒ `BLOCKED_PLAN_REFUSED` (gate de arquitetura do pai), 0 PIDs |
| `architecture_change_blocked_even_with_ack` | "…e remover a parede oeste" ⇒ `BLOCKED_ARCHITECTURE_CHANGE` **mesmo com o ack** (o ack só contorna `BLOCKED_CAPABILITY_MISSING`), 0 PIDs |
| `shaker_geometry_refused_before_job` | `frame_thickness` ≠ espessura da frente do pai ⇒ recusa antes do job, 0 PIDs |
| `fp047_strict_identity_planned_boxes_and_canonicals` | FP-047 `strict_identity` sobre a planta_74 antes × depois: 0 deltas nas 402 caixas planejadas, canônicos intactos, `introduced = 0`; **preexistente** (não introduzido): `CIRC|r000|corredor_principal` (circulação da SUITE 01, ver PR #351) |
| `canonicals_byte_identical` | SHA-256 dos canônicos antes = depois |

[`trace.json`](trace.json) é o trace completo; [`negatives.json`](negatives.json) os estados dos negativos; [`fp047_report.json`](fp047_report.json) o relatório do gate de regressão.
O `.skp` de saída fica em `runs/` (não versionado; SHA-256 em `trace.json: evidence.skp_sha256` = `833f3a70…`).

## Achado desta fase (a 1ª rodada foi descartada)

A 1ª execução já dava 8/8, mas deixou **3 arquivos de scratch dentro de `artifacts/planta_74/furnished/`**: `inspect_shaker` criava a pasta do
job AO LADO do `.skp` inspecionado, e aqui o `.skp` era o canônico. Os canônicos seguiram idênticos (hash conferido) e o lixo foi apagado,
mas a regra "nada de job escreve em `artifacts/`" estava quebrada. Corrigido (`_scratch_dir`: cai em `runs/`; teste novo reprova o comportamento
antigo) e **toda a prova foi refeita** no commit corrigido — esta pasta é a 2ª rodada. O mesmo padrão existe em `cabinet.sketchup.inspect`
(fluxo de frentes lisas, **não tocado** nesta fase): fica como achado para quem passar um `.skp` canônico direto àquele driver.

## Limites que o PASS não cobre

- **Pré-promoção, não promoção.** O fluxo só roda com `prepromotion_ack=True` (argumento de código do operador, nunca lido do texto/receita) e
  só contorna `BLOCKED_CAPABILITY_MISSING`. `specialists.plan` segue devolvendo esse bloqueio; catálogo, perfil e allowlist **não mudaram**.
  A fonte do binding é `TRANSCRIPT_AND_DESCRIPTION_ONLY` (`source_verified: false` é carregado, nunca invertido).
- **Sem veredito visual** (`PENDING_HUMAN`); nenhuma imagem foi gerada nem julgada. Veio `NOT_SUPPORTED`.
- Uma única posição/medida de gabinete (a do P7) e uma única porta; não há regressão visual dos demais cômodos além do `strict_identity` das caixas planejadas.
- A circulação da SUITE 01 reprova **antes e depois** (preexistente); esta prova não a corrige nem a esconde.
