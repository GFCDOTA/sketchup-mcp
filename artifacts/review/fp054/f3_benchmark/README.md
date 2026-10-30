# FP-054 F3 (#453) — linha de base MEDIDA do solver F2 (2026-10-25)

Primeira medição de desempenho do solver sem alterá-lo. **Não é meta nem budget**: a F3 manda fixar o budget de regressão por capability a partir de dados
observados, e estes são os primeiros dados.

| | |
|---|---|
| Código sob prova | commit `ac177f5`, árvore limpa (`dirty: false` no JSON) |
| Máquina | Windows 11 (10.0.26200), AMD64, 16 CPUs lógicas, Python 3.12.13 (uv) |
| Consenso | `fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json`, SHA-256 `69dbbf0394b5…` (hash do conteúdo com EOL normalizado, no JSON) |
| Reprodução | `PT_TO_M=0.0259 PYTHONPATH=. python -m tools.validation.solver_benchmark --repeats 5 --out runs/solver_benchmark.json` |
| Medida | `intelligent_pipeline.plan_room` (especialista + problema + solver + ranking) com teto `max_candidates`; 5 repetições por caso; pico de memória do **processo** (working set de pico) num subprocesso novo por caso |

## Resultado (segundos; mediana / p95) — `solver_benchmark_2026-10-25.json`
| Cômodo (candidatos totais) | teto 1 | teto 10 | teto 100 | pico RSS (1 / 10 / 100) |
|---|---|---|---|---|
| BANHO 01 `r005` (6724) | 0,15 / 0,25 | 0,92 / 1,09 | 9,50 / 9,93 | 53 / 57 / 70 MB |
| BANHO 02 `r006` (6724) | 0,16 / 0,24 | 0,99 / 1,08 | 8,69 / 9,55 | 56 / 58 / 69 MB |
| LAVABO `r007` (1681) | 0,11 / 0,18 | 0,81 / 0,87 | 7,51 / 7,99 | 52 / 52 / 59 MB |

## Leitura (o que os dados dizem e o que não dizem)
- **Custo linear em candidatos:** ≈ 0,09 s por candidato avaliado (teto 100 ≈ 10 × teto 10), custo fixo de montagem ≈ 0,1 s. Extrapolando, o cômodo completo (6724
  candidatos) leva ~10 min, o que bate com as execuções completas de 2026-10-24/25 (≈ 620–780 s, medidas sob outra carga).
- **Memória não é gargalo:** pico de processo 52–70 MB em todos os casos; cresce pouco com o teto.
- Onde otimizar primeiro (hipótese **a confirmar** com a contagem de `intersection`/`buffer`/`unary_union`, ainda não medida): o tempo por candidato (avaliação funcional + colisão).

## O que NÃO foi medido (pendente da F3)
- Dimensão **obstáculos** (10/100/1000) em cenas sintéticas e geometria adversarial.
- Contagem de operações geométricas (`intersection`, `buffer`, `unary_union`), serializações e rebuilds; STRtree/prepared geometries ainda não avaliados.
- ADR para qualquer biblioteca nova (OR-Tools/scipy): continua obrigatório antes de adotar; nenhuma foi adotada.
