# FP-042 — Migração exaustiva e faseada

## Contrato

**Escopo inicial:** 1.745 blobs versionados na árvore `develop` (`23691912a2eb6df3b215935b25c51f51686ff426`), sem truncamento. Inventário: `docs/specs/fp042_inventory.v1.json`.

Não significa converter TODOS os arquivos em código de cômodo. Para cada arquivo:
- código específico de um ambiente → módulo correspondente;
- código reutilizado em múltiplos ambientes → `shared` ou `core`;
- orquestradores, CLI, CI, bibliotecas, testes e infra → dono apropriado;
- PDFs, SKPs, renders, fixtures, referências e assets → preservar originais e proveniência;
- casos ambíguos → `manual_owner_review`, jamais realocar automaticamente.

**Estado inicial:** todos os arquivos estão `PENDING_REVIEW_OR_MIGRATION`, inclusive aqueles cujo destino preliminar sugere manter. A lista cobre a árvore versionada; não cobre arquivos locais ignorados ou instalações do SketchUp.

## Fases

| Fase | Objetivo | Gate |
|---|---|---|
| P0 | Captura exaustiva do tree, classificação inicial e controle de omissões | `inventory_gate` + teste negativo |
| P1 | Donos de infraestrutura, registry e orquestrador; eliminar ciclos | CI + dependências AST |
| P2 | Consolidar geometria, escala, validações e materiais compartilhados | unitários + golden synthetic |
| P3 | Migrar por cômodo os builders e planners legados com adapters | igualdade estrutural antes/depois, CI |
| P4 | Limpar entrypoints/scripts mantendo aliases públicos; resolver tooling | smoke MCP + CLI + gates |
| P5 | Testes, documentação, cursos, skills e recipes com fonte única | integridade referencial |
| P6 | Artefatos, assets, fixtures e referências: manter local ou registrar ownership | hashes, path/proveniência e smoke |

## Regra de conclusão

1. `git ls-files` corresponde **exatamente** ao inventário, descontando os quatro arquivos administrativos definidos no gate.
2. Nenhuma entrada com `PENDING_REVIEW_OR_MIGRATION`, `manual_owner_review` ou `unclassified_special_case` permanece.
3. Classes de entrada de alto risco recebem testes de compatibilidade relevantes.
4. CI em Python 3.11 e 3.12, suites de escala separadas, gates `planta_74` + `quadrado` e smoke MCP verdes.
5. Pendente L2 (SketchUp real) é registrado explicitamente, não convertido em `PROVEN` automaticamente.
6. `develop` só recebe PRs verdes; nunca merge direto com status pendente.

## Estado atual

P0 (inventário/gate) e o primeiro gate AST de P1 já foram integrados. Em P2, os boundaries wet-room e hidráulico (PRs #258/#259) estão na `develop`. A fatia seguinte extrai `place_decor_boxes` e `_chair_parts` para `shared` e componentes exclusivos da sala para `living`, com re-exports públicos em `furnish_apartment`. A cadeira é consumida tanto pela sala quanto pelo quarto. **P2–P6 seguem em andamento**, incluindo migração de builders inteiros, revisão de ownership e prova L2 no SketchUp. A aprovação da nova fatia depende de CI verde.

Classificações iniciais são heurísticas para triagem, **não certificação de propriedade**. Inventário fechado sobre a árvore base; para novas adições, atualizar o inventário no mesmo PR. Não afirmar que P1–P6 terminaram.


### Fatia P3 — adapter de bedroom

O adapter `bedroom_designer_boxes` foi movido para `tools.rooms.bedroom.furnishing`,
com re-export em `tools.furnish_apartment` e provider atualizado no manifesto.
Seus helpers de cadeira e caixa orientada são consumidos a partir de `shared`.
Teste de não-OK (fail-safe), OK vazio e cadeira de escrivaninha acompanha a
identidade do dispatch. **Builders legados de cama, guarda-roupa e bedroom_designer
ainda não foram integralmente migrados.** Merge condicionado a CI verde.


### Fatia P3 — brain de living

A lógica completa de `living_room_boxes` foi movida para
`tools.rooms.living.furnishing` sem reescrever os cálculos.
Acesso legado pelo orquestrador e identidade do dispatch preservados.
Validação regressiva de `no_plan_skip` impede sofá flutuante quando o
planejador não apresenta uma planta válida. `furnish_apartment` permanece
responsável por agregação, gates, estilos e geração de SKP; a migração
dos builders originais da sala, cozinha, banheiro e service ainda é pendente.


### Fatia P2 — regra hidráulica canônica da cozinha

A implementação real de `validate`, `_modules` e `TOUCH_TOL_IN`
foi migrada de `tools.kitchen_validation` para
`tools.rooms.kitchen.anchor_rules`. O módulo legado mantém CLI
`python -m tools.kitchen_validation` e re-exports dos nomes públicos.
`tools.rooms.kitchen.validation` continua invocando o nome legado,
permitindo mocks existentes e preservando o gate fail-closed.
Testes abrangem agregação geométrica, API antiga, delegação e falta
de layout. A validação visual/L2 continua pendente.


### FP-042/P3/P4 — ownership do brain SERVICE

`tools.rooms.service.layout` agora possui a implementação completa do builder A.S. + terraços, sem criar cômodos adicionais. `tools.service_layout` é uma fachada estável para imports históricos e CLI, com teste negativo para seeds inválidos. Alteração sem SKP/render, dependente dos gates de CI e de prova L2 futura.


### FP-042/P3 — implementação de layout em kitchen e bathroom

`tools.rooms.kitchen.layout` e `tools.rooms.bathroom.layout` passam a
conter os algoritmos completos dos layouts; os entrypoints legados
`tools.kitchen_layout` / `tools.bathroom_layout` permanecem fachadas de
compatibilidade e CLI (sem cópia de algoritmo). As funções compartilhadas
de geometria continuam em `tools.rooms.shared.geometry`. Testes de
contrato e as suites de fidelidade validam que os casos reais não
regrediram. Isso não prova L2/SketchUp.


### FP-042/P3 — ownership do planejamento dos quartos

As implementações integrais dos planejadores de quarto (layout alternativo e
designer minimalista) foram movidas para `tools.rooms.bedroom.layout` e
`tools.rooms.bedroom.designer`; entrypoints legados continuam como fachadas
que preservam API, CLI e imports públicos. Dependência entre planners agora
permanece dentro de bedroom. A rotina que exporta SKP resolve a raiz do repo
no novo nível de pacote. Regressão unitária e suíte de escala real obrigatórias
antes do merge; equivalência visual L2 ainda não comprovada.


### FP-042/P6 — abrangência dos artefatos versionados

O gate de binários protege 707 arquivos e o novo gate `reference_provenance` expande a preservação a **1060 referências e artefatos versionados**, inclusive JSON, MD e outros não binários. Cada registro P6 com `retain_canonical_location` possui hash Git e owner_group registrado. Essa evidência comprova somente integridade de bytes/caminhos, não SketchUp L2, visual nem arquivos não versionados.


### FP-042/P2 — construção paramétrica de peças de uso cruzado

`tools.rooms.shared.{anatomy,sofa,bed,wardrobe,nightstand}` passa a
conter os cinco algoritmos/contratos de peças usados pela sala, quartos,
closet e outros consumidores. Os nomes legados continuam fachadas com
identidade de métodos, helpers e entrada `python -m` preservada.
O conteúdo dos builders foi transferido literalmente; testes cobrem
identidade dos contratos e anatomia básica. Nenhum arquivo SKP
foi modificado e prova visual L2 continua pendente.


### FP-042/P2 — materiais multicomodos em shared

A fonte real de `StyleSpec`, `STYLE_TOKENS`, `apply_style`,
`resolve_material` e `attach_materials` passou a
`tools.rooms.shared.materials`; `tools.style_spec` mantém referências
idênticas para API legada. Aplicação de material por família de módulo,
RGB e texturas não foi reescrita. Testes de compatibilidade e gates de
render/determinísticos devem permanecer verdes antes do merge.


### FP-042/P5 — owners documentais auditáveis

Os documentos, skills, handoffs, contratos e testes que pertencem à P5
recebem `document_owner` por caminho e papel, com um gate fail-closed
para novos casos não catalogados. `VERIFIED_PATH_BASED_OWNER_CLASSIFICATION`
significa **somente classificação de path/owner**, não prova semântica
das aulas, nem execução SketchUp L2. Arquivos de infraestrutura
(`docker-compose*`) são explicitamente mantidos como configuração
operacional, sem mover ou alterar sua interpretação.


### FP-042/P1-P2 — ownership estático de infraestrutura e shared

Arquivos de infraestrutura, registry, core, schemas e gates têm
`architecture_owner` explícito. `tools.rooms.architecture_ownership`
reprova paths P1/P2 não reconhecidos; `ownership_audit` continua
impedindo dependências AST entre implementações de cômodos. Escopo
**classificação de caminho/owner**, não equivalência semântica/L2.


### FP-042/P4 — ownership das ferramentas e APIs públicas

A classificação da P4 distingue `tools.furnish_apartment` (orquestração
entre cômodos), `tools.mcp_server` (API), `tools.interior_studio`,
bridges, comandos legados, scripts e geração/validação. O gate
`tooling_ownership` falha para caminhos operacionais P4 não catalogados,
mantendo os entrypoints históricos para compatibilidade. A certificação
`VERIFIED_PATH_BASED_OWNER_CLASSIFICATION` prova **owner do caminho**,
não comportamento operacional: este depende de pytest, smoke MCP e
prova SketchUp L2 ainda pendente.


### FP-042/P3 — brain de posicionamento da sala e dependências de engine

O algoritmo de `plan_living` tem ownership em `tools.rooms.living.planner`,
com facade pública no caminho histórico `interior.planners.living_room_planner`.
`placement_brain` e `sofa_placement_gate` eliminam imports de quarto e
consomem a geometria de `tools.rooms.shared.geometry` e a escala de `core.scale`.
O funcionamento geométrico não foi alterado; CI exige gates e compatibilidade.


### FP-042/P3 — classes de mobiliário por owner

Classe de sofá, rack, mesa de centro, mesa de jantar, poltrona e cama
migradas para living/bedroom; builder genérico de poltrona em shared.
Imports históricos continuam disponíveis em facades tools.*, inclusive CLI.
Geometria e SKPs não foram alterados.
