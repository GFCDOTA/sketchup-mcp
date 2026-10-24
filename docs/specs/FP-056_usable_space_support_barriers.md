# FP-056 — Espaço utilizável, apoio físico e semântica de portas e barreiras

```yaml
id: FP-056
versao: 1.0.0
status: RASCUNHO              # contratos definidos; implementação começa pelo contrato 1
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

## Ordem de correção (na origem)
1. Contrato 1: `UsablePlacementRegion` derivada da arquitetura construída. Planejadores e solver passam a usá-la; gate de
   proposta. Fecha R1 e o `xfail` da D-007.
2. Contrato 3: barreiras na região utilizável (R2 da A.S.) e porta com folga inferior construída e tapete (R5).
3. Contrato 2: modos de apoio declarados por peça e validados (R4).
4. Contratos de vizinhança entre peças compostas (R3), no especialista dono da composição.
Cada passo: teste vermelho a partir do defeito registrado → correção no gerador → prova no SketchUp real → decisão visual do
Felipe quando a aparência muda (nada aprovado é alterado em silêncio; o impacto é declarado antes).

## Gate de não regressão (vigente desde a FP-055 P4)
O registro acima é o **baseline de defeitos**. Uma proposta ou geração que crie um defeito novo, ou piore um existente
(profundidade maior que o registrado + resolução), é bloqueada. Defeito que some é registrado como resolvido. O baseline
nunca é editado para "aceitar" um defeito novo.

## Não aprovação
Cômodo com bloqueio físico não resolvido (R1 a R5) não é funcionalmente aprovado, ainda que o solver diga FEASIBLE.
