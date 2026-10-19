# L2 pós-FP-042 — bateria real no SketchUp (2026-10-19)

**Resultado:** a camada SketchUp foi exercitada no SketchUp real, com resultados salvos,
reabertos e inspecionados. Seis defeitos comprovados foram corrigidos e mergeados com CI
verde (PRs #281–#284). Ficam pendentes achados de layout por cômodo e uma divergência de
contrato que pedem decisão humana. **Não é um "L2 aprovado" geral:** a aparência está
pendente de VISUAL_REVIEW e há itens bloqueados.

Separação de níveis usada aqui:
- **L1:** cálculo e plano em Python (brains, gates, testes). Não abre o SketchUp.
- **L2:** o que o SketchUp materializou, salvo e reaberto, inspecionado por job Ruby (`inspect_model`, `geometry_probe` com raytest).
- **Visual:** só o Felipe. Nenhum IMPROVED/SAME/WORSE foi declarado.

## Ambiente

| Item | Valor |
|---|---|
| Commit base | `develop` @ `8891ca5` (PR #280). Correções mergeadas depois: #281 `0d37c22`, #283 `d8859d5`, #282 `642e8c5`, #284 `15910ec` |
| Windows | 11 Pro 10.0.26200.9711 |
| SketchUp | 26.0.429 Pro, `C:\Program Files\SketchUp\SketchUp 2026` |
| Ruby embarcado | 3.2.2 |
| Plugins | V-Ray for SketchUp 7.20.00 (carregado; licença OK no render), Enscape 4.18, `autorun_consume.rb` presente, nenhum `*_control.txt` pendente |
| Instâncias antes | nenhuma. Toda instância foi aberta por esta bateria e fechada pelo PID dela, nunca por nome |
| Modo | `interactive` em todos os runs (headless não foi usado: proibido em dev local) |
| MCP | servidor real `tools.mcp_server.server` por stdio, processo novo a cada chamada, 18 tools |
| Escala | `PT_TO_M=0.0259` só em processos da planta_74; o quadrado e as sintéticas rodaram na escala padrão 0,0352 (ver S01a) |

## Integridade dos protegidos

`integrity/hashes_before.sha256` e `hashes_after.sha256`: os 882 arquivos de `fixtures/`, `artifacts/` e `assets/` estão **byte a byte iguais**.
- Hashes do consensus e do `.skp` canônicos conferem com `planta_74.skp.metadata.json` (`adeace53…`, `7512d592…`).
- A cena V-Ray usada como entrada (`runs/scenes/living_room_black_wood_gold_boutique`) também ficou intacta: mesmos hashes, mesmos 20 arquivos.
- Nenhum `.skp`, fixture, render ou referência aprovada foi regravado.

## Matriz de cenários

| ID | Objetivo | Status | Evidência / observação |
|---|---|---|---|
| ENV | ambiente, versões, MCP | PASS | tabela acima; `su_status` via stdio |
| S01a | quadrado com escala errada | INVALID (erro do operador) | Exportei `PT_TO_M=0.0259` também para o quadrado. Descartado e refeito; depois o mesmo defeito foi provado no produto (P06) |
| S01 | shell quadrado: medidas, grupos, vão, topologia, reabertura | PASS | PlanShell 3,4235–7,6135 m = referência canônica; 72 KB. Raytest: parede em z=0,5/1,2 m (abaixo do peitoril) e 2,4/2,65 m (acima da verga); vão em 1,8 m. 0 faces degeneradas, 0 arestas soltas/zero/não-manifold. Inspect do `.skp` reaberto confere com o `geometry_report` |
| S01-ref | relatório real vs referência canônica | **FAIL: contrato divergente** | O builder faz janela horizontal ≤1,20 m virar basculante (peitoril 1,50/verga 2,10, `b45712a`). Referência `docs/specs/_assets/quadrado_canonical_geometry_report.json` e `test_window_aperture_geometry` esperam 0,90/2,10. Com o build real presente, 8 testes passam e 1 falha. **Decisão sua:** atualizar a referência ou o builder. Também diverge da referência: piso agora vai sob a parede (intencional, 2026-06-04) e há grupo `WindowSash` |
| S02 | shells sintéticos (quarto 14 m², sala 18/28 m²) | PASS | gates PASS |
| S03 | mobília sintética (quarto, sala) | materialização PASS; layout **FAIL** | 64/64 e 53/53 peças batem com o plano (erro máx. 0,05 mm). **Guarda-roupa 4,5 cm dentro da parede oeste:** a fixture sintética põe o polígono no eixo da parede, a convenção do consensus é a face interna. Sala média: o `circulation_gate` do projeto reprova a porta da varanda (`w_furnished=0`); o furnish só loga WARN. Giro de porta: NOT_RUN, porque a fixture não declara swing |
| S04 | materiais e texturas com estilo `modern_warm` | PASS | 9 materiais texturizados (madeira/tecido) preservados após reabrir; 83/83 peças. Sobreposições de 2–4 cm entre peças de parede (prateleira/planta/quadro × painel TV) passam no `furniture_overlap_gate`, que está abaixo dos limiares → VISUAL_REVIEW |
| S05 | builders isolados (sofá reto, chaise, poltrona, cama, guarda-roupa, criado) a 0/90/30° | **FAIL → corrigido** | 240/240 peças a 0,05 mm. Mas a 30° o chanfro vazava da pegada: 71 raios fora da pegada acertaram a peça. Corrigido em #283 → S09 |
| S09 | builders após o fix | PASS | 0/126 raios acertam; topologia idêntica em todas as instâncias a 0/90° e nas classes não afetadas; 240/240 peças |
| S05-sep | separação das peças dentro do móvel | OBS | Sofás sem interpenetração. Poltrona, cama, guarda-roupa e criado têm sólidos sobrepostos dentro do móvel (puxador 30 mm dentro do corpo; cabeceira × estrado 80 mm). Não há contrato contra; **não é apto para fabricação** |
| S05-def | definições compartilhadas / componentes | N/A | os builders só emitem grupos únicos (`contexts=1`); nenhum componente compartilhado foi produzido |
| S05-grain | orientação de veio | NOT_SUPPORTED | `place_layout_skp.rb` só define o tamanho do tile da textura; não há controle de UV/rotação |
| S06 | contratos `su_*` via MCP stdio | **FAIL → corrigido** | Antes: `su_inspect` dava TIMEOUT em 180 s ("Sem nome", sem resposta), e as recusas Ruby viravam erro da tool (WinError 32). Depois (#282): **38/38** dentro do contrato (tabela abaixo) |
| S07 | causa do travamento MCP | PASS (diagnóstico) | Repros isolados: stdin com leitura pendente → TIMEOUT; com `stdin=DEVNULL` → OK em 9 s. Descartados: pipe sem leitura, `CREATE_NO_WINDOW`, Job Object. `faulthandler` do `su_furnish`: travava importando numpy |
| S08 | V-Ray: porte e render de prova | PASS | Launcher legado tinha `taskkill /F /IM SketchUp.exe`; portado em #281. 600×400, `vray.exe` 0 erros/0 warnings, 9,5 s; `scene_dir` intacto; instância concorrente intacta |
| S10 | gabinete do catálogo | BLOCKED_CAPABILITY_MISSING | `cabinet_plan` L1 só de cálculo, 10 peças propostas, ferragens como informação faltante, `execution_authorized=false`. Não existe materializador Ruby/SKP; nada foi improvisado |
| P01 | shell planta_74 | PASS | Rebuild determinístico: 25 grupos, bboxes, contagens e gates iguais ao canônico. **72/72 raios** nas 12 aberturas, dos dois lados: janelas com massa abaixo/acima, portas e porta-vidro em altura cheia. 1 folha/vidro por abertura (sem duplicata). 0 defeitos de topologia |
| P02 | apê integrado via `su_furnish` (MCP) | materialização PASS; **achados** | Antes do #282: travava (import do numpy). Depois: 402/402 peças em 14 s, todas batendo com o plano em 0,05 mm, 0 geometria solta, 25 grupos do shell travados. Achados por cômodo abaixo |
| P03 | cada cômodo isolado vs integrado | PASS | 8/8 cômodos idênticos ao integrado; shell idêntico; nenhum módulo estranho |
| P04 | editar um cômodo sem afetar os outros | PASS | SUITE 02 inteira (material + mover a cama 5 cm) → 15 nós mudaram, todos da SUITE 02; **0 fora**; dx = 0,0500 m após reabrir |
| P05 | sofá premium aprovado | posição/escala PASS; **VISUAL_REVIEW** | Mesmo bbox (0,879×1,621 m) e 8/9 peças idênticas (≤0,1 mm). Diferenças: `plinth_riser` desceu 8 cm (agora 0,08–0,14, entre plinto e base; no aprovado ficava dentro da base), +2 almofadas (topo 0,76→0,92 m), materiais `ph_*`. O conjunto da sala também difere do aprovado: sem mesa de centro; com painel TV, TV e pendente |
| P06 | `su_build_shell` do quadrado via MCP | **FAIL → corrigido** | Saiu na escala da planta_74 (3,08 m) e **todos os gates deram PASS**. Corrigido em #284 → P07 |
| P07 | escala após o fix | PASS | quadrado = referência; planta_74 inalterada |

### S06: contratos MCP (servidor da branch corrigida)

**Positivos, todos reabertos e inspecionados**
- `move`: deslocamento exato; outros objetos e shell intactos.
- `move` reaplicado acumula 2× (esperado; não é idempotente).
- `rotate` 90°: dimensões trocadas, centro mantido.
- `set_material` (cor e textura), `set_tag`, `set_hidden`, material no shell (permitido) sem mexer na geometria, `rename`.
- Setters reaplicados: mesmo estado e mesma contagem de materiais e tags.
- `insert_component` (componente, tag, origem exata).

**Recusas Ruby**
Nestes casos a cópia que fica no destino é byte a byte igual à base e ganha um marcador `.NOT_A_RESULT.txt`:
- alvo inexistente;
- alvo ambíguo;
- arquitetura protegida por `persistent_id`;
- arquitetura por `name_contains`;
- `delete` do piso;
- `rename` da janela;
- `insert` de `.skp` que traz arquitetura;
- lote que falha no meio (atômico: as 2 primeiras ops eram válidas);
- alvo que casa um grupo e uma peça dentro dele.

**Recusas do validador Python, sem subir o SketchUp:** `move` de arquitetura por nome, `rename` para nome reservado, falta de `by_m`, cor fora de 0–255, op desconhecida, 201 ops.

**Destino:** recusados `fixtures/`, `artifacts/`, destino já existente e destino = entrada. `.skp` inexistente, preset inválido e `close` sem `confirm` também são recusados.

## Achados por cômodo (planta_74 integrada)

Os achados foram medidos contra o polígono **extrudado** das paredes (`_shell_polygon.json`) e contra o quarto de círculo real de cada folha. O `swing_side`/`hinge_side` do consensus já foi conferido contra os arcos do PDF por `door_swing_audit`. Revestimentos finos (Pele/PeleTeto) ficam de fora, como no gate do projeto.

| Cômodo | Dispatch | Resultado |
|---|---|---|
| Sala (estar/jantar) | LIVING, 51 peças | **FAIL:** tampo da mesa de jantar dentro do giro da porta h_o000 (36 cm²). FAIL menor: painel TV 5 cm dentro de um retorno de parede (14 cm de extensão). Sofá: ver P05. Sem mesa de centro nem poltrona |
| SUITE 01 | BEDROOM, 65 | **FAIL:** Criado-mudo 2 entra **6,3 cm** na parede ao longo dos 42 cm (o 1 não entra). Criados suspensos a 0,30 m por desenho |
| SUITE 02 | BEDROOM, 47 | PASS |
| Cozinha | KITCHEN, 76 | PASS: pia/cooktop/coifa/bancada na parede oeste (âncora hidráulica do PDF, L1 PASS), tudo dentro da cozinha. OBS: corpo da geladeira em z0 = 2 cm por desenho do brain, sem peça de pé |
| Banho 01 | BATHROOM, 59 | FAIL menor: piso do box 4,1 cm sob a parede (78 cm de extensão) |
| Banho 02 | BATHROOM, 58 | FAIL menor: ralo 2,6 cm na parede |
| Lavabo | BATHROOM, 33 | **FAIL:** porta-escova dentro do giro da porta h_o001 (65 cm², até 0,40 m de altura) |
| A.S./Terraço social/técnico | SERVICE (composto), 13 | PASS. Prateleira, varal, coifa e condensadora elevados por desenho |

Varanda, closet e home office **não têm brain próprio**: a varanda está dentro do SERVICE composto; closet e home office reusam o quarto. Nenhum desses aparece aqui como brain independente.

Os achados de layout são de L1: o `.skp` reproduz o plano em 0,05 mm. Nenhum foi corrigido nesta bateria, porque mudam aparência e precisam de decisão de projeto.

## Correções (branch própria, testes, CI 4/4 verde, merge em `develop`)

| PR (merge) | Defeito | Prova |
|---|---|---|
| #281 `0d37c22` | `su_render_vray` recusava: o launcher legado matava o SketchUp por nome | export pela própria instância + render real |
| #282 `642e8c5` | (a) SketchUp herdava o stdin do MCP e travava; (b) recusa Ruby virava erro e deixava a cópia não editada no destino; (c) import preguiçoso do numpy travava o servidor | repros S07; MCP 38/38; `su_furnish` 402/402 em 14 s |
| #283 `d8859d5` | chanfro de peça macia girada vazava da pegada (inset pelo AABB) | 71 → 0 raios; topologia 0/90° idêntica; Ruby test no CI (pegou uma falha do meu helper, corrigida) |
| #284 `15910ec` | `su_build_shell` herdava a escala do servidor | 4/5 testes falham no develop; L2 quadrado = referência |

## Capacidades

**Executadas no SketchUp (L2):**
- `su_status`, `su_inspect`, `su_apply_edits` (todas as ops), `su_close`;
- `su_build_shell` (quadrado, sintéticas, planta_74);
- `su_furnish` (planta_74);
- `place_layout_skp.rb` (sintéticas, builders, cômodos isolados);
- `su_render_vray` (após o porte).

`su_render` só foi exercido no caminho negativo (preset inválido). Os renders top/iso foram gerados pelos builders. `su_open` não foi chamado: ele abre uma janela solta para uso humano.

**Só consultivas:** 19 recipes `KNOWLEDGE_ONLY_UNTESTED_IN_SKETCHUP`, `cabinet_plan`, brains de varanda, closet e home office.

## Bloqueios e riscos restantes

- **S01-ref:** contrato do peitoril do quadrado divergente (sua decisão).
- **Achados de layout:** SUITE 01, sala, lavabo e banhos; fixture sintética com polígono no eixo da parede.
- **Escala do quadrado:** escala padrão 0,0352. Nenhum gate confere escala; o P06 passou em todos.
- **`build_shell` usa o `autorun_control.txt` global do Plugins:** qualquer SketchUp aberto durante um build executaria o build. Não foi corrigido nesta bateria.
- **`SketchUpBasicProvider`** (gera `scene_closed.skp`) ainda usa `taskkill /IM`. O `render_scene_vray` só o chama quando nenhum SketchUp está aberto.
- **`print` para stdout em `build_plan_shell_skp.run` e `collect_boxes`:** no servidor MCP, stdout é o canal JSON-RPC. O cliente Python tolerou; outros clientes podem não tolerar.
- **Job Object do cliente MCP Python:** sem breakaway, o SketchUp aberto via MCP morre quando o servidor fecha (o fallback do #282 cobre o lançamento, não isso). O Claude Code (Node) não foi medido.
- **Unidade dos modelos:** `length_unit_code=0` (polegadas) herdado do bootstrap. O `_bootstrap.skp` traz 21 materiais `Sree_*` e uma definição sem uso.
- **Sem cobertura no CI:** o teste do pré-carregamento do MCP pula no job pytest (sem o extra `[mcp]`).
- **Fechamento forçado por PID:** uma vez precisou de 2ª tentativa (o SketchUp levou mais de 5 s para sair).
- **Arquivos `.skb`:** o SketchUp grava `.skb` ao lado de cada `.skp` salvo.

## Aguardando sua revisão visual

1. `S01_quadrado_shell/model_iso.png`: basculante a 1,50 m (contrato S01-ref).
2. `S05_builders_before_fix/builders_iso.png` × `S09_builders_after_fix/builders_iso.png`: as 4 instâncias a 30°.
3. `P02_furnish_integrated/*_after_top.png` e `*_after_iso.png`, e `P03_rooms_isolated/*_room_top.png` / `*_room_iso.png` por cômodo.
4. P05: sofá da sala vs. premium aprovado (riser, almofadas, conjunto da sala).
5. `S04_styled_living_large`: peças de parede sobrepostas.
6. `S08_vray_proof/vray.png`: só prova de execução, não qualidade.

## Reprodução

Scripts em `tools/` (os mesmos que geraram cada número). Exemplos:
- `run.py <out.json> build_shell '{...}'`
- `probe.py <skp> <dir> '<rays json>'`
- `mcp_suite.py <base.skp> <dir>`, com `PT_TO_M=0.0259` no env do servidor
- `planta_check.py`

Hashes de tudo em `SHA256SUMS`.
