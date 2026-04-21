# ROADMAP.md — Execução revisada pós fix estrutural

**Atualizado:** 2026-04-21, após `fix/dedup-colinear-planta74` (`a11724a`)
atingir 4/5 targets em `planta_74.pdf` sem DL.
**Duração total revisada:** **6-8 semanas** de trabalho focado (antes
estimadas 3-4 semanas; bump reflete realidade de CI/weights/vendoring
dos itens DL + fato de que o fix atual não usa DL).
**Pré-requisito:** Python 3.10+ instalado (testado em 3.12.10 fresh
via winget user-scope). Venv isolada, sem torch/scipy em
`requirements.txt`.
**Estratégia:** cada fase entrega valor isolado + não quebra o anterior.

---

## Onde o roadmap mudou

- **Fase 1** (higiene) continua, mas os patches 01/06 viraram
  REJEITADOS (duplicam código existente). 02/03/04 continuam válidos
  nas versões corrigidas (wall.start/end, fallback_reason canônico,
  sem F1-against-GT).
- **Fase 2** (color-aware preprocessor) permanece baixa prioridade —
  o fix estrutural já resolve 4/5 targets sem precisar de K-means.
  Vira útil quando plantas sem red-mask aparecerem.
- **Fase 3** (DL wall oracle CubiCasa5K) foi **reduzida em prioridade
  e bumped em complexidade**: requer CI de modelo (vendoring do
  repo, pinned SHA de weights, offline fallback honesto). Realisticamente
  **10-15 dias** em vez de 5-7.
- **Fase 4** (Openings L3) foi **REMOVIDA do caminho crítico**:
  `openings/service.py` no main (`dcb9751`) já implementa
  `_detect_arc_and_hinge` + `_arc_coverage` + `_assign_rooms` com
  259 linhas de teste. Sobra só validação end-to-end + `debug_openings.svg`.
- **Fase Nova — Semantic filter dos órfãos residuais** é o próximo
  blocker real (4 nodes residuais em `planta_74`).
- **Fase Nova — Opening-aware topology** passa a ser Fase 2.

---

## FASE 0 — Higiene pós-fix (1-2 dias)

**Objetivo:** aplicar patches 02/03/04 corrigidos, fechar dívidas de
invariante sem regredir o fix estrutural.

| # | Tarefa | Patch | Tempo |
|---|---|---|---|
| 0.1 | Integrar `_retention_score` + `_quality_score` em `model/pipeline.py` | [03](patches/03-quality-score.py) | 2h |
| 0.2 | Adicionar `fallback_used` aditivo em `RoiResult`; manter `fallback_reason` canônico | [04](patches/04-roi-fallback-explicit.py) | 1h |
| 0.3 | Calibrar threshold de density-trigger (sweep) antes de mergear patch 02 | [02](patches/02-density-trigger.py) | 4h |
| 0.4 | Atualizar `README.md` + schema docs pros 2 campos novos | inline | 1h |
| 0.5 | Rodar suite, confirmar 77 pass / 15 pre-existing fails | `pytest` | 30min |

**Baseline esperado** em `planta_74` (metrics NUMÉRICAS não mudam,
só semântica dos scores):

| Métrica | Pré | Pós Fase 0 |
|---|---|---|
| walls | 42 | 42 |
| `component_count` | 3 | 3 |
| `largest_component_ratio` | 0.9273 | 0.9273 |
| `quality_score` (novo) | — | ~0.70-0.80 |
| `retention_score` (renomeado) | — | `walls / raw_candidates` |
| `roi.fallback_used` (novo) | — | `true/false` honesto |

---

## FASE 1 — Opening-aware topology (3-5 dias)

**Objetivo:** ligar portas detectadas ao grafo de walls antes da
detecção de rooms, pra eliminar fragmentação semântica.

**Motivação:** `rooms=16` pode ser numericamente igual antes e depois
do fix mas semanticamente diferente — um cômodo fundido por falta de
porta + um par quebrado separado dá o mesmo count. Opening-aware
topology resolve isso.

| # | Tarefa | Tempo |
|---|---|---|
| 1.1 | Criar pipeline order: classify → detect_openings → topology | 4h |
| 1.2 | Em `topology/service.py`, adicionar passagem "soft" pelas portas detectadas como edges virtuais do grafo | 6h |
| 1.3 | Split walls nas portas detectadas (subdivisão física) | 4h |
| 1.4 | Teste: planta com 2 cômodos + 1 porta → `rooms == 2` após reordering | 2h |
| 1.5 | Validar em `planta_74` — comparar `rooms` antes/depois | 2h |

**Entregável:** topology consome `openings/service.py`, rooms
semanticamente corretas. Se melhorar em `planta_74`, re-pin do
snapshot de regressão.

---

## FASE 2 — Semantic filter dos órfãos residuais (2-3 dias)

**Objetivo:** reduzir `orphan_node_count` de 4 → 0 em `planta_74`
através de filtro baseado em tamanho e contexto (não mais dedup).

| # | Tarefa | Tempo |
|---|---|---|
| 2.1 | Analisar overlay visual dos 4 órfãos residuais em `planta_74.pdf` | 2h |
| 2.2 | Se mobiliário/legenda: filtro "drop components de ≤2 nodes com bbox pequeno (<40px) fora do maior bounding box de rooms" | 4h |
| 2.3 | Se paredes reais perdidas: NÃO filtrar; bump do prioridade Fase 3 (DL oracle) | — |
| 2.4 | Teste: `planta_74` passa com `orphan_node_count == 0` | 1h |
| 2.5 | Validar não-regressão em `p12_red` + sintéticos | 2h |

**Bifurcação importante:** antes de assumir mobiliário, renderizar
cada órfão em overlay com a planta. Se for parede real (ex: um
closet estreito não detectado pelo Hough-threshold), filtro por
tamanho é regressão disfarçada.

---

## FASE 3 — Color-aware preprocessor (2-3 dias, baixa prioridade)

**Objetivo:** substituir `proto_red.py` hardcoded por módulo portável.

**Prioridade abaixo de Fases 1 e 2** porque o fix estrutural já funciona
sem K-means — só importa quando aparecer plantas sem red-mask.

| # | Tarefa | Tempo |
|---|---|---|
| 3.1 | Criar `preprocess/color_aware.py` com K-means 5 clusters | 4h |
| 3.2 | Identificação automática do cluster com walls (maior contraste com background) | 3h |
| 3.3 | Integrar em `main.py` como pré-Stage 2 (pré-ROI) | 2h |
| 3.4 | Deprecar `proto_red.py` → `archive/proto_red.py` | 30min |
| 3.5 | Fixture regressiva: `p12` rodando sem red-mask manual | 2h |
| 3.6 | Teste em `planta_74.pdf` — confirmar wall detection não piora | 2h |

---

## FASE 4 — DL Wall Oracle (10-15 dias, custo alto)

**Objetivo:** integrar CubiCasa5K Hourglass pretrained como pré-filtro
semântico quando Hough falhar em plantas sem red-mask.

**Custo real** (atualizado vs estimativa anterior de 5-7 dias):

| # | Tarefa | Tempo |
|---|---|---|
| 4.1 | Vendoring do repo CubiCasa5k em `vendor/CubiCasa5k` (NÃO install -e remoto) | 4h |
| 4.2 | Pipeline de download + SHA validation dos weights (offline-capable; não depender de Google Drive em runtime) | 1-2 dias |
| 4.3 | Arch correta `hg_furukawa_original` + softmax só em channels de rooms (B2-B4 da review) | 6h |
| 4.4 | Inference wrapper com padding múltiplo de 32 (não resize) | 4h |
| 4.5 | Skeleton path tracing com loops, 4-junctions, borders (B9 da review) | 2 dias |
| 4.6 | Fallback chain: DL > Hough + dedup (atual) | 4h |
| 4.7 | Benchmark tempo inference (alvo <10s/página CPU) | 2h |
| 4.8 | Teste `planta_74` + `p12` + 2-3 PDFs adicionais | 1 dia |
| 4.9 | Documentar licenças (CubiCasa5K, weights) + README | 4h |

**Entregável:** DL oracle como FALLBACK do Hough, não substituto.
`orphan_node_count == 0` em plantas sem red-mask.

---

## FASE 5 — Peitoril Detection Automático (2-3 dias)

**Objetivo:** substituir `pNN_peitoris.json` manual por detecção
automática.

| # | Tarefa | Tempo |
|---|---|---|
| 5.1 | Refatorar `proto_colored.py` em `preprocess/peitoris.py` | 3h |
| 5.2 | Pair detection (linhas finas paralelas curtas ortogonais ao wall) | 3h |
| 5.3 | PaddleOCR opcional pra labels "PEITORIL H=" (feature-flag) | 4h |
| 5.4 | Match altura do label OCR próximo | 2h |
| 5.5 | Integração em `main.py` antes de `detect_openings` | 2h |
| 5.6 | Testar em `planta_74` | 2h |

---

## FASE 6 — Ruby/SketchUp Bridge (2-3 dias)

**Objetivo:** reconstruir o bridge que consome `observed_model.json` e
gera `.skp`.

**Pré-requisito:** confirmar com Felipe fate de `E:\Sketchup V6.1` na
máquina dele (local, não no monorepo).

### Opção A — V6.1 existe em outra máquina → migrar
- Copiar V6.1 pra `skp_export/`, ajustar imports, testar com `observed_model.json` atual.
- ~1 dia.

### Opção B — V6.1 perdido → reconstruir
- Scaffold `skp_export/` (TCP socket bridge padrão mhyrr/sketchup-mcp).
- `place_door_component` com attributes (não scale).
- ~2-3 dias.

| # | Tarefa | Tempo |
|---|---|---|
| 6.1 | Confirmar fate V6.1 | 0 (pergunta) |
| 6.2 | Setup TCP listener Ruby em SketchUp Extension | 3h |
| 6.3 | Python MCP server → socket → Ruby | 4h |
| 6.4 | Paramétricas de porta via attributes | 4h |
| 6.5 | Teste end-to-end: PDF → JSON → .skp | 3h |
| 6.6 | Validar 7/7 portas `place_door_component` | 2h |

---

## Resumo agregado revisado

| Fase | Tempo | Entregável |
|---|---|---|
| 0 | 1-2 dias | Patches 02/03/04 aplicados, invariantes #4 #6 respeitadas |
| 1 | 3-5 dias | Topology consome openings (rooms semânticos) |
| 2 | 2-3 dias | `orphan_node_count == 0` em `planta_74` via filtro semântico |
| 3 | 2-3 dias | PDF-agnóstico (K-means em vez de red-mask), baixa prioridade |
| 4 | 10-15 dias | DL oracle CubiCasa5K vendor + weights CI + skeleton tracer |
| 5 | 2-3 dias | Peitoris automáticos (sem JSON manual) |
| 6 | 2-3 dias | Ruby bridge restaurado/reconstruído |
| **TOTAL** | **~22-37 dias** (**6-8 semanas** calendário) | Pipeline completo PDF → .skp |

**Com paralelização (múltiplos agents Claude, git worktrees):** redução para **4-6 semanas**.

**Sem DL (pular Fase 4, assumir fix estrutural + semantic filter suficiente):** **12-19 dias** (**2-4 semanas**).

---

## Ordem de prioridade recomendada

Se não puder fazer tudo, execute na ordem:

1. **Fase 0** (higiene). Sem isso, qualquer métrica nova continua semanticamente enganosa. Rápido, baixo risco.
2. **Fase 1** (opening-aware topology). Ataca o "rooms count = same but semantics different".
3. **Fase 2** (semantic filter). Acaba com os 4 órfãos residuais em `planta_74`.
4. **Fase 5** (peitoris). Elimina JSONs manuais, quality-of-life alto.
5. **Fase 6** (Ruby bridge). Torna o pipeline end-to-end utilizável.
6. **Fase 3** (color-aware). Só quando uma planta sem red-mask aparecer.
7. **Fase 4** (DL oracle). Só quando Hough + fix estrutural falharem em plantas novas.

---

## Métricas de sucesso por fase

| Fase | Métrica que deve mover | Baseline pós-fix | Meta |
|---|---|---|---|
| 0 | `roi.fallback_used` presente no JSON | ausente | sempre presente |
| 0 | `quality_score` exposto, retention separado | só `geometry` | ambos honestos |
| 1 | `rooms` semanticamente corretas | 16 (num igual ao pré-fix) | 16 validados 1-a-1 |
| 2 | `orphan_node_count` em `planta_74` | 4 | 0 |
| 3 | `p12_red` sem red-mask manual | precisa red-mask | detecção auto |
| 4 | wall IoU em plantas novas | — | ≥ 85% |
| 5 | peitoris auto-detectados | 0 | ≥ 80% |
| 6 | .skp gerado end-to-end | — | OK visual |

---

## Invariantes a respeitar (CLAUDE.md §6)

- **Não usar `strict=False`** em `load_state_dict` sem reportar keys ignoradas explicitamente (Fase 4).
- **Nada de F1-against-GT no extrator** — GT é contrato do consumer, não do pipeline (Fase 0 patch 03 corrigido).
- **`RoiResult.fallback_reason`** é campo estável v2.1.0 — não renomear, aditivos apenas (Fase 0 patch 04 corrigido).
- **`max_components_within_page`** (plural, count) é o nome real no `ConnectivityReport`. Usar `largest_component_ratio` direto quando o objetivo é a fração (Fase 0 patch 03 corrigido).

---

**Próximo passo:** [patches/README.md](../patches/README.md) explica
como aplicar cada patch com as correções da revisão.
