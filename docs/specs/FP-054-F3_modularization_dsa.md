# FP-045-F3 — Micropartições, especialistas, complexidade e custos

> **Registro no repo (Claude, 2026-10-23):** recebida do Felipe como *FP-045*; renumerada para **FP-054** porque FP-045…FP-053 já existem (a FP-045 do repo é a de especialistas/modularização, mergeada). Texto original preservado abaixo; correções e reconciliação com o código ficam na §0 da spec-mãe (`docs/specs/FP-054_spatial_core_reliability_program.md`). Evidências em `docs/reports/fp054/`.

**Pré-requisito:** contrato F1 e solver F2 estabilizados; portar gradualmente sem quebrar behavior.

## Inventário e decisão de fronteiras
- Cruzar catálogo dos 9 perfis atuais com as capacidades reais; mapear contratos/owner, consumidores, dependências, testes e side effects.
- Taxonomia candidata: 10 especialidades core + 9 ambientes + 8 qualidade/operação; **não** criar 27 agentes/processos por padrão. Consolidar quando responsabilidades não justificarem separação.
- Shared: geometry, topology, semantics, constraints, validation, placement, optimization, furniture primitives, knowledge interfaces. Room owns room-specific rules and objective weights.
- Extrair módulos com adapter de compatibilidade, refazer imports por consumidor, provar zero circular imports e nenhuma duplicate implementation ativa; remover facade só após todos consumidores migrarem.

## Big O / benchmarking
- Documentar tempo e espaço em `F` móveis, `C` candidatos, `P` vértices, `E` conexões, `R` regiões; explicar worst/average quando aplicável e efeitos da biblioteca geométrica.
- Profiling com contagem de `intersection`, `buffer`, `unary_union`, serializações, construir shell, rebuilds, subprocessos SketchUp e alocações.
- Avaliar `STRtree`, prepared geometries, memoização com invalidação por hash e atualizações incrementais; provar equivalência de resultados com baseline correta.
- Benchmark 10/100/1000 obstáculos, 1/10/100 candidatos, geometria adversarial; report p50/p95, pico de memória, hardware e SHA.
- Não impor metas absolutas sem baseline; fixar budget de regressão por capability a partir de dados observados.

## Critérios de aceite
- 100% de módulos ativos com dono; microcontratos tipados e versionados; 0 dependências circulares introduzidas.
- Testes contrato e integração sem regressão; benchmarks com comparabilidade de precisão/qualidade; sem ajuste de threshold para esconder lentidão.
- Sem reescrita indiscriminada e sem otimização prematura; PRs pequenos por fronteira.
