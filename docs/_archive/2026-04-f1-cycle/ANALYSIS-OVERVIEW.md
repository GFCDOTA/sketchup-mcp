# MEMORY — Projeto sketchup-mcp (Felipe)

**Data:** 2026-04-21
**Contexto:** auxílio ao amigo Felipe (GFCDOTA) no projeto sketchup-mcp que converte PDF de planta arquitetônica em modelo SketchUp 3D.
**Repo:** https://github.com/GFCDOTA/sketchup-mcp (clonado em `sketchup-mcp/`)
**Status:** análise técnica completa, solução definitiva proposta, patches prontos pra aplicar

---

## 1. Objetivo do projeto (Felipe)

- **Pipeline atual:** PDF → `observed_model.json` (Python) → `.skp` (Ruby SketchUp API)
- **Ponto de ingresso:** `planta_74.pdf` (apartamento Living Grand Wish 74m², Torre 1 Finais 4A/3B)
- **Problema central:** wall detection falha — planta sai despedaçada (perimetral aberto, ilhas flutuantes)
- **Estratégias hackeadas atuais:**
  - Red-channel mask hardcoded (viola invariante de portabilidade)
  - Gap detection [8-280 px] fixo para portas
  - Text-baseline/orientation-dominance removendo walls reais
  - Score geometry = `len(walls)/len(candidates)` — **é retenção, não qualidade**
- **Ruby/SketchUp V6.1** funcionava (7/7 portas validadas) mas diretório `E:\Sketchup` sumiu da máquina

## 2. Invariantes invioláveis (AGENTS.md §2)

1. Não inventar rooms / walls
2. Não mascarar falhas (rooms=0 é informação, não erro)
3. Não usar bounding box como sala
4. Não acoplar pipeline a um PDF específico
5. Sempre emitir `debug_walls.svg`, `debug_junctions.svg` e `connectivity_report.json`
6. Ground truth NUNCA entra como saída do extrator

## 3. Arquivos deste pacote

| Arquivo | Conteúdo |
|---|---|
| [MEMORY.md](MEMORY.md) | Este arquivo — overview consolidado |
| [ANALYSIS.md](ANALYSIS.md) | Análise crítica do repo (4 violações de invariantes, 5 bons padrões) |
| [SOLUTION.md](SOLUTION.md) | Arquitetura técnica definitiva (Hybrid CV + DL) |
| [ROADMAP.md](ROADMAP.md) | 6 fases de execução, ~3-4 semanas total |
| [patches/](patches/) | 6 patches Python prontos pra aplicar no repo |
| [sketchup-mcp/](sketchup-mcp/) | Fork local do repo clonado |

## 4. Achados principais (de pesquisa paralela com 4 agents)

### 4.1 Violações de invariantes no código atual

| # | Arquivo:linha | Violação | Severidade |
|---|---|---|---|
| 1 | `topology/service.py:89-101` | `_infer_snap_tolerance` hardcoded 25.0 pra "input limpo" | ALTA (inv #4) |
| 2 | `classify/service.py:70-71, 81-82` | Gatilhos `len(strokes) > 200` acoplam pipeline a tamanho de planta | ALTA (inv #4) |
| 3 | `roi/service.py:72-74` | Fallback ROI com `applied=True` em imagens pequenas mascara falha | MÉDIA-ALTA (inv #2, #3) |
| 4 | `model/pipeline.py:208-211` | `_geometry_score = len(walls)/len(candidates)` — semântica invertida | CRÍTICA (inv #6) |

### 4.2 Estado da arte 2024-2026 descoberto

**Line Segment Detection:**
- **ScaleLSD (CVPR 2025)** — github.com/ant-research/scalelsd — SOTA, self-supervised 10M+ imgs
- **LINEA (ICIP 2025)** — github.com/SebastianJanampa/LINEA — deformable line attention
- **DeepLSD (CVPR 2023)** — github.com/cvg/DeepLSD — baseline robusto

**Deep Learning para plantas:**
- **CubiCasa5K** — github.com/CubiCasa/CubiCasa5k — multitask (walls, rooms, doors, windows) MIT license
- **FloorSAM (Set 2025)** — arxiv 2509.15750 — SAM2 + geometry fusion, 90%+ precision
- **MitUNet (Dez 2025)** — arxiv 2512.02413 — Mix-Transformer + Tversky loss
- **Raster-to-Graph (EG 2024)** — github.com/SizheHu/Raster-to-Graph — vectorization SOTA
- **U-Net ResNet (production-ready)** — github.com/ozturkoktay/floor-plan-room-segmentation

**OCR (peitoris, dimensões):**
- **PaddleOCR v2.7+** — melhor em layouts complexos
- **TrOCR (Microsoft)** — huggingface.co/microsoft/trocr-base — handwriting

**Datasets pra fine-tune:**
- **ArchCAD-400K** — huggingface datasets (26× FloorPlanCAD)
- **ResPlan** — github.com/m-agour/ResPlan — 17k residential + vector

**SketchUp MCP existente (referência):**
- **mhyrr/sketchup-mcp** — github.com/mhyrr/sketchup-mcp — TCP socket bridge, padrão MCP já publicado em PyPI

### 4.3 Diferenciais críticos da solução definitiva

| Aspecto | Atual | Definitivo |
|---|---|---|
| Color detection | Red-channel hardcoded | K-means + Felzenszwalb adaptativo |
| Line detection | LSD clássico | ScaleLSD zero-shot (ou DeepLSD) |
| Junction detection | Hough Transform | L-CNN / HAWP v3 |
| Room detection | Flood fill simples | Watershed + NetworkX cycle detection |
| Door/window | Gap size heurístico | Arc detection + symbol recognition |
| Vectorization | Manual contour trace | Douglas-Peucker + Manhattan snapping |
| **Score** | **Retenção (invertida)** | **F1 + perimeter closure + connectivity** |
| Portabilidade | Um PDF por cliente | Zero-shot qualquer planta |
| Peitoris | JSON manual | Color + OCR "PEITORIL H=" |
| Openings L3 | Só gap | Arc + hinge_side + swing_deg + rooms[A,B] |

## 5. Decisão de eixo recomendada (entre A-E do contexto Felipe)

### Ordem de ataque: **B > E(scores/triggers) > C > D > A > Ruby**

**Fase 1 (quick wins, 3-5 dias):**
- Renomear `_geometry_score` → `_retention_score` + documentar inversão (15 min)
- Substituir `len > 200` trigger por densidade por área (30 min)
- Tornar fallback ROI explícito com reason="small_input" (20 min)
- Parametrizar `snap_tolerance` floor hardcoded (10 min)

**Fase 2 (red-mask → portável, 2-3 dias):**
- Promover `proto_red.py` a módulo `preprocess/color_aware.py`
- K-means adaptativo detecta paleta de walls sem hardcoding
- Config opcional (invariante #4 respeitada: PDF-agnóstico)
- Rodar `p12` como fixture regressiva

**Fase 3 (DL oracle, 5-7 dias):**
- Integrar U-Net CubiCasa5K como pré-filtro de walls mask
- Hough fica como refinement, não descoberta bruta
- Fallback chain: U-Net → CubiCasa → Hough clássico
- CPU-compatible via ONNX export

**Fase 4 (openings L3, 3-5 dias):**
- Arc detection (Circular Hough + template matching)
- Campos `hinge_side`, `swing_deg`, `opens_to_room[A, B]`
- Confirmação visual por quarter-circle próximo ao gap

**Fase 5 (peitoril auto, 2-3 dias):**
- OCR PaddleOCR detecta "PEITORIL H=" nos labels
- Color detection (paleta brown/marrom)
- Substitui `pNN_peitoris.json` manual

**Fase 6 (Ruby bridge, 2-3 dias):**
- Scaffold `skp_export/` conforme V6.1
- TCP socket bridge (padrão mhyrr/sketchup-mcp)
- place_door_component com attributes (não scale_x)

**Total:** ~3-4 semanas. Cada fase entrega valor isolado.

## 6. Restrições importantes

- Python 3.12 **não está instalado** na máquina do Felipe → usar Python 3.10+ compatível
- Não instalar nada sem autorização
- Ambiente que produziu runs/ atuais precisa ser identificado antes de rodar baseline
- SketchUp Ruby V6.1 em E:\Sketchup — **confirmar se foi descartado ou movido antes de reconstruir**

## 7. Próximas ações concretas

Quando Felipe (ou Renan) voltar a esta pasta:

### Opção A — aplicar quick wins imediatos (Fase 1)
→ Patches em [patches/01-04](patches/) são drop-in, ~1.5h total de implementação + testes

### Opção B — ler análise e decidir escopo
→ [ANALYSIS.md](ANALYSIS.md) + [SOLUTION.md](SOLUTION.md) antes de qualquer código

### Opção C — entregar ao Felipe o pacote inteiro como consulta
→ Esta pasta F:\Projetos\sketchup-felipe\ é autoexplicativa. Pode zipar e enviar.

### Opção D — começar a reconstrução Ruby
→ Primeiro confirmar com Felipe se E:\Sketchup V6.1 foi descartado. Se sim, scaffold em [patches/07-skp-bridge/](patches/07-skp-bridge-TODO)

## 8. Referências primárias (validadas pelos agents)

### Pesquisa técnica
- [DeepLSD CVPR 2023](https://openaccess.thecvf.com/content/CVPR2023/papers/Pautrat_DeepLSD_Line_Segment_Detection_and_Refinement_With_Deep_Image_Gradients_CVPR_2023_paper.pdf)
- [ScaleLSD CVPR 2025](https://github.com/ant-research/scalelsd)
- [FloorSAM 2025](https://arxiv.org/html/2509.15750v1)
- [MitUNet 2025](https://arxiv.org/abs/2512.02413)
- [Raster-to-Graph EG 2024](https://github.com/SizheHu/Raster-to-Graph)
- [ArchCAD-400K NeurIPS 2025](https://arxiv.org/abs/2503.22346)
- [FloorplanTransformation](https://github.com/art-programmer/FloorplanTransformation)
- [CubiCasa5K original](https://github.com/CubiCasa/CubiCasa5k)

### SketchUp MCP
- [mhyrr/sketchup-mcp (referência padrão)](https://github.com/mhyrr/sketchup-mcp)
- [SketchUp Ruby API oficial](https://ruby.sketchup.com/)
- [ruby-api-stubs (IntelliSense)](https://github.com/SketchUp/ruby-api-stubs)
- [SketchUp Release Notes](https://ruby.sketchup.com/file.ReleaseNotes.html)

### Ferramentas
- [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR)
- [TrOCR HuggingFace](https://huggingface.co/microsoft/trocr-base-printed)
- [Shapely 2.0](https://shapely.readthedocs.io/)
- [NetworkX](https://networkx.org/)
- [segmentation-models-pytorch](https://github.com/qubvel/segmentation_models.pytorch)
- [ONNX Runtime](https://onnxruntime.ai/)

## 9. Pacote neste diretório

```
F:/Projetos/sketchup-felipe/
├── MEMORY.md                    # este arquivo
├── ANALYSIS.md                  # análise crítica detalhada do repo
├── SOLUTION.md                  # arquitetura técnica definitiva
├── ROADMAP.md                   # 6 fases de execução
├── patches/                     # 6 patches prontos pra aplicar
│   ├── README.md                # como aplicar cada patch
│   ├── 01-kmeans-color-aware.py # substitui red-mask hardcoded
│   ├── 02-density-trigger.py    # substitui len>200
│   ├── 03-quality-score.py      # substitui retenção
│   ├── 04-roi-fallback-explicit.py  # sinaliza fallback
│   ├── 05-unet-oracle-stub.py   # integração U-Net CubiCasa5K
│   └── 06-arc-detection-openings.py # openings nível 3
├── analysis/                    # diagnósticos técnicos
└── sketchup-mcp/                # fork local do repo
```

---

**Última atualização:** 2026-04-21
**Autor da análise:** Claude (sessão autônoma)
**Próxima revisão:** aguardando Felipe ou Renan retornar
