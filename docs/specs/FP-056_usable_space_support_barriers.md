# FP-056 — Espaço utilizável, apoio físico e semântica de portas e barreiras

```yaml
id: FP-056
versao: 1.0.0
status: EM_EXECUCAO           # P0 (causa-raiz) entregue; segue pela ordem de fases abaixo
prioridade: P0_CRITICAL
origem: achados da FP-055 P4 (geometria construída da planta_74, 2026-10-23) + pedido do Felipe no chat
dependencias: [FP-043 (D-007, P3a-03), FP-054 (solver F2), FP-055 (contrato de referencial, validação do construído)]
politica:
  corrigir_na_origem: true          # o planejador deixa de gerar a falha; o validador NÃO ganha exceção
  limiar_inalterado_sem_evidencia: true
  decisao_visual_aprovada_so_com_impacto_declarado: true
  aprovacao_funcional_bloqueada_com_bloqueio_fisico: true
```

## Problema
A validação da FP-055 sobre a geometria construída mostrou que o planejador posiciona móveis dentro de paredes, fora do
cômodo e uns dentro dos outros. A causa principal é que o espaço de mobiliar é a **laje construtiva**, que entra
`FLOOR_UNDER_FRAC = 0,4 × espessura` sob a parede (`tools/sketchup/shell/build_plan_shell_skp.py:664`, D-007, FP-043
P3a-03, `xfail(strict)` em `tests/test_synthetic_polygon_convention.py:95`). A correção é no planejador e no solver. O
validador não aprende a aceitar móvel atravessando parede.

## Contrato 1 — geometria construtiva ≠ espaço utilizável
| Tipo | O que é | Quem produz | Quem consome |
|---|---|---|---|
| `ConstructedFloorGeometry` | a laje como é construída (pode entrar sob a parede para esconder a junta) | shell builder | render, SketchUp. **Nunca** o planejador |
| `BuiltWallMass` | massa de parede construída (com vãos recortados), lida do modelo e conferida contra o consensus pelo contrato de referencial | shell builder → inspeção | validador, planejador (obstáculo) |
| `UsablePlacementRegion` | onde um móvel pode ocupar o piso: laje **menos** massa de parede, barreiras (contrato 3), pilares, shafts, peitoris e qualquer superfície arquitetônica construída | derivada da geometria arquitetônica (não de um recuo fixo do polígono) | planejador, solver, gate |
| `FunctionalClearanceRegion` | espaço que precisa ficar livre para usar uma peça ou circular (frente de uso, varredura de porta, passagem) | especialista do cômodo + regras F1B/F1C | solver, gate funcional |

Regras:
- O planejador e o solver só posicionam peças dentro de `UsablePlacementRegion`; a pegada que sai dela é violação rígida
  na proposta, antes do SketchUp.
- Embutimento intencional (pele de parede, nicho, peça hospedada na parede) só é aceito quando a **peça** declara a
  relação (`geometry_intent`/`host` em `core.spatial_semantics`) e a profundidade fica dentro do que a declaração permite.
  Proximidade geométrica nunca vale como declaração.
- A FP-043 D-007 vira resolvida quando o `xfail(strict)` "nenhum móvel dentro da parede" passar sem alterar a laje.

## Contrato 2 — apoio físico e relações verticais
Cada peça declara um **modo de apoio**:
- `FLOOR`: base no piso;
- `ON_SURFACE(<peça>)`: bandeja, sabonete ou equipamento sobre bancada ou móvel;
- `WALL_MOUNTED(<parede>)`: armário suspenso, espelho, papeleira, gancho;
- `CEILING`;
- `SUSPENDED_INTENTIONAL`: luminária pendente, com o elemento de fixação.

Validação no modelo construído:
- `FLOOR`: base a no máximo `EPS_DEPTH` acima do piso.
- `ON_SURFACE`: a face inferior apoiada na face superior do suporte declarado (folga ≤ `EPS_DEPTH`) e a projeção dentro do
  topo do suporte.
- `WALL_MOUNTED`: a face de fundo em contato com a face da parede declarada (folga ≤ `EPS_DEPTH`, penetração >
  `EPS_DEPTH` reprova).
- Sem declaração: **BLOCKED** (não se deduz suporte por proximidade).
- Flutuando sem modo `SUSPENDED_INTENTIONAL`: FAIL.

Achado de origem: `LAVABO · Enxoval kb_bandeja` está a 2,0 cm acima do tampo (`bancada_banho` termina em z 0,880; a bandeja
começa em 0,900). Não é colisão, é falta de apoio.

## Contrato 3 — semântica de portas e barreiras
- `SoftBarrier`, guarda-corpo, peitoril e limite de varanda entram como obstáculo e limite de `UsablePlacementRegion`
  conforme a função. Exemplos: o guarda-corpo limita o piso utilizável; o peitoril bloqueia móvel alto e libera móvel baixo
  sob a janela só se a regra declarar. Isso vale mesmo quando não pertencem à `BuiltWallMass`.
- Porta = geometria construída + movimento real: dobradiça, folha, sentido, **folga inferior construída** (faixa de Z da
  folha no modelo) e interferência com piso, soleira e tapete. Abrir menos que o exigido é FAIL; folga inferior não modelada
  é registrada como tal.
- Regressões registradas (FP-055 P4, porta construída sem folga inferior, z 0,0–2,1 m):
  - `r000` SUÍTE 01, porta `h_o003`: abre até **49°**, bloqueada pelo tapete;
  - `r003` SUÍTE 02, porta `h_o004`: abre até **16°**, bloqueada pelo tapete.

## Defeitos de origem por causa-raiz (planta_74, geometria construída, FP-055 P4)
| Causa-raiz | Cômodo · peça (parte) | Medida | Parede/local |
|---|---|---|---|
| **R1 — laje sob a parede usada como área de mobiliar (D-007)** | COZINHA · base_cabinet (kc_corpo, kc_soculo), countertop (kc_tampo) | 4,6 mm na parede | m006 |
| R1 | COZINHA · backsplash | 0,5 mm (no limite) | m006 |
| R1 | SUÍTE 01 · rug / SUÍTE 02 · rug | 5,6 cm na parede | m005 / m016 |
| R1 | BANHO 01 · Box (kb_perfil, kb_trilho) | 6,2 / 5,1 cm | m018 |
| R1 | BANHO 02 · Box (kb_piso_box) | 7 mm | m003 |
| **R2a — atravessa barreira de varanda (SoftBarrier) que não limita a área de mobiliar** — confirmado | A.S. · Bancada gourmet (730 cm² dentro do `SoftBarrier_Group_8`), cuba gourmet (172 cm²), Jardineira (`_8` 133 cm², `_9` 358 cm²), Condensadora (112 cm²) | fora do cômodo 20,3 / 7,6 / 15,6 / 2,9 cm | barreiras 0–1,1 m e 0–0,7 m: guarda-corpo/peitoril físico |
| **R2b — mobiliado sobre região SEM laje e SEM parede construída** — confirmado | A.S. · Máquina de lavar, Varal de teto, Armário de serviço | 21,1 / 23,1 / 3,3 cm | x 1,42–1,71 m, y 12,45–13,11 m (29 × 66 cm): nenhum grupo construído cobre o ponto, só a máquina e o varal. A parede m012 (eixo x 1,344, face 1,414) confere com o construído. O planejador mobilia área que o shell não construiu como piso |
| R2 | SUÍTE 01 · Guarda-roupa; SALA · Painel TV; SUÍTE 02 · Painel cabeceira; BANHO 01 · Bancada | 7,8 mm; 9,1 mm; 1,5 cm; 1,9 cm | junto a m016 / m004 / m014 / m019, fora da laje do cômodo: a investigar (vão, soleira, integração de cômodos) |
| **R3 — composição de peças sem contrato de vizinhança** | SUÍTES · Cama (cabeceira) × Painel cabeceira (ks_bronze) | 3,0 cm | — |
| R3 | COZINHA · backsplash × cuba / vidro do cooktop | 4,6 cm | — |
| R3 | BANHO 01/02 · papeleira × gabinete/vaso; gancho × espelho; tapete de banho × vaso | 8,9 / 11,0 / 3,1 / 16,4 cm | — |
| **R4 — apoio inexistente** | LAVABO · bandeja | 2,0 cm acima do tampo | — |
| **R5 — porta sem folga inferior × tapete** | SUÍTE 01 h_o003, SUÍTE 02 h_o004 | 49°, 16° | — |
| **R6 — funcional (F2)** | BANHO 01/02, LAVABO | vão do box, frente do vaso | já registrados (INFEASIBLE no DOF atual) |

Evidência bruta (SHA-256) e cálculo: `artifacts/review/fp055/p4/`.

## Causas-raiz (P0, `docs/reports/fp056/p0/README.md`)
- **RC-A:** os planejadores mobiliam a laje construtiva (`spatial_model.build_spatial_model` usa `compute_room_floors`, que
  entra 0,4·t sob a parede e sob a barreira). Sintomas: R1.
- **RC-B:** erro de unidade no planejador da A.S. (`service/layout.py` `_cell_m`/`_circ_m` tratam pontos como polegadas;
  zona 1,9% menor). Sintomas: os seis da A.S. antes rotulados R2a/R2b. **Corrige a leitura anterior desta SPEC**, que
  atribuía esses casos à barreira de varanda e à falta de laje.
- **RC-C:** composição sem contrato de vizinhança. Sintomas: R3.
- **RC-D:** porta construída sem folga inferior × tapete. Sintomas: R5.
- **RC-E (P3a, 2026-10-24):** os traços `sb000`–`sb007` do consensus não têm fonte e **não são construídos** pelo shell
  (Hard Rule 1), mas `compute_room_floors` os usa para fechar o envelope e recortar a laje e o `cell` de todos os cômodos
  (−0,26 a −1,97 m² por cômodo). Isso invalida a leitura do experimento da P2 (a região utilizável subtraía esses traços).
  **Decisão do Felipe pendente** (Issue de decisão no backlog); nada foi alterado. Detalhe: `docs/reports/fp056/p3/README.md`.
- Sem causa provada: 4 ocorrências R2 de 0,8 a 1,9 cm, junto a parede (hipótese a testar contra RC-E).

## Fases (cada uma: teste vermelho a partir do defeito → correção no gerador → prova → PR com CI verde)
| Fase | Entrega | Fecha |
|---|---|---|
| P0 | causa-raiz + testes `xfail(strict)` (esta PR) | — |
| P1 | RC-B: unidade da A.S. | os 6 da A.S. (a medir) |
| P2 | contrato 1: `UsablePlacementRegion` no `spatial_model` (laje − massa de parede − barreiras), planejadores e solver passam a usá-la; gate de proposta antes do SketchUp; impacto nas decisões aprovadas declarado antes; L2 da cozinha revogado e refeito (R-18) | R1, xfail D-007 |
| P3 | contrato 3: barreiras como limite (**P3a feita**: `barrier_penetration` no pré-voo e zona da A.S. sem a massa das barreiras construídas, #434); porta com folga inferior construída × tapete (P3b, #435; decisão de projeto registrada se precisar do Felipe) | R5 |
| P4 | contrato 2: modo de apoio declarado por peça e validado no construído | bandeja e outros flutuantes |
| P5 | RC-C: contratos de vizinhança por especialista | R3 |
| P6 | geração nova completa da planta_74 + defeitos corrigidos × remanescentes contra o baseline | — |
Depois: FP-055 P5–P9 (conhecimento, cômodos restantes, gates de CI, geração limpa integrada, reconciliação).

### Estado em 2026-10-24 (backlog: GitHub Project #1; cada linha vira Done só com a evidência na Issue)
| Fase | Estado | Evidência / Issue |
|---|---|---|
| P1 | feita | `docs/reports/fp056/p1/` |
| P2 | infraestrutura feita; adoção pelos planejadores **bloqueada** pela decisão sobre os traços sem fonte (#484) e refazer a medição | #431, #433; `docs/reports/fp056/p2/` |
| P3a barreiras | feita | #434; `docs/reports/fp056/p3/` |
| P3b porta × tapete | **bloqueada**: decisão R5 (folga inferior da folha × tapete) | #435, #486 |
| P4a/P4b apoio | parcial: `ON_SURFACE`, `FLOOR`, `WALL_MOUNTED` medidos; CEILING/SUSPENDED e 26 módulos sem modo | #436, #491; `docs/reports/fp056/p4/` |
| P5 vizinhança | não iniciada; ver defeitos R3 do baseline | #437 |
| P6 geração completa | **medição feita** (34 → 29 defeitos, 0 novos); fecha só sem perda de programa e sem os 29 | #439; `artifacts/review/fp056/p6/` |
Decisões do Felipe pendentes: K-1, AS-1, S2-1, S1-1, B-1, R6, D-007, RC-E (#484), R5 (#486).

## Gate de não regressão (vigente desde a FP-055 P4)
O registro acima é o **baseline de defeitos**. Uma proposta ou geração que crie um defeito novo, ou piore um existente
(profundidade maior que o registrado + resolução), é bloqueada. Defeito que some é registrado como resolvido. O baseline
nunca é editado para "aceitar" um defeito novo.

## Não aprovação
Cômodo com bloqueio físico não resolvido (R1 a R5) não é funcionalmente aprovado, ainda que o solver diga FEASIBLE.
