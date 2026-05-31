# Fidelity gate — sketchup-mcp

Define o que conta como "fiel" entre PDF, consensus e `.skp`.

> Este spec foi alinhado em 2026-05-27 com o schema real do
> `geometry_report.json` produzido por
> `tools/build_plan_shell_skp.py`. Se a implementação mudar,
> seguir a implementação — abrir PR pra realinhar texto.

## Dois eixos: gate machine-readable vs julgamento humano

O sistema atual tem **dois eixos** separados de fidelidade. Não
confundir um com o outro:

### Eixo 1 — `gates_self_check` (machine-readable, no report)

`geometry_report.json` carrega o bloco `gates_self_check` com **4
checks booleanos** de integridade estrutural do SKP gerado:

| Field | OK quando |
|---|---|
| `plan_shell_group_exists` | `PlanShell_Group` existe no SKP |
| `wall_shell_is_single_group` | shell é UM group (não fragmentado) |
| `floors_separated_from_walls` | floor groups são separados, não fundidos com walls |
| `default_material_faces_zero` | nenhuma face com material default (= todas pintadas com `plan_*`) |

Estes 4 são objetivos: passam ou não passam. Falha em qualquer um
= **FAIL canônico**, build não promove pra `artifacts/`.

### Eixo 2 — Fidelidade arquitetônica (julgamento humano, no README)

Não há campo machine-readable pra "wall_fidelity / room_fidelity
/ opening_fidelity" hoje. Esses julgamentos vivem no
`artifacts/<plant>/README.md` como provenance prose, com
justificativa por exceção (e.g. `room_fidelity = WARN` por cells
open-plan fundidos — ver
[`memory/lessons_learned.md`](../memory/lessons_learned.md) #4).

## Campos relevantes do `geometry_report.json`

Schema atual (`schema_version: "1.0.0"`):

| Top-level key | Propósito |
|---|---|
| `tool` | sempre `build_plan_shell_skp` |
| `consensus_path` | input fixture |
| `skp_path` | onde o build caiu (geralmente `runs/<plant>/...`) |
| `plan_shell` | stats do wall shell group (faces, edges, sub_groups, etc.) |
| `floor_groups` | per-room floor records (areas em in² + m²) |
| `soft_barrier_groups` | parapeitos / grades — `count`, `skipped_count`, `skip_reasons[]` |
| `totals` | top-level group / face / edge totals |
| `groups_diagnostic[]` | per-group bbox + height + footprint |
| `shell_stats_from_python` | input/output walls, openings carved, endpoints junction-aware, slivers, etc. |
| `gates_self_check` | os 4 booleans do Eixo 1 |

## Critérios qualitativos por dimensão (Eixo 2)

Estes são heurísticos pro humano em review. **Não são campos do
JSON** — vão como prose no README de provenance.

### Wall fidelity

- **OK** = todas walls da consensus extrudaram, sem stubs
  residuais (PR #192/#193 FP-026), sem notches / slivers
- **WARN** = wall presente mas com geometria degenerada (<ε
  comprimento)
- **FAIL** = wall sumiu

### Room fidelity

- **OK** = N cells fechadas == N ambientes semânticos
- **WARN** = N cells < N ambientes porque cells fundem ambientes
  open-plan (ex.: planta_74 r001/r002). Honesto.
- **FAIL** = cell esperado pelo wall geometry não fecha

### Opening fidelity

| `kind_v5` | Routing | Geometria |
|---|---|---|
| `interior_door` / `interior_passage` / `glazed_balcony` | 2D | Full-height carve |
| `window` | 3D | Post-extrude aperture, preserva peitoril + verga |

`geometry_origin = wall_gap` deixa em paz; outros (`svg_arc`,
`svg_segments`, `human_annotation`) carvam.

Soft barriers (peitoril, grade) **NÃO** viram parede cheia.

## Evidências obrigatórias

Pra declarar sucesso canônico em task de geração SKP:

1. `.skp` versionado em `artifacts/<plant>/<plant>.skp`
2. Render top em `artifacts/<plant>/<plant>_top.png`
3. Render iso em `artifacts/<plant>/<plant>_iso.png`
4. Side-by-side em `artifacts/<plant>/side_by_side_pdf_vs_skp.png`
5. Report JSON em `artifacts/<plant>/geometry_report.json` com os
   4 `gates_self_check` em `true`
6. Contract suite verde (`python -m pytest tests/`)
7. README de provenance com julgamento humano do Eixo 2 (wall /
   room / opening fidelity como prose + justificativa pra WARN)

Falta 1+ dos 7 = não declarar sucesso. Status é **incompleto**.

## Exemplo numérico — `planta_74` (snapshot 2026-05-27)

| Métrica | Valor | Status |
|---|---|---|
| `gates_self_check.plan_shell_group_exists` | `true` | ✅ |
| `gates_self_check.wall_shell_is_single_group` | `true` | ✅ |
| `gates_self_check.floors_separated_from_walls` | `true` | ✅ |
| `gates_self_check.default_material_faces_zero` | `true` | ✅ |
| Wall fidelity (Eixo 2, prose) | sem stubs após FP-026 | OK |
| Room fidelity (Eixo 2, prose) | 8 cells vs 11 ambientes | WARN (justificado) |
| Opening fidelity (Eixo 2, prose) | 8 carved (5 door + 3 window 3D + 1 glazed balcony) de 12 | OK |
| `shell_stats_from_python.input_walls` | 35 | — |
| `shell_stats_from_python.window_apertures_3d` | 4 | — |
| `shell_stats_from_python.slivers_removed` | 0 | OK |

## TODO

- [ ] Decidir se Eixo 2 (room/wall/opening fidelity) merece
      campos machine-readable no `geometry_report.json` schema
      1.1.0 — ou se prose no README é suficiente
- [ ] Se sim, definir critério algorítmico (e.g. room_fidelity =
      WARN se `floor_groups.count < ambients_label_count`)
