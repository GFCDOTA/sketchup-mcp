# SKP Proof-of-Progress Gate

> Também conhecido como: **No SKP, no progress** · FP-028 · LL-021.
> Esta spec é a fonte canônica da regra. Bootloader importa.

## Frase-regra

> **No SKP, no progress.**
>
> Se a mudança promete melhorar o modelo, mas não gera um `.skp`
> novo comparável em pasta human-facing, ela não pode ser
> considerada melhoria concluída.

## Problem

Estamos fazendo melhorias no pipeline `consensus.json → .skp` em
ritmo razoável, mas o gate de avanço real é frágil:

- Correção técnica pode "parecer ok" pelas métricas
  (`gates_self_check = true`) e ainda regredir visualmente.
- Render PNG bonito sozinho não prova fidelidade — o humano abre
  o `.skp` no SketchUp.
- `.skp` em `/runs/` é scratch (gitignored). Não serve pra
  revisão humana nem pra trilha histórica.
- Já tivemos casos onde uma correção de wall stub levantou
  hipótese de regressão de openings que só foi descartada quando
  rodamos um build novo e comparamos contagens (2026-05-27,
  pós PR #194).

A constituição já diz "SKP é o artefato principal" (#1) e "sem
`.skp` versionado, não há sucesso canônico" (#2). Esta spec
operacionaliza essas duas regras pra qualquer PR que toque
fidelidade arquitetônica.

## Quando este gate aplica

Aplica a **qualquer alteração** que toque ou alegue tocar:

- Geração de `.skp` (`tools/build_plan_shell_skp.{py,rb}`)
- Walls / wall shell / stubs / canonicalização
- Openings — portas, janelas, glazed_balcony, kind_v5 routing
- Rooms / floors / labels / soft_barriers
- Fidelity reports (`geometry_report.json`)
- Renderer (Ruby `write_image`, side-by-side composer)
- Artifact policy (paths, naming, sidecar schema)
- Consensus schema usado pelo build
- Builder Python OU Ruby
- Validação visual

**Heurística PR body**: se o body mencionar "melhora fidelity",
"corrige wall", "corrige janela", "corrige room", "corrige
artifact", "melhora SKP", ou similar, este gate **aplica**.

## Quando NÃO aplica

Não aplica a mudanças puramente textuais ou infra que **não
afetam o modelo**:

- Typo em docs / README / comments
- CI / workflows sem mudar build behaviour
- Refactor com prova de equivalência (testes mostram
  byte-equivalent ou report-equivalent output)
- Mudança em `.claude/` (documentação operacional do agente)
- Mudança em `.gitignore` / `.github/` / `pyproject.toml`
  metadata sem afetar deps
- Adição de teste que pina invariante já satisfeito (defense-in-
  depth puro — ver PR #195)

Em dúvida: aplica. Custo de gerar SKP novo é baixo (~30-60s),
custo de não ter prova de progresso é alto.

## Artefatos obrigatórios

Após cada alteração relevante, gerar e versionar em pasta
human-facing/reviewable:

```
artifacts/review/<plant>/<cycle_or_pr>/
├── <plant>_after.skp                  ← obrigatório
├── <plant>_before.skp                 ← se aplicável (ou referenciar)
├── model_top_after.png                ← obrigatório
├── model_top_before.png               ← se aplicável
├── model_iso_after.png                ← obrigatório
├── model_iso_before.png               ← se aplicável
├── side_by_side_before_after.png      ← obrigatório quando possível
├── geometry_report_after.json         ← obrigatório
├── geometry_report_before.json        ← se aplicável
├── fidelity_report_after.json         ← se existir
├── fidelity_report_before.json        ← se existir
└── regression_summary.md              ← obrigatório
```

**Não duplicar `.skp before` à toa.** Se o baseline já mora em
`artifacts/<plant>/<plant>.skp` (canonical promovido) ou num
artifact review anterior, **referenciar o path + commit SHA**
no `regression_summary.md` em vez de copiar.

## Separação de pastas (reforça `artifact_policy.md`)

| Path | Quem olha | Status |
|---|---|---|
| `artifacts/<plant>/` | Humano (deliverable canônico) | Tracked |
| `artifacts/review/<plant>/<cycle_or_pr>/` | Humano (evidência de PR) | Tracked |
| `artifacts/internal/` | Agente (intermediários, debug) | Tracked (se existir) |
| `runs/<plant>/` | Agente (scratch local) | **Gitignored** |
| `fixtures/<plant>/` | Pipeline (input canônico) | Tracked |
| `docs/specs/` | Humano (specs FP-NNN) | Tracked |

**Nunca** deixar o único `.skp` relevante a uma PR apenas em
`/runs/`. Promover obrigatoriamente pra `artifacts/review/<plant>/<cycle_or_pr>/`
(ou pra `artifacts/<plant>/` se for substituir baseline canônico).

## Fluxo obrigatório

Para qualquer PR coberta por este gate:

### 1. Identificar baseline

- Consensus usado: `fixtures/<plant>/...`
- PDF de referência: `<plant>.pdf` no raiz ou doc
- SKP baseline: `artifacts/<plant>/<plant>.skp` (canonical promovido)
  ou último review SKP relevante
- Commit base: SHA de `origin/develop` na criação da branch

### 2. Rodar o build novo

```bash
python -m tools.build_plan_shell_skp \
  fixtures/<plant>/<consensus>.json \
  --out runs/<plant>/<plant>.skp
```

Gera: `<plant>.skp`, `<plant>_iso.png`, `<plant>_top.png`,
`geometry_report.json`, `<plant>.skp.metadata.json`.

### 3. Comparar antes/depois

Eixos mínimos (cf. [`evals/fidelity_rubric.md`](../evals/fidelity_rubric.md)):

- Walls (count, stubs, slivers)
- Doors (count, routing 2D)
- Windows (count, routing 3D, peitoril preservado)
- Rooms / Floors (count, labels, áreas)
- Scale / rotation (dimensional global)
- Visual global (side-by-side)
- Groups no SKP (PlanShell / Floor / WindowGlass / DoorLeaf /
  GlazedBalcony / SoftBarrier counts)
- Opening counts vs consensus

### 4. Escrever `regression_summary.md`

Usar [`specs/templates/regression_summary_template.md`](templates/regression_summary_template.md).
Conteúdo mínimo:

- O que melhorou (com evidência)
- O que piorou (regressões reais ou aceitáveis)
- O que ficou igual
- WARN/FAIL remanescentes
- Veredito final (PASS / WARN / FAIL)

### 5. Promover artefatos

```bash
mkdir -p artifacts/review/<plant>/<cycle_or_pr>
cp runs/<plant>/<plant>.skp           artifacts/review/<plant>/<cycle_or_pr>/<plant>_after.skp
cp runs/<plant>/<plant>_top.png       artifacts/review/<plant>/<cycle_or_pr>/model_top_after.png
cp runs/<plant>/<plant>_iso.png       artifacts/review/<plant>/<cycle_or_pr>/model_iso_after.png
cp runs/<plant>/geometry_report.json  artifacts/review/<plant>/<cycle_or_pr>/geometry_report_after.json
# regression_summary.md preenchido manualmente
# side_by_side_before_after.png gerado quando possível
git add artifacts/review/<plant>/<cycle_or_pr>/
```

## Critérios de bloqueio

A PR é **incompleta** se qualquer condição abaixo é verdadeira:

1. Não gerou `.skp`
2. Gerou `.skp` mas só em `/runs/` (não promovido)
3. Não gerou render `top` e `iso`
4. Não comparou contra baseline (sem `regression_summary.md`)
5. Declarou melhoria sem evidência visual
6. Corrigiu um bug mas introduziu regressão crítica não
   justificada
7. Alterou builder/consensus sem provar impacto no SKP

Bloqueio = não merge. Reviewer humano DEVE cobrar.

## Critério de sucesso

Sucesso canônico exige TODAS as 5 condições:

1. `.skp after` existe em `artifacts/review/<plant>/<cycle_or_pr>/`
2. `model_top_after.png` + `model_iso_after.png` presentes
3. `regression_summary.md` preenchido com veredito final
4. Nenhuma regressão crítica não justificada
5. O objetivo declarado da PR aparece no artifact final
   (evidência visual concreta, não só números)

## Bloqueios legítimos (registrar no PR)

Se houver impedimento real:

- SketchUp 2026 indisponível na máquina
- Licença / headless runner quebrado
- PDF / consensus canônico ausente do repo
- Erro operacional (Python install, dep faltando, etc.)
- Risco destrutivo (ex.: mudança bate em fixture canônica
  exigindo aprovação humana)

Registrar **explicitamente** no PR body:

```
SKP Proof-of-Progress Gate: BLOCKED
Reason: <bloqueador específico>
Missing artifact: <o que não conseguiu gerar>
Next command to run: <comando exato pro reviewer humano>
```

PR sem build pode ser revista mas **não merge** até bloqueio
resolver, exceto se reviewer humano aprovar override explícito.

## Regra para agentes

**Não perguntar ao usuário se deve gerar SKP** após mudança de
melhoria. Gerar automaticamente, faz parte do escopo da PR.

Excepão: se a mudança encaixa em "Quando NÃO aplica" acima, não
gerar — mas justificar no PR body por que a regra não se aplica.

## Encaixe no operational rules

Este gate é categoria **3** ("failing gate" — se a PR alega
melhoria sem prova, é gate falhando) e **2** ("artifact quality"
— enquanto o `.skp` não existe em pasta versionada review, o
artifact está incompleto).

NÃO é categoria 6 ou nova: continua dentro dos 5 produto-ROI da
[`memory/operational_rules.md`](../memory/operational_rules.md).

## Testes / gates automáticos (follow-up)

Spec preliminar pra futuro tool de CI:

```bash
python tools/check_skp_proof_of_progress.py \
  --changed-files <git diff --name-only base..HEAD> \
  --artifact-dir artifacts/review/<plant>/<cycle_or_pr>
```

Deve verificar:

- Existe `<plant>_after.skp`
- Existe `model_top_after.png` E `model_iso_after.png`
- Existe `regression_summary.md`
- Summary referencia commit base + commit head
- Se `--changed-files` toca `tools/build_plan_shell_skp.*` OU
  `fixtures/<plant>/*.json` OU `consensus_*.json`, artifact
  review é **obrigatório**

**Não criado nesta PR** — é trabalho de produto separado (tool
em `tools/` + CI workflow). Spec aqui só pra ancorar a próxima
iteração.

## Resultado esperado

Depois desta regra cravada, toda PR que promete melhorar a
planta deve responder no body:

1. Qual SKP foi gerado?
2. Onde está o `.skp` versionado?
3. Qual render mostra a melhoria?
4. Qual comparação prova que melhorou?
5. O que regrediu?
6. O que ainda falta?

Sem isso, a PR não está completa.

## Relacionado

- Constitution: [`../constitution.md`](../constitution.md) §1 (SKP é
  artefato principal), §2 (sem SKP versionado, não há sucesso
  canônico)
- [`memory/artifact_policy.md`](../memory/artifact_policy.md)
- [`memory/lessons_learned.md`](../memory/lessons_learned.md) LL-021
- [`specs/skp_artifact_layout.md`](skp_artifact_layout.md)
- [`evals/fidelity_rubric.md`](../evals/fidelity_rubric.md)
- [`skills/generate-and-compare-skp-after-change/SKILL.md`](../skills/generate-and-compare-skp-after-change/SKILL.md)
- [`specs/templates/regression_summary_template.md`](templates/regression_summary_template.md)
