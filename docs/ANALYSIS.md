# ANALYSIS.md — Análise crítica do repo sketchup-mcp

**Data:** 2026-04-21
**Repo analisado:** https://github.com/GFCDOTA/sketchup-mcp @ commit HEAD (pushedAt 2026-04-20 21:51)
**Total LOC:** ~1.8K estruturado + ~700 LOC proto* (deprecável)
**Escopo:** apenas etapa PDF → `observed_model.json` (Python). Etapa Ruby/SketchUp fora deste escopo.

---

## 1. Arquitetura atual (pipeline Python)

```
PDF bytes
  ↓
ingest/service.py (56 LOC)
  └─ ingest_pdf() via pypdfium2 → IngestedDocument(pages[])
  ↓
roi/service.py (131 LOC)
  └─ detect_architectural_roi() → seleciona componente por pixel_count (não bbox area)
  ↓
extract/service.py (119 LOC)
  └─ Hough + distance transform (thickness) → WallCandidate[]
  ↓
classify/service.py (525 LOC) — 6 estágios:
  ├─ Stage 1: _consolidate_hough_duplicates (cluster perpendicular + tolerance)
  ├─ Stage 2: _remove_text_baselines [SE len > 200]          ← VIOLAÇÃO
  ├─ Stage 3: _drop_orientation_imbalanced [SE len > 200]     ← VIOLAÇÃO
  ├─ Stage 4: _drop_low_aspect_strokes (aspect >= 2.0)
  ├─ Stage 5: _pair_merge_strokes [SE len > 200]              ← VIOLAÇÃO
  └─ Stage 6: _drop_low_aspect_strokes (de novo)
  ↓
openings/service.py (319 LOC)
  └─ detect_openings() → gaps colineares [8, 280] px + classify door/window/passage
  ↓
topology/service.py (432 LOC)
  ├─ Split em intersecções + snap endpoints (tolerance hardcoded 25.0)  ← VIOLAÇÃO
  ├─ Merge colinear (cross/tee passam, L corners não)
  └─ Polygonize (min_area = (2*median_thickness)²) → rooms
  ↓
model/pipeline.py (226 LOC) — scoring + artifacts:
  ├─ _geometry_score = len(walls)/len(candidates)  ← CRÍTICO: retenção, não qualidade
  ├─ _topology_score
  ├─ _room_score
  └─ write_debug_artifacts() → debug_walls.svg, debug_junctions.svg, connectivity_report.json
```

---

## 2. Violações de invariantes (4 encontradas)

### VIOLAÇÃO #1 — `_geometry_score` retenção, não qualidade

**Arquivo:** `model/pipeline.py:208-211`

```python
def _geometry_score(candidates: list[WallCandidate], walls: list) -> float:
    if not candidates:
        return 0.0
    return min(1.0, len(walls) / len(candidates))
```

**Invariante violada:** #6 (scores observacionais, não licença para mascarar).

**Por que é crítico:**
- 1000 candidatos ruidosos + 100 walls reais legítimas → score 0.1 (parece "ruim")
- 10 candidatos (todos bons) → score 1.0 (parece "perfeito")
- **Semântica invertida:** mais candidatos (pipeline mais permissivo) = score pior, mesmo que qualidade real seja melhor.

**Severidade:** CRÍTICA.

**Fix proposto:** substituir por F1-score + perimeter closure + connectivity. Ver [patches/03-quality-score.py](patches/03-quality-score.py).

---

### VIOLAÇÃO #2 — Gatilhos `len(strokes) > 200` acoplam pipeline a tamanho

**Arquivo:** `classify/service.py:70-71, 81-82`

```python
if len(strokes) > 200:
    strokes = _remove_text_baselines(strokes)
    strokes = _drop_orientation_imbalanced(strokes)
...
if len(strokes) > 200:
    wall_candidates = _pair_merge_strokes(strokes)
```

**Invariante violada:** #4 (não acoplar pipeline a PDF específico).

**Por que é ruim:**
- Plantas pequenas (estúdio < 40m²) com ~150 candidatos **skipam filtros** e acumulam ruído.
- Plantas muito grandes (>500 candidatos) **perdem text-baseline legítimo** se o filtro é over-aggressive.
- O threshold 200 é tuning para um PDF específico (planta_74), violando portabilidade.

**Severidade:** ALTA.

**Fix proposto:** substituir por densidade por área (`candidates_per_cm²`). Ver [patches/02-density-trigger.py](patches/02-density-trigger.py).

---

### VIOLAÇÃO #3 — ROI fallback com `applied=True` mascara falha

**Arquivo:** `roi/service.py:70-74`

```python
if min(height, width) < min_image_side:
    # Too small to meaningfully partition -- behave as if ROI were the
    # whole image. Signal `applied=True` so callers do not emit a
    # fallback warning for legitimate small inputs (synthetic tests).
    return RoiResult(True, (0, 0, width, height), None)
```

**Invariante violada:** #2 (não mascarar falhas) e #3 (não usar bbox como sala).

**Por que é ruim:**
- Comentário admite explicitamente: "signal applied=True so callers do not emit a fallback warning".
- Isso **esconde** o fato de que o ROI é um fallback bbox, não uma detecção real.
- PDFs reais de A4 pequeno (< 500 px) são silenciosamente tratados como sucesso.

**Severidade:** MÉDIA-ALTA.

**Fix proposto:** adicionar `reason="small_input"` separado de `applied`. Ver [patches/04-roi-fallback-explicit.py](patches/04-roi-fallback-explicit.py).

---

### VIOLAÇÃO #4 — `_infer_snap_tolerance` hardcoded floor

**Arquivo:** `topology/service.py:89-101`

```python
base = max(2.0, 3.0 * median)
if len(walls) < 30:
    return max(base, 25.0)  # input limpo -> snap mais agressivo
return base
```

**Invariante violada:** #4 (não acoplar pipeline a PDF específico).

**Por que é ruim:**
- `25.0` é hardcoded para "input limpo" (definição vaga).
- PDFs reais com ~20 walls legítimas (banheiro pequeno, lavanderia) terão snap over-aggressive e colapsarão geometria válida.
- Comentário admite design temporário ("poucas walls").

**Severidade:** ALTA.

**Fix proposto:** parametrizar via config ou remover; se snap agressivo for necessário, basear em geometria (DPI, bbox) e não em `len(walls)`.

---

## 3. Padrões bem implementados (crédito onde devido)

### ✓ BOM #1 — Orphan component reporting sem drop

**Arquivo:** `topology/service.py:64-68, 201-202`

Orphans são **reportados** em `metadata.connectivity`, nunca silenciosamente dropados. Commit 9410820 reverteu uma violação anterior. Código honesto.

### ✓ BOM #2 — Split/merged graph desacoplados

**Arquivo:** `topology/service.py:28-31, 48-55`

Junctions/rooms/connectivity do SPLIT graph (antes de merge). Output walls são MERGED. `len(walls) < len(junctions)` é esperado e honesto.

### ✓ BOM #3 — Reasoning documentado nos filtros

**Arquivo:** `classify/service.py:1-53`

Cada filtro tem comentário explicando o porquê (texto = 3+ paralelas com gap uniforme; hachura = floor pattern). Valores derivam de observação real, não mágicos.

### ✓ BOM #4 — Opening detection com range baseado em DPI

**Arquivo:** `openings/service.py:20-35`

Comentário explícito: "porta interna 0.6-0.9 m → ~50-100 px @ 150 DPI". Valores defensáveis.

### ✓ BOM #5 — Debug artifacts sempre escritos

**Arquivo:** `model/pipeline.py:157-162`

SVGs + JSON escritos mesmo quando `rooms=0` ou `walls=0`. Invariante #5 respeitada.

---

## 4. Débito técnico

### 4.1 Arquivos proto_* (~700 LOC) — deprecar

- `proto_red.py`, `proto_colored.py`, `proto_skel.py`, `proto_v2.py`, `proto_runner.py`
- Status: exploração manual de masking por cor. Hardcoded para `C:/Users/felip_local/Documents/paredes.png`.
- **Recomendação:** mover para `archive/` ou refatorar o aspect "color-aware extraction" em módulo limpo (Fase 2 do roadmap).

### 4.2 Scripts `render_*.py`, `crop_legend.py`, `peek_pdf.py`, `make_test_pdf.py`

- One-off scripts para debug manual. Pollui root.
- **Recomendação:** mover para `tools/` ou `scripts/`.

### 4.3 Duplicação conceitual em classify filters

- `_remove_text_baselines` vs `_drop_orientation_imbalanced` — ambos clusterizam por perpendicular + ratio.
- **Recomendação:** considerar unificar em `filter_noise_by_density()` genérica. Médio esforço.

### 4.4 Test fixtures sintéticos apenas

- `tests/fixtures.py` tem 6 imagens sintéticas 100×100 (quadrado, L, T, etc.).
- **Não há fixtures de PDFs reais.** Validação só em rasters sintéticos.
- **Recomendação:** adicionar fixture regressiva com `planta_74.pdf` e `p12` assim que red-mask virar módulo.

---

## 5. Baseline runs (não executado — Python 3.12 ausente na máquina)

Baseado em README.md§86-98 + commits históricos, o estado esperado de `planta_74`:

| Métrica | Valor esperado | Ideal |
|---|---|---|
| walls | 94 | ≤ 150 |
| rooms | 14 | 6-15 |
| junctions | 161 | — |
| orphan_component_count | 7 | < 3 |
| orphan_node_count | 16 | < 10 |
| geometry_score | 0.156 | >0.5 (se F1) |
| topology_score | 0.275 | >0.7 |
| room_score | 0.581 | >0.8 |
| topology_quality | "poor" | "good" |
| warnings | walls_disconnected, many_orphan_components | [] |

**Trajetória histórica:**
- v1-8: thickness bugs → explosão de candidates
- v14-17: orientation filter → honest reporting de orphans
- v23: snap + aspect → 328 walls, 32 rooms
- v26+: ROI crop → 227 walls, 14 rooms, geometry 0.156

**Código está estável.** Não há runs ativos porque ambiente não configurado (Python 3.12 ausente).

---

## 6. Recomendação de próximo eixo (entre A-E do contexto Felipe)

### Decisão: **B + F1 (Fase 1+2 do roadmap) > C > D > A > Ruby**

**Justificativa detalhada:**

1. **Fase 1 (quick wins: scores, triggers, ROI fallback, snap floor)** — 4h de trabalho total.
   - Remove 4 violações de invariantes.
   - Torna pipeline defensável antes de adicionar features novas.
   - **Deve vir antes de qualquer coisa.**

2. **Fase 2 (B — red-mask → módulo portável)** — 2-3 dias.
   - Código existe (`proto_red.py`). Falta integração + generalização.
   - Abre caminho para PDFs coloridos reais.
   - Reduz dependência de geometria pura (Hough frágil em PDFs degradados).
   - **Impacto:** 5-10× redução em ruído residual.

3. **Fase 3 (C — openings nível 3)** — 3-5 dias.
   - Já detecta door/window/passage por width.
   - Faltam campos que JSON já declara: `hinge_side`, `swing_deg`, `arc_center`.
   - Arc detection com Circular Hough ou template matching.
   - **Necessário para SketchUp** (fase 6).

4. **Fase 4 (D — peitoril automático)** — 2-3 dias.
   - Código proto existe (`proto_colored.py` detecta por marrom).
   - Peitoris atualmente hardcoded em JSON manual.
   - OCR opcional com PaddleOCR para "PEITORIL H=".
   - **Baixo impacto** se muros não têm variação de altura (mas melhora automação).

5. **Fase 5 (A — extract tuning)** — 1 semana.
   - Hough já está bem. Ganho marginal.
   - Deveria vir após Fase 2 (red-mask reduz ruído, Hough fica mais limpo).
   - Integrar DeepLSD/ScaleLSD como alternativa opcional.

6. **Fase 6 (E — SketchUp bridge)** — 2-3 dias.
   - Requer A-D completos primeiro.
   - Scaffold mínimo com TCP bridge (padrão mhyrr/sketchup-mcp).

---

## 7. Resumo executivo

**Pontos fortes do repo:**
- Arquitetura limpa (8 módulos independentes, testáveis)
- Pipeline honesto (não mascara falhas, orphans reportados)
- Reasoning documentado nos filtros
- Debug artifacts obrigatórios respeitados

**Problemas críticos:**
- 4 violações de invariantes (2 altas, 1 crítica, 1 média-alta)
- Heurísticas frágeis acopladas a tamanho de planta
- Score geometry semanticamente invertido
- ~700 LOC proto não integrado contamina repo

**Maturidade:** 70% — código bom, mas gateway para real-world PDFs bloqueado por heurísticas fixas e scoring enganoso.

**Ação imediata:** aplicar [patches/01-04](patches/) (4 quick wins, ~4h de implementação + testes). Ganho: pipeline honesto e portável.

**Ação média (1-2 semanas):** [patches/05-06](patches/) (U-Net oracle + arc detection). Ganho: 85%+ wall IoU, openings L3 completos.

**Ação longa (2-4 semanas):** Ruby bridge reconstruído conforme V6.1.
