# FP-054 F0 — baseline, inventário e diagnóstico (2026-10-23)

> Retrato datado. Código de medição em `2556f41` (`tools/navigation/baseline_inventory.py`,
> `tools/navigation/baseline_probes.py`, testes em `tests/test_fp054_baseline.py`). Nenhuma regra funcional mudou nesta fase.
> Spec: `docs/specs/FP-054-F0_baseline_inventory.md`; programa: `docs/specs/FP-054_spatial_core_reliability_program.md`.

## Arquivos

| Arquivo | O que é | Como regenerar |
|---|---|---|
| `inventory.csv` | 1 linha por arquivo versionado: classe, estado, owner, especialista/fragmento, capacidades, testes que importam, achados | `python -m tools.navigation.baseline_inventory --out docs/reports/fp054/f0` |
| `inventory_summary.json` | contagens; `reconciled: true` = linhas == `git ls-files` (2.332 em `2556f41`) e nenhuma sem classe | idem |
| `dependency_graph.json` / `.md` | 394 nós, 679 arestas: imports (topo/tardio), Python→Ruby, `require` Ruby, tool MCP→módulo, CI→módulo | idem |
| `hazards.json` | except silencioso/amplo, `noqa`, skip/xfail, `global`, cache, `sys.path`, ambiente, escala, constantes duplicadas, semântica por nome | idem |
| `critical_flow_map.md` | PDF→…→inspecionar com os caminhos reais e o gate de cada etapa (escrito à mão; caminhos travados por teste) | — |
| `baseline_environment.json` | SHA, Python, pacotes, GEOS, SO, hardware, SketchUp 26.0.429 (instalado, 0 instâncias), 80 arquivos protegidos com hash, harness-app `develop@0928e75`, PRs abertos (0 e 0) | `python -m tools.navigation.baseline_probes env --gh --harness E:/Claude/apps/harness-app --out docs/reports/fp054/f0` |
| `baseline_tests.json` | as 2 escalas por junit: passed/failed/skip/bloqueado por ambiente/xfail, motivos e 15 mais lentos | `python -m tools.navigation.baseline_probes tests --out docs/reports/fp054/f0` |
| `baseline_performance.json` | 5 cenas sintéticas semeadas + planta_74 por cômodo: p50/p95, pico de memória, chamadas | `python -m tools.navigation.baseline_probes perf --profile docs/reports/fp054/f0/profile_collect_boxes.txt --out docs/reports/fp054/f0` |
| `profile_collect_boxes.txt` | cProfile (top 30 cumulativo) do furnish do apartamento | idem |
| `dining_scenario_trace.json` | a busca da mesa reproduzida: os 1.040 pontos da grade com motivo, as 37 chamadas do gate com o check que reprovou | `PT_TO_M=0.0259 python -m tools.navigation.baseline_probes dining` (o `all` faz isso sozinho) |
| `gate_probes.json` | sondas de falso PASS do gate de circulação | `python -m tools.navigation.baseline_probes gate-probes --out docs/reports/fp054/f0` |
| `risk_register.md` | 15 riscos com severidade × probabilidade × escopo × detectabilidade e evidência | — |

Tudo de uma vez: `python -m tools.navigation.baseline_probes all --out docs/reports/fp054/f0 --gh --harness E:/Claude/apps/harness-app`
(≈ 3 min nesta máquina; as suítes são 2,5 min).

## Resultado

- **Inventário**: 2.332/2.332 arquivos classificados (`reconciled: true`); 0 ciclos e 0 imports quebrados; 2.328 com owner do
  inventário FP-042 e 4 por regra de caminho; 67 módulos ativos sem teste que os importe diretamente.
- **Especialistas** (BLOCO 8): 9 perfis (`balcony`, `bathroom`, `bedroom`, `circulation`, `closet`, `home_office`, `kitchen`,
  `living`, `service`), 20 fragmentos, 18 capacidades (5 `L2_PASS`, 12 `L1_PASS`, 1 `UNTESTED`), 15 bindings. Os 27 papéis da
  spec seguem como taxonomia: nenhum agente ou processo novo foi criado.
- **Suítes**: padrão 2.714 passed / 0 failed / 11 skip / 19 bloqueados por ambiente / 1 xfail conhecido; planta_74 150 passed.
- **Mesa de jantar** (BLOCO 1, "relato não reproduzido"): **reproduzido**. Busca determinística (sem semente: não há sorteio).
  Grade de 6 in: 1.040 pontos → 772 fora da margem de 20 in, 230 sem exatamente 2 cadeiras, 10 com sobreposição > 50 in²,
  28 ao gate (17 reprovam no corredor, 9 nas cadeiras, 2 passam mas tocam o arco da porta `h_o000`); refino de 0,5 in em volta
  da âncora de maior folga: 9 chamadas (8 reprovam no corredor) → escolhida (190,5; 668,5) in com folga 0,00 m. Total 37
  chamadas, igual a `n_candidates_tried`. Espião passivo (hash da sala igual com e sem ele).
- **Performance**: furnish do apartamento p50 0,82 s (402 caixas, pico 0,74 MB Python); brain mais caro = serviço (0,41 s),
  depois sala (0,31 s). Gate de circulação: 4–37 ms em cenas de até 100 móveis, 0,16 s com 1.000. Gate de sobreposição
  O(M²): 2,86 s com 1.000 módulos (R-12).
- **Defeitos provados** → issues GFCDOTA/sketchup-mcp#380 (PASS com < 2 portais), GFCDOTA/sketchup-mcp#381 (Suíte 01 com
  circulação FAIL materializada), GFCDOTA/sketchup-mcp#382 (cadeira por nome). Detalhe e os demais riscos em `risk_register.md`.

## Complexidade das ferramentas de medição

| Ferramenta | Tempo | Espaço | Observação |
|---|---|---|---|
| `baseline_inventory.build` | O(A + T) | O(A + T) | A = arquivos versionados, T = bytes de texto; 1 leitura + 1 parse por arquivo; ≈ 3 s |
| `dining_trace` | O(G · (k + c)) | O(G) | G = 1.040 pontos da grade, k = caixas do conjunto mesa+cadeiras, c = custo de um `check` só nos 28 que chegam ao gate |
| `synthetic_perf` | O(Σ cenas · repetições · custo do gate) | O(n) por cena | o gate de sobreposição domina em n = 1.000 (O(n²) pares) |

## Limites declarados

- Memória é o pico do `tracemalloc` (alocações Python), não RSS: GEOS aloca fora dele.
- p95 com 3–7 amostras é posto mais próximo — indicador, não estatística robusta; as amostras brutas não são guardadas.
- O censo da mesa reimplementa as 3 podas antes do gate; a prova de fidelidade é casar 1:1 com as 37 chamadas reais
  (`census_aligned_with_spy`). As rejeições pré-gate do refino não são listadas uma a uma (só as chamadas ao gate).
- `hazards.json` é um detector textual/AST: conta ocorrências, não julga se cada uma é errada.
- Nada foi rodado no SketchUp (sem L2/L3 nesta fase).

## Próximo passo

F1 (`docs/specs/FP-054-F1_geometry_correctness.md`): começar por GFCDOTA/sketchup-mcp#380 — teste vermelho com as cenas P1/P2 de
`gate_probes.json`, depois o contrato `ConstraintResult` com `BLOCKED_MISSING_INPUT`/`NOT_APPLICABLE`.
