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

Schema real produzido por `tools/build_plan_shell_skp.py`
(`write_metadata`), com extensão pra artifact promovido:

```json
{
  "schema_version": "1.0.0",
  "exporter": "build_plan_shell_skp",
  "consensus_sha256": "<64 hex>",
  "skp_path": "artifacts/<plant>/<plant>.skp",
  "source_run_path": "runs/<plant>/<plant>.skp",
  "created_at": "2026-05-27T13:42:00Z",
  "sketchup_path": "C:\\Program Files\\SketchUp\\SketchUp 2026\\SketchUp\\SketchUp.exe",
  "command": "<exact command used to invoke SU>"
}
```

**Função**: cache key pra invalidação. `should_skip()` em
`build_plan_shell_skp.py` compara `consensus_sha256` + `exporter`
tag. Se qualquer um diverge da build atual, o `.skp` é stale e o
build re-executa.

**Promotion SOP**: o `write_metadata()` produzido pelo builder
escreve `skp_path` apontando pro path do build (geralmente
`runs/<plant>/<plant>.skp`). Ao promover pra `artifacts/<plant>/`,
**rewrite o sidecar**:

- `skp_path` ← path canônico do artifact (`artifacts/<plant>/<plant>.skp`)
- `source_run_path` ← path original do build (`runs/<plant>/<plant>.skp`)
- demais campos preservados

Sem esse rewrite, o sidecar canônico aponta pra `runs/` —
contradição com a regra "`runs/` é scratch, `artifacts/` é
deliverable" (Constitution #1, `memory/artifact_policy.md`).

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

## Schema status (2026-05-27)

- ✅ `<plant>.skp.metadata.json` schema confirmado em
  `tools/build_plan_shell_skp.py` (`write_metadata` linha ~611).
  Resolvido por audit P1 desta data: extensão com `source_run_path`
  pra distinguir build path vs canonical path.
- ✅ `geometry_report.json` schema mapeado em
  `specs/fidelity_gate.md` § "Campos relevantes". Top-level keys:
  `plan_shell`, `floor_groups`, `soft_barrier_groups`, `totals`,
  `groups_diagnostic[]`, `shell_stats_from_python`, `gates_self_check`.
- ✅ Decisão: sidecar é **gerado automaticamente** pelo builder
  (campo `skp_path` aponta pro build path em `runs/`). Promotion
  pra `artifacts/<plant>/` **deve rewrite** o sidecar pra apontar
  `skp_path` ao path canônico e adicionar `source_run_path`. Esse
  rewrite é manual hoje — TODO produto: automatizar via
  `tools/promote_artifact.py` (não criado ainda).

## TODO follow-ups

- [ ] Criar `tools/promote_artifact.py` que faz cp + sidecar rewrite
      + provenance README stub de uma vez
- [ ] Bump `schema_version` pra `1.1.0` quando `source_run_path`
      virar campo padrão (depende do builder também passar a
      escrever)
