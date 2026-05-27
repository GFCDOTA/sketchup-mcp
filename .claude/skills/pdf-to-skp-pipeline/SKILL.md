---
name: pdf-to-skp-pipeline
description: Use when a task touches the PDF → consensus.json → .skp pipeline of sketchup-mcp. Triggers on `consensus.json`, `build_plan_shell_skp.{py,rb}`, wall/opening/room extraction, fixtures/quadrado or fixtures/planta_74, `_shell_polygon.json`, kind_v5 routing, peitoril/verga handling, or any phrase like "gerar SKP", "rodar pipeline", "build do plant", "consensus do <plant>".
---

# pdf-to-skp-pipeline

Skill operacional pro pipeline principal do repo.

## Quando usar

- Mudança em `tools/build_plan_shell_skp.py` ou `.rb`
- Nova fixture sob `fixtures/<plant>/`
- Debug de `_shell_polygon.json`
- Ajuste em `kind_v5` routing (window vs door vs porta-vidro)
- Tratamento de soft barriers (peitoril, grade)
- Geração / regeneração de `.skp` canônico

## Fluxo

```
consensus.json (PDF-points)
   ↓ tools/build_plan_shell_skp.py
_shell_polygon.json (intermediate, em runs/)
   ↓ tools/build_plan_shell_skp.rb (Ruby/SU autorun plugin)
<plant>.skp + iso.png + top.png + geometry_report.json (em runs/)
   ↓ promotion (manual)
artifacts/<plant>/<plant>.skp + sidecars
```

## Comandos chave

### Build local (default, SU stays open)

```bash
python -m tools.build_plan_shell_skp \
  fixtures/quadrado/consensus_with_window.json \
  --out runs/quadrado/quadrado.skp
```

### Render

```bash
python tools/quadrado/render_view.py \
  runs/quadrado/quadrado.skp \
  --out runs/quadrado/render.png
```

### Plant real

```bash
python -m tools.build_plan_shell_skp \
  fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json \
  --out runs/planta_74/model.skp
```

### Contract suite

```bash
python -m pytest tests/ -q
```

## Cuidados

### Raster vs vetor

PDF pode ser raster (sem geometria extraível). Não usar
heurística raster pra fabricar paredes em PDF vetorial. Ver
`memory/lessons_learned.md` #7.

### `--mode headless` proibido em dev local

Default é `interactive` (SU fica aberto). `--mode headless` é só
pra CI. Cravado em PR #186.

### `kind_v5` routing

| `kind_v5` | Path |
|---|---|
| `interior_door` / `interior_passage` / `glazed_balcony` | 2D full-height carve |
| `window` | 3D post-extrude aperture (preserva peitoril + verga) |

`geometry_origin = wall_gap` deixa em paz; resto carva.

### NUNCA mutar fixture canônica sem aprovação humana

`fixtures/quadrado/`, `fixtures/planta_74/` → Hard Rule #3.

## Validações mínimas

Pra qualquer mudança nesta skill:

1. Contract suite verde: `python -m pytest tests/ -q`
2. Quadrado canonical render bate com `docs/specs/_assets/quadrado_canonical_success_render.png`
3. Se mudou builder: regerar SKP de `planta_74` e comparar
   side-by-side
4. Se mudou contract: spec atualizada em `docs/specs/FP-NNN_*.md`
5. Promotion se artifact mudou: copiar pra `artifacts/<plant>/`

## Skills relacionadas

- `fidelity-review/` — revisar SKP vs PDF
- `skp-artifact-management/` — promover runs/ → artifacts/
- `repo-governance/` — PR, branch, hygiene
