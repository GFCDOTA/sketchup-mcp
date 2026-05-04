# Plano — integração do fluxo SVG como ingest paralelo no plan-extract-v2

## Context

O PoC v5 provou que o fluxo SVG entrega resultado superior ao raster (15 rooms + 0 lixo vs 48 polys + 58% lixo) com ~300 LOC de Python puro. Decisão: SVG vira caminho primário de ingest no `plan-extract-v2`, raster vira fallback legado.

Esta integração traz o fluxo do `D:\Claude\svg_poc\` pra dentro do repositório real, preservando 100% do pipeline raster existente e reaproveitando todo o hardening downstream (classify, openings, topology, model, debug).

## Premissas não negociáveis (de CLAUDE.md §2)

- Não inventar rooms/walls; `rooms=[]` é observação válida, não falha.
- Não mascarar falhas; warnings são visíveis.
- Não acoplar a PDFs específicos (nada de hardcoded para `planta_74*`).
- Debug artifacts obrigatórios: `debug_walls.svg`, `debug_junctions.svg`, `connectivity_report.json`, `overlay_audited.png`, `observed_model.json`.
- Contrato `observed_model.json` estável — mesmo shape para input raster e SVG.

## Arquitetura da integração

Pipeline atual (raster, `run_pdf_pipeline`):
```
PDF bytes
  → ingest_pdf (rasteriza)
  → _extract_with_roi_from_document (Hough + morph + classify)
  → classify_walls (dedup, merge colinear)
  → detect_openings (bridge + extend L-corner)
  → build_topology (split + polygonize)
  → observed_model + debug artifacts
```

Novo pipeline (SVG, `run_svg_pipeline`):
```
SVG bytes
  → ingest_svg (parse + transform flatten + stroke/width filter)
  → *SKIP extract, SKIP classify* (walls já são vetoriais e limpas)
  → detect_openings (mesmo detector, thresholds escalados por thickness)
  → build_topology (mesmo código) + filtro is_wall_interior (novo, opt-in)
  → observed_model + debug artifacts (mesmo shape, source_type="svg")
```

**Ponto-chave**: os dois pipelines convergem em `detect_openings → build_topology → write_artifacts`. Toda a nova superfície de código é upstream dessa junção.

## Mudanças nos arquivos do repo

### Novos arquivos

1. **`ingest/svg_service.py`** — parser SVG → `list[Wall]`
   - Porta 180 LOC de `D:\Claude\svg_poc\svg_rooms_v5.py` (funções `parse_transform`, `parse_style`, `parse_d`, `walk`, `extract_walls_as_objects`)
   - Assinatura pública: `ingest_svg(svg_bytes: bytes, filename: str) -> IngestedSvgDocument`
   - Retorna `IngestedSvgDocument` análogo ao `IngestedDocument` atual, com campo extra `walls: list[Wall]` já populado (sem passar por extract/classify)
   - **Reuso**: `model.types.Wall` existente; não criar novo tipo.

2. **`topology/wall_interior_filter.py`** — filtro v5
   - Uma função única: `is_wall_interior(polygon, wall_thickness, margin=1.3) -> bool`
   - 12 LOC. Copia literal do v5.
   - Aplicado dentro de `build_topology` sob flag `filter_wall_interior: bool = False` (opt-in; default preserva comportamento atual no caminho raster).

3. **`tests/test_ingest_svg.py`** — cobertura do parser
   - Transforms aninhados (matrix, scale, translate, rotate)
   - Filter stroke/stroke-width
   - Skip curve paths
   - SVG malformado → erro claro
   - Fixture: `tests/fixtures/svg/minimal_room.svg` (3-4 paredes, 1 porta)

4. **`tests/test_svg_pipeline.py`** — smoke test end-to-end
   - Input: fixture SVG → `run_svg_pipeline` → assertions em walls, rooms, openings counts
   - Deve rodar sob 3s (sem PDF real)

5. **`tests/fixtures/svg/minimal_room.svg`** — SVG sintético 200-300 bytes
   - Usado por ambos os testes acima

### Arquivos modificados

1. **`model/pipeline.py`**
   - Adicionar função `run_svg_pipeline(svg_bytes, filename, output_dir, peitoris=None) -> PipelineResult`
   - Reusa `_run_pipeline` existente (linha 116+); a diferença é que para SVG o `candidates` é substituído por walls já prontos que pulam `classify_walls`
   - Alternativa cirúrgica: introduzir novo `_run_pipeline_from_walls(walls, ...)` que faz o mesmo que `_run_pipeline` mas recebe `walls: list[Wall]` direto em vez de `candidates: list[WallCandidate]`, pulando `classify_walls`. O `_run_pipeline` existente permanece para o caminho raster.
   - Novo `_build_svg_source(svg_bytes, filename)` análogo a `_build_pdf_source`, com `source_type="svg"`

2. **`main.py`**
   - `cmd_extract` detecta extensão: `.pdf` → `run_pdf_pipeline`, `.svg` → `run_svg_pipeline`
   - Sem breaking change: comando e flags continuam iguais

3. **`api/app.py`**
   - Ajustar validação do endpoint `/extract` para aceitar `.pdf` ou `.svg` (detecta por filename extension ou content-type)
   - Dispatch pra `run_pdf_pipeline` ou `run_svg_pipeline`
   - OU, conservador: novo endpoint `POST /extract-svg`. Preferência pela detecção no endpoint único, é mais simples pro consumidor.

4. **`openings/service.py`** (pequeno patch, opcional nesta fase)
   - Tornar thresholds configuráveis via kwarg único `wall_thickness: float | None = None`
   - Quando `None`, usa constantes atuais (preserva comportamento raster)
   - Quando fornecido, deriva thresholds como no fork `openings_svg.py` (`_Thresholds.from_thickness`)
   - Com esse patch, o fork `openings_svg.py` pode ser descartado — SVG path chama `openings/service.py` diretamente passando `wall_thickness=median_stroke_width`
   - **Se preferir evitar este patch no primeiro round**, o SVG path importa uma versão local do detector temporariamente. Recomendo fazer o patch agora porque é trivial (10 linhas) e elimina duplicação.

### Arquivos intocados (não mexer nesta fase)

- `extract/`, `classify/`, `roi/`, `ingest/service.py` (caminho raster permanece exatamente como está)
- `debug/`, `model/builder.py`, `model/types.py` (shape do output preservado)
- `runs/overpoly_audit/over_polygon_categorized.png` (histórico raster — **proibido** sobrescrever)
- `docs/*.md`, `PROMPT-*.md`, `CLAUDE.md` (documentação do Renan, respeitada)
- Os 8 commits locais não-pushed de Felipe (nodeclass, PROJECT_STATE, feat(topology) etc.) — integração feita em branch nova, sem rebase sobre esses
- Worktree `D:\Claude\svg_poc\main-worktree\` (permanece read-only)

## Decisões de design resolvidas

1. **SVG produz `Wall` direto, não `WallCandidate`**. Motivo: SVG vem vetorial e sem duplicatas; rodar `classify_walls` seria desperdício e pode remover geometria válida. O pipeline só precisa de dedup quando a entrada é rasterizada (Hough gera múltiplas detecções do mesmo segmento).

2. **Endpoint único `/extract`, detecção por extensão**. Menos superfície pro consumidor. Segue o padrão CLI atual.

3. **`is_wall_interior` é opt-in**. Default `False` preserva raster. SVG path ativa por padrão (`filter_wall_interior=True`). Cada caller decide.

4. **`wall_thickness` para SVG é derivada da mediana do `stroke-width` dos paths filtrados** (no PoC foi 6.25). Não hardcodar. Logar no console do extrator.

5. **`wall_interior_filter` roda em `build_topology` após `polygonize`**, não em `_run_pipeline`. Motivo: é um passo topológico puro; ficar em `topology/` respeita a fronteira arquitetural do projeto.

## Fluxo de dados (pipeline SVG, detalhado)

```
svg_bytes, filename
  ↓
ingest_svg() → IngestedSvgDocument(walls: list[Wall], page_count=1,
                                    bounds, stroke_width_median=6.25)
  ↓
detect_openings(walls, wall_thickness=6.25)
  ↓ (returns extended walls + openings list)
build_topology(walls, filter_wall_interior=True)
  ↓ (returns split_walls, junctions, rooms, connectivity_report)
_run_pipeline_from_walls(walls, openings, topology_result, source, output_dir)
  ↓
observed_model.json + debug_walls.svg + debug_junctions.svg +
connectivity_report.json + overlay_audited.png
```

## Plano de implementação — ordem de passos

**Branch**: `feat/svg-ingest` (no remote), partindo de `origin/main`. **Não** sobre o local atrasado.

### Passo 1 — preparar worktree de trabalho
- `git worktree add D:/Claude/svg_poc/feat-svg-ingest -b feat/svg-ingest origin/main`
- Isolamento do HEAD local do Felipe.

### Passo 2 — portar parser SVG para `ingest/svg_service.py`
- Criar arquivo, copiar funções do v5, adaptar imports (`model.types.Wall`)
- Função pública `ingest_svg()` retornando `IngestedSvgDocument` (novo dataclass)

### Passo 3 — patch `openings/service.py` para thresholds configuráveis
- Adicionar `wall_thickness: float | None = None` kwarg
- Manter constantes atuais como default quando kwarg é `None`
- Rodar tests existentes para garantir zero regressão

### Passo 4 — criar `topology/wall_interior_filter.py`
- Função `is_wall_interior()` (12 LOC)
- Modificar `build_topology()` pra aceitar `filter_wall_interior: bool = False` e aplicar após polygonize

### Passo 5 — adicionar `run_svg_pipeline` em `model/pipeline.py`
- Introduzir `_run_pipeline_from_walls(walls, ...)` que pula classify
- `run_svg_pipeline` = `ingest_svg` + `_run_pipeline_from_walls` com `filter_wall_interior=True`

### Passo 6 — dispatch em `main.py` e `api/app.py`
- CLI: `if pdf_path.suffix.lower() == ".svg": run_svg_pipeline else: run_pdf_pipeline`
- API: extrair `.endswith((".pdf", ".svg"))`, dispatch similar

### Passo 7 — testes
- `tests/fixtures/svg/minimal_room.svg` (fixture sintética)
- `tests/test_ingest_svg.py` (unit)
- `tests/test_svg_pipeline.py` (integration, smoke)
- `pytest` verde localmente

### Passo 8 — rodar em `planta_74m2.pdf` convertido + no SVG do Felipe
- Gerar artefatos em `runs/svg_planta74/` para inspeção
- **Não** escrever em `runs/overpoly_audit/`
- Comparar lado-a-lado com `runs/planta_74/` existente (raster)

### Passo 9 — PR contra `origin/main`
- Título: `feat(ingest): SVG ingest as primary path, raster as fallback`
- Descrição inclui: PNGs comparativos (runs/svg_planta74 vs runs/planta_74), métricas, link pro PoC original
- Não mergear direto; aguardar review (Felipe e/ou Renan)

## Plano de validação

### Testes automatizados
- `pytest tests/test_ingest_svg.py` — passa
- `pytest tests/test_svg_pipeline.py` — passa
- `pytest tests/` full suite — sem regressão no caminho raster

### Validação manual (obrigatória, §10 de CLAUDE.md)
1. Rodar `python main.py extract Anexo-1...svg --out runs/svg_planta74`
2. Abrir `runs/svg_planta74/observed_model.json` e verificar:
   - `source.source_type == "svg"`
   - `walls` tem ~400 entradas (vs 94 no raster — SVG captura mais detalhe, é esperado)
   - `rooms` tem ~15 entradas (meta: 10-15 para 74m²)
   - `openings` tem 30-40 entradas (ainda alto, mas aceitável por ora)
   - `warnings` não contém `rooms_not_detected`
3. Abrir `runs/svg_planta74/debug_walls.svg` e `overlay_audited.png` — verificar visualmente:
   - Perímetro fechado
   - 15 rooms coloridos e separados
   - Zero sliver/triangle visível
4. Rodar `python main.py extract planta_74.pdf --out runs/raster_planta74_ctrl` — caminho raster **inalterado**, saída igual à atual

### Métricas alvo
| | raster atual | SVG alvo |
|---|---:|---:|
| walls | 94 | ~400 |
| rooms | 14 | ≥ 10, ≤ 20 |
| slivers/triangles em rooms | 28 | 0 |
| orphan_component_count | 7 | ≤ 3 |
| `rooms_not_detected` warning | ausente | ausente |
| pipeline wall-clock | ~3s | ≤ 2s |

### Artefatos visuais a publicar
- `runs/svg_planta74/overlay_audited.png` — novo baseline visual SVG
- `runs/svg_planta74/debug_walls.svg`
- **Não** renomear nem sobrescrever `runs/overpoly_audit/over_polygon_categorized.png`

## Rollback

Abandonar a integração se:
1. Raster pipeline regride em qualquer planta baseline (`planta_74`, `p10`, `p11`, `p12`) — `pytest` vermelho é bloqueante
2. SVG pipeline produz `rooms_not_detected` em `planta_74m2` (algo quebrou na conversão)
3. Observed_model.json muda shape no caminho raster (breaking change)
4. `legitimate < 10` no SVG planta_74 (pior que v5 isolado — sinal que porte introduziu bug)

Rollback = branch deletada, nada mergeado. Local do Felipe intocado. PoC em `D:\Claude\svg_poc\` continua existindo como artefato de prova.

## Explicitly out of scope (não fazer nesta fase)

- Detector de portas mais inteligente (reduzir 38 → 10 openings) — tema de v6, não-bloqueante
- Centerline collapse upstream (v4 rejeitado por enquanto)
- Ruby/SketchUp bridge
- Suporte a SVG multi-página (1 página por arquivo por enquanto)
- Parametrizar `margin` do `is_wall_interior` via CLI/config
- Migrar raster pipeline pra usar `is_wall_interior` (mudança separada se desejada)
- Deprecar raster — só rebaixar mentalmente, código continua vivo e testado

## Arquivos do plano

- **Novos**: `ingest/svg_service.py`, `topology/wall_interior_filter.py`, `tests/test_ingest_svg.py`, `tests/test_svg_pipeline.py`, `tests/fixtures/svg/minimal_room.svg`
- **Modificados**: `model/pipeline.py`, `main.py`, `api/app.py`, `openings/service.py` (patch threshold-configurável)
- **Intocados**: `extract/`, `classify/`, `roi/`, `ingest/service.py`, `debug/`, `model/types.py`, `runs/overpoly_audit/*`, docs, PROMPT-*
- **Worktree novo**: `D:\Claude\svg_poc\feat-svg-ingest\` (branch `feat/svg-ingest`)
- **Worktree existente**: `D:\Claude\svg_poc\main-worktree\` (read-only, preservado)
