# FP-054 F3 (#453) — dimensão obstáculos e contagem de chamadas shapely (2026-10-25)

Evidência nova, datada, ao lado de [`README.md`](README.md) (a linha de base por candidatos não é reescrita).
Dado bruto: [`solver_benchmark_obstacles_2026-10-25.json`](solver_benchmark_obstacles_2026-10-25.json) (`solver_benchmark_obstacles.v1`, commit
`941f83f`, árvore limpa `dirty=false`, Windows 11, AMD64, 16 CPUs, Python 3.12.13, `--repeats 3`, consenso planta_74 de mesmo SHA-256 da linha de base).

Comando: `PT_TO_M=0.0259 PYTHONPATH=. python -m tools.validation.solver_benchmark --obstacles --repeats 3 --out artifacts/review/fp054/f3_benchmark/solver_benchmark_obstacles_2026-10-25.json`

## O que foi medido
`plan_room` (especialista + problema + solver + ranking) nos três cômodos planejáveis (BANHO 01 `r005`, BANHO 02 `r006`, LAVABO `r007`) com **candidatos fixos
em 10** e 0 / 10 / 100 / 1000 caixas **sintéticas** acrescentadas às 390 da planta (caixas 4×4 pol., posições determinísticas, `room="SYNTH"`):

- `far`: fora da vizinhança (célula + 1 m) — mede o custo do filtro `neighborhood`;
- `near`: no anel entre a célula e célula + 1 m — entram na avaliação de cada candidato (sobreposição entre sintéticas é intencional quando n passa do número de posições do anel).

Cada caso roda num subprocesso novo (pico de memória não herda). Uma passada **extra**, fora dos tempos, conta `intersection`, `buffer`, `union`, `intersects`, `distance`, `difference`
e `unary_union` (`CallCounter`). A cena sintética nunca toca a planta nem o consenso.

## Resultado (p50 em s; chamadas de `intersection` por `plan_room`)
| Cômodo | 0 obst. | 1000 `far` | 1000 `near` | `intersection` 0 → 1000 `near` |
|---|---|---|---|---|
| BANHO 01 | 1,036 | 1,050 | 2,155 | 10 384 → 49 664 |
| BANHO 02 | 1,162 | 1,114 | 1,667 | 9 940 → 49 220 |
| LAVABO | 0,991 | 1,000 | 1,540 | 6 462 → 44 062 |

Pico de memória do processo: 52–60 MB em todos os casos (sem tendência com o número de obstáculos).

## Leitura (o que os dados sustentam — e o que não)
1. Com 10 candidatos o tempo é **dominado pelos candidatos**, não pelos obstáculos: 1000 obstáculos fora da vizinhança custam ≤ 1% (dentro do ruído; p95 ≈ p50 × 1,2).
2. Obstáculos **dentro da vizinhança** custam linearmente: +≈ 39 chamadas de `intersection` por obstáculo (≈ 3,9 por candidato avaliado) e +0,5 a 1,1 s a 1000 obstáculos. Nenhum comportamento quadrático apareceu até 1000.
3. `buffer` (≈ 11 000–12 500) e `unary_union` (≈ 350) quase não dependem do número de obstáculos: vêm do enunciado do problema/ranking, não da cena. É onde estaria o custo fixo (candidatos 1→10→100 já medidos: ≈ 0,15 s → 0,9 s → 9,5 s no BANHO 01).
4. **Não** há meta nem budget aqui (a spec manda fixar budget de regressão por capability a partir de dados observados; este é um segundo conjunto de dados, não um budget).
5. **Não medido:** geometria adversarial (obstáculos longos/encostados em muitos candidatos); gates fora do solver (apenas `plan_room` é contado); mais de uma máquina.
6. **Não decide** adoção de OR-Tools/scipy nem mudança no solver: qualquer otimização em `tools/rooms/shared/spatial_solver/` é caminho crítico e exige a revisão independente (#524).
