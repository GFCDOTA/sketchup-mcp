# FP-043 / P0 — Mapa de reorganização

**Estado:** P0 entregue (mapa + gate). Nenhuma movimentação física foi feita.
**Baseline:** `develop` `07959bfdd153031de13190e883583c7e8acb5c70` (PR #285).
**Fonte de verdade:** [`fp043_p0_map.v1.json`](fp043_p0_map.v1.json) · gate: `python -m tools.navigation.p0_map --check`
· consumidores de qualquer item: `python -m tools.navigation.consumers <caminho>`.

Spec: [FP-043](FP-043_repository_navigation_and_room_specialists.md). Este documento resume o mapa; o JSON é o
que o gate valida.

## O que o mapa cobre

188 itens: os 15 arquivos da raiz, os 142 arquivos diretos de `tools/`, os 11 de `scripts/`, e cada
subdiretório de `tools/`, `scripts/`, `ops/` e `interior/` como UMA unidade (os arquivos de dentro herdam
a decisão do diretório). Cada item tem disposição, destino, fase, compatibilidade, risco com motivos e
consumidores. Os outros diretórios de topo têm só a responsabilidade registrada (`directories` no JSON).

| Disposição | Itens | Significado |
|---|---|---|
| `retain` | 25 | fica onde está, com motivo |
| `facade` | 19 | já é fachada de uma implementação canônica em `tools/rooms/…`; fica como exceção nomeada |
| `move` | 140 | move na fase indicada, preservando o caminho antigo conforme `compat` |
| `decision` | 4 | bloqueado por uma pergunta registrada |

Risco: 64 alto, 68 médio, 56 baixo. Fase: 2 em P1, 14 em P2 (raiz), 170 em P4 (tools/scripts/interior), 1 em
P5, 1 em P8.

## Limites do que foi medido

- Consumidores vêm de `git ls-files`: imports por AST e referências em texto (caminho, módulo pontuado, nome
  do arquivo isolado). **Caminho montado em tempo de execução não aparece** (`REPO / f"{fix}.pdf"` em
  `door_swing_audit`). Esses itens estão marcados `dynamic_path_risk` e sobem para risco alto.
- As decisões são autorais, a partir de docstring/cabeçalho, consumidores e do dono já registrado na FP-042.
  Não são revisão semântica do conteúdo nem prova de L2.
- Cada PR de movimento revisa os consumidores do seu item à mão antes de mover.

## Decisões de organização registradas

**Novos pacotes** (a spec §4.2 não os lista; a classificação por responsabilidade os exige e nenhum nasce vazio):
- `tools/knowledge/`: RAG, memória do projeto, banco de referências, gramática de referência, PDFs (`tools/pdf_knowledge/`).
- `tools/oracle/`: juízes visuais e consultas (FP-030). O veredito visual continua só do Felipe.

**Subpacotes de `tools/sketchup/`:** `shell/` (consensus→.skp), `furnish/` (materialização de móveis),
`inspect/` (leitura/captura), `vray/` (exportador). Os `.rb` são carregados por caminho: só se movem junto com um
resolvedor único (`compat: path_resolver_unico`).

**Direto da spec §4.2:** `tools/validation/` (28 gates e auditorias transversais), `tools/rendering/`,
`tools/orchestration/`. Regras exclusivas de um cômodo vão ao cômodo: `kitchen_ergonomics`,
`kitchen_wall_regression_gate`, `sofa_gate`, e os validadores de `interior/validators/` (bed/nightstand/wardrobe →
bedroom; sofa_placement → living).

**`tools/` ao fim da migração** conterá só fachadas nomeadas (CLI e import históricos), infra explícita e
pacotes. Os arquivos hoje diretos em `tools/` viram fachada com `compat: facade_at_old_path`.

## Raiz (P2)

Permanecem: `.dockerignore .gitattributes .gitignore CLAUDE.md README.md docker-compose.rag.yml docker-compose.yml
pyproject.toml uv.lock` (lista exata em `root_allowlist`).

| Arquivo | Destino | Observação |
|---|---|---|
| `CLAUDE_COGNITIVE_ARCHITECTURE.md` | `docs/architecture/agent_architecture.md` | conferir se o conteúdo ainda vale; gates citam o nome |
| `HANDOFF.md` | `docs/handoffs/2026-08-27_ai_pipeline_inspector_handoff.md` | é histórico (2026-08-27); o fio vivo é `.ai_bridge/HANDOFF.md` |
| `KICKOFF.md` | `docs/handoffs/2026-07-23_kickoff_proxima_sessao.md` | gerado junto de um HANDOFF antigo; histórico |
| `HISTORICO_SOFA.json` | `references/sofas/history/` | bytes e hash preservados |
| `planta_74.pdf` | `projects/planta_74/source/` | path protegido; resolvedor único; revisão manual dos f-strings |
| `vray_pipeline_proof.png` | `artifacts/review/vray_pipeline_proof_2026-06/` | renomeação autorizada nos manifestos FP-042 |

Arquivos soltos na raiz que NÃO estão no git (`sala_vray_iter6.*.png`, `sala_vray_iter7_premium.*.png`) são locais de
outra sessão: ignorados, não tocados.

## Achados do P0

1. **README raiz desatualizado:** nega o servidor MCP, cita 85 suites e descreve o cockpit `:8765` como ativo. P1 corrige.
2. **Dashboard do estúdio morto:** `docker-compose.yml` e `tools/Dockerfile.dashboard` sobem `tools/studio_dashboard.py`,
   que não existe mais (dashboard removido em 2026-07-24). `docker-compose.yml` fica na raiz (spec §4.1) com nota
   `stale`; o Dockerfile aguarda decisão.
3. **Validadores por cômodo em `interior/`:** `bed_gate`, `bed_placement_gate`, `nightstand_gate`, `wardrobe_gate`
   (quarto) e `sofa_placement_gate` (sala) vivem em `interior/validators/`, fora do cômodo.
4. **Governança dentro de `tools/rooms/`:** 8 módulos (`inventory_gate`, `ownership_audit`, `p3_ownership`, `asset_provenance`,
   `reference_provenance`, `architecture_ownership`, `knowledge_ownership`, `tooling_ownership`) não são de cômodo; saem do
   namespace de cômodo em P4 (destino proposto `tools/validation/governance/`). `registry` e `dispatch` ficam.
5. **`interior/planners/placement_brain.py`** precisa de auditoria contra `tools/rooms/living/planner.py` para não manter
   planner paralelo.
6. **Dependências externas ao repo** (não mudam de caminho sem coordenação): `E:/Claude/.mcp.json` inicia
   `python -m tools.mcp_server.server`; o `harness-app` lê `fixtures/planta_74/consensus_…json`, `core/observability` e
   `.ai_bridge/responses`; `ops/sync_latest_skp.ps1` varre `*.skp` por mtime.

## Perguntas abertas (bloqueiam só o que dependem delas)

| Item | Pergunta |
|---|---|
| `tools/Dockerfile.dashboard` | arquivar o dashboard do estúdio (Dockerfile + compose)? |
| `tools/furnish_plan.py` (+ `.rb`) | capacidade vigente (3D Warehouse) ou histórico? |
| `tools/trace_view.py` | fica como infra nomeada em `tools/` ou vai para `core/observability/`? |
| `scripts/set_clipboard_image.ps1` | ainda útil? (a memória do projeto registra que Ctrl+V/upload não funcionam) |

Nenhuma das quatro bloqueia P1/P2.

## Maiores riscos de P4

`furnish_apartment.py` (22 testes, 18 consumidores em código), `place_layout_skp.rb` (15 em código + MCP + caminho em
tempo de execução), `spatial_model.py` e `room_type.py` (muitos consumidores), `build_plan_shell_skp.py/.rb` (CLI
pública em 24 docs; o `.py` carrega o `.rb` por caminho), `vray_export.rb`, `run_deterministic_gates.py` (CI e MCP).
Ordem proposta: cozinha e `shared` primeiro, depois validação, renderização, orquestração e, por último, os `.rb`
carregados por caminho, já com o resolvedor único.

## Como manter

Cada PR de movimento atualiza o mapa no mesmo PR: o item vira `status: done` (com a origem ausente ou fachada) e o gate
exige o destino rastreado. `python -m tools.navigation.p0_map --check` roda na suíte (`tests/test_fp043_p0_map.py`).
