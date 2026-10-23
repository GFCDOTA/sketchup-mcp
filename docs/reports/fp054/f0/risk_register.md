# FP-054 F0 — registro de riscos (severidade × probabilidade × escopo × detectabilidade)

> 2026-10-23, `develop` após #379, código de medição em `2556f41`. Cada linha cita a evidência desta pasta; "provado" =
> reproduzido por sonda ou teste, "hipótese" = lido no código e ainda sem fixture negativa. Nada aqui foi corrigido na F0.
> Escalas: severidade C/A/M/B (crítica/alta/média/baixa); probabilidade e escopo como medidos; detectabilidade =
> quão fácil é notar sem esta auditoria (baixa = pior). Falso PASS geométrico e perda de fidelidade vêm primeiro (BLOCO 3).

| ID | Risco | Sev. | Prob. | Escopo | Detect. | Estado | Evidência | Fase |
|---|---|---|---|---|---|---|---|---|
| R-01 | **Gate de circulação aprova cômodo com < 2 portais.** `corredor_principal` vira PASS com só `{"erro": "menos de 2 portais no comodo"}` no detalhe; sem portal, ou com 1 portal e o cômodo partido ao meio por móvel, o resultado é PASS | C | certa | planta real: cozinha `r004` e banhos `r005`, `r006`, `r007` (1 portal cada) → 4 de 8 cômodos com PASS vazio | baixa (resultado PASS; o erro só aparece no detalhe) | **provado** | `gate_probes.json` P1/P2; `baseline_performance.json` → `planta_74.rooms[*].circulation_gate.portals_detected` | F1-01 |
| R-02 | **Layout reprovado pelo gate é materializado como OK.** Suíte 01 (`r000`): entre a porta do quarto e a da suíte a largura livre mobiliada é 0,00 m (vazia 1,00 m); a cadeira da escrivaninha fecha a passagem e, sem ela, sobra 0,89 m para alvo 0,90. O brain do quarto não chama o gate; `collect_boxes` reporta `OK` | A | certa | 1 cômodo hoje; qualquer cômodo cujo brain não chame o gate | baixa | **provado** | `baseline_performance.json` → `rooms[r000].circulation_gate.corridor`; diagnóstico por remoção de módulo no handoff | F1-02 (contrato) + F2 (layout); mudar o quarto muda o `.skp` → L2 + L3 |
| R-03 | **Cadeira e mesa reconhecidas por nome.** `_chair_checks` só mede módulos que começam com `Cadeira` (kind `seat`) e mesas `Mesa de jantar`; a mesma geometria rotulada `Chair`/`Dining table` não é medida e passa | A | média (builders atuais usam os nomes PT) | todo gate de cadeira | baixa | **provado** | `gate_probes.json` P4 (FAIL com nome PT) × P5 (PASS com nome EN) | F1-03 |
| R-04 | **Validação não é passo obrigatório antes de materializar.** `collect_boxes` roda só a âncora da pia (bloqueia) e o guarda do banho (só loga); circulação e sobreposição não rodam antes de `su_furnish` | A | certa | apartamento inteiro | média | **provado** (leitura + R-02) | `critical_flow_map.md` etapa 5 | F1-04 / F4 |
| R-05 | **Mesa de jantar escolhida com folga zero.** A posição final (190,5; 668,5) in passa com folga de corredor 0,00 m (resolução da bisseção: 0,01 m); qualquer deslize de 1 cm reprova | M | — | sala | baixa | **provado** | `dining_scenario_trace.json` → `chosen.corridor_slack_m = 0.0` | F2 (ranking por folga/robustez) |
| R-06 | **Arco de porta conferido só no tampo.** A busca da mesa testa o arco só contra o módulo `Mesa de jantar`; cadeiras e cadeira puxada não. Hoje nenhum móvel da sala invade arco (conferido), então é latente | M | baixa hoje | sala; qualquer reuso da busca | baixa | hipótese (latente) | leitura de `tools/rooms/living/furnishing.py` `_swing_hit`; checagem de interseção = 0 | F1-05 |
| R-07 | **`add_face ... rescue nil` no builder do shell.** 6 resgates silenciosos em `tools/sketchup/shell/build_plan_shell_skp.rb` (faces de piso, peitoril, vidro): face que falha some sem erro no `.skp` | A | desconhecida | toda geração de shell | baixa | hipótese | `hazards.json` (`silent_except` em `build_plan_shell_skp.rb`) | F4 (contar faces esperadas × criadas no inspector) |
| R-08 | **Excepts silenciosos e amplos no código vivo.** 175 silenciosos e 112 amplos (maioria em Ruby de render/sofá); 60 `noqa: BLE001` | M | — | transversal | baixa | medido | `hazards.json` → `counts`, `noqa_codes` | F3 (triagem só no caminho P0) |
| R-09 | **PDF → consenso sem extrator ativo.** O consenso da planta_74 é fixture anotada à mão; não há como refazê-lo a partir do PDF no repo | M | — | nova planta | alta | medido | `critical_flow_map.md` etapa 2 | fora da FP-054 (registrado) |
| R-10 | **Constantes duplicadas que divergem.** `ANCHOR_MAX_M` 0,45 × 0,5 e `CLEAR_M` 0,45 × 0,55 entre gates de cama e sofá; `EPS` com 3 valores; 13 nomes duplicados no total | M | — | gates de placement | baixa | medido (intenção ainda não verificada) | `hazards.json` → `duplicated_constants` | F3 (mover para `core/project_policy.py` com fonte, ou documentar a diferença) |
| R-11 | **Conversão de escala redefinida fora de `core/scale.py`.** 15 definições (ex.: `M2IN = 39.37…` local em `tools/rooms/living/furnishing.py`, `tools/rooms/service/layout.py`, `tools/rooms/kitchen/layout.py`) — mesmo valor hoje | B | — | 6 módulos | baixa | medido | `hazards.json` (`scale_constant`) | F3 |
| R-12 | **Gate de sobreposição é O(M²).** 1.000 módulos → 499.500 pares → 2,86 s; nos cômodos reais (≤ 76 caixas) é desprezível | B hoje | — | cenas grandes | alta | medido | `baseline_performance.json` → `synthetic[S5].overlap_gate` | F3 (STRtree, mesma resposta) |
| R-13 | **Furnish do apartamento sem round-trip L2.** Só os fluxos de gabinete reabrem e inspecionam; o `.skp` mobiliado não é reaberto nem comparado com o plano | A | — | materialização | média | medido | `critical_flow_map.md` etapas 8–9 | F4 (BLOCKED_L2 fora desta estação) |
| R-14 | **Estado global em import.** 78 `sys.path` em import, 82 leituras de ambiente; `PT_TO_M` só vale se definido antes do 1º import de `core.scale` (o guarda `assert_pt_to_m_for_source` transforma isso em erro, não em geometria errada) | B | — | transversal | média | medido | `hazards.json` | F3 |
| R-15 | **67 módulos Python ativos sem teste que os importe diretamente** (cobertura só indireta) | B | — | ver lista | média | medido | `inventory_summary.json` → `active_python_without_direct_test` | F3 |

## O que NÃO é risco (conferido)

- Ciclos de import e imports quebrados: **0** (`inventory_summary.json` → `imports`).
- Suítes: escala padrão 2.714 passed / 0 failed; escala planta_74 150 passed / 0 failed. Os 19 "bloqueados" são ambiente
  (Ruby ausente, Qdrant/Ollama desligados, symlink sem privilégio) e o único xfail é o FP-043 P3a-03 já conhecido
  (`baseline_tests.json`).
- Arquivos protegidos: 80 (fixtures, PDF, `.skp` canônico e mobiliados) com blob idêntico ao índice
  (`baseline_environment.json` → `protected_summary`).
- O espião da busca da mesa é passivo: hash da sala igual com e sem ele, e o censo da grade casa 1:1 com as 37 chamadas
  reais do gate (`dining_scenario_trace.json`).

## Issues abertas para os defeitos provados

R-01 → GFCDOTA/sketchup-mcp#380 · R-02 → GFCDOTA/sketchup-mcp#381 · R-03 → GFCDOTA/sketchup-mcp#382 (cada uma com a reprodução
desta pasta). Correção só na F1, com teste vermelho → verde.
