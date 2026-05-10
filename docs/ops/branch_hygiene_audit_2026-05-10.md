# Branch hygiene audit — 2026-05-10

> Companion to [`repo_hygiene_audit_2026-05-10.md`](repo_hygiene_audit_2026-05-10.md)
> (file hygiene). This pass focuses on **branch hygiene** — local + remote
> branches that survived past their PR merge or never had a PR.

## TL;DR

- **8 local branches deleted** (all already merged into `develop`).
- **3 remote branches deleted** (all already merged into `origin/develop`).
- **1 local branch deleted** absorbed via cherry-pick port (PR #90 — `feat(smoke): gate G2 — port inspector v2 consumer from orphan branch`).
- **2 branches preserved** (`dashboard/architecture-sre-radar`, `dashboard/project-roadmap`) — flagged as `NEEDS_HUMAN`. 6-day-old, 11 + 7 file diffs, ~3300 LOC of dashboard work that has NO open PR and is NOT in `develop`.
- Open PRs: **0**.
- `main`, `develop`, current branch, branches with open PRs: **untouched**.

## Pre-state inventory

### Local branches (12 total)

| Branch | Status | Action |
|---|---|---|
| `develop` | INVIOLABLE | keep |
| `main` | INVIOLABLE | keep |
| `chore/fp014-refine-my-interpretation` | merged in `develop` (PR #106) | **DELETE_SAFE** |
| `docs/adr-002-room-polygon-overrides` | merged in `develop` | **DELETE_SAFE** |
| `docs/fp014-p0-spike` | merged in `develop` (PR #104) | **DELETE_SAFE** |
| `docs/fp014-validation-images` | merged in `develop` (PR #103) | **DELETE_SAFE** |
| `feature/fp014-gamma-structural-checks` | merged in `develop` (PR #105) | **DELETE_SAFE** |
| `feature/mission-control-cockpit-slice1` | merged in `develop` (PR #107) | **DELETE_SAFE** |
| `spike/fp014-p0-rooms-polygonize` | merged in `develop` | **DELETE_SAFE** |
| `feature/smoke-promotes-inspector-v2-gate` | NOT merge-traced; trabalho absorvido via cherry-pick em PR #90 (title literal: "port inspector v2 consumer **from orphan branch**"). Confirmação: `tests/test_smoke_gate_g2_inspector.py` existe em `develop`. | **DELETE_SAFE** (with cherry-pick note) |
| `dashboard/architecture-sre-radar` | NOT merged. 2 commits únicos (2026-05-04). 11 arquivos, ~2417 LOC dashboard work. Sem PR. | **NEEDS_HUMAN** |
| `dashboard/project-roadmap` | NOT merged. 1 commit único (2026-05-04). 7 arquivos, ~942 LOC dashboard work. Sem PR. | **NEEDS_HUMAN** |

### Remote branches (8 total, excluding HEAD pointers)

| Branch | Status | Action |
|---|---|---|
| `origin/develop`, `origin/main` | INVIOLABLE | keep |
| `origin/chore/repo-hygiene-2026-05-06` | merged in `origin/develop` (PR #73, 4 dias atrás) | **DELETE_SAFE** |
| `origin/docs/strengthen-autonomous-rules` | merged in `origin/develop` | **DELETE_SAFE** |
| `origin/feature/skp-structural-gate-inspector-v2` | merged in `origin/develop` (PR #49) | **DELETE_SAFE** |
| `origin/dashboard/architecture-sre-radar` | NOT merged (mirror of local) | **NEEDS_HUMAN** |
| `origin/dashboard/project-roadmap` | NOT merged (mirror of local) | **NEEDS_HUMAN** |

## Branches deleted this cycle

### Local (8)

```bash
git branch -d chore/fp014-refine-my-interpretation
git branch -d docs/adr-002-room-polygon-overrides
git branch -d docs/fp014-p0-spike
git branch -d docs/fp014-validation-images
git branch -d feature/fp014-gamma-structural-checks
git branch -d feature/mission-control-cockpit-slice1
git branch -d spike/fp014-p0-rooms-polygonize
git branch -D feature/smoke-promotes-inspector-v2-gate   # -D porque NOT merge-traced em develop, mas trabalho confirmado em PR #90
```

Justificativa do `-D` (force) em `feature/smoke-promotes-inspector-v2-gate`:
o único commit (`2417a20 feat(smoke): gate G2 — inspector v2 structural check (opt-in strict)`) introduz `tests/test_smoke_gate_g2_inspector.py` + alterações em `scripts/smoke/smoke_skp_export.py`. Ambos arquivos existem em `develop` via PR #90 (cuja própria descrição confirma "port inspector v2 consumer from orphan branch"). O commit `2417a20` permanece em `git reflog` por 90 dias (default) caso seja necessário recuperar.

### Remote (3)

```bash
git push origin --delete chore/repo-hygiene-2026-05-06
git push origin --delete docs/strengthen-autonomous-rules
git push origin --delete feature/skp-structural-gate-inspector-v2
```

## Branches preserved with rationale

### NEEDS_HUMAN — `dashboard/architecture-sre-radar` (local + remote)

**Why preserved:** 2 commits únicos não-mergeados.

```
f77af4f 2026-05-04 dashboard: add architecture SRE radar
992bb79 2026-05-04 dashboard: add project roadmap status view
```

**Diff scope (vs develop):**

```
A  docs/dashboard/architecture_sre_radar.md
A  docs/dashboard/project_status_dashboard.md
A  scripts/dashboard/generate_architecture_radar.py    (525 LOC)
A  tests/dashboard/test_generate_architecture_radar.py (187 LOC)
M  tools/dashboard/README.md                           (+32 LOC)
A  tools/dashboard/architecture_radar.example.json    (304 LOC)
M  tools/dashboard/index.html                          (+798 LOC)
A  tools/dashboard/pipeline_timing.example.json       (69 LOC)
A  tools/dashboard/project_status.example.json         (98 LOC)
A  tools/dashboard/quality_history.example.json        (112 LOC)
A  tools/dashboard/repo_health_history.example.json   (23 LOC)
```

Total: 11 arquivos, ~2417 LOC. Inclui dashboard generator script + tests + 5 example JSONs + index.html updates.

**Status PR:** 0 PRs abertos, 0 PRs fechados/merged matching `architecture sre radar` (search retornou apenas PR #51 da hygiene cycle 2026-05-06 que MENCIONOU a branch).

**Hygiene Cycle 1 (PR #73, 2026-05-06)** classificou: "Active dashboard work, unrelated to merged feature stack. Preserve."

### NEEDS_HUMAN — `dashboard/project-roadmap` (local + remote)

**Why preserved:** 1 commit único `992bb79` (compartilhado com a branch acima — provável ancestor comum).

**Diff scope (vs develop):** subset da `architecture-sre-radar` — 7 arquivos, ~942 LOC focando em project_status.

**Recommended next action (decisão humana):**

| Opção | Quando usar |
|---|---|
| (A) Abrir PR pro topic dashboard | Se o trabalho ainda é desejado e está pronto pra review |
| (B) Tag + delete | Preservar commit como `git tag dashboard/architecture-sre-radar-2026-05-04 f77af4f` e deletar as branches |
| (C) Cherry-pick subset → develop via PR | Se só parte do trabalho é desejada (ex: só o `index.html` e exemplos JSON) |
| (D) Archive note | Documentar em `docs/_archive/` que esse trabalho existiu, descartar |

**Default recommendation:** se o user não tem certeza do status, ir com **(B) tag + delete** — preserva totalmente os commits + libera o nome da branch + reduz noise.

## Reference searches performed

```
git fetch --all --prune
gh pr list --state open                                 →  []
git branch --merged develop                             →  7 local merged
git branch --no-merged develop                          →  3 local unmerged
git branch -r --merged origin/develop                   →  3 remote merged
git branch -r --no-merged origin/develop                →  2 remote unmerged
git log develop..<branch> --oneline                     →  per branch
git diff --stat develop...<branch>                      →  per branch
gh pr list --state all --search "<topic>"               →  per branch
```

## Validations executed

- `git fetch --all --prune` — synced before analysis.
- `gh pr list --state open` — confirmou 0 abertos.
- `git branch --merged develop` — confirmou conjunto seguro pra delete.
- `git log develop..feature/smoke-promotes-inspector-v2-gate` — único commit confirmado portado via PR #90.
- Existência de `tests/test_smoke_gate_g2_inspector.py` em `develop` confirmada.
- Idade dos commits dashboard: 2026-05-04 (6 dias) — abaixo do threshold de 14d auto-delete, acima do 7d auto-revisar.
- Working tree de `develop`: limpo apart from pre-existing `M .ai_bridge/events.jsonl` (Mission Control runtime log — gitignored content por design).

## What this cycle did NOT do

- ❌ Não deletou `develop`, `main`, branch atual.
- ❌ Não deletou branches com PR aberto (havia 0).
- ❌ Não deletou branches com commits únicos não-mergeados sem cherry-pick traceável (preservou as 2 dashboard).
- ❌ Não tocou em `runs/`, `patches/`, `ground_truth/`, `.ai_bridge/`, código source.
- ❌ Não fez force-push em `main`/`develop`.
- ❌ Não modificou git config / hooks.

## Summary

- 8 local + 3 remote = **11 branches deleted**.
- 4 branches preserved (`dashboard/*` × local + remote = 4 refs total) com decisão pendente.
- 0 perda de commits — trabalho dashboard preservado, trabalho mergeado já estava em develop, trabalho portado (`feature/smoke-promotes-inspector-v2-gate`) confirmado via PR #90 + reflog 90d backup.
- `develop` intacta, sem novo commit funcional. Apenas este doc adicionado.
