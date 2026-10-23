# FP-054 F0 — mapa do fluxo crítico P0 (PDF → consenso → shell → planejar → validar → materializar → salvar → reabrir → inspecionar)

> Escrito à mão em 2026-10-23 sobre `develop` (após #379), conferindo cada caminho no código. Todo caminho entre crases
> existe no repositório (trava: `tests/test_fp054_baseline.py::test_critical_flow_map_paths_exist`). Números vêm de
> `baseline_performance.json` e `dining_scenario_trace.json` desta pasta.
> Legenda do gate: **bloqueia** = o fluxo para; **loga** = só imprime; **ausente** = nada confere nesta etapa.

## Visão em uma linha

`projects/planta_74/source/planta_74.pdf` → (sem extrator ativo) → `fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json`
→ `su_build_shell` → shell `.skp` → `collect_boxes` (brains por cômodo) → **nenhum gate global** → `su_furnish` (Ruby)
→ `.skp` mobiliado em `runs/` → **sem reabertura no fluxo do apartamento** → `su_inspect` (opcional, manual).

## Etapas

| # | Etapa | Entrada (MCP / CLI) | Código | Gate nesta etapa | Prova hoje | Lacuna (vira item de fase) |
|---|---|---|---|---|---|---|
| 1 | PDF (fonte) | — | `projects/planta_74/source/planta_74.pdf` | hash no índice git (`baseline_environment.json` → `protected_files`) | arquivo protegido | — |
| 2 | PDF → consenso | **não há extrator ativo**: o consenso é fixture anotada por humano (`fixtures/planta_74/human_walls_annotation.png`, `human_openings_annotation.png`, `human_soft_barriers_annotation.png`); regeneração só escreve candidato: `tools/orchestration/regenerate_consensus.py` | `core/scale.py` (`PLANT_PT_TO_M`, `assert_pt_to_m_for_source`), `tools/validation/scale_anchor_gate.py`, `tools/rendering/pdf_overlay_verify.py` | escala: **bloqueia** (`assert_pt_to_m_for_source` levanta erro); âncora de cota: CI (`scale_anchor_gate`) | L1 (CI deterministic fidelity gates) | etapa congelada: mudança de planta exige refazer a anotação; fora do escopo da FP-054 (registrado no risk register R-09) |
| 3 | consenso → shell | `su_build_shell` (`tools/mcp_server/server.py`) → `tools/sketchup/jobs.py` `build_shell` | `tools/sketchup/shell/build_plan_shell_skp.py` → `tools/sketchup/shell/build_plan_shell_skp.rb` | `tools/validation/run_deterministic_gates.py` `run_all` depois do build (**loga** no retorno; promoção é separada) | L2 histórico do shell; `artifacts/planta_74/planta_74.skp` canônico | promoção só via `promote_canonical` (`tools/orchestration/promote_canonical.py`) + VISUAL_REVIEW humano |
| 4 | planejar | `su_furnish` → `tools/sketchup/jobs.py` `furnish` → `tools/orchestration/furnish_apartment.py` `collect_boxes`; capacidades de marcenaria: `tools/rooms/specialists.py` `plan()` | classificação `tools/rooms/shared/room_type.py`; registro `tools/rooms/dispatch.py`; modelo espacial `tools/rooms/shared/spatial_model.py`; brains: `tools/rooms/kitchen/layout.py`, `tools/rooms/living/furnishing.py` (+ `interior/planners/living_room_planner.py`), `tools/rooms/bedroom/furnishing.py`, `tools/rooms/bathroom/layout.py`, `tools/rooms/service/layout.py`; semântica `core/spatial_semantics.py` `annotate_all` | por brain, não global: sala usa `tools/validation/circulation_gate.py` na busca da mesa e da mesa de centro; quarto, cozinha, banho e serviço **não** chamam o gate de circulação | L1 (suíte + `room_regression_diff`) | brain do quarto produz layout que o gate reprova (Suíte 01, R-02); sem `PlacementDecision` com motivos (F2) |
| 5 | validar | dentro de `collect_boxes`; MCP `room_gates` (só sobreposição + estilo) | `tools/rooms/kitchen/validation/__init__.py` `require_kitchen_anchor` (**bloqueia**); `tools/rooms/bathroom/validation.py` `unexpected_wet_room_kinds` (**loga**); `tools/validation/furniture_overlap_gate.py` (MCP, sob demanda); `tools/validation/style_coherence_gate.py` (MCP) | **ausente como passo obrigatório**: `collect_boxes` não roda circulação nem sobreposição antes de materializar | L1 | gate de circulação dá PASS vacuamente em cômodo com < 2 portais (cozinha + 3 banhos, R-01); vocabulário por nome (R-03) |
| 6 | materializar | `tools/sketchup/jobs.py` `furnish` → `tools/sketchup/batch.py` `run_script` | `tools/sketchup/furnish/place_layout_skp.rb` (+ `tools/sketchup/furnish/place_layout_geom.rb`); marcenaria: `tools/rooms/kitchen/capabilities/cabinet_flow.py` → `tools/rooms/shared/cabinet/sketchup.py` → `tools/rooms/shared/cabinet/ruby/cabinet_build.rb` | o Ruby confia nas caixas recebidas (`LAYOUT_BOXES`) | L2 para `kitchen.layout.galley` e capacidades de gabinete (catálogo) | furnish do apartamento não tem L2 de round-trip próprio (F4) |
| 7 | salvar | idem | `tools/sketchup/paths.py` `check_output` (recusa escrever no canônico) | **bloqueia** caminho protegido | L1 (testes de path) + L2 nas capacidades | — |
| 8 | reabrir | só nos fluxos de gabinete/Shaker: `tools/rooms/shared/cabinet/sketchup.py` reabre o arquivo salvo em outro processo | — | ausente no fluxo do apartamento (`su_furnish` devolve o `.skp` sem reabrir) | L2 só nas capacidades de gabinete | round-trip do apartamento mobiliado = F4 |
| 9 | inspecionar | `su_inspect` → `tools/sketchup/jobs.py` `inspect_model` | `tools/sketchup/ruby/inspect_model.rb`; gabinete: `tools/rooms/shared/cabinet/ruby/cabinet_inspect.rb` | inspeção é leitura; compara com o plano só nos fluxos de gabinete | L2 nas capacidades de gabinete | inspeção independente do apartamento contra o plano (F4) |

## O que o mapa prova (e o que não prova)

- **Prova**: os 9 elos existem em código e o caminho de cada um é rastreável até a materialização; 2 elos têm gate que
  bloqueia (escala, caminho protegido) e 1 por cômodo (âncora da pia).
- **Não prova**: que os layouts entregues ao Ruby passaram pelos gates — o passo 5 não é obrigatório. Na planta real de hoje,
  `baseline_performance.json` mostra Suíte 01 (`r000`) com circulação **FAIL** e cozinha/banhos com **PASS vazio**
  (1 portal cada), e `collect_boxes` reporta todos como `OK`.
- **Fora do alcance da F0**: L2/L3. Nada aqui foi rodado no SketchUp; `baseline_environment.json` registra a versão
  instalada e se havia instância aberta.
