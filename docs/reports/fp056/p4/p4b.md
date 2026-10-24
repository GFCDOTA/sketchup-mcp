# FP-056 P4b — apoio por módulo: FLOOR e WALL_MOUNTED (2026-10-24)

Continua a P4a (`README.md`, retrato datado). `tools/validation/support_check.py::check_modules` julga cada **módulo** (grupo do
`.skp`) segundo o modo declarado em `MODULE_SUPPORT`; o mesmo `EPS_DEPTH` do validador do construído, nenhum limiar novo.
- `FLOOR`: ponto mais baixo do módulo a ≤ `EPS_DEPTH` do piso (`NOT_ON_FLOOR`).
- `WALL_MOUNTED`: a pegada toca a massa de parede **ou a pele de parede** (`Pele`) do mesmo cômodo (`NOT_IN_CONTACT`, com a folga
  medida). Os espelhos dos banhos estavam a 3,6 cm da massa de parede, mas apoiados na pele: não são defeito.
- `CEILING` / `SUSPENDED_INTENTIONAL`: declarados e **não avaliados** (falta medir forro e fixação); listados, nunca PASS.
- Módulo sem declaração: lista `undeclared` (BLOCKED na spec). Hoje 26 de 61: Bancada, Box, Enxoval, Pele, Vaso (banhos), Condensadora,
  Criado-mudo, TV, cooktop/countertop/sink/fridge/decor da cozinha. Cada um pede uma decisão de modo (ex.: Criado-mudo a 0,30 m do
  piso é suspenso: `WALL_MOUNTED`?), por isso não foram declarados por dedução.

## Medido na planta_74 (`develop@716c8fd`)
30 módulos julgados, 7 achados `NOT_IN_CONTACT` (defeito de apoio conhecido, não corrigido aqui):

| Cômodo | Módulo | Distância da parede |
|---|---|---|
| A.S. | Coifa | 75,3 cm |
| A.S. | Prateleira serviço | 34,7 cm |
| Cozinha | hood | 6,3 cm |
| Cozinha | upper_cabinet_02 | 1,7 cm |
| Sala | Painel TV | 1,1 cm |
| Suíte 01 / 02 | Painel cabeceira | 0,5 cm |

A Churrasqueira da A.S. também está a 75,3 cm da parede mais próxima (e a Coifa, fixada nela): a posição "alvenaria cega" do
planejador da A.S. precisa ser conferida (Issue de investigação no backlog). O retrato está travado em
`tests/test_fp056_p4_support_check.py`: defeito novo ou pior reprova; corrigido sai da tabela. Sem SketchUp real (P6).
