---
name: gh-autopilot
description: Use pra automatizar commit->PR->merge->cleanup de branch via gh CLI, e pra configurar/consertar a auth do gh. Dispara em "abrir PR", "mergear PR", "auto-merge", "gh auth", "token github", "limpar/organizar branches", "nunca deixar PR aberto", ou quando o loop/worker precisa landar trabalho sozinho. Captura os gotchas reais (token 366-day da org GFCDOTA, permissao Pull requests, GH_TOKEN). NAO usar pra git local puro sem gh.
---

# gh-autopilot — commit->PR->merge->cleanup sem humano

`gh` em `C:\Program Files\GitHub CLI\gh.exe`. Sempre `--repo GFCDOTA/sketchup-mcp`.

## Auth — CAMINHO ATUAL: `gh auth login` (mudou em 2026-09-19)

Auth via **keyring** (`gh auth login`, device flow no browser). Token `gho_*` com
scopes `gist, read:org, repo, workflow` — `repo` cobre `gh pr create`.

```powershell
Remove-Item Env:GH_TOKEN -ErrorAction SilentlyContinue
[Environment]::SetEnvironmentVariable('GH_TOKEN', $null, 'User')
gh auth login   # GitHub.com -> HTTPS -> browser
```

**`GH_TOKEN` TEM PRECEDENCIA sobre o keyring.** Enquanto a env var existir, o
`gh auth login` roda mas o gh continua usando o token velho ("The value of the
GH_TOKEN environment variable is being used for authentication"). Limpar PRIMEIRO.

### Por que a orientacao anterior (PAT via `GH_TOKEN`) queimou uma sessao

O SKILL dizia "usar fine-grained PAT em `GH_TOKEN`, nao confiar no keyring".
Dois enganos reais, custaram varias sessoes travadas em `createPullRequest` 403:

- **Resource owner errado e INVISIVEL no sintoma.** Um fine-grained PAT so
  alcanca recursos do *resource owner* dele. O token em uso tinha owner = conta
  **pessoal** (`fmodesto30`), e os repos sao da **org GFCDOTA** -> nenhuma
  permissao ligada nele chega no repo. A pagina do token mostra
  "does not have access to any repositories" e NAO tem dropdown de Pull requests
  pra consertar. So se resolve criando outro token com owner = **GFCDOTA**.
- **`git push` mascarou o problema.** Push NAO le `GH_TOKEN` — vai por
  `credential.helper=manager` (Git Credential Manager, credencial
  `git:https://github.com` no Windows). Entao "push funciona, PR da 403" parecia
  falta de permissao de PR, quando na verdade o token estava VAZIO e o push era
  de outra credencial. Diagnostico so fecha checando `git config credential.helper`.

### Alternativa least-privilege (fine-grained PAT)

Se quiser escopo minimo em vez do keyring:
`github.com/settings/personal-access-tokens/new` · **Resource owner = `GFCDOTA`**
(nao a conta pessoal) · repo **sketchup-mcp** · **Contents = R/W + Pull requests = R/W**
(Metadata auto) · aprovar em `organizations/GFCDOTA/settings/personal-access-token-requests`.

- **Validade <= 366 dias** — a org GFCDOTA **PROIBE** fine-grained > 366d
  (erro: `organization forbids ... lifetime greater than 366 days`). "No expiration" so
  existe pra PAT **classico**, nao fine-grained.
- Persistir: `setx GH_TOKEN "<pat>"`. `setx` grava no REGISTRO e **nao atualiza
  processo ja rodando** — shell (ou app) nascido antes da troca segue com o valor
  velho e o diagnostico sai errado. Carregar no shell atual:
  `$env:GH_TOKEN = [Environment]::GetEnvironmentVariable("GH_TOKEN","User")`.
- Validar com operacao REAL (`gh pr list --repo ...`), NAO so com
  `gh auth login --with-token` (esse tem frescura de validacao e pode dar 401 mesmo com
  token bom).

GOTCHAS:
- Sem `Pull requests: RW` -> `gh pr create` falha com
  `Resource not accessible by personal access token (createPullRequest)`.
  `Contents: RW` sozinho SO da push, NAO cria PR.
- Repo **publico** responde a leitura de QUALQUER token, ate um sem permissao
  nenhuma. `gh api repos/<owner>/<repo>` retornar dados **nao prova** que o token
  serve. O unico probe honesto de PR-write e tentar criar a PR.

## Auto-merge (commit -> PR -> merge)
```bash
gh pr create --repo GFCDOTA/sketchup-mcp --base develop --head <branch> --title "..." --body "..."
gh pr merge <branch> --repo GFCDOTA/sketchup-mcp --squash
```
- **`--delete-branch` SO se a branch NAO estiver checked-out** na arvore principal (senao o
  gh troca o branch da sessao viva = colisao). Em duvida: merge sem, e limpar depois.
- **Develop-first**: PR `feat/`|`chore/` -> **develop**, nunca direto em `main` (Hard Rule #4).
- **Modo B**: PR tecnica/verde = GO (auto-merge). PR que muda **aparencia da planta** ou
  **fixture canonica** -> `VISUAL_REVIEW` (Felipe decide), NUNCA auto.

## Limpeza de branches (segura)
Deletar SO branches com PR **ja merged** — confirmar via gh (squash nao deixa ancestral,
entao `git branch --merged` por ancestralidade ENGANA):
```bash
gh pr list --repo GFCDOTA/sketchup-mcp --state merged --limit 80 --json headRefName --jq ".[].headRefName"
# pra cada branch viva (!= develop/main) que esteja nessa lista: git push origin --delete <b>
```
NUNCA deletar branch sem PR merged confirmada (pode ter trabalho nao-landado).

## Nao force
`gh` 401/403 = problema de AUTH (ver secao Auth), nao re-tentar cego. PR que toca
render/fixture canonica = VISUAL_REVIEW, nao auto-merge.
