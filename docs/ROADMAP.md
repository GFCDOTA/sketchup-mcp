# ROADMAP.md — Execução em 6 fases

**Duração total:** 3-4 semanas trabalho focado
**Pré-requisito:** Python 3.10+ instalado (não 3.12), ambiente que rodou `runs/` identificado
**Estratégia:** cada fase entrega valor isolado + não quebra o anterior

---

## FASE 1 — Quick Wins (1 dia)

**Objetivo:** remover 4 violações de invariantes sem adicionar features.

**Tarefas:**

| # | Tarefa | Patch | Tempo |
|---|---|---|---|
| 1.1 | Renomear `_geometry_score` → `_retention_score` + docstring | [03](patches/03-quality-score.py) parte 1 | 15 min |
| 1.2 | Adicionar `_quality_score` real (F1 + perim + connectivity) | [03](patches/03-quality-score.py) parte 2 | 2h |
| 1.3 | Substituir `len(strokes) > 200` por densidade/área | [02](patches/02-density-trigger.py) | 1h |
| 1.4 | ROI fallback explícito com `reason` | [04](patches/04-roi-fallback-explicit.py) | 30 min |
| 1.5 | Remover hardcoded `max(base, 25.0)` em snap | inline edit | 10 min |
| 1.6 | Rodar test suite | `pytest` | 30 min |

**Baseline antes/depois esperado em `planta_74`:**

| Métrica | Antes | Depois (mesma run) |
|---|---|---|
| walls | 94 | 94 (mesma lógica) |
| rooms | 14 | 14 |
| geometry_score | 0.156 | — (deprecated) |
| retention_score | — | 0.156 |
| quality_score | — | ~0.45-0.60 (novo, real) |
| perimeter_closure | — | ~0.75-0.85 |

**Entregável:** pipeline honesto. Scores não mais enganosos. Invariantes #4 #6 respeitadas.

---

## FASE 2 — Color-aware preprocessor (2-3 dias)

**Objetivo:** substituir `proto_red.py` hardcoded por módulo portável.

**Tarefas:**

| # | Tarefa | Tempo |
|---|---|---|
| 2.1 | Criar `preprocess/color_aware.py` | 4h |
| 2.2 | K-means 5 clusters + identificação de cluster walls | 3h |
| 2.3 | Felzenszwalb segmentation como refinement opcional | 2h |
| 2.4 | Integrar em `main.py` como pré-Stage 2 (pré-ROI) | 2h |
| 2.5 | Deprecar `proto_red.py` → `archive/proto_red.py` | 30 min |
| 2.6 | Fixture regressiva: `p12` rodando sem red-mask manual | 2h |
| 2.7 | Teste em `planta_74.pdf` — confirmar wall detection não piora | 2h |

**Saída esperada em `planta_74`:**

| Métrica | Antes Fase 2 | Depois Fase 2 |
|---|---|---|
| walls | 94 | 95-105 (+5-10%, menos ruído) |
| orphan_components | 7 | 3-5 |
| quality_score | 0.50 | 0.58-0.65 |
| perimeter_closure | 0.80 | 0.85-0.90 |

**Entregável:** pipeline PDF-agnóstico. Invariante #4 estritamente respeitada. `p12` funciona sem red-mask manual.

---

## FASE 3 — DL Wall Oracle (5-7 dias)

**Objetivo:** integrar U-Net pretrained como pré-filtro semântico.

**Tarefas:**

| # | Tarefa | Tempo |
|---|---|---|
| 3.1 | Setup segmentation-models-pytorch + torch CPU | 2h |
| 3.2 | Clone + integrar `ozturkoktay/floor-plan-room-segmentation` | 4h |
| 3.3 | Criar `preprocess/unet_oracle.py` com inference wrapper | 6h |
| 3.4 | Export ONNX pra CPU-only deployment | 3h |
| 3.5 | Integrar U-Net mask como peso em `extract/service.py` | 4h |
| 3.6 | Fallback chain: U-Net > CubiCasa > Hough puro | 3h |
| 3.7 | Benchmark tempo inference (alvo <10s/página CPU) | 2h |
| 3.8 | Teste `planta_74` + `p12` — confirmar +5-10% wall IoU | 3h |
| 3.9 | Documentar em README + add debug_wall_confidence.png | 2h |

**Saída esperada em `planta_74`:**

| Métrica | Antes Fase 3 | Depois Fase 3 |
|---|---|---|
| walls | 95-105 | 100-115 (recuperação de walls perdidas) |
| quality_score | 0.60 | 0.75-0.85 |
| perimeter_closure | 0.87 | 0.92-0.97 |
| orphan_components | 4 | 1-2 |

**Entregável:** wall IoU 85-92%. Planta não mais despedaçada. CPU-compatible.

---

## FASE 4 — Openings Nível 3 (3-5 dias)

**Objetivo:** completar detecção de portas com arc + hinge_side + swing_deg + rooms[A,B].

**Tarefas:**

| # | Tarefa | Tempo |
|---|---|---|
| 4.1 | Estudar openings/service.py atual (gap detection) | 2h |
| 4.2 | Implementar arc detection via HoughCircles | 4h |
| 4.3 | Pareamento arc ↔ gap (pivô no canto, raio ≈ width) | 4h |
| 4.4 | Determinar hinge_side por posição do centro do arc | 2h |
| 4.5 | Determinar swing_deg pela orientação | 2h |
| 4.6 | Mapear rooms[A,B] via topology.rooms + adjacência | 3h |
| 4.7 | Adicionar campo confidence (gap_ok × arc_ok × room_ok) | 2h |
| 4.8 | Fallback template matching se Hough arcs falhar | 3h |
| 4.9 | Expandir `debug_openings.svg` com arcs detectados | 2h |
| 4.10 | Testar em `planta_74` (7 portas) | 3h |

**Saída esperada em `planta_74`:**

| Métrica | Antes | Depois |
|---|---|---|
| openings detectados | 7 (só gap) | 7 (com arc confirm) |
| hinge_side preenchido | 0/7 | 6-7/7 |
| swing_deg preenchido | 0/7 | 6-7/7 |
| rooms[A,B] preenchido | 0/7 | 7/7 |

**Entregável:** openings L3 completos. JSON pronto pra SketchUp consumer.

---

## FASE 5 — Peitoril Detection Automático (2-3 dias)

**Objetivo:** substituir `pNN_peitoris.json` manual.

**Tarefas:**

| # | Tarefa | Tempo |
|---|---|---|
| 5.1 | Estudar `proto_colored.py` (detector marrom existente) | 2h |
| 5.2 | Refatorar em `preprocess/peitoris.py` limpo | 3h |
| 5.3 | PaddleOCR opcional pra labels "PEITORIL H=" | 4h |
| 5.4 | Pair detection (linhas finas paralelas curtas ortogonais) | 3h |
| 5.5 | Match com altura do label OCR próximo | 2h |
| 5.6 | Integração em `main.py` (antes de `detect_openings`) | 2h |
| 5.7 | Deprecar leitura de `pNN_peitoris.json` | 30 min |
| 5.8 | Testar em `planta_74` | 2h |

**Entregável:** peitoris detectados automaticamente. Pipeline 100% PDF → JSON sem artefatos manuais.

---

## FASE 6 — Ruby/SketchUp Bridge (2-3 dias)

**Objetivo:** reconstruir minimalista V6.1 equivalent ou substituir por TCP socket padrão.

**Pré-requisito:** confirmar com Felipe se E:\Sketchup V6.1 foi descartado ou movido.

**Decisão bifurcação:**

### Opção A — V6.1 existe em outra máquina → migrar
- Copiar V6.1 pra `skp_export/`
- Ajustar imports e paths
- Testar com novo `observed_model.json`
- ~1 dia

### Opção B — V6.1 perdido → reconstruir
- Scaffold `skp_export/` conforme [SOLUTION.md §4](SOLUTION.md#4-stack-técnico-recomendado)
- TCP socket bridge (padrão mhyrr/sketchup-mcp)
- `place_door_component` com attributes (não scale_x)
- Arquivos:
  - `skp_export/lib/su_exporter.rb` (150 LOC)
  - `skp_export/src/wall.rb` (200 LOC)
  - `skp_export/src/door.rb` (150 LOC)
  - `skp_export/src/room.rb` (100 LOC)
- ~2-3 dias

### Tarefas comuns:

| # | Tarefa | Tempo |
|---|---|---|
| 6.1 | Confirmar fate de E:\Sketchup V6.1 | 0 (pergunta) |
| 6.2 | Setup TCP listener Ruby em SketchUp Extension | 3h |
| 6.3 | Python MCP server → socket → Ruby | 4h |
| 6.4 | Paramétricas de porta via attributes | 4h |
| 6.5 | Teste end-to-end: PDF → JSON → .skp | 3h |
| 6.6 | Validar 7/7 portas place_door_component | 2h |

**Entregável:** pipeline end-to-end funcional. `.skp` gerado automaticamente a partir de `planta_74.pdf`.

---

## Resumo agregado

| Fase | Tempo | Entregável |
|---|---|---|
| 1 | 1 dia | Pipeline honesto, sem violações invariantes |
| 2 | 2-3 dias | PDF-agnóstico (K-means em vez de red-mask) |
| 3 | 5-7 dias | Wall IoU 85-92% com U-Net oracle |
| 4 | 3-5 dias | Openings L3 completos (arc + hinge + swing) |
| 5 | 2-3 dias | Peitoris automáticos (sem JSON manual) |
| 6 | 2-3 dias | Ruby bridge restaurado/reconstruído |
| **TOTAL** | **15-22 dias** | Pipeline completo PDF → .skp |

**Com paralelização (múltiplos agents Claude, git worktrees):** redução para **10-15 dias**.

**Com Felipe dedicado full-time:** redução para **8-12 dias** (elimina wait de review/playtest).

---

## Ordem de prioridade recomendada

Se não puder fazer tudo, execute na ordem:

1. **Fase 1** sempre primeiro (invariantes). Sem isso, qualquer métrica nova continua enganosa.
2. **Fase 2** (color-aware). Garante portabilidade. Invariante #4 crítica.
3. **Fase 3** (DL oracle). Maior salto de qualidade mensurável.
4. **Fase 4** (openings L3). Requer isso pra SketchUp funcionar corretamente.
5. **Fase 5** (peitoris auto). Quality-of-life, não blocker.
6. **Fase 6** (Ruby). Após todas as etapas Python estarem sólidas.

---

## Métricas de sucesso por fase

| Fase | Métrica que deve mover | Baseline | Meta |
|---|---|---|---|
| 1 | quality_score (novo) | — | ≥ 0.50 |
| 2 | orphan_components | 7 | ≤ 5 |
| 3 | perimeter_closure | 0.80 | ≥ 0.90 |
| 4 | openings L3 completos | 0/7 | 7/7 |
| 5 | peitoris auto-detectados | 0 | ≥ 80% |
| 6 | .skp gerado end-to-end | — | OK visual |

---

**Próximo passo:** [patches/README.md](patches/README.md) explica como aplicar cada patch.
