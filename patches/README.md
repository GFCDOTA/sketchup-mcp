# Patches — guia de aplicação

**ATUALIZADO após code review com 3 agents. Versões FIXED obrigatórias.**

## Ordem recomendada

### Fase 1 — Higiene (4h, baixo risco)
1. [01-kmeans-color-aware.py](01-kmeans-color-aware.py) — substitui red-mask hardcoded
2. [02-density-trigger.py](02-density-trigger.py) — substitui len>200 hardcoded
3. [03-quality-score.py](03-quality-score.py) — substitui retenção por F1
4. [04-roi-fallback-explicit.py](04-roi-fallback-explicit.py) — sinaliza fallback explícito

### Fase 2 — AFPlan (1 dia, sem deps novas)
5. [09-afplan-convex-hull.py](09-afplan-convex-hull.py) — multi-scale + CCA (TOPOLOGIA FORÇA RECONNECT)

### Fase 3 — LSD real (1 dia, se 09 insuficiente)
6. [07-reconnect-fragments-FIXED.py](07-reconnect-fragments-FIXED.py) — LSD core + KDTree

### Fase 4 — DL oracle (2-3 dias, solução definitiva)
7. [08-unet-oracle-FIXED.py](08-unet-oracle-FIXED.py) — CubiCasa5K arch real

### Fase 5 — Features adicionais
8. [06-arc-detection-openings.py](06-arc-detection-openings.py) — openings L3 (arc + hinge + swing)

---

## Arquivos DEPRECATED — não usar

- ❌ `05-unet-oracle-stub.py` — substituído por `08-unet-oracle-FIXED.py`
- ❌ `07-reconnect-fragments.py` (sem "FIXED") — 9 bugs, substituído por FIXED
- ❌ `08-unet-oracle-real.py` (sem "FIXED") — 6 bloqueantes, arch errada, substituído por FIXED

---

## Comando de aplicação

```bash
cd sketchup-mcp/
git checkout -b fix/planta-despedacada

# Fase 1 (higiene)
cp ../patches/01-kmeans-color-aware.py preprocess/color_aware.py
# Editar main.py e pipeline.py conforme comments dos patches 02, 03, 04
pytest
git commit -am "fix: remove invariant violations (scores, triggers, ROI, snap)"

# Fase 2 (AFPlan)
cp ../patches/09-afplan-convex-hull.py extract/afplan.py
# Editar model/pipeline.py para chamar extract_from_raster_afplan
pytest
python main.py extract planta_74.pdf --out runs/afplan_only
# Verificar: orphan_components baixou? perimeter_closure subiu?
git commit -am "feat: AFPlan multi-scale + CCA extraction"

# Se 09 resolveu → pular pra Fase 5
# Senão → continuar

# Fase 3 (LSD)
cp ../patches/07-reconnect-fragments-FIXED.py extract/reconnect.py
# Integrar como ensemble com AFPlan
pytest
python main.py extract planta_74.pdf --out runs/afplan_plus_lsd
git commit -am "feat: LSD + morphological reconnection"

# Fase 4 (DL oracle) — opcional mas DEFINITIVO
bash scripts/setup_cubicasa.sh  # clone repo + download weights
cp ../patches/08-unet-oracle-FIXED.py preprocess/cubicasa_oracle.py
# Integrar em extract com fallback
pytest
python main.py extract planta_74.pdf --out runs/cubicasa_dl
git commit -am "feat: CubiCasa5K DL wall oracle"
```

---

## Validação obrigatória

Após CADA patch aplicado:

```bash
# 1. Tests passam
pytest -v

# 2. Baseline comparável em planta_74
python main.py extract planta_74.pdf --out runs/fase_N
# Comparar com runs/baseline_before:
#   - walls (não deve cair drasticamente)
#   - rooms (deve subir ou manter)
#   - orphan_components (deve cair)
#   - perimeter_closure (deve subir)

# 3. Debug artifacts gerados
ls runs/fase_N/
# debug_walls.svg debug_junctions.svg connectivity_report.json observed_model.json
```

---

## Setup dependências

### Para Fase 2 (AFPlan — ZERO deps novas)
```bash
# Já tem no requirements.txt: opencv-python, numpy
```

### Para Fase 3 (LSD real)
```bash
pip install "opencv-python>=4.5.4"  # LSD no core
pip install scipy  # KDTree
```

### Para Fase 4 (CubiCasa5K DL)
```bash
# Clonar repo oficial
cd ..  # fora de sketchup-mcp
git clone https://github.com/CubiCasa/CubiCasa5k
cd CubiCasa5k
pip install -e .

# Dependências Python
pip install torch torchvision gdown scikit-image

# Download weights (~100MB, Google Drive)
cd ../sketchup-mcp
python -c "from patches.unet_oracle_fixed import download_cubicasa_weights; download_cubicasa_weights()"

# Download manual fallback se gdown falhar:
# https://drive.google.com/uc?id=1gRB7ez1e4H7a9Y09lLqRuna0luZO5VRK
```

---

## Troubleshooting

### "cv2.createLineSegmentDetector not found"
- Atualize: `pip install --upgrade "opencv-python>=4.5.4"`
- LSD foi removido em 4.1 por patent, restaurado em 4.5.4 após expirar.

### "No module named 'floortrans'"
- CubiCasa5K não está no PYTHONPATH.
- `cd CubiCasa5k && pip install -e .`

### "torch.load fails with UnpicklingError"
- Checkpoint CubiCasa5K foi baixado corrompido.
- Delete `models/*.pkl` e rerun download.

### "gdown: download exceeded quota"
- Google Drive limita downloads públicos.
- Alternativa: baixar manualmente e colocar em `models/model_best_val_loss_var.pkl`.

### Orphan components não caiu após patches
- Debug: olhar `runs/X/debug_walls.svg` visualmente.
- Se gaps visíveis >120px: aumentar `max_gap_px` em `_merge_collinear_fragments`.
- Se walls diagonais presentes: AFPlan aceita, LSD não.
