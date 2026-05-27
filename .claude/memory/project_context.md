# Project context — sketchup-mcp

Contexto estável. Não é estado-do-dia (esse vai em `current_state.md`).

## Identidade

Repo `sketchup-mcp` (privado, owner `GFCDOTA`). Pipeline mínimo
pra gerar um `.skp` SketchUp a partir de um consensus JSON que
descreve walls + openings + rooms + soft barriers em PDF-points.

## Pipeline

```
consensus.json (PDF-points coords)
   │
   ▼
[Python] tools/build_plan_shell_skp.py
   - shapely.unary_union nas wall footprints
   - canonicaliza corners (no notches / no slivers)
   - 2D carve full-height openings (doors, passages, porta-vidro)
   - emite window apertures separadas pra 3D post-extrude carve
   │
   ▼
_shell_polygon.json
   │
   ▼
[Ruby/SU] tools/build_plan_shell_skp.rb (autorun plugin)
   - extrude wall shell até ceiling height
   - 3D carve windows preservando peitoril + verga
   - floor + window-glass groups separados
   │
   ▼
model.skp + model_iso.png + model_top.png + geometry_report.json
```

## Fixtures canônicas

| Fixture | Path | Papel |
|---|---|---|
| `quadrado` | `fixtures/quadrado/consensus_with_window.json` | Smoke gate micro-fixture. Prova do paradigma wall-shell/window. Não é produto final. |
| `planta_74` | `fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json` | Apartamento real, 35 walls. PDF fonte em `planta_74.pdf` no raiz. |

## Coordenadas

Tudo em **PDF points** (`pts`). Conversão pra metros sai de uma
âncora física conhecida no PDF — tipicamente `wall_thickness_pts /
0.19` (parede estrutural ≈ 19 cm). Nunca usar `0.0254 / 72` default
(ver `memory/lessons_learned.md`).

## Componentes externos

| Componente | Caminho | Versão |
|---|---|---|
| SketchUp | `C:\Program Files\SketchUp\SketchUp 2026\SketchUp\SketchUp.exe` | 2026 |
| Ruby exporter plugin | `%APPDATA%\SketchUp\SketchUp 2026\SketchUp\Plugins\` | autorun |
| Python | 3.11+ | dev install via `pip install -e ".[dev]"` |

## Não pertence ao escopo

Estes itens NÃO fazem parte do produto atual e foram podados em PR
#184 e nas sequenciais de cleanup:

- Pipelines V3–V6.x antigas (extração vetorial / raster Hough)
- Dashboard / Cockpit antigo (FastAPI fusion server em `exp-dedup`)
- Dedup/consume_consensus.rb (V6.2 two-repos)
- Vendor CubiCasa5K (peso ML não-vendorizado)

Se algo dessa lista aparecer no working tree, é sinal de que foi
ressuscitado por engano — verificar com o humano antes de seguir.

## TODO — validação ao vivo

- [ ] Confirmar `pyproject.toml` deps ainda batem com `shapely`, `pypdfium2`, `Pillow`
- [ ] Confirmar que `tools/quadrado/` e `tools/build_plan_shell_skp.{py,rb}` continuam sendo os únicos entry points produtivos sob `tools/`
