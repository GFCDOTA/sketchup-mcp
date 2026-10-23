# FP-054 F1-01 — contrato do `circulation_gate` (#380): L2 dos fluxos de gabinete da cozinha refeito

**Defeito (provado na F0, `docs/reports/fp054/f0/gate_probes.json` P1/P2):** com menos de 2 portais o `circulation_gate` devolvia
`PASS` sem medir nada. Na planta_74, cozinha e 3 banhos (1 portal cada) saíam `PASS`; os planos de gabinete de frentes lisas e
Shaker exigiam esse `PASS` e registravam "circulation_gate PASS" — um PASS vazio.

**Correção (`4ad1f33`):** sem portal ou com portal sem ponto interno → `BLOCKED_MISSING_INPUT`; 1 portal → `NOT_APPLICABLE`;
cadeiras sem conjunto de jantar → `NOT_APPLICABLE`; resultado agregado por `core.constraint_result.combine` (nada medido nunca
vira PASS). Os planos da cozinha aceitam `PASS` ou `NOT_APPLICABLE` e **registram qual foi e por quê**; `FAIL` e
`BLOCKED_MISSING_INPUT` continuam recusando. Testes vermelho → verde em `tests/test_fp054_f1_circulation_contract.py`.

**Por que L2 de novo:** `plan_kitchen_cabinet` mudou e o fecho de `materialize_kitchen_cabinet` e `plan_kitchen_shaker` também (R-18).
O commit da correção revoga `kitchen.cabinet.plain-fronts` e `kitchen.cabinet.shaker-door` (`L1_PASS`, sem evidência); o commit
seguinte restaura apontando para esta pasta.

| | |
|---|---|
| Código sob prova | commit `4ad1f33`, árvore **limpa** (`dirty: false`) |
| SketchUp | 26.0.429 (Windows 11), `interactive`; 7 PIDs, todos fechados por PID; nenhum SketchUp restante; nenhum SketchUp alheio tocado |
| Reprodução | `PT_TO_M=0.0259 PYTHONPATH=. python artifacts/review/fp054/f1_circulation_l2/l2_f1_circulation.py <saida em runs/> <cópia do .skp mobiliado>` |
| Pedidos | os das provas anteriores: `artifacts/review/fp043/p7_kitchen_cabinet/request.json` (frentes lisas) e `artifacts/review/fp046/promotion_l2/request.json` (Shaker) |

## Resultado — 15 verificações, 15 PASS (`summary.json`)

- **gate na cozinha:** `NOT_APPLICABLE` (corredor `SINGLE_PORTAL`; cadeiras `NO_DINING_TABLE`) — não mais PASS.
- **frentes lisas:** `DONE_L2_VERIFIED`, 42 checks do modelo reaberto, erro máx. 3,6e-15 m; o gate `circulation` do plano diz
  `NOT_APPLICABLE` com o motivo; idempotência `ALREADY_DONE` sem SketchUp.
- **Shaker:** `DONE_L2_VERIFIED`, 50 checks, erro máx. 3,6e-15 m, `non_cabinet_fingerprint` antes = depois; os 2 registros de
  circulação (pai e composição) dizem `NOT_APPLICABLE`; idempotência `ALREADY_DONE`.
- **5 negativos, 0 PIDs, sem diretório de saída:** os novos — circulação `BLOCKED_MISSING_INPUT` (portal forçado ausente) recusa
  antes do SketchUp nos **dois** fluxos (`BLOCKED_PLAN_REFUSED`); e os anteriores ainda valem: pose fora da cozinha, mudança de
  arquitetura, `source_verified` de outra recipe do mesmo vídeo.
- **FP-047 `strict_identity`:** 0 deltas; preexistente (não introduzido): `CIRC|r000|corredor_principal` (Suíte 01, #381).
- canônicos byte a byte idênticos; nenhum scratch dentro de `artifacts/`.

## O que NÃO é

- Não é veredito visual: `visual` segue `NOT_REVIEWED` / `PENDING_HUMAN`.
- Não prova circulação **na** cozinha: com 1 portal não há corredor a medir; o que o plano garante é zona de porta livre e
  nenhum `FAIL`/`BLOCKED` do gate. Checagem de alcance a partir do portal único é item futuro da F1.
- Não corrige a Suíte 01 (#381) nem o reconhecimento de cadeira por nome (#382).
- O negativo `BLOCKED_MISSING_INPUT` força o portal ausente trocando `_portal_points` no processo do script (a planta real não
  tem esse caso); prova o caminho de recusa dos fluxos, não um defeito da planta.
