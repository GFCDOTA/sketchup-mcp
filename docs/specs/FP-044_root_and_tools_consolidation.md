# FP-044 — Consolidação da raiz e de `tools/` (continuação da FP-043)

**Estado:** especificação executável. **Base:** `develop` @ `4840ef0` (PR #319), 2026-10-20.
**Antecessoras:** [FP-043](FP-043_repository_navigation_and_room_specialists.md), [plano P3–P8](FP-043_remaining_execution_P3_P8.md), [relatório final P8](../reports/FP-043_final_validation.md), [decisões abertas](FP-043_open_decisions.md), [mapa P0](FP-043_P0_map.md).
**Dados de apoio medidos:** [`fp044_tools_facades.v1.json`](fp044_tools_facades.v1.json) (123 arquivos de `tools/*.py`, dono real, consumidores por categoria, ação).

> A FP-043 deixou a **lógica** no lugar certo (cada comportamento tem um dono) e a documentação fiel. Ela **não** deixou a árvore
> *parecendo* organizada: a raiz tem 20 pastas, `tools/` tem 123 arquivos soltos de 600–800 bytes, e três pastas de histórico do sofá
> ficaram no topo. Esta spec fecha essa diferença, sem mudar comportamento.

---

## 1. Objetivo e não-objetivos

**Objetivo.** Depois da FP-044 um humano que abre o repositório vê: uma raiz curta com pastas de papel óbvio, `tools/` com subpacotes por
responsabilidade e **sem** dezenas de arquivos-ponte, e um README/mapa que descrevem exatamente o que existe. Tudo provado por teste
(um *guard* da raiz e um *guard* de `tools/`) para que a bagunça não volte.

**Não-objetivos (proibido nesta spec).**
- Mudar comportamento de qualquer planner, gate, builder ou Ruby. Cada PR é *movimento + religação*; saídas idênticas (caixas dos brains, relatórios, `.skp`).
- Alterar `fixtures/planta_74/`, `fixtures/quadrado/`, `assets/` aprovados, `.skp` canônicos, renders aprovados, referências (`docs/specs/_assets/`). Mover um arquivo que o inventário marca como protegido exige o contrato próprio (mesmo blob, caminho novo registrado nos manifestos FP-042).
- Decidir D-001…D-005 (do Felipe) ou atribuir veredito visual.
- Remover um arquivo só porque "parece morto": remover = grep de referências (inclusive fora do repo) + classificar A/B/C (Hard Rule #4 do workspace).

## 2. Invariantes (valem para toda fatia)

1. **Grep de referências antes de mover/remover** (Hard Rule #1): repo inteiro, `.claude/`, `.github/`, `docker-compose*.yml`, launchers e `apps/harness-app` (consumidor **externo** real: importa `tools.furnish_apartment`, `tools.geometry_sanity`, `tools.furniture_overlap_gate`, `tools.finding_router`, `tools.circulation_gate`, `tools.correction_loop`, `tools.spatial_model`, `tools.room_type`).
2. **Um owner por comportamento; fachada só delega** (já garantido por `ownership_audit`; a FP-044 reduz o número de fachadas, não cria implementação paralela).
3. **Nada de pasta vazia, `misc/` ou `legacy/`.** Pasta que perde o último arquivo some no mesmo PR.
4. **Cada PR pequeno, `develop`-first**, branch `refactor/…` ou `chore/…` a partir de `origin/develop`, merge só com ≥4 checks verdes (`/tmp/waitmerge.sh`).
5. **Binários**: mover por `git mv` (mesmo blob), atualizar `fp042_inventory.v1.json`, `fp042_asset_blobs.v1.json` (proveniência binária) e `fp042_references.v1.json`. Os testes `test_fp042_{inventory_gate,asset_provenance,reference_provenance}` são o juiz.
6. **Saída idêntica**: antes/depois de cada fatia, comparar `collect_boxes` da planta_74 (por cômodo), `geometry_report` do shell e, quando tocar Ruby/ativo, um build L2 real (SketchUp 26.0.429, MCP, PID próprio). Sem L2 não se declara "Ruby/ativo funciona".
7. **Escala**: `PT_TO_M` é lido no 1º import — testes da planta_74 em processo próprio (marker `planta74_scale`); nunca rodar tooling com cwd na raiz do workspace `E:\Claude`.
8. **Honestidade**: falha real continua falha; não mudar limiar/esperado para passar. Pendência vira linha em `FP-043_open_decisions.md` (continua a série D-xxx).

## 3. O que foi feito (FP-043, PRs #286–#319) — para não refazer

| Fase | Resultado | PRs / prova |
|---|---|---|
| P0 mapa | 189 itens classificados, gate `tools.navigation.p0_map --check` | #287 |
| P1 navegação | README, mapa, rotas (≤3 links), `docs_check` | #288 |
| P2 raiz | 15 arquivos soltos → 6 movidos (PDF → `projects/planta_74/source/`), `core.project_sources`, hashes intactos | #289, #292 |
| P3a-01/02/05 | gates de `--report`; polígono sintético (D-007 documentada); repo health no CI (D-006 resolvida) | #298–#300 |
| P3a-03 | colisões de mobília: sala (painel/mesa), SUITE 01/02 (criados), lavabo (escova), banho 02 (ralo/vidro) + auditoria L1 `tools/validation/room_collisions.py`; **L2: 402/402, 0 móvel na parede/giro** | #312, #313, #315, #318 |
| P3a-04 | material da D-001 pronto (comparação referência × atual × janela larga, renders reais) — **decisão do Felipe** | #319 |
| P3b | executor/processo/Job Object; `su_open` fora do Job; nenhum `taskkill /IM`; 19/19 operações MCP no SU real; janela humana preservada | #311 |
| P4a–d | modularização física em `tools/rooms/<cômodo>/`, `tools/rooms/shared/`, `tools/sketchup/{shell,furnish,inspect,vray}/`, `tools/{mcp_server,validation,rendering,orchestration,knowledge,oracle,…}/`; caminhos antigos viraram **fachadas** | #301–#306, #314 |
| P5 | 9 especialistas + catálogo de capabilities com 4 dimensões de estado | #307 |
| P6a/b | gabinete paramétrico compartilhado (L1) e no SU (L2, 13 micro-fixtures) | #308, #309 |
| P7 | pedido → gabinete na cozinha (42 checks L2; negativos fail-closed) | #310 |
| P8 | relatório final reconciliado, matriz final, decisões | #316, #319 |

Pendências herdadas (continuam do Felipe): **D-001** (referência do `quadrado`), **D-002…D-005** (dashboard legado, `furnish_plan`, `trace_view`, `set_clipboard_image.ps1`), veredito visual dos reparos, D-007 (`xfail(strict)` nas sintéticas).

## 4. Estado atual medido (develop @ `4840ef0`)

### 4.1 Raiz — pastas versionadas

| Pasta | Arquivos | KB | Papel real | Problema |
|---|---:|---:|---|---|
| `artifacts/` | 922 | — | entregáveis + evidência L2/review | ok (identidade do repo) |
| `tools/` | 451 | — | código | 123 arquivos soltos em `tools/*.py` (ver 4.2) |
| `docs/` | 205 | — | specs, arquitetura, relatórios | ok |
| `tests/` | 191 | — | regressões | ok |
| `.claude/` | 73 | — | instruções para agentes | ok (convenção) |
| `fixtures/` | 69 | — | inputs canônicos/sintéticos | ok (protegida) |
| `references/` | 58 | 6 222 | referências de design (sofás, recipes) | sobrepõe-se a `assets/` na cabeça de quem lê |
| `renders/` | 54 | 9 841 | **histórico do programa do sofá** (`renders/check`, `renders/sofa_eval`) | sem dono, na raiz |
| `assets/` | 45 | 19 496 | texturas/recursos de entrada | ok, mas `textures/` está fora dele |
| `interior/` | 38 | 184 | semântica/composição de cena, validators, renderers | pacote irmão de `tools/`; fronteira pouco clara |
| `.ai_bridge/` | 38 | 326 | handoff entre sessões | oculta; ok |
| `core/` | 21 | 157 | escala, IDs, observabilidade | ok |
| `ops/` | 20 | 17 253 | só `ops/estudio-front/` (painel de um dashboard removido em 2026-07-24; assets pesados) | pasta "ops" para um único front legado |
| `schemas/` | 9 | 56 | JSON Schemas de contratos (catálogo, perfis, findings, judged_variant…) | longe de quem os usa (`core/`, `tools/`, `tests/`) |
| `textures/` | 6 | 1 220 | albedo/bump de tecido do sofá | duplica o papel de `assets/textures/` |
| `projects/` | 2 | 176 | fonte identificada de cada projeto | ok |
| `scripts/` | 4 | 7 | 3 fachadas de `.py` do sofá + `set_clipboard_image.ps1` (D-005) | pasta quase só de fachadas |
| `configs/` | 4 | 24 | JSON do programa do sofá (`sofa_*`) lidos pelo Ruby via `File.join(ROOT,'configs',…)` | sem dono na raiz |
| `.github/` | — | — | CI | ok |
| `.impeccable/` | 1 | 1 | `config.json` com o hook de design **desligado** | sobra (D-008) |

Arquivos na raiz (9, ok): `.dockerignore .gitattributes .gitignore CLAUDE.md README.md docker-compose.yml docker-compose.rag.yml pyproject.toml uv.lock`.

### 4.2 `tools/*.py` soltos: 123 arquivos

- 102 são fachadas "novas" (`_TARGET = "tools.<dono>…"`); 19 são fachadas de estilo antigo (re-export `from tools.rooms… import …`); **2 não são fachada**: `furnish_plan.py` (D-003) e `trace_view.py` (D-004).
- Todas as 121 fachadas (102 + 19) têm consumidor real (nenhuma sem uso). Os mais usados: `spatial_model` (22), `furnish_apartment` (20), `render_parts_iso` (14), `kitchen_ergonomics` (14), `sofa_class_matrix` (13), `room_type` (13).
- **8 têm consumidor externo ao repositório** (`apps/harness-app`) e ficam como **API pública estável** (ação `KEEP_PUBLIC` no JSON): `furnish_apartment`, `geometry_sanity`, `furniture_overlap_gate`, `finding_router`, `circulation_gate`, `correction_loop`, `spatial_model`, `room_type`.
- As outras 113 só têm consumidores **dentro do repo** (código, testes, docs, configs): migráveis por reescrita mecânica de imports (ação `MIGRATE_CONSUMERS_THEN_REMOVE`).

### 4.3 Documentação desatualizada
`README.md` ainda diz que CLIs legadas fecham o SketchUp por nome (removido no P3b), que o Ruby legado está em `tools/*.rb` (hoje `tools/sketchup/{shell,furnish,inspect,vray}/`) e lista `furnish_apartment`/`bedroom_designer` como caminhos "legados". O mapa descreve `renders/`, `scripts/`, `textures/` como "classificação em P2" sem destino.

## 5. Diagnóstico (por que ainda parece bagunçado)

1. **Pastas de uma matéria só na raiz** (`configs`, `renders`, `textures`, `scripts`) — pertencem ao cômodo `living` (programa do sofá) ou a `assets/`/`artifacts/`.
2. **Fachadas demais à vista**: o P4 moveu a lógica mas manteve todos os caminhos antigos "por segurança"; sem política de aposentadoria, viraram a face de `tools/`.
3. **Contratos longe do uso** (`schemas/`) e **um front legado numa pasta de operação** (`ops/`).
4. **Sem guard**: nada impede a raiz/`tools/` de voltarem a crescer.

## 6. Destino-alvo (árvore de chegada)

```
raiz: .ai_bridge .claude .github artifacts assets core docs fixtures interior projects references tests tools
      + 9 arquivos de projeto            (de 20 pastas → 12; .impeccable e ops/schemas/configs/renders/textures/scripts saem do topo)
```
Mapa de movimento (origem → destino) — cada linha é uma fatia/PR da §7:

| Origem | Destino | Fatia |
|---|---|---|
| `configs/sofa_*.json` | `tools/rooms/living/capabilities/ruby/sofa_program/configs/` (junto de quem lê); Ruby passa a resolver relativo ao próprio arquivo, com `ENV['SOFA_*']` preservado | F2 |
| `textures/fabric_*.{png}` | `assets/textures/sofa_fabric/` (proveniência binária preservada); `sofa_vray_material_spec.json` e `sofa_fabric_material.py` repontados | F2 |
| `renders/check`, `renders/sofa_eval` | `artifacts/review/sofa_program/` (histórico/evidência; blobs idênticos) ; `tools/oracle/make_gpt_review_sheet.py` (`EV`) repontado | F2 |
| `scripts/{generalization_gate,make_gpt_review_sheet,sofa_fabric_material}.py` | removidas após migrar consumidores (já são fachadas) | F2 |
| `scripts/set_clipboard_image.ps1` | **fica** até a D-005; `scripts/` some só quando a D-005 for decidida | F2 (parcial) |
| `schemas/*.json` | `core/schemas/` (contratos de domínio) — testes e `interior/schemas` referenciam por constante única `core.schemas.SCHEMA_DIR` | F3 |
| `ops/estudio-front/` | `tools/interior_studio/frontend/` (dono natural: o estúdio); BFF e RAG chat continuam iguais; `core/observability` e testes repontados | F4 (ver D-009) |
| `.impeccable/` | removida **se** o Felipe confirmar (D-008); senão registrada como exceção anotada | F5 |
| 113 fachadas `tools/*.py` | consumidores reescritos para o dono → fachada removida em lotes por pacote-dono | F6 |
| 8 fachadas públicas | ficam, documentadas como API estável (`tools/PUBLIC_API.md` + teste) | F6 |
| `furnish_plan.py`, `trace_view.py` | ficam até D-003/D-004 | F6 |

## 7. Fatias de execução (detalhe operacional)

> Ordem obrigatória. Cada fatia = 1 PR (F6 = vários). Rollback de qualquer fatia = `git revert` do merge (nada irreversível; blobs idênticos).

### F0 — Linha de base e guards (PR `chore/fp044-guards`)
**Passos.** (a) Congelar a linha de base: `collect_boxes` da planta_74 por cômodo (JSON em scratch, hash por cômodo), `geometry_report` do shell, saída de `run_deterministic_gates` nos 2 fixtures, contagem de fachadas, e SHA-256 dos 3 canônicos. (b) Criar `tests/test_fp044_root_guard.py`: allowlist explícita das entradas da raiz **hoje** + alvo; o teste começa aceitando a lista atual e cada fatia **encolhe** a allowlist no mesmo PR (a raiz nunca cresce sem uma linha deliberada). (c) Criar `tests/test_fp044_tools_guard.py`: `tools/*.py` só pode conter nomes de `fp044_tools_facades.v1.json` com ação `KEEP_PUBLIC`/`BLOCKED_DECISION` + os da fatia em curso; cada lote de F6 encolhe a lista. (d) Registrar arquivos novos nos manifestos FP-042.
**Aceite.** Testes novos verdes; nenhum arquivo movido; baseline versionado em `artifacts/review/fp044/baseline/` (JSON de hashes, não SKP).

### F1 — Documentação fiel (PR `docs/fp044-readme-map`)
**Passos.** Reescrever no README: seção "Como o pedido vira .skp" com os caminhos reais (`tools/sketchup/{shell,furnish,inspect,vray}`); remover o aviso de `taskkill /IM` (substituir por "nenhum código rastreado encerra processo por nome — teste `test_fp043_no_kill_by_name_scan`"); trocar "legado" onde já é dono novo; apontar para esta spec e para o relatório final. Atualizar `repository_map.md` (linhas de `renders/scripts/textures/configs/schemas/ops/.impeccable` ganham destino e fatia) e `migration_guide.md`. Rotas de navegação (≤3 links) revalidadas.
**Aceite.** `docs_check`, `p0_map --check`, `test_fp043_navigation` verdes; um teste novo garante que o README **não** contém `taskkill /IM` nem cita caminho inexistente (`tools/*.rb` legados).

### F2 — Programa do sofá sai da raiz (PR `refactor/fp044-sofa-assets`)
**Passos.** (1) Inventariar referências (já medido): Ruby `build_sofa_eval_suite.rb`/`build_sofa_from_config.rb` (`File.join(ROOT,'configs',…)`), `sofa_vray_material_spec.json` (aponta `textures/…`), `sofa_fabric_material.py`, `tools/oracle/make_gpt_review_sheet.py` (`renders/sofa_eval`), `interior/schemas/furniture_asset.schema.json`, docs `SOFA_*.md`, `references/sofas/*.jsonl` (histórico: **não reescrever**; registrar nota). (2) `git mv` dos 4 JSON, 6 PNG de tecido e `renders/**` para os destinos da §6, **sem alterar bytes**. (3) Ruby passa a derivar o diretório de configs de `__dir__` (override por `ENV['SOFA_*']` mantido) — teste-contrato em texto (o `.rb` não é verificável sem SU; **L2 obrigatório** abaixo). (4) Repontar Python/JSON/docs. (5) Remover as 3 fachadas de `scripts/` depois de migrar os consumidores. (6) Atualizar os 3 manifestos FP-042 (caminho novo, mesmo blob). (7) Encolher a allowlist da raiz (`configs`, `renders`, `textures` saem; `scripts` fica só com o `.ps1`).
**Testes.** Guard da raiz; provenance (3 testes); novo `test_fp044_sofa_paths.py` (nenhum caminho antigo restante em código; Ruby resolve configs relativos); pytest 2 escalas sem falha nova.
**L2.** Rodar o gerador de sofá real (`build_sofa_from_config.rb` via SketchUp próprio, PID próprio) antes/depois e comparar o `.skp` por inspeção (peças, bbox, materiais) — sem declarar visual.
**Rollback.** `git revert`; blobs idênticos.
**Aceite.** Raiz sem `configs/ renders/ textures/`; hashes dos binários iguais; L2 antes = depois.

### F3 — Contratos perto do uso (PR `refactor/fp044-schemas`)
**Passos.** Criar `core/schemas/` com constante `SCHEMA_DIR` e helper `load(name)`; mover os 9 schemas (`git mv`); repontar os 11 testes que fazem `REPO_ROOT / "schemas" / …`, `capability_catalog.py`, `specialists.py` e `interior/schemas`; manter **um** lugar que sabe o caminho (nada de string de caminho espalhada). Docs/specs que citam `schemas/…` ganham o caminho novo (históricos em `docs/archive/` ficam).
**Aceite.** `schemas/` some da raiz; todos os testes de contrato verdes; `test_fp044_root_guard` encolhido.

### F4 — Front do estúdio no dono natural (PR `refactor/fp044-estudio-front`, **depende de D-009**)
**Passos (se D-009 = mover).** `git mv ops/estudio-front tools/interior_studio/frontend` (17 MB: `assets/` pesados, `chat_history.json`, `status.json`, `curadoria/`); ajustar `sys.path` do `rag_chat.py`/`server.py`, `core/observability/context.py` (comentário/constante), `tests/test_instrumentation_call_sites.py` (`FRONT`), `tests/test_fp043_p0_map.py`, `docs/architecture/*`, `.claude/memory`/ADR-0002 (referências textuais) e o launcher do painel (se existir fora do repo — grep em `E:\Claude\ops\launchers`). Manifestos FP-042 dos ~20 binários/JSON. `ops/` some.
**Aceite.** servidor do front sobe (smoke local), testes de instrumentação verdes, raiz sem `ops/`.
**Alternativa (D-009 = arquivar).** mover para `archive`-equivalente dentro de `docs/archive/` com README de proveniência; o dashboard já foi removido (2026-07-24).

### F5 — `.impeccable/` (PR `chore/fp044-impeccable`, **depende de D-008**)
Se confirmado: remover `.impeccable/`, tirar a linha do `.gitignore`, `tools/rooms/knowledge_ownership.py` e do mapa P0 (`status: done`), garantir que nenhum hook referencia. Se o Felipe preferir manter: registrar exceção anotada no guard da raiz e no mapa.

### F6 — Aposentar as fachadas de `tools/` (vários PRs, um por pacote-dono)
**Pré-requisito.** F0 (guards) e o JSON `fp044_tools_facades.v1.json` (ação por arquivo).
**Procedimento por lote** (lotes por dono: `rooms/bathroom`, `rooms/bedroom`, `rooms/living`, `rooms/kitchen`, `rooms/shared`, `sketchup/*`, `validation`, `rendering`, `orchestration`, `knowledge`, `oracle`, `interior_studio`, demais):
1. Gerar o mapa `tools.<X>` → `<dono real>` a partir do JSON (campo `owner_module`).
2. **Reescrever consumidores** (AST, não regex): `import tools.X`, `from tools.X import …`, `from tools import X`, `python -m tools.X`, strings de caminho `tools/X.py` em `.py/.rb/.ps1/.cmd/.sh/.yml/.json/.md`. Respeitar `sys.modules` aliasing (um módulo importado pelos dois nomes **não** pode virar dois módulos — o teste de identidade `tools.X is <dono>` roda **antes** da remoção).
3. Rodar a matriz (pytest 2 escalas, gates dos 2 fixtures, smoke/stdio MCP, `inventory_gate --strict`, `ownership_audit`, comparação de saída idêntica da F0).
4. Remover as fachadas do lote; atualizar manifestos FP-042, mapa P0 e `migration_guide.md` (linha "antes → depois").
5. Encolher a lista do `test_fp044_tools_guard`.
**Regras duras.** As 8 fachadas **públicas** (`furnish_apartment`, `geometry_sanity`, `furniture_overlap_gate`, `finding_router`, `circulation_gate`, `correction_loop`, `spatial_model`, `room_type`) **não** são removidas nesta spec: ganham `tools/PUBLIC_API.md` (contrato: caminho, semântica estável, dono) e um teste que verifica que continuam importáveis e idênticas ao dono. Repontar `apps/harness-app` para os donos é **trabalho separado, em outro repositório**, com PR próprio no harness, e só depois essas fachadas podem sair (spec futura). `furnish_plan.py`/`trace_view.py` ficam até D-003/D-004.
**Aceite.** `ls tools/*.py` = só as 8 públicas + 2 bloqueadas + `__init__.py`; nenhum import/caminho antigo no repo; saída idêntica; harness continua funcionando (teste de import dos 8 módulos).

### F7 — Validação final (PR `docs/fp044-final`)
Matriz completa; L2 integrado (build + furnish + inspect + `planta_check`) e do programa do sofá; `planta_74` e canônicos com SHA-256 iguais à F0; relatório `docs/reports/FP-044_final_validation.md` (por fatia: PR, merge SHA, antes/depois, hashes, PIDs/versões, o que NÃO foi feito); mapa/README/guia de migração finais; memória do projeto atualizada (nota de estado). Marcar `status: done` nas fachadas remanescentes do mapa P0 e documentar a exceção dos módulos de governança (`tools/rooms/p3_ownership.py` etc.).

## 8. Matriz de teste e comandos (cada PR)

```bash
python -m tools.rooms.inventory_gate --strict
python -m tools.navigation.p0_map --check
python -m tools.navigation.docs_check
python -m tools.rooms.ownership_audit
python -m pytest tests/ -q -m "not planta74_scale"
PT_TO_M=0.0259 python -m pytest tests/ -q -m planta74_scale        # PowerShell: $env:PT_TO_M="0.0259"
python -m pytest tests/test_fp044_root_guard.py tests/test_fp044_tools_guard.py -q
python -m tools.run_deterministic_gates --fixture quadrado
PT_TO_M=0.0259 python -m tools.run_deterministic_gates --fixture planta_74
python -m tools.mcp_server.smoke && python -m tools.mcp_server.stdio_check
```
Comparação de saída idêntica (F0 → cada fatia): `collect_boxes` por cômodo (hash JSON), `geometry_report`, gates. CI (4 checks) é a referência final; o pytest local tem falhas de ambiente **preexistentes** idênticas antes/depois — comparar listas, não contagens absolutas.

## 9. Riscos e mitigação

| Risco | Mitigação |
|---|---|
| Consumidor fora do repo (harness, launchers, Scheduled Tasks, atalhos) quebra | Varredura de `E:\Claude\apps`, `E:\Claude\ops`, `.claude\settings*.json` **antes** de cada remoção; 8 públicas mantidas; harness repontado em PR próprio |
| Módulo importado por dois nomes vira dois módulos (estado duplicado) | Teste de identidade antes da remoção; reescrita por AST |
| Ruby resolve caminho relativo errado após mover `configs/` | Resolução por `__dir__` + override por ENV + teste-contrato + **L2 real** |
| Binário movido sem registrar nos manifestos | `git mv` + atualização dos 3 manifestos no mesmo commit; testes de proveniência no CI |
| Regressão silenciosa de layout | Baseline F0 por cômodo + comparação por hash a cada fatia |
| Refatoração mascara trabalho em paralelo | Fetch antes; **uma sessão** por vez no working tree (Hard Rule #5); parar e reconciliar se `develop` andar |
| Aparência muda sem querer | Fatias são só movimento; qualquer diferença de saída é bug a corrigir, não a aprovar |

## 10. Decisões novas (continuam as D-001…D-007 da FP-043)

| ID | Pergunta | Recomendação | Bloqueia |
|---|---|---|---|
| D-008 | Apagar `.impeccable/` (hook de design desligado)? | Sim | só F5 |
| D-009 | `ops/estudio-front/` (17 MB, painel do dashboard removido): **mover** para `tools/interior_studio/frontend/` ou **arquivar**? | Mover (mantém o front utilizável) | só F4 |
| D-010 | Política das 8 fachadas públicas: manter para sempre como API estável, ou repontar o harness e aposentá-las numa spec futura? | Manter agora; aposentar só com PR no harness | nada nesta spec |

Enquanto D-008/D-009 não forem respondidas, F5/F4 ficam `BLOCKED_DECISION` e **não** impedem F0–F3, F6, F7.

## 11. Definição de pronto

FP-044 só é "concluída" se **todas**: raiz com as 12 pastas-alvo e nenhuma pasta de matéria única; `tools/*.py` reduzido às 8 públicas + 2 bloqueadas; guards da raiz e de `tools/` em CI; README, mapa e guia de migração iguais ao que existe (teste); saída idêntica à F0 em todas as fatias; L2 real do build integrado e do programa do sofá; canônicos com SHA-256 iguais; CI verde em cada merge; relatório final com PRs, SHAs e pendências. Caso contrário o estado é `PARTIAL` com o motivo (decisão do Felipe, consumidor externo, falta de L2).

## 12. Ordem e PRs previstos

`F0 guards` → `F1 docs` → `F2 sofá` → `F3 schemas` → `F6 lotes` (em paralelo lógico, **sequencial** no merge) → `F4 front` (após D-009) → `F5 impeccable` (após D-008) → `F7 final`.
Estimativa de PRs: ~3 (F0–F2) + 1 (F3) + 8–12 (F6) + 2 (F4/F5) + 1 (F7).
