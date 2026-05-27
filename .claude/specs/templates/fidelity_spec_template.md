# Fidelity spec: <plant> @ <YYYY-MM-DD>

> Template para documentar o veredito de fidelidade de um build
> SKP de uma planta. Vai pro `artifacts/<plant>/README.md` ou
> spec dedicado em `docs/specs/fidelity_<plant>_<date>.md`.
> Apagar este aviso ao usar.

## Build provenance

- **Input consensus**: `fixtures/<plant>/<consensus>.json`
- **Consensus SHA256**: `<64 hex>` (deve bater com sidecar)
- **Built**: `<YYYY-MM-DDTHH:MM:SSZ>`
- **Builder commit**: `<git SHA do tools/build_plan_shell_skp.{py,rb}>`
- **SU version**: `2026`

## Reproduce

```bash
python -m tools.build_plan_shell_skp \
  fixtures/<plant>/<consensus>.json \
  --out runs/<plant>/<plant>.skp
# Promote → artifacts/<plant>/ (ver skill skp-artifact-management)
```

## Eixo 1 — `gates_self_check` (machine-readable)

| Gate | Valor | Status |
|---|---|---|
| `plan_shell_group_exists` | `true` / `false` | ✅ / ❌ |
| `wall_shell_is_single_group` | `true` / `false` | ✅ / ❌ |
| `floors_separated_from_walls` | `true` / `false` | ✅ / ❌ |
| `default_material_faces_zero` | `true` / `false` | ✅ / ❌ |

Qualquer `false` = não promove pra `artifacts/`.

## Eixo 2 — Rubric humano (Camada 3)

Aplicar [`evals/fidelity_rubric.md`](../../evals/fidelity_rubric.md):

### Dimensão A — Walls

- **A1** (walls extrudadas): OK / WARN / FAIL — <justificativa>
- **A2** (sem stubs residuais): OK / WARN / FAIL — <justificativa>
- **A3** (sem notches / slivers): OK / WARN / FAIL — <justificativa>

### Dimensão B — Rooms

- **B1** (closed cells): OK / WARN / FAIL — <justificativa,
  incluir lista de cells fundidos open-plan se WARN>
- **B2** (labels preservados): OK / WARN / FAIL

### Dimensão C — Openings

- **C1** (`kind_v5` routing): OK / WARN / FAIL
- **C2** (soft barriers != parede cheia): OK / WARN / FAIL
- **C3** (`geometry_origin = wall_gap` respeitado): OK / WARN / FAIL

### Dimensão D — Visual / dimensional

- **D1** (side-by-side bate): OK / WARN / FAIL — <% discrepância
  e onde>
- **D2** (dimensões batem com PDF ±2%): OK / WARN / FAIL —
  <medidas comparadas>

## Veredito final

- **PASS**: todas as dimensões em OK
- **PASS com WARN**: WARN justificado em B / D — pode promover
- **FAIL**: 1+ FAIL — bloqueia promotion

Veredito desta build: **<PASS / PASS com WARN / FAIL>**

## Anomalias / observações

<O que reviewer humano notou que não cabe em A–D mas merece registro.>

## Comparison vs build anterior

| Métrica | Build anterior (<SHA>) | Esta build | Δ |
|---|---|---|---|
| `floor_groups.count` | N | N' | ±0 / +X / -X |
| `shell_stats_from_python.input_walls` | N | N' | ±0 / +X / -X |
| `gates_self_check` fails | N | N' | ±0 / +X / -X |

## Artefatos relacionados

- `artifacts/<plant>/<plant>.skp`
- `artifacts/<plant>/<plant>_iso.png`
- `artifacts/<plant>/<plant>_top.png`
- `artifacts/<plant>/side_by_side_pdf_vs_skp.png`
- `artifacts/<plant>/geometry_report.json`
- `artifacts/<plant>/planta_74.skp.metadata.json`
