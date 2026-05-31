---
name: gh-autopilot
description: Use pra automatizar commit->PR->merge->cleanup de branch via gh CLI, e pra configurar/consertar a auth do gh. Dispara em "abrir PR", "mergear PR", "auto-merge", "gh auth", "token github", "limpar/organizar branches", "nunca deixar PR aberto", ou quando o loop/worker precisa landar trabalho sozinho. Captura os gotchas reais (token 366-day da org GFCDOTA, permissao Pull requests, GH_TOKEN). NAO usar pra git local puro sem gh.
---

# gh-autopilot — commit->PR->merge->cleanup sem humano

`gh` em `C:\Program Files\GitHub CLI\gh.exe`. Sempre `--repo GFCDOTA/sketchup-mcp`.

## Auth (a parte que mais deu trabalho — NAO re-descobrir)
Auth via **`GH_TOKEN`** (env var) = **fine-grained PAT**. NAO confiar no keyring (expira -> 401).

1. Criar: `github.com/settings/tokens?type=beta` · owner **GFCDOTA** · repo **sketchup-mcp** ·
   **Permissions: Contents = Read/write + Pull requests = Read/write** (Metadata auto).
2. **Validade <= 366 dias** — a org GFCDOTA **PROIBE** fine-grained > 366d
   (erro: `organization forbids ... lifetime greater than 366 days`). "No expiration" so
   existe pra PAT **classico**, nao fine-grained.
3. Persistir: `setx GH_TOKEN "<pat>"`. No shell atual, carregar:
   `$env:GH_TOKEN = [Environment]::GetEnvironmentVariable("GH_TOKEN","User")`.
4. Validar com operacao REAL (`gh pr list --repo ...`), NAO so com
   `gh auth login --with-token` (esse tem frescura de validacao e pode dar 401 mesmo com
   token bom). Direto na API: `Invoke-WebRequest https://api.github.com/user
   -Headers @{Authorization="Bearer $pat"; "User-Agent"="x"}`.

GOTCHAS:
- Sem `Pull requests: RW` -> `gh pr create` falha com
  `Resource not accessible by personal access token (createPullRequest)`.
  `Contents: RW` sozinho SO da push, NAO cria PR.
- `gh auth status` pode acusar conta de keyring invalida -> ignorar; `GH_TOKEN` sobrepoe.

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
