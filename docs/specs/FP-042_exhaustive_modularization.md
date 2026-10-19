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
