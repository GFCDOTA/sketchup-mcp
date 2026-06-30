# FP-031: Wire furniture classes into furnish (laço curadoria/classe → .skp)

> Fecha o laço entre o conhecimento de design provado (classes de móvel, curadoria
> do Felipe) e o gerador `furnish_apartment.py`. Roadmap em 4 fases; **Fase 0 e 1
> FEITAS** nesta branch (`feat/furnish-sofa-class-gate-warn`), Fase 2–3 planejadas.

## Problem

As 6 classes de móvel (sofá/poltrona/cama/mesa-centro/rack/mesa-jantar) têm teoria
executável madura (`tools/*_class.py`: `CLASS_RANGES` + `RELATIONS` + `ARCHETYPES` +
`derive_*` + `*_class_gate` + testes), e a curadoria do Felipe vive em
`tools/interior_studio/reference_packs.py` (Venezia Slate = `⭐main`). Mas
`furnish_apartment.py` gera com **specs HARDCODED** e **nunca chama `derive_*` nem os
`*_class_gate`** — as classes e a curadoria são ILHAS que provam conhecimento sem
alimentar a geração. A única ponte viva referência→.skp é o token de COZINHA
(`references/tokens/planned_fridge_tower.json` consumido por `kitchen_layout.py`).

Evidência concreta: a heurística antiga do sofá no living — `_seats = 3 if width>=2.0
else 2` — estica `per_seat > 0.75` (fora da faixa de classe `[0.52, 0.75]`) em larguras
de nicho como 1.9 m e 2.8 m. Ou seja: o `.skp` podia conter móvel anatomicamente
fora-da-classe, porque só se validava colisão/sanidade, nunca proporção.

## Scope

Fechar o laço por fases, de ROI decrescente:

- **Fase 0 (FEITA):** chamar `sofa_class_gate(spec, parts)` no caminho REAL
  (`furnish_apartment.py::living_room_boxes`, após `build_sofa`), em **WARN-log** (não
  aborta). Surfaça móvel fora-da-classe sem quebrar o build.
- **Fase 1 (FEITA):** `tools/sofa_class.py::derive_living_sofa(width)` — fonte única: a
  CLASSE escolhe os lugares (`per_seat` na faixa, clampa `seats∈[2,4]`), fixa a largura
  ao nicho, e o sofá nasce do arquétipo **VENEZIA curado** (`thin` arms + `legs`).
  `furnish_apartment` passa a usar isso no lugar da heurística.
- **Fase 2 (planejada):** wirar as demais classes — trocar `_dining_table_square()`
  primitivo por `dining_table_class`; tirar `coffee_table_class` do gate só-industrial.
- **Fase 3 (planejada):** retrieval — o gerador pede "móvel `⭐main` do tema X + params"
  ao `reference_packs`/`reference_db` e injeta como override; adicionar referência muda
  o próximo `.skp` sem editar código.

## Non-goals

- **NÃO** construir RAG semântico / embeddings / kNN (o índice atual é faceted; fora de
  escopo aqui).
- **NÃO** mexer no pipeline do shell (`build_plan_shell_skp.{py,rb}`) — paredes/portas/
  aberturas seguem intocados; isto é só a camada de MOBÍLIA.
- **NÃO** autodeclarar veredito visual. Toda mudança de APARÊNCIA pende
  `VISUAL_REVIEW` do Felipe/GPT (IMPROVED/SAME/WORSE), nunca automático.
- **NÃO** promover o gate de classe a hard-FAIL ainda — fica WARN-log por ≥1 ciclo.
- **NÃO** inventar números a partir de foto: a tradução verdito-prosa→`FurnitureToken`
  (Fase 3) é PROPOSTA pelo agente e APROVADA pelo Felipe.

## Artifact contract

| Path | Mudança | Quem produz | Fase |
|---|---|---|---|
| `tools/sofa_class.py` | `+ derive_living_sofa(width)` (fonte única) | classe | 1 |
| `tools/furnish_apartment.py` | living usa `derive_living_sofa`; `sofa_class_gate` WARN-log | gerador | 0+1 |
| `tools/sofa_furnish_fase1_compare.py` | render SU-free BEFORE/AFTER (iso) | review | 1 |
| `tests/test_furnish_sofa_gate.py` | invariante in-class do sofá da sala | testes | 0+1 |
| `artifacts/review/furniture/sofa/fase1/*.png` | sheet ANTES×DEPOIS pro veredito visual | review | 1 |

## Detection heuristic / algorithm

`derive_living_sofa(width_m, archetype="venezia", arm_style="thin", base_style="legs")`:

```
arm   = ARM_STYLES[arm_style]                 # thin = 0.15 m
ideal = ARCHETYPES[archetype]["per_seat"]     # venezia = 0.583 m
s_lo, s_hi = CLASS_RANGES["seats"]            # (2, 4)
ps_hi      = CLASS_RANGES["per_seat"][1]      # 0.75
seats = clamp(round((width - 2*arm) / ideal), s_lo, s_hi)
max_w = seats * ps_hi + 2*arm                 # largura que mantém per_seat <= teto
width = min(width_m, max_w)                    # preenche o nicho; encolhe se estouraria a classe
return derive_spec(seats, archetype, arm_style, base_style, width=width)
```

O `sofa_class_gate` então roda no `living_room_boxes`; em WARN-log só imprime quando
`result != PASS` (guarda-corpo contra regressão futura, ex.: mexer no arquétipo).

## Acceptance criteria (PASS / WARN / FAIL)

| Status | Critério |
|---|---|
| PASS | `derive_living_sofa(w)` é in-class (`sofa_class_gate != FAIL`) e `per_seat ∈ [0.52,0.75]` para todo nicho `w ∈ [1.5, 3.0]`; largura ≤ nicho; sofá carrega a curadoria venezia (`thin` arms + base `legs`). |
| WARN | Gate de classe imprime no build mas NÃO aborta (Fase 0); nichos < mínimo (2 lugares) deixam `per_seat < 0.52` logado, sem travar. |
| FAIL | (futuro, pós-promoção) `sofa_class_gate == FAIL` no caminho real — hoje WARN-log, não FAIL. |

## Required tests

| Teste | Cobertura |
|---|---|
| `tests/test_furnish_sofa_gate.py::test_living_sofa_is_in_class` | `derive_living_sofa` in-class + per_seat na faixa, 1.5–3.0 m |
| `…::test_living_sofa_carries_venezia_curation` | braços `thin` + base `legs` (curadoria) |
| `…::test_fase1_fixes_the_old_heuristic_defect` | heurística antiga FAIL@2.8m → Fase 1 corrige |

Vermelho→verde respeitado: Fase 0 deixou os 2 casos-limite como `xfail(strict)`; a Fase 1
os virou assert real. Ver [`sdd_and_harness_engineering.md`](../../.claude/specs/sdd_and_harness_engineering.md).

## Regression coverage

- Camada 1: a suíte de classe (`tests/test_sofa_class.py`) + `test_furnish_sofa_gate.py`.
- Camada 2: `sofa_class_gate` no caminho real (guarda-corpo de regressão de proporção).
- Camada 3: rubric visual — proporção do assento / leveza da base (dimensão "forma").

## Done means

- [x] Fase 0: `sofa_class_gate` WARN-log no `living_room_boxes`
- [x] Fase 1: `derive_living_sofa` + furnish usando-a; xfail → assert
- [x] Teste vermelho→verde em `tests/test_furnish_sofa_gate.py`
- [x] Render SU-free BEFORE/AFTER (iso) gerado e mostrado ao Felipe
- [ ] **VISUAL_REVIEW do Felipe/GPT** no sofá novo (IMPROVED/SAME/WORSE) — PENDENTE
- [ ] `.skp` real da planta_74 mobiliada com o sofá novo (precisa SU + review Chrome)
- [ ] PR contra develop mergeada (`feat/furnish-sofa-class-gate-warn`)
- [ ] Fase 2 (mesa-jantar/coffee) — PR separada
- [ ] Fase 3 (retrieval `reference_packs`→override) — PR separada

## Out of scope (placeholder)

- Tradução numérica dos verditos-prosa do Felipe em `FurnitureToken` para móveis além do
  sofá (Fase 3) — agente propõe, Felipe aprova; PR própria.
- Promoção do gate de classe a hard-FAIL (após ≥1 ciclo verde em WARN).
- Wiring das classes restantes (poltrona/cama/rack) que ainda não entram no living.

## Reference

- Constitution: [`.claude/constitution.md`](../../.claude/constitution.md)
- Método de mobília: [`.claude/specs/room_furnishing_method.md`](../../.claude/specs/room_furnishing_method.md)
- Programa de classes: memória `project_furniture_class_program`
- Gate de fidelidade: [`.claude/specs/fidelity_gate.md`](../../.claude/specs/fidelity_gate.md)
