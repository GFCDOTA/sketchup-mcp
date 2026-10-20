# FP-043 — Auditoria final P8 (status parcial e rastreável)

**Data:** 2026-10-19. **Estado global:** `PARTIAL_BLOCKED`; **NÃO** declarar FP-043 encerrada.
**Base verificada:** `develop` após os PRs #286–#318 (merge `e67f86c`). Documento de auditoria técnica; **não** é `VISUAL_REVIEW` nem uma nova prova L2.
**Constituição / spec:** [FP-043](../specs/FP-043_repository_navigation_and_room_specialists.md), [plano executável](../specs/FP-043_remaining_execution_P3_P8.md), [decisões abertas](../specs/FP-043_open_decisions.md).
**Fontes:** [P3b Windows L2](../../artifacts/review/fp043/p3b_windows_l2/README.md), [P6b gabinete L2](../../artifacts/review/fp043/p6b_cabinet_l2/README.md), [P7 cozinha L2](../../artifacts/review/fp043/p7_kitchen_cabinet/README.md), [FP-042 L2 original](../../artifacts/review/l2_fp042_20261019/README.md).

## 1. Status por fase e evidências

| Fase | Estado verificável | Limites |
|---|---|---|
| P0 (mapa) | DONE — #287, mapa com gate `tools.navigation.p0_map` | Classificação não comprova execução por si só |
| P1 (navegação) | DONE — #288 e README/mapa/rotas de links | Revalidar ao mudar destinos |
| P2 (raiz protegida) | DONE — #289/#292, PDF resolvido via `core.project_sources`, renames e hashes | Nenhum byte de fonte/artefato canônico alterado |
| P3a-01 (gates de report) | DONE_L1 — #298: gates de `--report` aplicados ao baseline canônico e contraprovas | Não altera referências |
| P3a-02 (polígono sintético) | PARTIAL — #299, causa real documentada como D-007 | Teste `xfail(strict)`: laje passa sob parede; depende de correções por ambiente |
| P3a-03 (colisões) | DONE_L2 (mobília) — #312/#313/#315 + #318; L2 do apê integrado na `develop` atual: 402/402 peças, **0** móvel/fixture/decor na parede e **0** no giro de porta ([evidência](../../artifacts/review/fp043/p8_l2_20261019/planta_check.json)) | Revisão visual (Felipe) pendente; restam só peças `STRUCTURAL` por desenho (pele, `kb_piso_box` 4,1 cm, `kb_folha` 0,8 cm) |
| P3a-04 (quadrado) | BLOCKED_DECISION — D-001; **material de decisão pronto**: [comparação A × B × referência, renders e medidas](../../artifacts/review/fp043/p3a04_quadrado_d001/README.md) | NÃO alterar referência/fixture sem decisão do Felipe + visual |
| P3a-05 (repo health) | DONE_L1 — #300, D-006 resolvida e gate em CI | Não reintroduzir escala fora do core |
| P3b (processo/MCP/render/escala) | DONE_L2 para a versão #311: Windows SU 26.0.429, 19/19 positivos, 6/6 janela humana preservada; PIDs próprios | Não cobre as alterações de layout #312/#313/#315; Node SDK não é Claude Code Desktop |
| P4 (modularização física) | DONE_COM_EXCECOES — #301–#306; #314 sincroniza 3 diretórios de fachadas com mapa | D-002 a D-005 retêm os itens nominados por decisão; não confundir fachada com duplicação |
| P5 (perfis e capabilities) | DONE_L1 — #307, 9 perfis roteados, catálogo de provas e `BLOCKED_CAPABILITY_MISSING` | Consultar `tools.rooms.specialists`, catálogo e registros reais; nenhum selo visual |
| P6a (gabinete/plano) | DONE_L1 — #308, builder shared e adapter cozinha | Sem ferragem/Shaker/UV de veio |
| P6b (gabinete no SU) | DONE_L2 — #309, 13/13 micro-fixtures com 0°/90°/30°, reabertura, edits, `make_unique` | `grain=NOT_SUPPORTED`, `visual=NOT_REVIEWED`; geometria não certifica fabricação |
| P7 (pedido → gabinete SKP) | DONE_L2 — #310, 42 checks do cenário positivo, negativos fail-closed, reinício idempotente | Posição do gabinete é experimental e requer avaliação visual/projeto |
| P8 (navegação/auditoria/relatório) | DONE_COM_PENDÊNCIAS — matriz final abaixo; relatório reconciliado | `COMPLETE` só depois de D-001 e do visual (seção 3) |

## 2. Correções integradas após o L2 do #311

| PR | Merge SHA | Prova L1 integrada | Pendente |
|---|---|---|---|
| [#312](https://github.com/GFCDOTA/sketchup-mcp/pull/312) | `bc759f5af5fe6c33295ac3db0364fe6e897ee12c` | Planner/body/top dos criados na SUITE 01 e SUITE 02 verificam footprint real | Reconstruir suite(s), inspecionar e rever visual |
| [#313](https://github.com/GFCDOTA/sketchup-mcp/pull/313) | `5be70cf921ffed06c4099a1689922130338bf6dc` | Porta-escova do lavabo não invade o arco real `h_o001`, sem omissão de peça | Materializar lavabo, inspecionar arco/escova e visual |
| [#314](https://github.com/GFCDOTA/sketchup-mcp/pull/314) | `4a6800151934304f0bc82cfb3e48e2e63d07c729` | Estado P4 e D-006 refletidos fielmente em documentos/mapa | Apenas navegação contínua |
| [#315](https://github.com/GFCDOTA/sketchup-mcp/pull/315) | `61783a43fdbb6316ff18d2f21fdbf132588f3a40` | Painel de TV fora da parede; mesa de jantar fora do arco da porta e circulação PASS na planta real; 2 cadeiras preservadas | Rebuild SU real, comparação top/iso e visual |

**Escopo da evidência recente:** os quatro checks do CI (pytest 3.11, pytest 3.12, deterministic fidelity e MCP) passaram para #312–#315. Isso prova comportamento Python e protocolos sem SketchUp; **não equivale** a L2 dos SKPs novos.

## 3. Pendências reais a NÃO esconder

1. **Visual (Felipe)**: aparência mudou na sala (painel/mesa), SUITE 01/02 (criados), lavabo (escova) e banho 02 (ralo/vidro). Nenhum `VISUAL_REVIEW` foi atribuído por mim.
2. **D-001**: referência do `quadrado` (vidro 0,90–2,10 m) × builder (1,50–2,10 m + `WindowSash`). Material pronto em `artifacts/review/fp043/p3a04_quadrado_d001/`; 1 teste condicional segue FAIL autêntico (só roda com build real). Decisão A/B/C é do Felipe.
3. **D-007 sintéticas**: `test_contrato_nenhum_movel_dentro_da_parede` segue `xfail(strict)` (laje sob a parede); a varanda sintética mantém `circulation_gate: FAIL/WARN` explícito.
4. **Peças `STRUCTURAL` do box**: `kb_piso_box` (4,1 cm) e `kb_folha` (0,8 cm) do BANHO 01 entram sob a parede por desenho (piso do box/vidro); não são mobília e ficam fora do gate de mobília. Se o Felipe quiser tratá-las como colisão, é decisão de produto.
5. **D-002–D-005**: dashboard legado, `furnish_plan`, `trace_view`, `set_clipboard_image.ps1` — cada uma só retém o seu arquivo.
6. **Fabricação**: gabinete experimental sem Shaker/UV/ferragens; geometria não certifica fabricação.
7. **Limites de prova**: cliente Node ≠ Claude Code Desktop; CI Linux não substitui o SketchUp.

## 4. Como reproduzir CI e gates independentes

```bash
python -m tools.rooms.inventory_gate --strict
python -m tools.navigation.p0_map --check
python -m tools.navigation.docs_check
python -m tools.rooms.ownership_audit
python -m tools.rooms.capability_catalog
python -m pytest tests/ -q -m "not planta74_scale"
PT_TO_M=0.0259 python -m pytest tests/ -q -m planta74_scale
python -m tools.run_deterministic_gates --fixture quadrado
python -m tools.run_deterministic_gates --fixture planta_74
python -m tools.mcp_server.smoke
python -m tools.mcp_server.stdio_check
```

A escala 0,0259 da `planta_74` deve rodar em **processo separado**, pois `core.scale` lê `PT_TO_M` no primeiro import; o quadrado usa escala própria. O CI Linux não consegue substituir o SketchUp real.

## 5. Retomada Windows/L2 para Claude Code

1. Conferir `git fetch`, `develop` atual, PRs abertos e **toda** a documentação/decisões; preservar canônicos. Executar apenas `interactive`, nunca `headless` em dev.
2. Rodar [bateria de reprodução P3b](../../artifacts/review/fp043/p3b_windows_l2/README.md) com as versões atuais, adaptando a evidência a um **novo** diretório `artifacts/review/fp043/p3a_layout_l2_<data>/`; não reusar resultados do commit antigo como prova nova.
3. Inspecionar geometricamente cada peça real e cruzar contra as paredes extrudadas, arcos das portas, circulação e arquivos do projeto. Regressão do cômodo não pode alterar geometria arquitetônica nem outros cômodos; conferir hashes.
4. Para cada problema, corrigir na **camada dona** e abrir PR testado; comparar antes/depois com o Felipe quando a aparência mudar. A única decisão bloqueada por referência protegida é D-001; não reaproveitar `VISUAL_REVIEW` passado para novos renders.
5. Completar este relatório com números atuais de L2, hashes, commits, versões e conclusões por item. Só trocar `PARTIAL_BLOCKED` por `COMPLETE` quando **todas** as condições da FP-043 §11 e da spec de conclusão §8 forem satisfeitas.

## 6. Auditoria de invariantes

- Origem de verdade: PDF + consensus, sem paredes/portas inventadas; o `.skp` continua sendo o artefato principal.
- Gates verdes em CI ≠ SketchUp executado nem visual aprovado.
- Nunca `taskkill /IM SketchUp.exe` nem autorun global; preservar sessões humanas e alterações não salvas.
- Fixtures, fontes, .skp, materiais aprovados, referências e renomes protegidos intactos nas PRs #312–#315; mudar um deles exige contrato/consentimento apropriado.
- Perfis consultivos não executam Ruby arbitrário; capability sem implementação responde `BLOCKED_CAPABILITY_MISSING`.
- PR para `develop` somente com CI aplicável verde, registra fase e teste, sem `main` direto.

## 7. Matriz final (2026-10-19, `develop` @ `e67f86c`)

Locais (Windows, interpretador do venv do repo, cwd no worktree), todos `exit=0`: `inventory_gate --strict`, `p0_map --check`, `docs_check`, `ownership_audit`, `capability_catalog`,
`run_deterministic_gates --fixture quadrado` (escala própria) e `--fixture planta_74` (`PT_TO_M=0.0259`), `mcp_server.smoke`, `mcp_server.stdio_check`.
CI do merge #318: 4/4 verdes (pytest py3.11, pytest py3.12, deterministic fidelity gates, mcp smoke+stdio). Obs.: o pytest **local** tem ~61 falhas/erros que **já existem na `develop`**
(testes que exigem `PT_TO_M` definido no import e outros de ambiente); o CI é a referência e os números locais são idênticos antes/depois de #318.

**L2 final (SketchUp 26.0.429, MCP stdio real, PIDs próprios fechados):** `su_build_shell` OK, `su_furnish` 402 peças, `su_inspect` OK; `planta_check`: 402/402 casadas (erro máx. 0,05 mm),
0 geometria solta, 0 mobília/fixture/decor na parede, 0 no giro de porta. Canônicos intactos (SHA-256 `7512d592…` `planta_74.skp`, `dfc431da…` `geometry_report.json`, `d2846ab6…` furnished; saída em `runs/`).
Quadrado: build atual e variante de comparação renderizados em `p3a04_quadrado_d001/`.

## 8. Decisões (linha final)

| ID | Estado |
|---|---|
| D-001 | BLOCKED_DECISION (Felipe) — material em `p3a04_quadrado_d001/` |
| D-002 – D-005 | BLOCKED_DECISION (Felipe) — só retêm o próprio arquivo |
| D-006 | RESOLVED (#300) |
| D-007 | OPEN_TECNICA — `xfail(strict)` nas sintéticas; os controles reais (planta_74) já respeitam o contrato via vão livre por cômodo (#312–#318) |
