# Post-merge snapshot — 2026-05-05

> Consolidação pós-merge dos 10 PRs de Trilha A + B integrados em
> `develop` ao longo da sessão de 2026-05-04 → 2026-05-05. Snapshot
> exigido pela direção do reviewer (ChatGPT, browser session at
> `chatgpt.com/c/69f90cab-...`) antes de retomar codificação de feature.
>
> **Loaded by:** ninguém automaticamente — é um marcador histórico
> que registra o que `develop` ganhou neste ciclo. Próxima sessão deve
> abrir esta página antes de decidir Trilha A subsequente.

## Develop tip

```
692a302  Merge pull request #34 from GFCDOTA/test/v1-v5-integration-pipeline
```

23 commits ahead do tip anterior `55239fd`. Origin/develop atualizado;
local tracking limpo (`git status --short` = vazio).

## PRs mergeados (ordem real de merge)

| # | Branch | Mensagem do merge commit |
|---|---|---|
| 25 | skp/fidelity-return-pass | `0725932` test(skp): pin consume_consensus.rb fidelity-fix invariants |
| 26 | skp/regenerate-and-inspect-current-plan | `a572674` docs(validation): empirical SKP fidelity proof |
| 27 | ci/skp-fidelity-metrics | `6ce828e` ci(skp): add fidelity metric extractor for inspect_report.json |
| 28 | docs/matterport-visual-validation | `0760a5d` Docs/matterport visual validation |
| 29 | chore/ruff-rooms-from-seeds-imports | `4922547` refactor: clean rooms_from_seeds lint issues |
| 30 | skp/fix-v1-living-notch | `f740e3c` Skp/fix v1 living notch |
| 31 | skp/investigate-planta-74-clean | `c1b7504` vector: clarify rasterized PDF incompatibility |
| 32 | skp/v5-opening-kind-enrichment | `81a2d62` feat(openings): V5 schema-additive kind_v5 classifier (opt-in) |
| 33 | ci/skp-fidelity-gate | `f0c166a` ci(skp): add SKP Fidelity Gate paths-filtered workflow |
| 34 | test/v1-v5-integration-pipeline | `692a302` Test/v1 v5 integration pipeline |

PRs #33 e #34 precisaram **rebase** em `origin/develop` atualizado antes
do merge porque referenciavam tests/tools mergeados em #25, #27, #30 e
#32. Rebase + force-push, depois merge — sem conflito.

## Features agora disponíveis em develop

### V1 — SALA DE ESTAR diagonal canonicalize (opt-in)

```bash
python -m tools.rooms_from_seeds <consensus> <labels> \
    --canonicalize-rooms \
    --room-canonicalization-tol 8
```

Quando o flag está setado, polígonos de rooms têm vertices snapados ao
grid de eixos induzido pelas wall edges. Default OFF — pipeline antigo
inalterado. Stamp em `metadata.rooms_from_seeds.{canonicalize_rooms,
room_canonicalization_tol}`.

Resultado empírico em planta_74 (tol=8 pt): SALA DE ESTAR diagonal
count 6 → 3, total length 78.9 → 59.4 pt. Counts globais 33/11/12/8
preservados. A.S. (V4 invariant) mantém width<100pt + ratio>=2.

### V5 — opening kind enrichment (opt-in)

```bash
python -m tools.extract_openings_vector <pdf> \
    --consensus <out> \
    --classify-kind --mode replace
```

Adiciona dois campos opcionais por opening: `kind_v5` ∈
`{door_arc, open_passage, glazed_balcony, window}` e
`kind_v5_reason`. Default OFF. Existing `kind: door|window` field
preservado (schema-additive). Stamp em
`metadata.opening_kind_v5_classifier.{version, counts,
n_openings_input, n_openings_output}`.

Resultado em planta_74: 12/12 openings → `door_arc`. Conservador (não
inventa door_arc sem evidência svg_arc).

### V1 + V5 integration test

`tests/test_v1_v5_pipeline_integration.py` — 9 tests via subprocess
CLI exercitando o chain completo `build_vector_consensus +
extract_room_labels + rooms_from_seeds --canonicalize-rooms +
extract_openings_vector --classify-kind` em planta_74. Skipa em fresh
checkout (planta_74.pdf gitignored em CI).

### SKP fidelity gate (CI)

`.github/workflows/skp_fidelity_gate.yml` — paths-filtered workflow que
roda 3 jobs (`source-invariants`, `smoke-cheap-gates`, `ruby-syntax`)
quando uma PR toca o exporter Ruby, o metric extractor, ou a vector
pipeline. 5 successful checks na PR de origem.

### `tools.inspect_metrics`

Extractor que condensa `inspect_walls_report.rb` JSON (~35 KB) nas 8
métricas de fidelidade SKP. CLI:

```bash
python -m tools.inspect_metrics <inspect_report.json>          # exit 0 if clean
python -m tools.inspect_metrics --before <a> --after <b>       # delta table
```

### `tools.canonicalize_room_polygons`

Helper Python pure (stdlib + types only) que faz vertex-snap a
wall-induced axis grid. Opt-in via CLI flag em `tools.rooms_from_seeds`,
mas reutilizável programaticamente:

```python
from tools.canonicalize_room_polygons import canonicalize_rooms
consensus["rooms"] = canonicalize_rooms(rooms, walls, t, tol_pts=8.0)
```

### `tools.classify_opening_kind`

Helper Python pure que classifica openings em `kind_v5`:

```python
from tools.classify_opening_kind import classify_openings
classify_openings(consensus)   # in-place, schema-additive
```

### Diagnostic: rasterized PDF detection

`tools.build_vector_consensus` agora reporta diagnóstico claro quando
o PDF não tem path objects:

```
[err] PDF appears rasterized; vector pipeline incompatible.
      drawings=0 page_size=856x1212 mode=raster-like.
      Use the raster pipeline (`python main.py extract <pdf>`) or
      supply a vector PDF whose walls are filled paths.
```

E quando há paths mas o wall extractor rejeita todos:

```
[err] no wall paths detected.
      drawings=N filled_only=K stroked_only=M page_size=WxH.
      ...possibly stroke-based walls or a different fill color.
      See docs/learning/planta_74_clean_compatibility.md.
```

## Novas flags / endpoints

| Flag | Em | Default |
|---|---|---|
| `--canonicalize-rooms` | `tools/rooms_from_seeds.py` | OFF |
| `--room-canonicalization-tol <float>` | `tools/rooms_from_seeds.py` | 8.0 |
| `--classify-kind` | `tools/extract_openings_vector.py` | OFF |

## Novos arquivos

```
tools/canonicalize_room_polygons.py     V1 helper
tools/classify_opening_kind.py          V5 classifier
tools/inspect_metrics.py                fidelity metric extractor
.github/workflows/skp_fidelity_gate.yml CI gate
docs/learning/planta_74_clean_compatibility.md
docs/learning/v5_opening_kind_enrichment.md
docs/validation/skp_fidelity_2026-05-04.md
docs/tour/matterport_visual_findings_74m2.md (revised)
docs/tour/matterport_capture_failure_74m2.md
docs/tour/matterport_photo_inventory_74m2.md
references/matterport_74m2/01_living_room_official.jpg
scripts/investigation/planta_74_clean_diff.py
tests/test_consume_consensus_regression.py
tests/test_inspect_metrics.py
tests/test_living_terraco_shape_canonicity.py
tests/test_classify_opening_kind.py
tests/test_v1_v5_pipeline_integration.py
tests/test_vector_consensus_rasterized_input.py
```

## Validações finais

```
git status --short                      → vazio
git log --oneline -1                    → 692a302 Merge PR #34
gh-api pulls?state=open                 → 0
pytest -q [+ CI deselects]              → 333 passed / 6 skipped / 0 failed
pytest -q (no deselects)                → 17 failed (TODOS pré-existentes
                                          em CLAUDE.md §10:
                                          test_planta_74_regression
                                          test_text_filter
                                          test_pair_merge
                                          test_orientation_balance
                                          test_oracle / cubicasa)
ruff check tools tests scripts          → 81 errors (legado em outros
                                          módulos; código novo deste
                                          ciclo passa ruff clean)
```

`333 passed` = 286 baseline + 47 tests novos (3 + 5 + 16 + 3 + 11 + 9
das 6 PRs que adicionaram tests).

## Estado dos defeitos visuais (V1 / V2 / V4 / V5 / D3)

| Defeito | Estado | Como destravar |
|---|---|---|
| **V1** SALA DE ESTAR mordida diagonal | **Corrigido (opt-in)** via `--canonicalize-rooms`. 16 unit/integration + 9 V1+V5 integration tests pinned em CI. | Default-ON ainda não — aguarda V2 evidência + 2-3 plantas validadas. |
| **V2** TERRACO SOCIAL pentagonal | **Pending evidence**. Matterport tour visualizado mas Chrome multi-download policy bloqueia download em lote. 1 foto persistida (Living Room). | User flip `chrome://settings/content/automaticDownloads` permitindo `discover.matterport.com` → JS bundle download finaliza 11 fotos restantes. OU 2 prints manuais (top-down terraço, FPV terraço-interior). |
| **V4** A.S. proporção | **Confirmed correto**. Matterport FPV mostra A.S. é genuinamente faixa estreita vertical. Pinned por `test_v4_as_stays_narrow` (width<100pt + ratio>=2). | (não atacar) |
| **V5** openings finas | **Explicado + enriquecido (opt-in)** via `--classify-kind` (4 classes: door_arc, open_passage, glazed_balcony, window). Schema-additive. | Default-ON ainda não — Ruby render branch em `tools/consume_consensus.rb` precisa explicit human approval (CLAUDE.md §1.4) para usar `kind_v5`. |
| **D3** floor whitespace em outras plantas | **Cleared on planta_74**, não testado em outras (planta_74_clean é raster, test_plan é synthetic raster). | Atacar quando uma planta vetorial real adicional estiver disponível. |
| **planta_74_clean.pdf** incompatibility | **Diagnosticado** como PDF rasterizado puro (0 paths). Mensagem de erro clara emite no extractor. | (caso fechado) |

## Próximos passos recomendados

Per direção do ChatGPT no chat: **uma fase curta de consolidação**
(este snapshot) e depois retomar Trilha A. As únicas opções reais que
sobram são:

1. **V2 — capturar evidência Matterport** (alto valor, depende do
   user). Sem isso, não há base pra atacar TERRACO pentagonal em
   `tools/rooms_from_seeds.py`.
2. **V5 Ruby render semantics** (alto valor de produto, mas mexe em
   `tools/consume_consensus.rb` — CLAUDE.md §1.4 forbidden zone, precisa
   explicit human approval). Adicionaria branch no exporter por
   `kind_v5` para renderizar `glazed_balcony` como sliding glass +
   `open_passage` como wall break sem door symbol.
3. **wall-gap detector** (gera `geometry_origin: "wall_gap"` no
   classifier; produz openings de tipo `open_passage`). Médio risco —
   nova heurística no extractor. Útil em plantas com passagens abertas
   sem arc symbols.
4. **Default-ON do `--canonicalize-rooms`**. Bloqueado por (1):
   precisa V2 evidência + 2-3 plantas validadas.

Recomendação para a próxima sessão: **(1) primeiro**. Sem
evidência V2 persistida, qualquer ataque a TERRACO em
`rooms_from_seeds.py` é cego. (2) e (3) ficam dependentes
operacionalmente.

## Cross-links

- `CLAUDE.md` §0 (git flow inviolável), §1 (hard safety rules), §3 (SU is the last gate), §10 (baseline planta_74)
- `OVERVIEW.md` §4.4 (pipeline vetorial completo, agora documentado com flag opt-in V1)
- `docs/validation/skp_fidelity_2026-05-04.md` — empirical SKP fidelity proof
- `docs/learning/v5_opening_kind_enrichment.md` — V5 rationale + classifier table
- `docs/learning/planta_74_clean_compatibility.md` — raster PDF diagnostic
- `docs/tour/matterport_visual_findings_74m2.md` — V1/V2/V4/V5 verdicts
- `docs/tour/matterport_capture_failure_74m2.md` — Chrome multi-download bloqueio + workarounds
