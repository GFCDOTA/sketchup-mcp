# FP-056 P4a — apoio físico declarado (contrato 2), validador na proposta (2026-10-24)

## O que entrou
`tools/validation/support_check.py`: cada tipo de peça (`kind`) declara o modo de apoio em `DECLARED`; nesta fatia só
`ON_SURFACE` (bandeja, sabonete, copo). A checagem usa o mesmo `EPS_DEPTH` do validador do construído e roda sobre as
caixas da proposta (antes do SketchUp):
- `FLOATING`: base acima do topo do suporte declarado por mais de `EPS_DEPTH` (medida em `gap_m`);
- `NO_SUPPORT`: nenhum suporte declarado sob a pegada (suporte nunca é deduzido por proximidade);
- `OVERHANG`: projeção fora do topo do suporte.
Modos `FLOOR`, `WALL_MOUNTED`, `CEILING` e `SUSPENDED_INTENTIONAL` ficam **não avaliados** (não viram PASS). Nenhuma
geometria, limiar ou layout foi alterado.

## Medido na planta_74 (`develop@b60dc14`, caixas do `collect_boxes`)
| Cômodo | Peça | Folga | Causa |
|---|---|---|---|
| LAVABO | `kb_bandeja` | 1,98 cm | tampo termina em 0,88 m; a bandeja começa em 0,90 m (confirma o achado de origem de 2,0 cm) |
| BANHO 01 | `kb_sabonete` | 3,48 cm | idem: sabonete em 0,915 m sem bandeja |
| BANHO 02 | `kb_sabonete` | 3,48 cm | idem |

Os dois sabonetes são **achado novo** desta fatia (o baseline FP-055 P4 não tinha checagem de apoio). Mesma causa-raiz R4:
o enxoval assume tampo a 0,90 m. A correção muda a aparência (rebaixar 2–3,5 cm ou subir o tampo), então fica como decisão
para o Felipe; **nada foi corrigido aqui**. O retrato está travado em `tests/test_fp056_p4_support_check.py`: defeito novo
ou pior reprova; corrigido sai da tabela.

## Limites
Validação em caixas (gêmeo), não no modelo construído: a prova no SketchUp real entra com a geração completa (FP-056 P6).
Declaração por `kind` (tabela), não por instância; peças sem declaração não são julgadas (contadas só quando declaradas).
