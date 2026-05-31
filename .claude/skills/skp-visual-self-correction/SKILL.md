---
name: skp-visual-self-correction
description: Use when a task generates an .skp and a visual review must happen before declaring progress. Triggers on `model.skp`, `model_top.png`, `model_iso.png`, "visual review", "visual findings", "FP-030", "Visual Oracle", `geometry_report.json`, `artifacts/review/.../final/`, or any PR that touches SKP generation and needs evidence that the build does not have floating doors, orphan glass, misplaced soft barriers, wall stubs, missing walls, or floor leaks. Implements Constitution #8 + FP-030. Skill rule: the user is NOT the visual regression detector.
---

# skp-visual-self-correction

Skill operacional pro **Visual Oracle Gate** (FP-030).
Detalhe completo em
[`docs/specs/FP-030_visual_oracle_gate.md`](../../../docs/specs/FP-030_visual_oracle_gate.md).

## Core rules

```text
No SKP, no progress.
No visual proof, no progress.
The user is not the visual regression detector.
```

## When to use

Auto-trigger após qualquer mudança SKP-affecting (mesmas paths
da Constitution #8). Especificamente:

- Builder (`tools/build_plan_shell_skp.{py,rb}`) mudou
- Consensus de uma planta alterado
- Routing de kind_v5 / openings / soft_barriers ajustado
- Schema de `geometry_report.json` evoluiu
- Promoção de novo baseline canônico

## Operating loop (5 passos)

### 1. Identificar baseline + consensus

```bash
ls fixtures/<plant>/consensus*.json
ls artifacts/<plant>/<plant>.skp  # baseline canonical, se houver
git rev-parse origin/develop
```

### 2. Rodar visual review

```bash
python -m tools.run_skp_visual_review \
  --fixture <plant> \
  --out artifacts/review/<plant>/<branch_or_pr> \
  --max-attempts 3
```

O script:
- Invoca `build_plan_shell_skp` (interactive mode — Hard Rule #4)
- Carrega `geometry_report.json`
- Aplica heurísticas determinísticas (`gates_self_check`,
  window count mismatch, floating door, orphan glass,
  bad window aperture, floor leak)
- Escreve `visual_findings.json` (schema v1)
- Promove SKP + renders + report pra
  `artifacts/review/<plant>/<run_id>/attempt_N/`
- Para early em PASS / WARN / FAIL_no_auto_fix
- Copia attempt final pra `final/` + escreve `regression_summary.md`

### 3. Review qualitativo (axes não-determinísticos)

`global_visual` e `scale_rotation` ficam como
**WARN: needs_human_or_agent_inline_review**. O agente deve:

- `Read` o `model_top.png` e `model_iso.png` no contexto
- Comparar com PDF underlay ou baseline anterior
- Decidir PASS / WARN / FAIL pra esses axes
- Editar `visual_findings.json` adicionando finding
  qualitativo (se houver) ou ajustando verdict do axis

### 4. Fix loop (se FAIL)

MVP **não auto-fix**. Se o script reporta FAIL:

- Ler `proposed_fix` em cada finding
- Validar com `suspected_owner` (builder vs opening_routing
  vs consensus)
- Aplicar fix source-supported (não inventar geometria)
- Rerun com `--max-attempts 3` (script naturalmente para no
  primeiro PASS/WARN)

### 5. Promover final

Após PASS ou WARN aceitável:

```bash
# artifacts já promovidos automaticamente em artifacts/review/<plant>/<branch>/final/
git add artifacts/review/<plant>/<branch>/final/
git add tools/run_skp_visual_review.py  # se mudou
git commit -m "evidence(<plant>): FP-030 visual review final = <verdict>"
```

## Hard rule

**Não peça ao usuário pra inspecionar screenshots antes do agente
ter gerado e inspecionado seus próprios artefatos.**

A regra existe porque ChatGPT bridge / vision API podem estar
offline / sem key. Em fallback, o agente CLAUDE INLINE (este aqui)
inspeciona via `Read` PNG. Inspeção do user é último recurso.

## Escalate apenas em RED

Pedir ajuda humana SÓ quando:

- SketchUp 2026 não disponível na máquina
- Headless runner / licença quebrada
- PDF / consensus ausente do repo
- Erro operacional (Python install, dep faltando)
- Fix requer julgamento arquitetônico / invenção de geometria

Formato do BLOCKED:

```
SKP Visual Review: BLOCKED
Attempt: <N>
Reason: <bloqueador específico>
Missing artifact: <o que falta>
Next command: <comando exato pro humano>
```

## Skills relacionadas

- [`generate-and-compare-skp-after-change`](../generate-and-compare-skp-after-change/SKILL.md)
  — superset; FP-030 é o "review visual" dentro do flow geral
- [`pdf-to-skp-pipeline`](../pdf-to-skp-pipeline/SKILL.md) — quem gera o `.skp`
- [`skp-artifact-management`](../skp-artifact-management/SKILL.md) — promotion + sidecar
- [`fidelity-review`](../fidelity-review/SKILL.md) — checklist humano original

## Oracle bridge mode (maturity 2+)

`--oracle chatgpt_bridge` activates the visual oracle bridge path.
The script:

1. Probes `localhost:8765/health` with 5s timeout
2. If reachable: POSTs 3 PNGs (b64) + minimal report context to `/ask`
3. Saves raw response to `final/visual_oracle_raw_response.json`
4. If unreachable: marks `oracle_status="unavailable"` and continues with deterministic-only (qualitative axes stay WARN)
5. With `--require-oracle`: bridge unreachable becomes BLOCKED

Without an active bridge, Claude inline becomes the visual reviewer
for qualitative axes (`global_visual`, `scale_rotation`).

## Maturity classification

Every run prints a maturity table in `regression_summary.md`. Honest
caps:

- Deterministic-only: **max ~70%**
- Bridge available + heuristics: **80–90%**
- **NEVER claim 100%**

## Confidence-tier rule (training data discipline)

Quando inspecionar exemplos em
`fixtures/visual_oracle_examples/manifest.json`, respeitar o
`confidence_tier` de cada entry:

- `bad_real_confirmed` → pode contribuir pra hard FAIL
- `bad_real_ambiguous` → **WARN only**, nunca hard FAIL
- `bad_synthetic_teaching` → didático, não golden absoluto
- `good_real_baseline` → strong PASS reference
- `good_synthetic_teaching` → didático positivo

Exemplos com `ambiguous_or_false_positive_regions` (e.g.
`bad_wall_stubs_*`) requerem cross-check com a FP-026 detector
(`tools/diagnose_wall_stubs.py`) antes de qualquer FAIL.

## Anti-padrões

- Declarar progress sem rodar `run_skp_visual_review`
- Aceitar `gates_self_check = true` como prova de fidelidade visual
- Marcar `global_visual` PASS sem ler PNGs inline
- Aplicar fix que inventa geometria pra "limpar" um FAIL
- Auto-fixar entre attempts sem source attribution
- Treinar hard FAIL a partir de `bad_real_ambiguous` (door jambs
  não são stubs)
