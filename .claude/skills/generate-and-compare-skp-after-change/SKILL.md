---
name: generate-and-compare-skp-after-change
description: Use AFTER any change that affects (or claims to affect) .skp generation, walls, openings, rooms, fidelity reports, geometry reports, renderer, artifact policy, consensus schema, or visual validation. Triggers on phrases like "melhora fidelity", "corrige wall", "corrige janela", "corrige room", "corrige artifact", "melhora SKP", "fix routing", or any PR body claiming improvement to the architectural model. Generates new .skp + renders, compares against baseline, promotes evidence to artifacts/review/. Enforces "No SKP, no progress" rule. Do NOT trigger for pure docs/CI/.claude/ changes.
---

# generate-and-compare-skp-after-change

Skill operacional que implementa o **SKP Proof-of-Progress Gate**.
Detalhe completo do contrato em
[`specs/skp_proof_of_progress_gate.md`](../../specs/skp_proof_of_progress_gate.md).

## Quando usar

Auto-trigger após qualquer mudança que toque (ou alegue tocar):

- `tools/build_plan_shell_skp.{py,rb}`
- `fixtures/<plant>/*.json` (consensus)
- `tools/su_runner_safety.py` ou outros tools/ que afetem build
- Schema de `geometry_report.json`
- Renderer (Ruby `write_image`, side-by-side composer)
- `artifacts/<plant>/*` quando mudança é "promoção de baseline novo"

Heurística rápida pra PR body:

| Frase no body | Aplica? |
|---|---|
| "corrige wall stub" | ✅ |
| "ajusta opening routing" | ✅ |
| "novo kind_v5" | ✅ |
| "melhora room fidelity" | ✅ |
| "refresh planta_74" | ✅ |
| "promove canonical" | ✅ |
| "typo em README" | ❌ |
| "atualiza .claude/" | ❌ |
| "test: pin invariant" | ❌ (sem mudar comportamento) |

Em dúvida: aplica.

## Quando NÃO usar

Mudanças **puramente** textuais ou infra que não afetam o modelo:

- Docs / README / comments
- CI sem mudar build
- `.claude/` (knowledge base operacional)
- `.gitignore` / `pyproject.toml` metadata sem afetar deps
- Refactor com prova de equivalência (teste mostrando
  byte-equivalent OU report-equivalent)
- Adição de teste pinando invariante já satisfeito (PR #195
  style)

## Fluxo (5 passos)

### 1. Identificar baseline

```bash
# Consensus a usar
ls fixtures/<plant>/consensus*.json

# SKP baseline
ls artifacts/<plant>/<plant>.skp

# Commit base
git rev-parse origin/develop
```

### 2. Build novo

Modo `interactive` (Hard Rule #4 — nunca `--mode headless` em dev):

```bash
python -m tools.build_plan_shell_skp \
  fixtures/<plant>/<consensus>.json \
  --out runs/<plant>/<plant>.skp
```

Produz em `runs/<plant>/`:

- `<plant>.skp`
- `<plant>_iso.png`, `<plant>_top.png`
- `geometry_report.json`
- `<plant>.skp.metadata.json`

### 3. Comparar antes/depois

Carregar os dois `geometry_report.json` e diffar:

```python
import json
before = json.load(open("artifacts/<plant>/geometry_report.json"))
after  = json.load(open("runs/<plant>/geometry_report.json"))

# Counts
for k in ("input_walls", "openings_carved", "window_apertures_3d",
          "slivers_removed"):
    b = before["shell_stats_from_python"][k]
    a = after["shell_stats_from_python"][k]
    print(f"{k}: {b} -> {a} ({'=' if a == b else '!'})")

# Gates
for gate, val in after["gates_self_check"].items():
    bval = before["gates_self_check"].get(gate)
    print(f"{gate}: {bval} -> {val}")

# Group counts
def count_groups(rep):
    out = {}
    for g in rep["groups_diagnostic"]:
        prefix = g["name"].rsplit("_", 1)[0]
        out[prefix] = out.get(prefix, 0) + 1
    return out
print("groups:", count_groups(before), "->", count_groups(after))
```

Visual: lado-a-lado das duas top renders. Side-by-side composer
(quando existir como tool dedicado) ou comparação manual no
review.

### 4. Escrever `regression_summary.md`

Usar [`specs/templates/regression_summary_template.md`](../../specs/templates/regression_summary_template.md)
como esqueleto. Preencher:

- Mudança em 1-2 frases
- Inputs canônicos (PDF, consensus, builder commit before/after)
- Paths dos artifacts before/after
- Tabela de comparação por eixo (wall/door/window/room/scale/visual)
- "Improvement claimed" vs "Improvement proven"
- Regressões (ou "none")
- Veredito final: PASS / WARN / FAIL

### 5. Promover artefatos

```bash
CYCLE="<branch-slug>"   # ex.: feat-fp028-...
PLANT="planta_74"
DIR="artifacts/review/${PLANT}/${CYCLE}"

mkdir -p "$DIR"
cp runs/${PLANT}/${PLANT}.skp           "$DIR/${PLANT}_after.skp"
cp runs/${PLANT}/${PLANT}_top.png       "$DIR/model_top_after.png"
cp runs/${PLANT}/${PLANT}_iso.png       "$DIR/model_iso_after.png"
cp runs/${PLANT}/geometry_report.json   "$DIR/geometry_report_after.json"
# regression_summary.md preenchido manualmente
# baseline before/* só se NÃO existir no canonical artifact
# (caso contrário, referenciar artifacts/<plant>/* no summary)

git add "$DIR/"
git commit -m "evidence(<plant>): proof-of-progress for <change>"
```

## Critério "feito"

Sucesso requer TODAS as 5:

1. `<plant>_after.skp` em `artifacts/review/<plant>/<cycle>/`
2. Renders `top` + `iso` after
3. `regression_summary.md` com veredito final
4. Sem regressão crítica não-justificada
5. Objetivo declarado da PR visível no artifact final (não só
   nos números)

## Bloqueio legítimo

Se não conseguir gerar (SU indisponível, Python quebrado, etc.),
registrar no PR body:

```
SKP Proof-of-Progress Gate: BLOCKED
Reason: <bloqueador específico>
Missing artifact: <o que não foi gerado>
Next command to run: <comando exato pro humano>
```

Sem build = não merge, exceto override humano explícito.

## Anti-padrões

- Declarar "fix" sem regenerar SKP
- Deixar `.skp` apenas em `/runs/` (gitignored)
- Trocar baseline canônico sem `regression_summary.md`
- Promover artifact sem rewrite do sidecar (ver
  [`skp-artifact-management/SKILL.md`](../skp-artifact-management/SKILL.md))
- Comparar contagem mas pular visual side-by-side
- "Improvement claimed" sem "Improvement proven"

## Skills relacionadas

- [`pdf-to-skp-pipeline/SKILL.md`](../pdf-to-skp-pipeline/SKILL.md) — quem gera o `.skp`
- [`skp-artifact-management/SKILL.md`](../skp-artifact-management/SKILL.md) — paths + sidecar
- [`fidelity-review/SKILL.md`](../fidelity-review/SKILL.md) — rubric pra review humano
- [`repo-governance/SKILL.md`](../repo-governance/SKILL.md) — PR mechanics
