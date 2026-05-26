# SOLUTION.md — Arquitetura técnica definitiva

**Data:** 2026-04-21
**Contexto:** solução definitiva para `sketchup-mcp` resolver wall detection despedaçada e completar pipeline PDF → observed_model.json → SketchUp 3D de forma portável e honesta.

---

## 1. Princípio norteador

**Hybrid CV + DL, respeitando invariantes:**

- DL (U-Net pré-treinado) fornece **wall mask** de alta qualidade como **pré-filtro semântico**
- CV clássico (Hough, morphology) faz **refinement** de geometria sobre regiões de alta confiança
- Validação topológica estrita (NetworkX + Shapely) detecta "planta despedaçada" programaticamente
- Score substituído por métrica composta (F1 + perimeter closure + connectivity) — nunca mais retenção

**O que NÃO mudar:**
- Arquitetura modular (ingest/classify/openings/topology) — é boa
- Debug artifacts obrigatórios — é boa
- Orphan reporting sem drop — é boa
- Reasoning documentado nos filtros — é boa

---

## 2. Pipeline definitivo (em 10 estágios)

```
┌──────────────────────────────────────────────────────────────────────────┐
│ STAGE 0 — INGEST                                                          │
│   ingest/service.py (mantém)                                              │
│   PDF bytes → IngestedDocument(pages[] @ 300 DPI via pypdfium2)           │
└──────────────────────┬───────────────────────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────────────────────┐
│ STAGE 1 — COLOR ANALYSIS (NOVO — substitui red-mask hardcoded)           │
│   preprocess/color_aware.py                                               │
│   • K-means 5 clusters na paleta da página                                │
│   • Felzenszwalb segmentation pra regiões homogêneas                      │
│   • Identifica cluster de walls por: (a) variância de tons, (b) density,  │
│     (c) oriented extent (walls são longas + finas)                        │
│   • Output: binary mask walls + mask peitoris (separado)                  │
│   INVARIANTE #4 RESPEITADA: sem hardcoding de cor                         │
└──────────────────────┬───────────────────────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────────────────────┐
│ STAGE 2 — ROI DETECTION (mantém, ajuste em fallback)                     │
│   roi/service.py + fix #4 (patches/04)                                    │
│   Resposta explícita: applied + reason (small_input, no_dominant, etc)    │
└──────────────────────┬───────────────────────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────────────────────┐
│ STAGE 3 — DL WALL ORACLE (NOVO)                                           │
│   preprocess/unet_oracle.py                                               │
│   • U-Net ResNet50 pretrained em CubiCasa5K (ozturkoktay fork)            │
│   • Input: ROI crop (RGB ou grayscale)                                    │
│   • Output: wall_confidence_map (0.0-1.0) + room_mask                     │
│   • CPU-compatible via ONNX export (5-10s por página)                     │
│   • Fallback chain: U-Net > CubiCasa multitask > Hough clássico           │
└──────────────────────┬───────────────────────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────────────────────┐
│ STAGE 4 — LINE DETECTION (UPGRADE)                                        │
│   extract/service.py (mantém interface, upgrade interno)                  │
│   • Opção A: ScaleLSD (CVPR 2025) — deep learning SOTA                    │
│   • Opção B: DeepLSD (CVPR 2023) — estável, bem-testado                   │
│   • Opção C: LSD clássico OpenCV (fallback CPU-only, sem modelo)          │
│   • Entrada: ROI crop + wall_confidence_map (peso em candidate scoring)   │
│   • Saída: WallCandidate[] com confidence real                            │
└──────────────────────┬───────────────────────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────────────────────┐
│ STAGE 5 — CLASSIFY (REFACTOR — remove gatilhos len>200)                   │
│   classify/service.py + fix #2 (patches/02)                               │
│   • Filtros aplicados baseado em densidade (candidates/cm² no ROI)        │
│   • Text-baseline: aplicar sempre, mas ajustar sensibilidade              │
│   • Orientation-dominance: aplicar sempre                                 │
│   • Aspect-ratio: mantém (threshold 2.0 é defensável)                     │
│   • Pair-merge: aplicar sempre, ajustar ratio mínimo                      │
│   INVARIANTE #4 RESPEITADA: sem acoplamento a tamanho absoluto            │
└──────────────────────┬───────────────────────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────────────────────┐
│ STAGE 6 — OPENINGS L3 (NOVO)                                              │
│   openings/service.py (expandir)                                          │
│   • Gap detection (mantém, [8, 280] px adaptado a DPI)                    │
│   • Arc detection NOVO: Circular Hough Transform no raster                │
│     - Procurar arcos próximos ao gap (quarter-circle, raio ~ width)       │
│     - Pivô = canto do gap                                                 │
│   • Determinar hinge_side (left/right) pelo centro do arc                 │
│   • Determinar swing_deg pela orientação do arc                           │
│   • Mapear rooms[A, B] via topology.rooms + adjacência do gap             │
│   • Confidence: gap_ok × arc_ok × room_mapping_ok                         │
│   INVARIANTE #1 RESPEITADA: não inventa opening se não houver arc         │
└──────────────────────┬───────────────────────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────────────────────┐
│ STAGE 7 — PEITORIL DETECTION AUTO (NOVO)                                  │
│   preprocess/peitoris.py                                                  │
│   • Color detection: cluster de marrom/tan da paleta (Stage 1)            │
│   • OCR opcional: PaddleOCR detecta labels "PEITORIL H=0.90m"             │
│   • Pair detection: linhas finas paralelas ortogonais a walls             │
│   • Match com labels OCR próximos → altura estrutural                     │
│   • Output: Peitoril[] substituindo pNN_peitoris.json manual              │
└──────────────────────┬───────────────────────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────────────────────┐
│ STAGE 8 — TOPOLOGY (mantém, ajuste em snap)                               │
│   topology/service.py + fix #1 (patches/01b)                              │
> NOTE: patches 01/01b/05/06 were REJECTED in review (duplicated existing code). See CLAUDE.md §11 for current patch inventory.
│   • Remove `return max(base, 25.0)` — substituir por base puro            │
│   • Ou tornar floor configurável via param                                │
│   • Split + snap + merge colinear + polygonize → rooms                    │
└──────────────────────┬───────────────────────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────────────────────┐
│ STAGE 9 — QUALITY SCORE (REFACTOR — remove retenção)                      │
│   model/pipeline.py + fix #3 (patches/03)                                 │
│   • F1-score walls (precision + recall contra ground truth se disponível) │
│   • Perimeter closure: largest_component_size / total_nodes               │
│   • Connectivity: 1 - (orphan_components / total_components)              │
│   • Orthogonality: 1 - (non_ortho_edges / total_edges)                    │
│   • Room IoU (se GT disponível) ou room_density validation                │
│   • composite_quality = f1*0.4 + perim_closure*0.3 + connectivity*0.2 +   │
│                         orthogonality*0.1                                 │
│   INVARIANTE #6 RESPEITADA: scores observacionais reais                   │
└──────────────────────┬───────────────────────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────────────────────┐
│ STAGE 10 — DEBUG ARTIFACTS (mantém, expandir)                             │
│   debug/service.py (mantém + adiciona)                                    │
│   • debug_walls.svg (já existe)                                           │
│   • debug_junctions.svg (já existe)                                       │
│   • connectivity_report.json (já existe)                                  │
│   • debug_openings.svg NOVO (arcs detectados + hinge)                     │
│   • debug_color_clusters.png NOVO (K-means output)                        │
│   • debug_wall_confidence.png NOVO (U-Net heatmap)                        │
│   INVARIANTE #5 RESPEITADA: todos escritos sempre                         │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Decisões de design críticas

### 3.1 Por que hybrid e não DL puro?

- **Dataset pequeno:** ~1-5 PDFs reais. DL from scratch = impossível.
- **DL pretrained (CubiCasa5K)** já cobre 80-85% wall IoU em zero-shot em plantas residenciais.
- **CV clássico** preserva geometria precisa (snapping ortogonal, merge colinear).
- **Melhor dos dois:** DL descobre onde walls estão; CV refina como elas se conectam.

### 3.2 Por que ScaleLSD (não Hough vanilla)?

- Hough vanilla perde linhas em PDFs com noise ou resolução variada.
- ScaleLSD treinado em 10M+ imagens → zero-shot generalization.
- Fallback chain permite CPU-only (ScaleLSD → DeepLSD → LSD OpenCV).

### 3.3 Por que K-means adaptativo (não red-mask)?

- **Invariante #4:** pipeline não pode ser acoplado a PDF específico.
- K-means detecta paleta automaticamente independente de cor que o CAD usou.
- Diferencial: identifica walls pela variância de tons + shape oriented, não pela cor em si.

### 3.4 Por que densidade (não len>200)?

- **Invariante #4:** plantas pequenas e grandes precisam do mesmo pipeline.
- Densidade por área (candidates/cm²) é robusta a DPI e tamanho de planta.
- Threshold de densidade pode ser calibrado em conjunto de plantas reais (não hardcoded).

### 3.5 Por que F1 + perimeter closure (não retenção)?

- **Invariante #6:** scores são observações, não licença para mascarar.
- F1 reflete qualidade real da extração (precisão × recall contra truth, ou plausibilidade topológica).
- Perimeter closure é indicador objetivo de "planta despedaçada".
- Connectivity e orthogonality são sinais adicionais.

### 3.6 Por que arc detection para doors?

- **Openings Level 3 requer:** hinge_side, swing_deg, rooms[A, B].
- Arc (quarter-circle) é marca visual canônica de porta em plantas arquitetônicas.
- Circular Hough Transform é rápido (CPU-only, OpenCV built-in).
- Match arc ↔ gap: pivô do arc = canto do gap, raio ≈ width da porta.

---

## 4. Stack técnico recomendado

| Componente | Escolha | Fallback | Licença |
|---|---|---|---|
| PDF → raster | pypdfium2 (mantém) | PyMuPDF | Apache 2.0 |
| Color clustering | scikit-learn KMeans + scikit-image felzenszwalb | OpenCV kmeans | BSD |
| DL wall oracle | U-Net ResNet50 (segmentation_models_pytorch) | CubiCasa5K | MIT |
| Line detection | ScaleLSD (via github release weights) | DeepLSD ou LSD OpenCV | Research (verificar) |
| OCR peitoris | PaddleOCR | TrOCR HuggingFace | Apache 2.0 |
| Topology graph | NetworkX 3.x (já usa?) | — | BSD |
| Geometry validation | Shapely 2.0+ | — | BSD |
| Arc detection | OpenCV HoughCircles | template matching | Apache 2.0 |
| SketchUp bridge | TCP socket (padrão mhyrr/sketchup-mcp) | file-based JSON | — |

**Python compatível:** 3.10+ (restrição do ambiente do Felipe).
**GPU:** opcional (acelera U-Net, mas ONNX CPU runtime funciona em 5-10s/página).
**Memória:** ~500MB durante inference. Aceitável.

---

## 5. Métrica definitiva de sucesso

Uma planta passa se e só se:

```python
plan_is_valid = (
    composite_quality >= 0.75
    and perimeter_closure >= 0.90
    and n_rooms >= 1
    and n_orphan_components <= 2
    and orthogonality >= 0.85
)
```

Se não passar, **emit warning com reason explícita** — nunca silenciar.

**Métrica composta:**

```python
def composite_quality(walls, rooms, connectivity, orthogonality, f1=None) -> float:
    """
    Substitui _geometry_score. Scores observacionais, não licença pra mascarar.
    
    Retorna 0.0 se inputs estão vazios; 1.0 se planta é perfeita.
    """
    components = {
        'perimeter_closure': min(1.0, connectivity.max_component_ratio),
        'room_density': min(1.0, len(rooms) / max(1, connectivity.edge_count)),
        'orthogonality': orthogonality,
        'orphan_penalty': 1.0 - min(1.0, connectivity.orphan_components / 5.0),
    }
    
    if f1 is not None:  # GT disponível
        components['f1'] = f1
        weights = {'f1': 0.4, 'perimeter_closure': 0.3, 'room_density': 0.1, 
                   'orthogonality': 0.1, 'orphan_penalty': 0.1}
    else:  # unsupervised
        weights = {'perimeter_closure': 0.4, 'room_density': 0.2, 
                   'orthogonality': 0.2, 'orphan_penalty': 0.2}
    
    return sum(components[k] * weights[k] for k in weights)
```

---

## 6. Compatibilidade com SketchUp Ruby downstream

O `observed_model.json` de saída deve incluir campos mínimos:

```json
{
  "walls": [
    {
      "id": "w1",
      "p0": [x, y],
      "p1": [x, y],
      "thickness": 0.15,
      "height": 2.80,
      "rooms": ["r1", "r2"],
      "confidence": 0.92
    }
  ],
  "doors": [
    {
      "id": "d1",
      "wall_id": "w1",
      "offset_m": 0.30,
      "width_m": 0.80,
      "height_m": 2.10,
      "hinge_side": "left",
      "swing_deg": 90,
      "rooms": ["r1", "r2"],
      "confidence": 0.88
    }
  ],
  "peitoris": [
    {
      "id": "p1",
      "wall_id": "w2",
      "offset_m": 0.10,
      "width_m": 1.20,
      "height_m": 0.90,
      "sill_height_m": 0.90,
      "source": "detected" | "labeled_ocr"
    }
  ],
  "rooms": [
    {
      "id": "r1",
      "polygon": [[x1,y1], [x2,y2], ...],
      "area_m2": 12.5,
      "label": "SALA" | null
    }
  ],
  "metadata": {
    "quality": {
      "composite": 0.82,
      "perimeter_closure": 0.95,
      "f1": 0.89,
      "orthogonality": 0.92,
      "orphan_components": 1
    },
    "warnings": []
  }
}
```

Ruby side consome isso via TCP bridge e gera `.skp` com `place_door_component(door_spec)` usando attributes (não scale_x).

---

## 7. Resumo da solução

| Problema | Solução | Patch |
|---|---|---|
| Red-mask hardcoded | K-means + Felzenszwalb adaptativo | [01-kmeans-color-aware.py](patches/01-kmeans-color-aware.py) |
| `len > 200` gatilhos | Densidade por área | [02-density-trigger.py](patches/02-density-trigger.py) |
| Score retenção invertida | F1 + perimeter + connectivity | [03-quality-score.py](patches/03-quality-score.py) |
| ROI fallback silencioso | Reason explícita | [04-roi-fallback-explicit.py](patches/04-roi-fallback-explicit.py) |
| Wall detection frágil | U-Net CubiCasa5K oracle | [05-unet-oracle-stub.py](patches/05-unet-oracle-stub.py) |
| Openings L2 incompleto | Arc detection + hinge + swing | [06-arc-detection-openings.py](patches/06-arc-detection-openings.py) |
| Peitoris manual | Color + OCR PaddleOCR | Fase 5 (stub em SOLUTION.md) |
| Ruby bridge perdido | TCP socket padrão mhyrr | Fase 6 (stub em SOLUTION.md) |

**Impacto esperado:**
- Wall IoU: 70% (atual estimado) → 85-92% (com U-Net)
- Portabilidade: 1 PDF específico → qualquer planta residencial
- Score real vs. marketing: inverte de retenção (enganosa) para F1 + topology (honesta)
- Openings L3 completos para SketchUp downstream
- Pipeline 100% PDF-agnóstico (invariantes respeitadas)

---

**Próximo passo:** leia [ROADMAP.md](ROADMAP.md) para sequência de execução.
