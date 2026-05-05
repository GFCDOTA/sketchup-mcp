# Post-merge E2E validation — 2026-05-05

> Validação end-to-end pós-merge do stack `develop@692a302` (10 PRs
> #25-#34) rodando o pipeline real em planta_74.pdf com as flags V1 e
> V5 ativadas. Pedido pelo reviewer (ChatGPT) como condição antes de
> qualquer próxima frente. Sem código novo, sem PR novo.

## Resultado

**Tudo verde.** Pipeline + smoke + inspector + métricas + pytest.

| Critério | Esperado | Obtido |
|---|---|---|
| Counts globais | 33 walls / 11 rooms / 12 openings / 8 soft_barriers | ✓ exato |
| V1: SALA DE ESTAR diag count | reduzido vs baseline | 6 → **3** |
| V1: SALA DE ESTAR diag total len | reduzido | 78.9 → **59.4 pt** |
| V4: A.S. width | < 100 pt | 75.71 pt ✓ |
| V4: A.S. ratio h/w | ≥ 2.0 | 2.339 ✓ |
| V2: TERRACO SOCIAL diag | sem regressão | 3 (mantido) |
| V5: kind_v5 em 100% das openings | sim | 12/12 (todos `door_arc`) |
| metadata stamps coexistem | V1 + V5 | ambos presentes |
| inspect_metrics is_clean | True | True |
| `default_faces_count` | 0 | 0 |
| `materials_count` | 13 canônicos | 13 |
| `wall_overlaps_count` | 0 | 0 |
| `components_count` (Sree leak) | 0 | 0 |
| pytest CI-mode | sem failed | 333 passed / 6 skipped / 0 failed |

## Comando único para reproduzir

```bash
OUT=runs/post_merge_e2e_2026_05_05
mkdir -p "$OUT"
python -m tools.build_vector_consensus planta_74.pdf \
    --out "$OUT/consensus.json" --detect-openings
python -m tools.extract_room_labels planta_74.pdf \
    --out "$OUT/labels.json"
python -m tools.rooms_from_seeds "$OUT/consensus.json" "$OUT/labels.json" \
    --out "$OUT/consensus_with_rooms.json" \
    --canonicalize-rooms --room-canonicalization-tol 8
python -m tools.extract_openings_vector planta_74.pdf \
    --consensus "$OUT/consensus_with_rooms.json" \
    --out "$OUT/consensus_with_openings.json" \
    --mode replace --classify-kind
python scripts/smoke/smoke_skp_export.py \
    --consensus "$OUT/consensus_with_openings.json" \
    --out-dir "$OUT" --force-skp --timeout 180
# Trigger inspector via autorun plugin (control file + relaunch SU)
python -m tools.inspect_metrics "$OUT/inspect_report.json"
```

## Artefatos no run dir (gitignored)

`runs/post_merge_e2e_2026_05_05/` contém o pacote completo com
`consensus_with_openings.json`, `preview_top.png`, `preview_axon.png`,
`model.skp`, `inspect_report.json`, `metrics.json`, e
`sidebyside_pdf_vs_skp.png` (3-panel: PDF | post-merge top | axon).
O `summary.md` daquele dir tem a tabela completa de validação.

## Por que isso importa

Os tests de unit e integration que entraram via #25, #27, #30, #32 e
#34 já provavam que cada peça funciona isolada e que V1+V5 coexistem
no nível de subprocess CLI. Esta validação E2E real sobre planta_74
fecha o último gap: o `.skp` físico produzido (`57 KB`, inspect
`is_clean=True`) confirma que o exporter Ruby ainda consome o
consensus enriquecido sem regressão visual ou estrutural.

Stack `develop@692a302` está, portanto, **pronto para uso operacional
em produção** assim que `develop → main` for promovido.

## Próxima frente real (per ChatGPT review)

Continua bloqueada por evidência V2: ou (a) flip de
`chrome://settings/content/automaticDownloads` permitindo
`discover.matterport.com` para Claude finalizar o download em batch,
ou (b) 2 prints manuais do tour Matterport (terraço top-down e
terraço FPV-interior) salvos em `references/matterport_74m2/02_*.png`
e `03_*.png`.

Sem essa evidência, qualquer ataque a `tools/rooms_from_seeds.py`
para corrigir o pentagon do TERRACO SOCIAL é especulação.

## Cross-links

- `docs/ops/post_merge_snapshot_2026-05-05.md` — inventário pós-merge
- `docs/tour/matterport_capture_failure_74m2.md` — bloqueios de captura V2
- `docs/learning/v5_opening_kind_enrichment.md` — V5 classifier rationale
- `docs/validation/skp_fidelity_2026-05-04.md` — baseline pré-stack
- `tests/test_v1_v5_pipeline_integration.py` — equivalent CLI test
