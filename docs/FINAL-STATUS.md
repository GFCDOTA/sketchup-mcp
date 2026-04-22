# FINAL-STATUS.md — Closure do PR #1 (planta despedaçada)

**Data:** 2026-04-21
**Escopo:** fecha o ciclo de fix/hardening iniciado em PR #1.
**Baseline mergeada:** `main` contém F1+F2+F3+F5 via PRs #2-#7. PR #8 adiciona F6 (triangle-sliver filter).

---

## TL;DR

- **Connectivity em `planta_74.pdf` 100 % resolvida**: 1 componente, ratio 1.0, 0 órfãos estruturais.
- **Rooms count caiu 48 → 27** (F5 + F6). Falta ~7-12 rooms pra chegar no alvo semântico 15-20; gap restante é over-polygonization em 4-vertex quads pequenos (decisão downstream se vale aumentar threshold).
- **Pytest 78 pass / 15 pre-existing fails**. Pre-existing bateu no commit `dcb9751` (pré-hardening); não são regressões.
- **Pipeline PDF → .skp não validado** (Fase 6 / Ruby bridge fora desta sessão).

---

## Tabela cumulativa (planta_74.pdf)

| Commit | Data | Intent | walls | rooms | comp | orphans | ratio | pytest |
|---|---|---|---|---|---|---|---|---|
| `dcb9751` (pre-fix) | 2026-04-21 | baseline main | 104 | 16 (fragmentado) | 4 | 5 | 0.52 | 57/15 |
| `a11724a` F-orig | 2026-04-21 | collinear dedup + re-extract | 42 | 16 | 3 | 4 | 0.93 | 57/15 |
| `e0973ed` F3 | 2026-04-21 | DedupReport + 6 adversarial tests | 42 | 16 | 3 | 4 | 0.93 | 63/15 |
| `53bc0f7` F2 | 2026-04-21 | room topology check + snapshot hash + overlay | 42 | 16 | 3 | 4 | 0.93 | 63/15 |
| `2a268fe` F1 refactor | 2026-04-21 | representative-anchored dedup + density gates | 230 | 48 | **1** | **0** | **1.0** | 63/15 |
| `fc3f2df` F5-a | 2026-04-21 | sliver filter (aspect + compactness) | 230 | 38 | 1 | 0 | 1.0 | 63/15 |
| `79878d3` F5-b | 2026-04-21 | strip-room merge multi-pass | 230 | 34 | 1 | 0 | 1.0 | 70/15 |
| `df11ec0` F6 (PR #8) | 2026-04-21 | triangle-sliver filter (vertices + area) | 230 | **27** | 1 | 0 | 1.0 | **78/15** |

---

## Checklist 8-item (fechado)

Sintetiza os 6 itens do Felipe + 2 novos da sessão:

- [x] **1. Prova visual antes/depois** — `overlay_audited.png` gerado automaticamente por `53bc0f7` (PDF raster side-by-side com modelo extraído). 1 wall magenta residual documentado em PR #5 como falso-positivo Hough (`segment-1` fundindo hachurado da SUÍTE 02 com linhas da cota "1.79").
- [x] **2. Diff estrutural do grafo** — `dedup_report.json` emitido por `e0973ed`: 22 clusters, 220 → 184 candidates, merged 36, `max_perp_spread_px ≤ 20` enforcado pelo representative-anchored F1.
- [x] **3. Regressão semântica em rooms** — 3 categorias documentadas em PR #7 (20 legitimate, 16 sliver_triangle, 7 thin_strip, 5 small_triangle). F5 dropou os thin_strips + slivers shape; F6 agora drop os triangle-tiny. 27 rooms pós-F6 ainda tem ~7-10 slivers residuais (4-vertex quads pequenos).
- [x] **4. Auditoria dedup** — PR #6 mostrou 94 % dos 71 openings pós-hardening são genuínos (`wall_a`/`wall_b` em rooms ≥3000 px²). Preserva 13 de 15 openings pre-fix por coord match tol=30px.
- [x] **5. Run sem gate `>200`** — F1 refactor (`2a268fe`) substituiu gate de raw count pelo `_DEDUP_ACTIVATION_RATIO = 0.05` (density scale-invariant). Documentado na docstring de `_dedupe_collinear_overlapping`.
- [x] **6. Não-regressão em openings** — medido empiricamente pós-F6: pre-fix 15 doors → post-F6 57 doors + 14 passages; 13/15 pre-fix preservados via coord match. Os 2 que sumiram foram absorvidos por walls deduplicadas (não silenciados).
- [x] **7. Fixtures sintéticas preservadas** — `test_plan.pdf` continua produzindo 3 rooms exatos; pytest synthetic canvases (simple_square, two_rooms_shared_wall, etc.) inalterados. Activation gate (`len(rooms) >= 25`) protege.
- [x] **8. p12_red snapshot hash estável** — por commit message do Felipe F5, `topology_snapshot_sha256 == 39b4138f4fd5613ed897824657b0329445d2eb332a6a1d810da75933ba4b5ce3`. Não validado localmente (PDF só em máquina do Felipe).

---

## PRs desta sessão (mergeados em `main` + pendentes)

### Mergeados (6)

| PR | Branch | Conteúdo |
|---|---|---|
| [#2](https://github.com/GFCDOTA/sketchup-mcp/pull/2) | `test/planta-74-dedup-coverage` | 18 unit tests + 5 snapshot regression tests, rebaseados pós-F1 |
| [#3](https://github.com/GFCDOTA/sketchup-mcp/pull/3) | `fix/patches-and-docs-post-dedup-review` | Patches 03/04 corrigidos (wall.start/end, `largest_component_ratio`, `fallback_used` aditivo, sem F1-against-GT) + SOLUTION-FINAL + ROADMAP |
| [#4](https://github.com/GFCDOTA/sketchup-mcp/pull/4) | `docs/cross-pdf-validation` | 3 PDFs validados. planta_74 atinge 5/5. Achado colateral: regressão em `dcb9751` (`clean_input_skip_roi` dispara `roi_fallback_used` em sintéticos). |
| [#5](https://github.com/GFCDOTA/sketchup-mcp/pull/5) | `docs/orphan-residual-audit` | 1 órfão magenta identificado como `segment-1` (falso-positivo Hough). Fix upstream, não downstream filter. |
| [#6](https://github.com/GFCDOTA/sketchup-mcp/pull/6) | `docs/openings-explosion-audit` | 94 % dos 71 openings genuínos. Rooms ≥3k px² saltaram 3→25 legítimas (H3 confirmada). |
| [#7](https://github.com/GFCDOTA/sketchup-mcp/pull/7) | `docs/over-polygonization-analysis` | Threshold `area≥1500 AND vertices≥4 AND compactness≥0.20 AND aspect≤6` → 48 rooms caem pra 19. Três sweeps independentes convergem. |

### Abertos nesta sessão

| PR | Branch | Conteúdo |
|---|---|---|
| [#8](https://github.com/GFCDOTA/sketchup-mcp/pull/8) | `feat/topology-weld-micro-shared` | F6 triangle-sliver filter: rooms 34 → 27 em planta_74, 0 em fixtures sintéticas. 8 tests novos. |
| (este doc) | `docs/final-status-post-f6` | Closure: tabela cumulativa + checklist 8-item fechado + ressalvas. |

---

## Known Limitations

### Rooms 27 vs alvo 15-20
- Gap restante (~7-12 rooms) vem de 4-vertex quads pequenos (area 1500-3000 px²) que F5 deixa passar (aspect decente, compactness decente). Subir `_TRIANGLE_SLIVER_AREA_MAX` para 3000 dropa mais, mas risco de eliminar room pequena legítima (banheiro 1.5m² em raster 2x = ~3500 px²).
- Decisão: manter threshold 2000 conservador. PR #9 separado quando houver segundo PDF real pra calibrar.

### p10/p11/p12_red não validados nesta sessão
- PDFs só na máquina do Felipe.
- `p12_red.pdf` snapshot SHA `39b4138f…` tomado como referência via commit message; não validado localmente.
- Generalização multi-PDF permanece hipótese sustentada apenas em 1 PDF real (planta_74.pdf) + 1 sintético (test_plan.pdf).

### Ruby bridge PDF → .skp (Fase 6 ROADMAP)
- Bloqueada por confirmação de `E:\Sketchup V6.1` com Felipe.
- Pipeline atual emite `observed_model.json` consumível, mas não gera `.skp` automaticamente.
- Custo estimado: 2-3 dias se V6.1 disponível; 2-3 dias se reconstruir TCP bridge pattern mhyrr/sketchup-mcp.

### CubiCasa5K DL oracle (DEFER permanente)
- Weights CC BY-NC 4.0 bloqueiam uso comercial.
- Se necessário DL: YOLOv8-seg (Apache 2.0) ou modelo custom. Não nesta sessão.

### Regressão pré-existente em `dcb9751`
- 15 tests em `test_orientation_balance.py`, `test_pair_merge.py`, `test_text_filter.py`, `test_pipeline.py` falham há tempo (fixtures com <10 candidates não ativam filter gates). Não é regressão desta sessão.
- Solução documentada: escalar fixtures com `pad_with_noise` helper. Trabalho pendente (agent bg falhou no setup de worktree).

---

## Como reproduzir

```bash
cd sketchup-mcp
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
git checkout feat/topology-weld-micro-shared  # HEAD do PR #8

# Baseline empírica
python main.py extract planta_74.pdf --out runs/final
jq '.component_count, .largest_component_ratio, .rooms_detected, .orphan_node_count' runs/final/connectivity_report.json
# → 1, 1.0, 27, 0 ✓

# Suite
python -m pytest tests/ --tb=no -q
# → 78 passed / 15 pre-existing failed

# Visual
open runs/final/overlay_audited.png  # PDF raster + modelo extraído side-by-side
```

---

## Próximos milestones

1. **PR #9 room filter calibration (opcional)**: validar `_TRIANGLE_SLIVER_AREA_MAX = 3000` em p10/p11 antes de merge. Target: rooms 27 → ~18.
2. **Fase 6 Ruby bridge**: 2-3 dias, bloqueado Felipe (V6.1 confirmação).
3. **Scaled fixtures**: escalar os 15 pre-existing tests com `pad_with_noise` helper. Trivial, ~6h.
4. **Multi-PDF validation**: quando p10/p11/p12_red chegarem, rodar snapshot regression em cada + tabular drift.
