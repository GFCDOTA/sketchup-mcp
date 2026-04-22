# Patches — guia de aplicação

**ATUALIZADO em 2026-04-21 após housekeeping na `feat/svg-ingest-openings-refine`.**

> **TL;DR**: o fix real que resolveu a planta despedaçada foi **dedup
> colinear co-posicionada pós-Hough + re-extração adaptativa**. Está
> em `classify/service.py` + `extract/service.py` desde `a11724a`,
> gated por `len(candidates) > 200` (dedup) e `> 500` (re-extract).
> Os patches 01/06 foram rejeitados e removidos deste diretório.
> Os patches 07/08/09 foram arquivados em `archive/`. Os patches
> 02/03/04 continuam aqui como "higiene opcional" — ainda **não
> integrados** e sujeitos às correções abaixo antes de qualquer PR.

---

## Patches aprovados (ainda não integrados)

Manter no topo do diretório — `patches/02-*.py`, `patches/03-*.py`,
`patches/04-*.py`.

| Patch | Verdict | Status | Motivo / correções |
|---|---|---|---|
| `02-density-trigger.py` | **APROVAR c/ mudanças** | não integrado | Threshold não calibrado; rerodar sweep antes de merge. |
| `03-quality-score.py` | **APROVAR c/ correções** *(já corrigidas no arquivo)* | não integrado | `wall.p0/p1` inexistentes → `wall.start/end`; `max_component_size_within_page` → usar `largest_component_ratio` direto; F1-against-GT removido (GT é contrato do consumer, não do extrator). |
| `04-roi-fallback-explicit.py` | **APROVAR c/ mudanças** *(já corrigidas no arquivo)* | não integrado | Manter `fallback_reason` canônico (schema 2.1.0 §4) e adicionar `fallback_used` ao lado — aditivo, não renomear. |

---

## Patches arquivados

Movidos para `patches/archive/` com seu próprio README. Não aplicar sem
spike isolado e revisão completa. Resumo:

| Patch | Status | Por quê |
|---|---|---|
| `archive/07-reconnect-fragments-FIXED.py` | **ADIADO** | `scipy` ausente em `requirements.txt`; morph close funde gaps de porta reais. |
| `archive/08-unet-oracle-FIXED.py` | **ADIADO** | Sem offline fallback para weights; `strict=False` silencioso viola CLAUDE.md §6. |
| `archive/09-afplan-convex-hull.py` | **APROVAR atrás de env flag** | GPT-4 consultado considerou inferior — só atrás de `SKM_EXTRACTOR=afplan` via env. |

Detalhes em `archive/README.md`.

---

## Patches removidos deste diretório (rejeitados)

Deletados no housekeeping de 2026-04-21 depois de verificação contra
`SOLUTION-FINAL.md`:

- `01-kmeans-color-aware.py` — **REJEITADO**: duplica
  `preprocess/color_mask` que já existe no main.
- `06-arc-detection-openings.py` — **REJEITADO**: `openings/service.py`
  já implementa `_detect_arc_and_hinge` / `_arc_coverage` /
  `_assign_rooms` com 259 linhas de teste; patch foi escrito contra
  HEAD stale.

Se precisar olhar o conteúdo original, usar `git log -- patches/` para
recuperar os blobs dos commits anteriores.

---

## Fix estrutural real (já aplicado em `fix/dedup-colinear-planta74`)

Dois estágios, ambos gated para não regredir baselines limpos
(`p12_red.pdf` etc.):

1. **`classify.service._dedupe_collinear_overlapping`** — gated por
   `len(candidates) > 200`. Segunda passada de dedup que colapsa
   detecções Hough gêmeas cujo offset perpendicular escapou do bucket
   de tolerância da consolidação original e cujos extents paralelos
   se sobrepõem (`_DEDUP_PERP_TOLERANCE=10`, `_DEDUP_OVERLAP_RATIO=0.35`).
2. **`extract.service.extract_from_document` re-extract adaptativo** —
   gated por `len(candidates) > 500`. Re-roda a extração com
   `hough_threshold=10` e `min_wall_length=20` quando o count explode
   no input noisy.

### Impacto medido em `planta_74.pdf`

| Métrica | Antes (main `dcb9751`) | Depois (`a11724a`) |
|---|---|---|
| walls | 104 | **42** |
| `component_count` | 4 | **3** |
| `largest_component_ratio` | 0.5208 | **0.9273** |
| `component_sizes` | [25, 2, 18, 3] | [51, 2, 2] |
| rooms | 16 | 16 |
| `orphan_component_count` | 2 | 2 |
| `orphan_node_count` | 5 | 4 |

Baseline `p12_red.pdf` intacto (ambos os gates não disparam).

### Cobertura de teste (adicionada em PR #2)

- 16 unit tests em `tests/test_collinear_dedup.py`.
- 4 regression snapshot tests em `tests/test_planta_74_regression.py`.
- Suite: **77 pass / 15 pre-existing fails** (os 15 já existiam em `dcb9751`).

---

## Ordem recomendada (atualizada)

### Já entregue
1. `fix/dedup-colinear-planta74` — resolve 4/5 targets em `planta_74.pdf`.

### Próximos passos sugeridos (todos em PRs separados)

1. **Patch 02 (density trigger)** — calibrar threshold com sweep
   adicional; sem calibração, arriscamos regressão em inputs limpos.
2. **Patch 03 (quality score)** — aplicar com as correções desta
   revisão (wall.start/end, largest_component_ratio direto, sem
   F1-against-GT).
3. **Patch 04 (ROI fallback aditivo)** — aplicar mantendo
   `fallback_reason` canônico e adicionando `fallback_used` ao lado.
4. **Patch 09 (AFPlan) atrás de feature-flag** — só se o usuário
   explicitar `SKM_EXTRACTOR=afplan` via env. Patch mora em
   `archive/09-afplan-convex-hull.py`.
5. **Semantic filter dos 4 órfãos residuais** em PR separado. PDF
   `planta_74.pdf` ainda tem 2 componentes órfãos de 2 nós cada
   (~[282,754]→[334,754] e ~[357,420]→[401,420]) que inferimos como
   mobiliário/legenda; validar com overlay no raster antes de
   filtrar automaticamente.

### Não aplicar sem spike isolado

- Patch `archive/07` (LSD + morph) — adiar até ter `scipy` na stack e
  teste contra gaps de porta reais.
- Patch `archive/08` (CubiCasa DL) — adiar até ter pipeline offline de
  weights + CI vendoring + SHA pinning.

---

## Comando de aplicação (referência, após revisar cada patch)

```bash
cd sketchup-mcp/

# Sanidade
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
python main.py extract planta_74.pdf --out runs/baseline_now
cat runs/baseline_now/connectivity_report.json

# Branch por patch, commit atômico
git checkout -b fix/patch-03-quality-score
# ... integrar patches/03-quality-score.py em model/pipeline.py ...
pytest
git commit -am "feat(pipeline): honest retention + quality scores (patch 03)"
```

---

## Validação obrigatória por patch

Após CADA patch aplicado:

```bash
# 1. Tests passam
pytest -v

# 2. Baseline comparável em planta_74
python main.py extract planta_74.pdf --out runs/fase_N
# Comparar com runs/baseline_now via jq:
# jq '.component_count, .largest_component_ratio, .orphan_component_count' \
#   runs/baseline_now/connectivity_report.json \
#   runs/fase_N/connectivity_report.json

# 3. Não regredir baselines limpos (sintéticos ou p12 quando disponível)
pytest tests/test_pipeline.py tests/test_planta_74_regression.py

# 4. Debug artifacts gerados
ls runs/fase_N/
# debug_walls.svg debug_junctions.svg connectivity_report.json observed_model.json
```

---

## Setup dependências

Atual `requirements.txt` é suficiente para o fix estrutural e para os
patches 02/03/04 corrigidos. Só os patches arquivados exigem extras:

### Para patch `archive/07` (LSD + morph) — adiado

```bash
pip install "opencv-python-headless>=4.5.4"  # LSD no core
pip install scipy  # KDTree, ainda não em requirements.txt
```

### Para patch `archive/08` (CubiCasa5K DL) — adiado

```bash
# Clonar repo oficial (vendor no monorepo; não usar install -e remoto)
git clone https://github.com/CubiCasa/CubiCasa5k vendor/CubiCasa5k
pip install torch torchvision gdown scikit-image

# Weights: vendorar localmente com SHA pinned; não depender de Google Drive
# em tempo de execução. Ver §Invariantes no PROMPT-RENAN.md.
```

---

## Troubleshooting

### "cv2.createLineSegmentDetector not found"
- Atualize: `pip install --upgrade "opencv-python-headless>=4.5.4"`.
- LSD foi removido em 4.1 por patent, restaurado em 4.5.4 após expirar.

### "No module named 'floortrans'"
- CubiCasa5K não está no PYTHONPATH (patch `archive/08` adiado — não espere que esteja).
- Para spike isolado: `cd vendor/CubiCasa5k && pip install -e .`.

### "torch.load fails with UnpicklingError"
- Checkpoint CubiCasa5K foi baixado corrompido ou não tem SHA validado.
- Delete `models/*.pkl` e rerun download; valide SHA contra manifest.

### Orphan components não caiu após patches
- Debug: olhar `runs/X/debug_walls.svg` visualmente.
- Se gaps visíveis >120px: aumentar `max_gap_px` em `_merge_collinear_fragments`.
- Se walls diagonais presentes: AFPlan aceita, LSD não.
- Se sobraram 2 componentes de 2 nós cada: é o padrão residual pós-fix
  estrutural — tratar com filtro semântico downstream, não com mais
  dedup (pode colapsar rooms legítimas).
