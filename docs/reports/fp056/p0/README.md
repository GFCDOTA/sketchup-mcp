# FP-056 P0 — causa-raiz dos defeitos da planta_74 no gerador (2026-10-24)

Baseline: os 34 defeitos de `artifacts/review/fp055/p4/defect_baseline.json`, preservados e inalterados. Os rótulos R1 a R5
desse registro são **classes geométricas do sintoma** no modelo construído. Aqui cada sintoma é ligado à **causa no código
que o gera**. Testes que travam as causas: `tests/test_fp056_p0_root_causes.py` (`xfail(strict)`: viram vermelhos quando a
correção entrar, que então remove o xfail no mesmo PR).

## Runtime
Servidor MCP novo, subido do checkout sincronizado (`952b853` = `origin/develop`), responde `runtime_identity: OK`, sem
motivos e `stale: false`. O servidor desta sessão é trocado no fim do turno (encerrar o PID dele e re-discar a conexão).

## RC-A — planejadores mobiliam a LAJE construtiva (D-007, FP-043 P3a-03)
- **Onde:** `tools/rooms/shared/spatial_model.py:112-113`. `build_spatial_model` usa como `cell` o piso de
  `compute_room_floors` (`tools/sketchup/shell/build_plan_shell_skp.py:732`), que é a laje do shell:
  `tucked = cell.buffer(0,4·t) ∩ envelope` (linha ~790), ou seja, 0,4 × espessura sob parede **e** sob a barreira
  (guarda-corpo).
- **Quem consome o `cell`/`usable`:**
  - planejadores: quarto (`bedroom/designer.py`, `bedroom/layout.py`), banheiro (`bathroom/layout.py:951`), cozinha
    (`kitchen/layout.py:328`, `kitchen/anchor_rules.py:38`, `kitchen/capabilities/cabinet.py:70`), serviço
    (`service/layout.py:88`), sala (`living/planner.py`, `living/furnishing.py`, `living/planning/layout_candidates.py`),
    `interior/planners/placement_brain.py`, `shared/geometry.py`;
  - gates: `circulation_gate`, `functional_clearance` e solver F2 (`spatial_solver/problem.py`, `engine.py`, `solver.py`),
    `sofa_placement_gate`, `geometry_sanity`.
- **Sintomas no baseline:** as 11 ocorrências R1 (cozinha 4,6 mm, tapetes 5,6 cm, box do Banho 01 6,2 cm, box do Banho 02
  7 mm) e o Box do Banho 02 classificado R2.
- **Teste:** `test_planner_cell_does_not_overlap_the_wall_mass` (xfail strict).

## RC-B — erro de UNIDADE no planejador da A.S. (novo; não era hipótese anterior)
- **Onde:** `tools/rooms/service/layout.py:88-100`. `_cell_m` e `_circ_m` multiplicam o `cell` por `IN2M = 0,0254`
  tratando-o como **polegadas**, mas o `cell` está em **pontos do PDF** (`compute_room_floors`). O certo é `× PT_TO_M`
  (0,0259). Os seeds da linha 127 já convertem certo (`× PT_TO_IN × IN2M`).
- **Medida:** cell do planejador × laje construída da r001 têm 3,16 m² de diferença simétrica, com **todas** as bordas na
  razão 0,981 = 0,0254 / 0,0259. A zona inteira fica 1,9% menor e puxada para a origem (3 a 29 cm nestas coordenadas).
- **Sintomas no baseline (reclassificados aqui):**
  - "R2b sem laje": máquina de lavar 21 cm, varal 23 cm, armário 3,3 cm;
  - "R2a atravessa barreira": bancada gourmet 20 cm, jardineira 15,6 cm, condensadora 2,9 cm.

  São **o mesmo** erro de escala. A barreira e a falta de laje são consequência, não causa. A conferência inicial "sem laje"
  usou `contains()` num ponto do contorno (falso por definição); a medida por área a corrigiu.
- **Teste:** `test_service_planner_cell_is_in_the_plants_metres` (xfail strict).

## RC-C — composição de peças sem contrato de vizinhança (R3, 9 ocorrências)
Peças de um mesmo builder ou de builders vizinhos que se sobrepõem em planta e em altura:
- cama × painel de cabeceira (`ks_bronze`), 3 cm;
- backsplash × cuba/vidro do cooktop, 4,6 cm;
- papeleira, gancho e tapete de banho × gabinete/espelho/vaso.

Dono: o especialista que compõe cada conjunto (quarto, cozinha, banheiro). Investigação por builder na fase que corrige R3.

## RC-D — porta construída sem folga inferior × tapete (R5)
A folha construída vai de z 0,0 a 2,1 m (`DoorLeaf_Group_*`): sem folga inferior. Os tapetes das suítes (0–2 cm) ficam no
caminho da folha, e as portas `h_o003` e `h_o004` abrem só 49° e 16°. Dois donos possíveis, que são decisão de projeto:
a folga inferior da porta construída (shell builder) **ou** o tapete fora da varredura (quarto). Registrado no contrato 3.

## Ainda sem causa provada (R2, 4 ocorrências de 0,8 a 1,9 cm)
Guarda-roupa (SUÍTE 01), Painel TV (SALA), Painel cabeceira (SUÍTE 02) e Bancada (BANHO 01, BANHO 02) saem do polígono
efetivo junto a uma parede, mas fora da massa de parede. Hipótese a provar na fase do contrato 1: borda entre laje e parede
nas juntas e vãos. Não está atribuída.

## Impacto esperado das correções sobre decisões aprovadas (a declarar antes de mexer)
| Correção | Muda posição de | Decisões/provas afetadas |
|---|---|---|
| RC-B (unidade da A.S.) | só a A.S. (r001) | nenhuma decisão visual registrada da A.S.; sem capacidade L2 |
| RC-A (região utilizável) | todos os cômodos encostados em parede (até 0,4·t ≈ 5,6 cm) | `layout_decisions` da SUÍTE 01 (#381: criado-mudo 1 in, sem cadeira) — conferir que a decisão segue válida; capacidade L2 `kitchen.layout.galley` (o fecho de `build_boxes` inclui o modelo espacial): **revogar e refazer o L2** (R-18); âncora da pia (`kitchen/anchor_rules.py`, distância à parede oeste) — conferir a tolerância da âncora antes |
