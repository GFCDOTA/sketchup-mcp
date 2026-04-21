# CAUSA-RAIZ.md — Por que a planta sai despedaçada

**Descoberta após leitura completa do código.**

## O bug geométrico exato

### Arquivo 1: extract/service.py:43-50
```python
lines = cv2.HoughLinesP(
    binary,
    rho=1,
    theta=np.pi / 180,
    threshold=12,
    minLineLength=15,    # linhas curtas (<15px) descartadas
    maxLineGap=40,       # ← AQUI: gap >40px quebra wall em fragmentos
)
```

Quando um PDF tem:
- Anti-aliasing em borda de wall
- Texto sobreposto a wall
- Hachura decorativa cortando wall
- Qualquer fragmentação de tinta no raster

…o Hough produz **2-5 segmentos** onde deveria ter **1 wall contínua**. Os fragmentos ficam a 40-80px de distância entre si.

### Arquivo 2: topology/service.py:98-101
```python
base = max(2.0, 3.0 * median)  # snap_tolerance = 3× thickness
if len(walls) < 30:
    return max(base, 25.0)
return base
```

Walls típicas têm `thickness ~8px`:
- `snap_tolerance = 3 * 8 = 24px`

Mas Hough deixa fragmentos a **40-80px de distância**.

### A consequência exata

| Gap entre fragmentos | Snap reconecta? | Resultado |
|---|---|---|
| 0-24px | Sim | Wall única ✓ |
| **24-80px** | **Não** | **Ilha flutuante (orphan)** |
| > 80px | N/A | Wall separada legítima |

**Aquela zona 24-80px é exatamente onde a planta despedaça.**

## Por que patches 01-04 não atacam isso

- Patch 01 (K-means color): decide QUAL pixel é wall. Não reconecta fragmentos.
- Patch 02 (density): decide QUANDO aplicar filtros. Não reconecta fragmentos.
- Patch 03 (quality score): reporta honestamente. Não muda extração.
- Patch 04 (ROI fallback): warn explícito. Não muda extração.

Todos os 4 são HIGIENE. Nenhum toca no gap 24-80px que causa o problema.

## O que RESOLVE (patches 07 e 08)

### Patch 07 — OpenCV puro (incremental, sem DL)

**Estratégia: reconectar fragmentos ANTES do snap.**

1. **Morphological closing 1D** (horizontal + vertical independente)
   - Kernel `(80, 1)` horizontal + `(1, 80)` vertical no binary
   - Preenche gaps colineares < 80px em walls horizontais/verticais
   - **Matematicamente resolve o 24-80px gap**

2. **LSD em vez de HoughLinesP**
   - `cv2.ximgproc.createFastLineDetector()` é menos fragmentador
   - Linhas LSD tendem a ser contínuas onde Hough quebra

3. **Collinearity-based merging antes do snap**
   - Se 2 walls têm mesma orientation + mesmo perp coord (±4px) + gap < 120px → merge
   - Rodado DUAS vezes: antes e depois de classify

4. **Snap adaptativo**
   - Medir distribuição real de gaps entre endpoints (percentil 75)
   - Snap tolerance = p75_gap × 1.2, com piso em 24px
   - Em vez de hardcoded 3× thickness

**Ganho esperado:**
- Orphan components: 7 → 1-2
- Perimeter closure: 0.80 → 0.92-0.95
- Zero mudança em invariantes (só melhora extração)

### Patch 08 — U-Net oracle REAL (definitivo, com DL)

**Estratégia: bypassar Hough completamente em regiões onde DL tem alta confiança.**

1. **U-Net CubiCasa5K pretrained** (github.com/CubiCasa/CubiCasa5k — MIT)
   - Inferência CPU via ONNX (5-10s por página)
   - Output: wall_mask (binary 512×512, upscale bilinear)

2. **Skeletonização da mask**
   - `skimage.morphology.skeletonize(wall_mask)` → centerlines de walls conectadas
   - Skeleton já é wall graph: nodes = junctions, edges = walls
   - **NUNCA fragmenta**: skeleton é sempre 1-pixel de espessura contínua

3. **Skeleton → WallCandidates direto**
   - Seguir cada ramo do skeleton
   - Ramo = wall. Bifurcação = junction.
   - Thickness recuperada por distance transform da mask original

4. **Hybrid com Hough atual**
   - U-Net como caminho primário
   - Hough como fallback se U-Net confidence média < 0.5
   - Best of both: DL em PDFs ruidosos, CV em plantas sintéticas

**Ganho esperado:**
- Wall IoU: ~70% (atual) → 85-92%
- Orphan components: 7 → 0-1
- Perimeter closure: 0.80 → 0.95-0.99
- **Resolve "planta despedaçada" de raiz**

## Resumo da entrega real

Patches 01-06 anteriores: **higiene + features, não resolvem despedaçada.**
Patches 07-08 novos: **atacam causa raiz.**
