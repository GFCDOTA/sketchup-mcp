# FP-043 — Auditoria final P8 (status parcial e rastreável)

**Data:** 2026-10-19. **Estado global:** `PARTIAL_BLOCKED`; **NÃO** declarar FP-043 encerrada.
**Base verificada:** `develop` após os PRs #286–#315. Documento de auditoria técnica; **não** é `VISUAL_REVIEW` nem uma nova prova L2.
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
| P3a-03 (colisões) | PARTIAL_L1 — #312 suíte 01, #313 lavabo, #315 sala; CI das duas escalas verde em cada merge | Precisa L2 atualizado e revisão visual; box/ralo BANHO 01/02 não declarados corrigidos |
| P3a-04 (quadrado) | BLOCKED_DECISION — D-001: peitoril do baseline 0,90 m × build 1,50 m | NÃO alterar relatório/fixture protegidos sem decisão + visual |
| P3a-05 (repo health) | DONE_L1 — #300, D-006 resolvida e gate em CI | Não reintroduzir escala fora do core |
| P3b (processo/MCP/render/escala) | DONE_L2 para a versão #311: Windows SU 26.0.429, 19/19 positivos, 6/6 janela humana preservada; PIDs próprios | Não cobre as alterações de layout #312/#313/#315; Node SDK não é Claude Code Desktop |
| P4 (modularização física) | DONE_COM_EXCECOES — #301–#306; #314 sincroniza 3 diretórios de fachadas com mapa | D-002 a D-005 retêm os itens nominados por decisão; não confundir fachada com duplicação |
| P5 (perfis e capabilities) | DONE_L1 — #307, 9 perfis roteados, catálogo de provas e `BLOCKED_CAPABILITY_MISSING` | Consultar `tools.rooms.specialists`, catálogo e registros reais; nenhum selo visual |
| P6a (gabinete/plano) | DONE_L1 — #308, builder shared e adapter cozinha | Sem ferragem/Shaker/UV de veio |
| P6b (gabinete no SU) | DONE_L2 — #309, 13/13 micro-fixtures com 0°/90°/30°, reabertura, edits, `make_unique` | `grain=NOT_SUPPORTED`, `visual=NOT_REVIEWED`; geometria não certifica fabricação |
| P7 (pedido → gabinete SKP) | DONE_L2 — #310, 42 checks do cenário positivo, negativos fail-closed, reinício idempotente | Posição do gabinete é experimental e requer avaliação visual/projeto |
| P8 (navegação/auditoria/relatório) | PARTIAL — relatório presente, CI/GitHub rastreáveis | Critérios finais bloqueados pelos itens abaixo |

## 2. Correções integradas após o L2 do #311

| PR | Merge SHA | Prova L1 integrada | Pendente |
|---|---|---|---|
| [#312](https://github.com/GFCDOTA/sketchup-mcp/pull/312) | `bc759f5af5fe6c33295ac3db0364fe6e897ee12c` | Planner/body/top dos criados na SUITE 01 e SUITE 02 verificam footprint real | Reconstruir suite(s), inspecionar e rever visual |
| [#313](https://github.com/GFCDOTA/sketchup-mcp/pull/313) | `5be70cf921ffed06c4099a1689922130338bf6dc` | Porta-escova do lavabo não invade o arco real `h_o001`, sem omissão de peça | Materializar lavabo, inspecionar arco/escova e visual |
| [#314](https://github.com/GFCDOTA/sketchup-mcp/pull/314) | `4a6800151934304f0bc82cfb3e48e2e63d07c729` | Estado P4 e D-006 refletidos fielmente em documentos/mapa | Apenas navegação contínua |
| [#315](https://github.com/GFCDOTA/sketchup-mcp/pull/315) | `61783a43fdbb6316ff18d2f21fdbf132588f3a40` | Painel de TV fora da parede; mesa de jantar fora do arco da porta e circulação PASS na planta real; 2 cadeiras preservadas | Rebuild SU real, comparação top/iso e visual |

**Escopo da evidência recente:** os quatro checks do CI (pytest 3.11, pytest 3.12, deterministic fidelity e MCP) passaram para #312–#315. Isso prova comportamento Python e protocolos sem SketchUp; **não equivale** a L2 dos SKPs novos.

## 3. Pendências reais a NÃO esconder

1. **L2 pós-layout**: reconstruir as versões **atuais** de SUITE 01/02, SALA, LAVABO e apartamento integrado. Capturar `.skp`, screenshot top/iso, inspector, `planta_check`, contagem de peças, folha/arcos e fingerprints de arquitetura. Provar que os três reparos L1 continuam válidos após salvar/reabrir. Não substituir SKP canônico.
2. **BANHO 01/02**: no L2 antigo há `kb_piso_box` 4,1 cm sob parede do BANHO 01; `kb_ralo` 2,6 cm na parede e contato de `box_vidro` no BANHO 02. Reproduzir no novo `HEAD`, separar pele hospedada intencional de colisão real, criar regressão por item e corrigir sem alterar estética aprovada às escondidas.
3. **D-007 sintéticas**: `test_contrato_nenhum_movel_dentro_da_parede` é `xfail(strict)` documentado. Resolver o vão real por cômodo sem derrubar SUITE 02, regra hidráulica da cozinha ou SERVICE. A varanda sintética conserva diagnóstico `circulation_gate: FAIL/WARN` explícito, não um PASS fictício.
4. **D-001**: referência do `quadrado` pinada em vidro 0,90–2,10 m diverge do builder 1,50–2,10 m + grupo `WindowSash`/piso. Sem decisão do Felipe, não alterar a referência protegida. O L2 #311 mostrou 8 testes condicionais verdes e 1 FAIL autêntico.
5. **D-002–D-005**: dashboard legado, uso do `furnish_plan`, owner de `trace_view`, utilidade do script `set_clipboard_image.ps1`. Cada decisão só bloqueia seu arquivo: manter exceções anotadas.
6. **Visual/fabricação**: nem aparência dos reparos nem gabinete experimental receberam `VISUAL_REVIEW=APPROVED`; Shaker, UV/veio, ferragens e fabricação permanecem explicitamente fora do piloto.

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
