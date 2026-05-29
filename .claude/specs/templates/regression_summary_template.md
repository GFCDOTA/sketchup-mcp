# SKP Proof-of-Progress Summary — <change-slug>

> Template do `regression_summary.md` exigido pelo
> [`specs/skp_proof_of_progress_gate.md`](../skp_proof_of_progress_gate.md).
> Copiar pra `artifacts/review/<plant>/<cycle_or_pr>/regression_summary.md`,
> preencher, apagar este aviso + os `<placeholders>`.

## Change

<1-2 frases. O que a PR muda no comportamento do builder / renderer
/ artifact. Não copiar o título do PR — escrever a intenção
arquitetônica, ex.: "Reduz width tolerance pra detectar wall stubs
mais finos que LL-017 threshold antigo deixava passar.">

## Canonical input

- **PDF**: `<path/to/plant>.pdf` (se aplicável)
- **Consensus**: `fixtures/<plant>/<consensus>.json`
  - SHA256: `<64 hex>`
- **Builder commit before**: `<git SHA>`
- **Builder commit after**: `<git SHA>`
- **SU version**: `2026`

## Artifacts

### Before

- **SKP**: `<path or "see <baseline_ref>">`
- **Top render**: `<path>`
- **Iso render**: `<path>`
- **Geometry report**: `<path>`
- **Fidelity report**: `<path or "none">`

> Se o baseline já é o canonical em `artifacts/<plant>/`, referenciar
> path + commit SHA aqui; **não duplicar arquivos**.

### After

- **SKP**: `artifacts/review/<plant>/<cycle>/<plant>_after.skp`
- **Top render**: `artifacts/review/<plant>/<cycle>/model_top_after.png`
- **Iso render**: `artifacts/review/<plant>/<cycle>/model_iso_after.png`
- **Geometry report**: `artifacts/review/<plant>/<cycle>/geometry_report_after.json`
- **Fidelity report**: `<path or "none">`

### Side-by-side

- **Composite**: `artifacts/review/<plant>/<cycle>/side_by_side_before_after.png`
  (se gerado)

## Before / After comparison

> **Regra anti-checklist-theater**: cada axis exige evidência
> **específica e concreta**. "PASS — ok" não conta; equivale a
> WARN. Use `N/A — <razão>` quando a PR comprovadamente não
> toca essa área.

| Eixo | Before | After | Verdict | Evidência específica |
|---|---|---|---|---|
| `wall_fidelity` | <stats / count> | <stats / count> | PASS/WARN/FAIL/N-A | <frase concreta: count exato, regiões do render, comparação> |
| `door_fidelity` | <count + routing> | <count + routing> | PASS/WARN/FAIL/N-A | <frase concreta> |
| `window_fidelity` | <count + peitoril ok?> | <count + peitoril ok?> | PASS/WARN/FAIL/N-A | <frase concreta> |
| `room_fidelity` | <cell count + labels> | <cell count + labels> | PASS/WARN/FAIL/N-A | <frase concreta> |
| `scale_rotation` | <dim deltas vs PDF> | <dim deltas vs PDF> | PASS/WARN/FAIL/N-A | <frase concreta> |
| `global_visual` | <qualidade side-by-side> | <qualidade side-by-side> | PASS/WARN/FAIL/N-A | <frase concreta com referência à imagem> |
| `gates_self_check` | <4 booleans> | <4 booleans> | PASS/WARN/FAIL | os 4 nomes + valores; FAIL = regressão true→false |

Exemplo bom (evidência específica):

```
wall_fidelity | 35 walls, 0 slivers | 35 walls, 0 slivers | PASS |
top render mostra L-shell externa contínua sem stubs; comparado
ao baseline <SHA>, regiões NW e SE limpas; FP-026 invariant preservado.
```

Exemplo ruim (checklist theater — REJEITAR em review):

```
wall_fidelity | ok | ok | PASS | ok
```

### Counts diff (do `geometry_report.json`)

| Métrica | Before | After | Δ |
|---|---|---|---|
| `input_walls` | | | |
| `openings_carved` | | | |
| `window_apertures_3d` | | | |
| `floor_groups.count` | | | |
| `soft_barrier_groups.count` | | | |
| `soft_barrier_groups.skipped_count` | | | |
| `slivers_removed` | | | |
| `endpoints_free` | | | |
| `endpoints_junction` | | | |

### Group counts in SKP (do `groups_diagnostic[]`)

| Group prefix | Before | After | Δ |
|---|---|---|---|
| `PlanShell_Group` | | | |
| `Floor_Group` | | | |
| `WindowGlass_Group` | | | |
| `DoorLeaf_Group` | | | |
| `GlazedBalcony_Group` | | | |
| `SoftBarrier_Group` | | | |

## Improvement claimed

<O que o PR body promete melhorar. Citar literalmente se possível.>

## Improvement proven?

**PASS / WARN / FAIL**

<Por quê. Evidência específica: "Antes do fix, `slivers_removed` = 3;
depois, = 0. Side-by-side mostra 3 stubs no canto inferior direito
desaparecidos.">

## Regressions

<Lista. Cada regressão deve ter:>

- **Onde**: <eixo + localização no SKP/render>
- **Severidade**: critical / acceptable
- **Justificativa** (se acceptable): <por quê é OK aceitar>

OU: `none observed`

## Remaining issues

<WARNs / FAILs que continuam apesar desta PR. Cada um:>

- **Issue**: <descrição>
- **Tracked in**: <PR/issue/spec onde será atacado, ou "backlog">

## Final verdict

**PASS / WARN / FAIL**

<Uma frase justificando. Se WARN ou FAIL, explicar se a PR ainda
pode mergear (com justificativa) ou se bloqueia.>

## Reproducibility

```bash
# Comando exato pra regerar o artifact after a partir do
# commit head desta PR
git checkout <branch-head-SHA>
python -m tools.build_plan_shell_skp \
  fixtures/<plant>/<consensus>.json \
  --out runs/<plant>/<plant>.skp
# + promotion steps (ver skill skp-artifact-management)
```
