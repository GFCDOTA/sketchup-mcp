# FP-051 — P0: baseline factual e escolha do primeiro móvel (snapshot datado)

**Data:** 2026-10-21 · **Código medido:** `develop@13b1372` · **Spec:** [FP-051 v1.1.0](../specs/FP-051_incremental_learning_furniture_composition.md)
**Escopo:** P0 e só P0 — leitura e medição. **Nenhuma geometria, nenhum `.skp`, nenhuma posição, parede ou dimensão foi escolhida**, e nada foi promovido.
Os números abaixo saem de [`fp051_baseline.json`](fp051/fp051_baseline.json) gerado por `tools/navigation/fp051_baseline.py` (reproduzível; o estado dos PRs vem de
[`external_snapshot.json`](fp051/external_snapshot.json), consulta pontual — o gerador nunca acessa a rede).

> Reprodução: `python -m tools.navigation.fp051_baseline --external docs/reports/fp051/external_snapshot.json --out docs/reports/fp051/fp051_baseline.json`

## 1. Reconciliação de specs e PRs (o que é entrega × o que é plano)
| Item | Estado em `develop@13b1372` | Observação |
|---|---|---|
| FP-045 (especialistas, conhecimento) | mergeada; F0/F1 (#341), F2 (#343), F4 (#340, #345) | F5–F10 pendentes |
| FP-046 (porta Shaker) | spec #342 + P1–P5 mergeados (#350, #352, #353, #354) + pacote L3 (#356) | 2 capacidades L2 vigentes; **aparência `PENDING_HUMAN`** |
| FP-047 (regressão por cômodo) | spec #344 + F1–F3 (#348, #349, #351) mergeados | F4–F8 pendentes (D-007, L2 por cômodo, L3 por hash) |
| FP-048 (#346) | **draft**, só spec | `shared/geometry` não existe |
| FP-049 (#347) | **draft**, só spec | `tools/rooms/shared/assembly/` não existe |
| FP-050 (#355) | **draft**, CI verde, mergeável; traz `tools/rooms/kitchen/planning/` + testes + `hypothesis` em `pyproject.toml` | L1 apenas; **não** está em `develop` |

## 2. Capacidades (18) — estado real
- **L2 com prova vigente (digest dos símbolos casa): 5** — `kitchen.layout.galley`, `shared.cabinet.parametric`, `kitchen.cabinet.plain-fronts`, `kitchen.cabinet.shaker-door`, `shared.cabinet.front.shaker`.
- **L1_PASS: 12** (living ×3, bedroom ×4, bathroom ×2, service, circulation, `kitchen.sink-anchor-guard`); **UNTESTED: 1** (`kitchen.ergonomics.audit`).
- **`visual`: `NOT_REVIEWED` nas 18.** Nenhum cômodo aprovado em L3.

## 3. Lacunas: bindings sem capability (6) e a evidência das fontes
| Binding | Fonte (classe de evidência) | Revisão humana **para este binding** |
|---|---|---|
| `bind.kitchen.drawer` | `yt-kitchen-joinery-2024` — inspecionada (rótulo) | **não** |
| `bind.kitchen.sink-cutout` | `yt-kitchen-joinery-2024` — inspecionada (rótulo) | **não** |
| `bind.kitchen.countertop` | `yt-cabinet-tips-2021` — inspecionada | **não**: a revisão do Felipe cobre `cabinet.front-gaps-and-profiles` 03:13–04:29, não a recipe do tampo (07:09–08:53) |
| `bind.balcony.pergola` | `yt-pergola` só descrição + docs oficiais | não |
| `bind.closet.sliding` | `yt-sliding-wardrobe` só descrição + doc oficial | não |
| `bind.home_office.desk` | só docs oficiais | n/a |

## 4. Matriz móvel → capability → cômodo
| Móvel candidato | Cômodo | Resolução dos componentes obrigatórios | `cycle_status` |
|---|---|---|---|
| **`kitchen_base_shaker_shelf`** | cozinha (r004) | carcaça `shared.cabinet.parametric` ✅L2 · frente `kitchen.cabinet.shaker-door` ✅L2 (alternativa: `plain-fronts` ✅L2) · prateleira (`shelf.count = 1` do mesmo `cabinet_request.v1`) ✅L2. Opcional ausente: **puxador** (sem capability) | **`READY_FOR_NEXT_STEP`** |
| `kitchen_base_drawer` | cozinha (r004) | carcaça ✅L2 · frente ✅L2 · **caixa de gaveta ❌** (`bind.kitchen.drawer`: sem builder nem fixture; fonte sem revisão humana). Opcional ausente: corrediça/ferragem | `BLOCKED_CAPABILITY_MISSING` |
| `bedroom_wardrobe` | quarto | `bedroom.wardrobe.build` e `.gate` só **L1**, frente em **-Y** (gabinete é **+Y**), depende de FP-048/049 (drafts) | `PENDING_SKETCHUP` |

`READY_FOR_NEXT_STEP` **não autoriza execução**: falta assembly assinado, **placement** e os gates integrados. A posição de hoje vem do pedido (`user_request`); não há gate de placement em `develop`.

## 5. Decisão do P0: primeiro móvel e primeiro gap
- **Primeiro móvel: `kitchen_base_shaker_shelf`** (gabinete baixo, frente Shaker, 1 prateleira). É o único candidato com o DAG **completo** hoje, sem aprender nada novo.
  Dito com honestidade: ele é, em grande parte, o que a FP-046 P4/P5 já provou em L2; o que falta para ser "bem posicionado" não é geometria nova, é o **gate de placement (P4, depende do #355)**.
- **Primeiro gap de aprendizado (P2): a caixa de gaveta** (`kitchen_base_drawer`) — **só a caixa montada, sem corrediça nem ferragem**. Antes de qualquer código: (a) dividir a recipe `cabinet.drawer-box-and-hardware` (caixa × ferragem);
  (b) **revisão humana do trecho da caixa** em `yt-kitchen-joinery-2024` (hoje o rótulo "inspecionada" não tem revisor; o trecho é de ~18 min — pedir o menor possível);
  (c) declarar `hypothesis` como dependência de dev, se o P2 usar propriedades (só o #355 a declara).
- Esta escolha é **revisável pelo Felipe antes do P3**. Nada de dimensão, posição ou parede foi fixado.

## 6. As quatro contagens da spec (§3.4), com a definição que cada número usa
| Métrica | Valor | Definição / por quê |
|---|---|---|
| `capabilities_L2_com_prova_vigente` | **5** | L2_PASS, com evidência, e digest de todos os símbolos provados ainda casa |
| `furniture_assemblies_L2` | **2** (1 tipo de móvel: gabinete baixo) | fluxos que entregam gabinete completo salvo/reaberto na cozinha: frente lisa e Shaker (variantes do mesmo móvel) |
| `furniture_placed_in_correct_room_L2` | **0** | nenhum gate de placement escolheu posição; a pose vem do pedido |
| `rooms_approved_L3` | **0** | nenhuma capability com `visual = APPROVED` |
| `blocked_gaps` | **6** | bindings sem capability |
| `reused_capabilities_cross_room` | **0** | reuso exige segundo consumidor **executado**; não há |

## 7. Achados desta validação
1. **Spec corrigida (v1.1.0):** vocabulário (reusar `PENDING_SKETCHUP`/`BLOCKED_KNOWLEDGE_EVIDENCE`); fonte "inspecionada" sem `human_review` não promove; P4 custa rerun L2 dos **dois** fluxos; `hypothesis` não está declarada em `develop`; escopo da `human_review` (uma recipe, um trecho).
2. **Achado em código já mergeado, NÃO corrigido no P0:** `shaker_flow.run_request` confere que a fonte tem *alguma* `human_review`, **não que ela cobre a recipe do pedido** (`origin_context.recipe_id`). Um `source_verified=true` apontando para outra recipe do mesmo vídeo passaria. Corrigir muda o símbolo → exige refazer o L2 do fluxo. Medido em `spec_claims` (`flow:source_verified-checks-review-scope`) — vai virar `ok: true` quando for corrigido.
3. Já conhecidos e inalterados: circulação da SUITE 01 reprova antes/depois (#351); `cabinet.sketchup.inspect` (frentes lisas) grava scratch ao lado de `.skp` em `artifacts/`.

## 8. Limites deste relatório
Retrato de uma data: ele **não** trava os números (o catálogo vai evoluir; os testes provam a lógica de classificação, não os valores de hoje). Estados de PR são uma consulta pontual. Nenhum L2/L3 foi executado: P0 é medição.

## 9. Próximo comando reproduzível
P1 — gap planner mínimo: função pura `plan_furniture_goal()` reutilizando `specialists.plan` e `capability_catalog` (sem Ruby, sem `.skp`), com testes vermelho→verde para reuso, gap, ciclo, evidência velha, fonte fraca/sem revisão e schema. Pré-requisito: este PR mergeado.
