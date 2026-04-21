# PROMPT-NEXT-CLAUDE.md — handoff para o próximo Claude

**Última sessão:** 2026-04-21 (Felipe + Claude Opus 4.7 via Claude Code)
**Branch:** `feat/svg-ingest` (a partir de `origin/main`)
**Estado:** integração SVG fim-a-fim **funcionando**, próximo passo **planejado mas não executado**.

---

## 1. O que foi feito nesta sessão

### PoC local (fora do repo, em `D:\Claude\svg_poc\`)
- **v3**: SVG + `openings/service.py` forkado → 15 rooms legítimos, 0 slivers, 0 triangles, mas 22 artefatos (thin_strip + tiny) de parede dupla
- **v4**: tentativa de centerline collapse → rejeitada (fundiu sala+hall+cozinha num salão central)
- **v5**: v3 + filtro `is_wall_interior(poly, thickness, margin=1.3)` pós-diff → **15 rooms preservados, 0 artefatos**

### Integração no repo (esta branch)
Commit `4716071 feat(ingest): SVG ingest as primary path, raster as fallback`

Arquitetura:
```
PDF:  PDF bytes → ingest_pdf → extract → classify → detect_openings → build_topology → artifacts
SVG:  SVG bytes → ingest_svg →           SKIP     → detect_openings → build_topology → artifacts
                                                      (filter opt-in: is_wall_interior via build_topology)
```

Arquivos novos:
- `ingest/svg_service.py` — parser SVG (stroke/stroke-width filter + transform flatten); 292 LOC
- `topology/wall_interior_filter.py` — helper `is_wall_interior`; 20 LOC
- `tests/fixtures/svg/minimal_room.svg` — fixture sintética
- `tests/test_ingest_svg.py` — 8 tests
- `tests/test_svg_pipeline.py` — 3 tests (inclui `test_wall_interior_filter_preserves_real_room` como safety trap)

Arquivos modificados cirurgicamente (zero regressão raster):
- `openings/service.py` — `wall_thickness: float | None = None` kwarg (default None = raster behavior preservado)
- `topology/service.py` — `filter_wall_interior=False`, `wall_thickness=None` kwargs (default = raster preservado)
- `model/pipeline.py` — `run_svg_pipeline` + `_run_pipeline_from_walls`
- `main.py` — CLI dispatch por extensão
- `api/app.py` — `/extract` aceita PDF ou SVG
- `tests/test_cli.py` — atualizado error message (`PDF not found` → `input not found`)

### Testes
```
97 passed, 15 failed (todos pré-existentes, mesmo set que origin/main)
```

Os 15 failures são em `test_classify`, `test_orientation_balance`, `test_pair_merge`, `test_pipeline`, `test_text_filter`. Não foram introduzidos por este commit.

### Resultado empírico `planta_74m2.svg` vs `planta_74.pdf`

| | raster (`.pdf`) | SVG (`.svg`) |
|---|---:|---:|
| walls | 230 | 359 |
| rooms | 48 | 54 |
| junctions | 71 | 142 |
| openings | 71 | 68 |
| geometry_score | 0.25 | **1.00** |
| topology_score | 1.00 | 0.35 |
| warnings | `[]` | `[walls_disconnected]` |
| % lixo em rooms (visual) | ~58% (28 de 48) | ~0% estrutural |

---

## 2. Por que 54 rooms é mais do que os 15 do PoC v5

**Não é regressão.** É diferença de escopo.

- v5 usava `bbox.difference(wall_mass)` **com crop do main plan bbox** — descartava carimbo/legenda/mini-planta
- Pipeline real usa `shapely.polygonize(wall_lines)` — detecta **todo ciclo fechado** no SVG, incluindo cabeçalho, rodapé, mini-planta

Dos 54 rooms:
- **~20 reais** no miolo central do overlay (suíte, sala, cozinha, banheiros, área serviço)
- **~34 fora do escopo** (carimbo superior R9-R14, rodapé com tabela de metragem R1-R8, mini-planta R52-R54)

Visualmente no `runs/svg_planta74m2/overlay_audited.png` isso é óbvio.

---

## 3. Próximo passo PLANEJADO (não implementado)

Ver `docs/SVG-MAIN-PLAN-ISOLATION.md`.

**TL;DR:** adicionar um filtro `select_main_component(walls)` que roda **depois de detect_openings, antes de build_topology**, mantendo apenas as walls do componente conectado com maior bbox-area. Guard de fallback se dominância < 3×.

Meta: rooms 54 → 15-20. Zero regressão raster (filtro só no caminho SVG; raster tem `detect_architectural_roi` fazendo papel análogo).

Arquivos propostos:
- **Novo**: `topology/main_component_filter.py` (~60 LOC)
- **Novo**: `tests/test_main_component_filter.py` (4 tests)
- **Modificado**: 3 linhas em `model/pipeline.py::_run_pipeline_from_walls`

---

## 4. O que NÃO mexer

- `extract/`, `classify/`, `roi/`, `ingest/service.py`, `debug/`, `model/builder.py`, `model/types.py` — caminho raster preservado
- `runs/overpoly_audit/*` — histórico de auditoria do raster (preservado como evidência do problema antigo)
- Os 15 test failures pré-existentes — não são escopo deste trabalho
- PROMPT-FELIPE.md / PROMPT-RENAN.md — documentação de handoffs anteriores, respeitar

---

## 5. Como validar localmente

```bash
# Checkout da branch
git fetch origin feat/svg-ingest
git checkout feat/svg-ingest

# Rodar testes
python -m pytest tests/ -q  # esperado: 97 pass, 15 fail pré-existentes

# SVG pipeline
python main.py extract path/to/file.svg --out runs/svg_out

# PDF pipeline (raster, comportamento inalterado)
python main.py extract planta_74.pdf --out runs/raster_out

# Comparar
ls runs/svg_out/  # esperado: observed_model.json, debug_walls.svg, debug_junctions.svg, connectivity_report.json, overlay_audited.png
```

Se implementar o próximo passo (main-plan isolation), rodar novamente o SVG pipeline:
- `rooms` cai para ~15-20
- `warnings` fica vazio ou só notes
- `observed_model["metadata"]["main_component"]` aparece com o report

---

## 6. Contexto adicional

- Os **8 commits locais** do Felipe (nodeclass, PROJECT_STATE, feat(topology) etc.) **não** foram integrados nesta branch. Ficaram no main local dele. Decidir separadamente o destino deles.
- PoC em `D:\Claude\svg_poc\` (fora do repo) **permanece intacto** com v3/v4/v5 + comparações visuais + scripts. Pode ser consultado para debug ou evolução.
- O filtro `is_wall_interior` é opt-in (flag False por default). Raster não ativa; SVG ativa automaticamente. Se quiser aplicar ao raster no futuro, basta passar `filter_wall_interior=True, wall_thickness=...` no `build_topology`.

---

**Se você é o próximo Claude lendo isto**: leia `docs/SVG-MAIN-PLAN-ISOLATION.md` e siga a seção 6 (Plano de implementação). Felipe já autorizou a estratégia; faltou só executar.
