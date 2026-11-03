# FP-056 / #447 — D-007 "vão de mobiliar = laje": as três alternativas medidas no estado atual (2026-11-02)

Evidência para a Issue de decisão #447. **Nada foi aplicado** ao gerador, ao consensus, às fixtures nem ao `.skp`, e o SketchUp
não foi aberto. Cada alternativa foi aplicada **em memória** e medida com as mesmas funções do CI
(`tools/validation/quality_geometry_gate.py:27` `evaluate`). Gêmeo em caixas = L1. A prova L2 da alternativa escolhida vem
depois, num commit limpo, com R-18. Aparência: `PENDING_HUMAN`.

| Item | Valor |
|---|---|
| Commit sob prova | `aa46a07b40f78d734e06bb08a9a751049af59126` (`origin/develop@b556ca9f` + este script; `dirty: false` no JSON) |
| SketchUp | não usado (L1) |
| Reprodução | `PT_TO_M=0.0259 PYTHONPATH=. PYTHONIOENCODING=utf-8 python artifacts/review/fp056/p7_d007_slab/measure_d007.py <saida.json>` (cerca de 8 min, determinístico: duas execuções deram os mesmos números) |
| Protegidos | SHA-256 do consensus e dos `.skp` canônicos iguais antes e depois (`protected_unchanged: true`) |
| Dados | `d007_alternatives.json`: 22 variantes, com caixas, pré-voo, gêmeo, programa, causas e âncora por cômodo |

## O que foi medido e de onde vem cada número
- **Laje / `cell`.** O shell recorta a célula livre e a estende `FLOOR_UNDER_FRAC = 0.4` × espessura sob a parede
  (`tools/sketchup/shell/build_plan_shell_skp.py:664`, aplicado em `:783`, `:790` e `:800`). Os planejadores recebem essa laje
  como `cell` (`tools/rooms/shared/spatial_model.py:98` e `:112-113`), guardada num cache cuja chave é o conteúdo do consensus
  (`:84-104`). Por isso o script limpa o cache a cada variante.
- **Região utilizável.** É a laje menos a massa de parede e de barreira (`tools/rooms/shared/placement_region.py:23-36`).
- **Caixas e programa.** `collect_boxes` (`tools/orchestration/furnish_apartment.py:87`) e o programa de
  `artifacts/review/fp056/p2/program_baseline.json`. Na contagem de programa perdido entram só as perdas **sem** registro em
  `docs/governance/known_gaps.json`.
- **Pré-voo por cômodo.** `tools/validation/layout_preflight.py:83`, com `planta74_twin` (`:27`).
- **Gêmeo.** `tools/validation/box_geometry.py:98`, cuja laje é `compute_room_floors`, a mesma do shell (`:63`), comparado com
  `artifacts/review/fp055/p4/defect_baseline.json` por `tools/validation/defect_baseline.py:99`. O `twin_borderline` de
  `known_gaps.json` fica fora, como no CI.
- **R1.** É a causa do baseline (`tools/validation/defect_baseline.py:6`): "peça dentro da massa de parede, sobre a laje que entra
  sob a parede (D-007)". Na regra geométrica, a parte para fora do piso efetivo está >50% na parede **e** >50% na laje
  (`:71`). O baseline tem 11 achados R1:
  - tapete das Suítes 01 e 02 (CONTAINMENT e WALL nas duas);
  - na cozinha, `base_cabinet_01` e `countertop` (CONTAINMENT e WALL) e `backsplash` (WALL);
  - Box do Banho 01 (CONTAINMENT e WALL).
- **Âncora da pia.** `tools/rooms/kitchen/anchor_rules.py:25`, com a regra dura em `:100`. Quem chama é
  `furnish_apartment.py:107-110`, que aborta com `SystemExit` (`tools/rooms/kitchen/validation/__init__.py:21`).

## Resultado — estado atual (#484 como está)
| Alternativa | Geração | Caixas | Pré-voo | Gêmeo novos / piores | R1 do baseline | Programa perdido sem registro | Âncora da pia |
|---|---|---|---|---|---|---|---|
| **(a)** laje 0,4t sob a parede (atual) | OK | **390** | **PASS** (8/8) | 0 / 0 | **11 de 11 persistem** | 0 (só AS-1, registrado) | PASS (pia a 1,2 in da face oeste) |
| **(b)** `FLOOR_UNDER_FRAC = 0` | **ABORTA** | 183 (diagnóstico) | FAIL em 5 cômodos | 10 / 1 | 0 restantes: 2 corrigidos, **9 sumiram com a peça** | **25 módulos** (Suíte 02 e cozinha inteiras, mesa de jantar, tanque, Box ×2, vaso do lavabo, escrivaninha) | FAIL: `build: sem parede limpa p/ bancada` |
| **(c)** região utilizável global (P2) | **ABORTA** | 255 (diagnóstico) | FAIL em 5 cômodos | 7 / 0 | 0 restantes: 7 corrigidos, **4 sumiram com a peça** | **14 módulos** (Suíte 02 inteira, mesa de jantar, tanque, Box ×2, vaso do lavabo, escrivaninha) | FAIL: `kitchen_door_clearance_ok = false` (bancada na faixa da porta) |

**Onde e por que abortam.** As duas param em
`furnish_apartment.py:110 → kitchen/validation/__init__.py:21 SystemExit: BUILD ABORTADO: cozinha reprovou o anchor da pia`.
- **(b)**: o planejador da cozinha devolve `NO_VALID_LAYOUT` (`tools/rooms/kitchen/layout.py:341-343`). Sem o recuo, a laje da
  cozinha (cômodo integrado à sala, separado pelo polígono do cômodo em `build_plan_shell_skp.py:800`) deixa de encostar nas
  paredes m011, m013 e m020. Pelo limiar de 0,8 pt (`spatial_model.py:115`) sobram só m006 e m010, as duas com porta.
  Conferido: com 0,4 o planejador vê m006, m010, m011, m013 e m020; com 0 vê m006 e m010.
- **(c)**: a bancada invade a faixa de circulação da porta. É o conflito K-1 da P2.

O "diagnóstico" desliga só o gate da âncora para medir os outros cômodos; a geração real continua abortada.

**Pré-voo e portas.** Nas duas, a Suíte 02 dá `NO_VALID_LAYOUT`. Os cômodos que reprovam no pré-voo são:
- **(b)**: Suíte 01 (circulação), Sala (circulação e colisões) e Banho 01, Banho 02 e Lavabo (colisões);
- **(c)**: os mesmos cinco.

No gêmeo, (b) e (c) deixam portas novas bloqueadas:
- `h_o002` abre 66°;
- `h_o006` abre 2°;
- `h_o001` (lavabo) abre 3°. Essa terceira não existia no experimento da P2: o lavabo mudou desde então.

**(b) e (c) são quase a mesma coisa.** Sem recuo, a laje fica praticamente igual à região utilizável (Suíte 01: 14,832 m² nas
duas; Banho 02: 2,453 m² nas duas). A alternativa (b) ainda muda a laje **construída** no `.skp`: volta a fresta entre a laje e a
parede que o recuo esconde (`build_plan_shell_skp.py:654-667`). Isso é aparência, não medida aqui.

## Adoção cômodo a cômodo — só o cômodo X usa a região utilizável (#431, D-010)
| Cômodo | Caixas | Pré-voo do cômodo | Novo/pior no cômodo | R1 corrigidos | Programa perdido | Resultado |
|---|---|---|---|---|---|---|
| Suíte 01 r000 | 57 → 50 | FAIL (circulação) | 0 | 2 (tapete) | Escrivaninha | não é melhora estrita |
| A.S. r001 | 9 → 8 | PASS | 0 | 0 | **Tanque** | não é melhora estrita |
| Sala r002 | 51 → 28 | FAIL | 4 (sofá e tapete na parede) | 0 | mesa de jantar, cadeiras, pendente | piora |
| Suíte 02 r003 | 47 → 0 | — | — | 0 (2 sumiram) | cômodo inteiro | piora |
| **Cozinha r004** | 76 → 72 | **PASS** | **0** | **5** | **nenhum** | **aborta na âncora da pia** (bancada na faixa da porta, K-1) |
| Banho 01 r005 | 59 → 39 | FAIL | porta `h_o002` | 0 (Box sumiu) | Box | piora |
| Banho 02 r006 | 58 → 35 | FAIL | porta `h_o006` | 0 | Box | piora |
| Lavabo r007 | 33 → 23 | FAIL | porta `h_o001` | 0 | Vaso | piora |

Hoje nenhum cômodo melhora de forma estrita. O mais perto é a cozinha: resolve 5 dos 11 R1 sem nada novo, mas reprova na âncora
da pia e tem prova L2 (R-18).

## Dependência da #484 (cada variante também foi medida com a alternativa (b) da #484: `sb000`–`sb007` retirados em memória)
| Variante | Geração | Caixas | Pré-voo | Novos / piores | R1 restantes | Programa perdido | Âncora |
|---|---|---|---|---|---|---|---|
| (a) + #484(b) | OK | 376 | FAIL em 6 cômodos | 16 / 11 | 11 (vários piores) | Box do Banho 02 | PASS |
| (b) + #484(b) | **ABORTA** (mesmo motivo) | 269 (diagnóstico) | FAIL em 5 | 6 / 3 | 2 | 17 (Suíte 02 e cozinha inteiras) | FAIL |
| (c) + #484(b) | OK | 318 | FAIL em 5 | 1 / 2 | 2 (Box do Banho 01) | 9 (Suíte 02 inteira e o jantar da Sala) | PASS |
| só a cozinha usa a região + #484(b) | OK | 374 | cozinha PASS | cozinha 0 / 0 | cozinha: 5 corrigidos | nenhum na cozinha | **PASS** |

Leitura:
- As alternativas (a) e (c) da #484 não mudam o `cell` por construção (`artifacts/review/fp056/p7/README.md`): nenhuma linha
  acima muda com elas.
- Só a #484(b) mexe nas medidas da D-007, e ela mesma reprova nos gates: (a) + #484(b) já sai com 16 novos, 11 piores e pré-voo
  FAIL em 6 cômodos.
- Com ou sem #484(b), a D-007 (b) aborta na cozinha e a (c) global esvazia a Suíte 02.
- O único efeito da #484(b) sobre a D-007 é local: a cozinha ganha 0,26 m² e a âncora passa, o que destrava a adoção
  cômodo a cômodo **só na cozinha**.
- Os números de (a) + #484(b) diferem dos da P7 (18 novos / 10 piores / 5 cômodos) porque o develop andou desde então
  (P7 em commit anterior).

## O que NÃO é
- Não aplica nem recomenda aplicar nada: a decisão é do Felipe na #447.
- Não é L2: o SketchUp não foi aberto, e a laje de (b) não foi construída.
- Não julga aparência (`PENDING_HUMAN`).
- A medida (c) troca o `cell` de **todos** os consumidores de `build_spatial_model`, que é como a P2 fez, e não reescreve nenhum
  planejador. A adoção real (#431) adaptaria o planejador de cada cômodo.
- A "continuação de diagnóstico" depois do aborto não é uma geração válida.
- No gêmeo não existe `SoftBarrier_Group`, então a causa R2a não aparece (`twin_findings_by_cause`).
