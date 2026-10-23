# FP-045-F0 — Baseline, inventário e diagnóstico comprovável

> **Registro no repo (Claude, 2026-10-23):** recebida do Felipe como *FP-045*; renumerada para **FP-054** porque FP-045…FP-053 já existem (a FP-045 do repo é a de especialistas/modularização, mergeada). Texto original preservado abaixo; correções e reconciliação com o código ficam na §0 da spec-mãe (`docs/specs/FP-054_spatial_core_reliability_program.md`). Evidências em `docs/reports/fp054/`.

**Objetivo:** mapear a aplicação inteira antes de otimizá-la; não alterar regras de negócio nesta fase.

## Passos de implementação
1. Congelar SHA de `develop`, versão do Python/SketchUp, SO, dependências e hash dos artefatos protegidos; registrar estado de PRs em ambos repositórios.
2. Inventariar todos os arquivos versionados (`git ls-files`), classificando por código ativo, teste, contrato, fixture, conhecimento, artefato, legado, documentação e gerado; nenhum arquivo sem classificação. Identificar dependências dinâmicas Ruby e imports Python.
3. Construir grafo de chamadas aproximado, imports, scripts entrypoints, ferramentas MCP, caminhos de UI/harness, builders e gates; mapear cada arquivo/capacidade com **owner** e consumidores.
4. Localizar duplicação de heurísticas, regras hardcoded, ranges e conversões de escala, acesso global a estado, side effects, silêncio de erro, suppressions, xfails, skip e wrappers.
5. Marcar fluxos críticos P0: PDF -> consenso -> shell -> planejar -> validar -> materializar -> salvar -> reabrir -> inspecionar.
6. Executar suíte atual em todos profiles/escalas suportados; registrar PASSED/FAILED/XFAIL/SKIP/BLOCKED e ambiente. Não 'consertar' testes mudando fixtures.
7. Capturar baseline de 5 cenas sintéticas, sala canônica e outros cômodos: posições, constraints, p50/p95, memória, número de geometrias e chamadas. Gerar flame/callgraph nos hotspots comprovados.
8. Matriz de riscos severity × probability × scope × detectability: falso PASS geométrico e perda de fidelidade têm prioridade máxima. Inventariar perfis/fragmentos/capabilities já existentes.

## Evidências
- `docs/reports/FP-045/inventory.csv` com todos caminhos, owner, status e justificativa; soma igual ao `git ls-files` no SHA.
- `dependency_graph.*`, `critical_flow_map.md`, `baseline_environment.json`, `baseline_tests.json`, `baseline_performance.json`, `risk_register.md`.
- `issues` pequenos para defeitos comprovados, sem declarar correção antecipadamente.

## Critérios de aceite
- 100% dos caminhos rastreados; 100% das rotas P0 mapeadas até a materialização; faltas de ambiente marcadas como BLOCKED.
- Cenário de mesa reproduzido com seed, entradas, posições e lista de motivos de rejeição; se não reproduzir, registrar isso explicitamente.
- Gate de integridade de artefatos não alterado; nenhuma mudança funcional neste PR.
