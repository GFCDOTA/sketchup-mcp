# SKP artifact layout — sketchup-mcp

Paths canônicos, naming e metadata pra `.skp` + sua evidência
visual / report. Complementa `memory/artifact_policy.md`.

## Estrutura

```
artifacts/
├── <plant>/                              ← deliverable canônico
│   ├── <plant>.skp                       ← THE deliverable
│   ├── <plant>.skp.metadata.json         ← consensus SHA256 sidecar
│   ├── <plant>_iso.png                   ← render iso (write_image)
│   ├── <plant>_top.png                   ← render top (write_image)
│   ├── side_by_side_pdf_vs_skp.png       ← overlay comparativo
│   ├── geometry_report.json              ← stats + gate self-check
│   └── README.md                         ← provenance
│
└── review/<plant>/                       ← evidência feature-specific
    ├── <feature_slug>.skp                ← SKP usado pra review
    ├── <feature_slug>_<view>.png         ← overlays / debug renders
    └── <feature_slug>_report.json        ← métricas da feature
```

## Naming

- `<plant>` em snake_case ou kebab-case minúsculo: `quadrado`,
  `planta_74`. Match com a fixture em `fixtures/<plant>/`.
- Arquivos no diretório do plant **prefixam** com `<plant>_` exceto
  `geometry_report.json` e `README.md` (singletons óbvios).
- Sub-diretório `review/<plant>/` carrega `<feature_slug>` no
  arquivo (ex.: `planta_74_stub_review.skp`,
  `wall_stub_debug_overlay.png`).

## Metadata mínima

### `<plant>.skp.metadata.json` (sidecar)

```json
{
  "consensus_path": "fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json",
  "consensus_sha256": "<64 hex>",
  "builder_version": "<git SHA do tools/build_plan_shell_skp.{py,rb}>",
  "built_at_utc": "2026-05-27T13:42:00Z",
  "su_version": "2026"
}
```

Função: cache key pra invalidação. Se `consensus_sha256` ou
`builder_version` mudarem, o SKP é stale.

### `README.md` (provenance)

Mínimo obrigatório:

```md
# <plant>

## Build provenance
- Input: `<consensus.json path>`
- Built: 2026-05-27
- Commit: <git SHA>

## Reproduce
```bash
python -m tools.build_plan_shell_skp \
  <consensus.json> \
  --out artifacts/<plant>/<plant>.skp
```

## Status
- room_fidelity: OK / WARN / FAIL (+ justificativa se WARN/FAIL)
- wall_fidelity: ...
- contract_tests: ...
```

## Promotion (run → artifact) — regra dura

Um `.skp` de `runs/` NUNCA é canônico. Pra virar deliverable:

1. Validar gates (contract tests verdes, gate self-check OK ou
   WARN justificado)
2. Copiar pro path canônico em `artifacts/<plant>/`
3. Gerar/atualizar metadata sidecar
4. Gerar side-by-side comparativo
5. Atualizar README de provenance
6. Commit + push + PR

## Exemplo vivo

Ver `artifacts/planta_74/` no repo. Estrutura real:

- `planta_74.skp`
- `planta_74.skp.metadata.json`
- `planta_74_iso.png`
- `planta_74_top.png`
- `side_by_side_pdf_vs_skp.png`
- `geometry_report.json`
- `README.md`

E `artifacts/review/planta_74/` carrega evidência da feature
FP-026 (stub review):

- `planta_74_stub_review.skp`
- `model_iso_stub_review.png`
- `model_top_stub_review.png`
- `wall_stub_debug_overlay.png`
- `wall_stub_report.json`
- `README.md`

## TODO — validar contra repo

- [ ] Confirmar schema de `<plant>.skp.metadata.json` atual (ler
      o arquivo em `artifacts/planta_74/`)
- [ ] Confirmar formato do `geometry_report.json` (campos
      obrigatórios)
- [ ] Decidir se `<plant>.skp.metadata.json` é gerado
      automaticamente pelo builder ou criado manualmente na
      promotion
