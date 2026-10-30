# FP-054 F3 (#453) — geometria adversarial no solver (2026-10-25)

Evidência nova, datada, ao lado de [`README.md`](README.md) (candidatos) e [`README_obstacles_2026-10-25.md`](README_obstacles_2026-10-25.md) (obstáculos benignos).
Dado bruto: [`solver_benchmark_adversarial_2026-10-25.json`](solver_benchmark_adversarial_2026-10-25.json) (`solver_benchmark_adversarial.v1`, commit `6998121`,
árvore limpa `dirty=false`, Windows 11, AMD64, 16 CPUs, Python 3.12.13, `--repeats 3`, mesmo consenso da planta_74).

Comando: `PT_TO_M=0.0259 PYTHONPATH=. python -m tools.validation.solver_benchmark --adversarial --repeats 3 --out artifacts/review/fp054/f3_benchmark/solver_benchmark_adversarial_2026-10-25.json`

## O que foi medido
`plan_room` nos três cômodos planejáveis (BANHO 01 `r005`, BANHO 02 `r006`, LAVABO `r007`), **candidatos fixos em 10**, 10 / 100 / 1000 caixas sintéticas em três formas
que maximizam trabalho dos gates de interseção (27 casos; cada um num subprocesso novo; uma passada extra só de contagem de chamadas shapely):

- `long`: barras de 1 pol. que atravessam **toda** a vizinhança (célula + 1 m), alternando horizontal/vertical e espalhadas por toda a extensão — cada barra cruza o cômodo e a maioria dos candidatos;
- `stacked`: caixas 4×4 pol. sobre o centroide da célula (deslocamentos de 0,5 pol.): sobreposição degenerada **dentro** do cômodo;
- `rotated`: quadrados de 6 pol. girados 45° numa grade de 8 pol. dentro da célula.

Nada disso toca a planta nem o consenso.

## Resultado (p50 em s; chamadas por `plan_room`)
| Cômodo | limpo (0) | `long` 1000 | `stacked` 1000 | `rotated` 1000 | `intersection` limpo → pior (1000) | `buffer` limpo → pior |
|---|---|---|---|---|---|---|
| BANHO 01 | 1,036 | 3,498 | 3,260 | 3,373 | 10 384 → 122 384 | 11 301 → 21 301 |
| BANHO 02 | 1,162 | 3,576 | 2,715 | 2,953 | 9 940 → 121 940 | 11 564 → 21 564 |
| LAVABO | 0,991 | 2,673 | 2,539 | 2,789 | 6 462 → 118 462 | 11 032 → 21 032 |

(limpo = linha de base do README de obstáculos, `obstacles=0`.) Pico de memória do processo: 52–60 MB em todos os 27 casos.

## Leitura (o que os dados sustentam — e o que não)
1. **Pior caso medido ≈ 3,3× o tempo limpo a 1000 obstáculos adversariais** (≈ 2,7 a 3,6 s contra ≈ 1 s), crescendo de forma aproximadamente **linear** em n (10 → 100 → 1000: +≈ 0,3 s, +≈ 2,3 s); não apareceu comportamento quadrático até 1000.
2. Diferente dos obstáculos benignos (que só adicionam `intersection`), os adversariais também aumentam `buffer` (≈ 11 mil → 16–21 mil): cada obstáculo dentro do cômodo entra na avaliação de todos os candidatos.
3. **`stacked` e `rotated` dão contagens idênticas** de `intersection`/`buffer` em todos os cômodos: o custo depende de *quantas* caixas entram na vizinhança, não da forma delas. Já `long` faz menos chamadas mas é a mais lenta no BANHO 01/02 — as barras são geometrias grandes (cada interseção custa mais).
4. Em nenhum caso o status mudou de `UNKNOWN` (teto de 10 candidatos de 1 681–6 724): este benchmark mede **custo**, não viabilidade.
5. **Não medido:** mais de 1000 obstáculos; outras máquinas; gates fora de `plan_room`; mais de 10 candidatos combinados com obstáculos adversariais (custo ≈ produto dos dois).
6. **Sem meta nem budget.** Qualquer otimização do solver (`tools/rooms/shared/spatial_solver/`) é caminho crítico e exige a revisão independente (#524) e ADR antes de OR-Tools/scipy.

## Defeito achado e corrigido no próprio gerador (registro honesto)
A primeira versão de `long` espaçava as barras de 2 em 2 pol. a partir da borda da vizinhança: com n pequeno nenhuma barra chegava ao cômodo (o teste `test_long_bars_span_the_whole_neighborhood_and_cross_the_cell` pegou). Agora as barras são distribuídas por toda a extensão; os dados acima são da versão corrigida.
