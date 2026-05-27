# Fidelity gate — sketchup-mcp

Define o que conta como "fiel" entre PDF, consensus e `.skp`.

> **Nota:** este spec é descritivo. Implementação ao vivo está em
> `geometry_report.json` produzido por `build_plan_shell_skp.py` +
> contracts em `tests/`. Discrepâncias entre este doc e a
> implementação seguem a implementação — abrir PR pra realinhar
> texto.

## Dimensões de fidelidade

### 1. Wall fidelity

Todas walls da consensus aparecem como mass extrudada no `.skp`.

- Sem stubs residuais (PR #192/#193 FP-026)
- Sem notches / slivers no shell polygon
- Junction-aware endpoint extension aplicada

**Falha** = wall sumiu ou virou stub. **WARN** = wall presente
mas com geometria degenerada (e.g. <ε comprimento).

### 2. Room fidelity

Closed cells emergem do `polygonize` do shell. Labels de planta
de vendas (semantic ambients) são metadata, não fonte de verdade.

- **OK** = N closed cells == N semantic ambients
- **WARN** = N cells < N ambients porque cells fundem múltiplos
  ambientes open-plan (ex.: planta_74 r001/r002). Honesto. Ver
  `memory/lessons_learned.md` #4.
- **FAIL** = cell esperado pelo wall geometry não fecha (parede
  presente mas cell aberto)

### 3. Opening fidelity

| `kind_v5` | Routing | Geometria |
|---|---|---|
| `interior_door` | 2D | Full-height carve |
| `interior_passage` | 2D | Full-height carve |
| `glazed_balcony` | 2D | Full-height carve (porta-vidro) |
| `window` | 3D | Post-extrude aperture, preserva peitoril + verga |

Soft barriers (peitoril, grade) NÃO viram parede.
`geometry_origin = wall_gap` deixa gap em paz; outros
(`svg_arc`, `svg_segments`, `human_annotation`) carvam.

### 4. Semantic labels

Label de ambient sobrevive pra audit trail. Cells fundidos
mantêm labels com `|`:

```
r001: A.S. | TERRACO SOCIAL | TERRACO TECNICO
```

Não normalizar / pluralizar / traduzir labels.

### 5. Global visual fidelity

Side-by-side PDF vs SKP é critério qualitativo, julgado por humano
em review. Render PNG ajuda mas não substitui o `.skp` aberto no SU.

## Evidências obrigatórias

Pra declarar sucesso canônico em task de geração SKP:

1. `.skp` versionado em `artifacts/<plant>/<plant>.skp`
2. Render top em `artifacts/<plant>/<plant>_top.png`
3. Render iso em `artifacts/<plant>/<plant>_iso.png`
4. Side-by-side em `artifacts/<plant>/side_by_side_pdf_vs_skp.png`
5. Report JSON em `artifacts/<plant>/geometry_report.json`
6. Contract tests verdes (`python -m pytest tests/`)

Falta 1+ dos 6 = não declarar sucesso. Status é **incompleto**.

## Status gates

| Gate | Origem | Critério OK |
|---|---|---|
| `wall_fidelity` | `geometry_report.json` | TODO — confirmar campo exato |
| `room_fidelity` | `geometry_report.json` | TODO — confirmar campo exato |
| `opening_fidelity` | `geometry_report.json` | TODO — confirmar campo exato |
| `contract_tests` | `pytest tests/` | exit 0 |

## TODO — validar contra repo

- [ ] Ler `artifacts/planta_74/geometry_report.json` e listar
      campos exatos do schema atual
- [ ] Confirmar que o gate self-check está em
      `tools/build_plan_shell_skp.py` ou em outro arquivo
- [ ] Adicionar exemplos numéricos de OK / WARN / FAIL
