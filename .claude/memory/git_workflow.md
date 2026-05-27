# Git workflow — sketchup-mcp

## Branch model — develop-first

```
main         ← release-quality, recebe SÓ via merge de develop
 ↑
develop      ← integration branch, base pra toda feature/chore
 ↑
feature/<x>  ← work branches, abertas a partir de develop
chore/<x>
fix/<x>
docs/<x>
```

**Nunca push direto em `main`.** Bake rule do `CLAUDE.md` (Hard
Rule #4): PR `feature/<x>` ou `chore/<x>` → `develop`; `main` só
recebe `develop`.

## Naming de branch

| Prefixo | Quando usar |
|---|---|
| `feature/` | Funcionalidade nova ou mudança de comportamento |
| `fix/` | Bugfix |
| `chore/` | Refactor sem mudança de comportamento, cleanup, docs estrutural |
| `docs/` | Doc-only |

## Session start protocol

```bash
git fetch --all --prune
git status --short
git branch --show-current
git rev-parse HEAD
git rev-parse origin/develop
```

Não rodar `git fetch` e `git rev-parse origin/...` em paralelo —
o rev-parse pode pegar ref stale. Sequencial.

## PR via gh

`gh` está instalado e autenticado (account `fmodesto30`, scope
`repo`, keyring). Caminho absoluto necessário no Git Bash:

```bash
"/c/Program Files/GitHub CLI/gh.exe" pr create \
  --repo fmodesto30/sketchup-mcp \
  --base develop \
  --head <branch> \
  --title "<title>" \
  --body-file -  <<'EOF'
...
EOF
```

**Sempre `--repo fmodesto30/sketchup-mcp`** e **sempre
`--body-file -` com heredoc** (evita escape hell no body).

NÃO propor "abrir PR manual no browser" — está superseded
(deprecated_context.md). `gh` é o default.

## Checks antes de merge

- `python -m pytest tests/ -q` verde
- PR target = `develop` (nunca `main`)
- Sem unresolved merge conflicts
- Sem ` D` no diff que apague fixture canônica sem prova

## Branch cleanup

Após merge:

```bash
git -C /e/Claude/sketchup-mcp checkout develop
git -C /e/Claude/sketchup-mcp pull --ff-only
git -C /e/Claude/sketchup-mcp branch -d <branch-merged>
git -C /e/Claude/sketchup-mcp push origin --delete <branch-merged>
```

Não usar `branch -D` (force delete) sem autorização explícita —
pode apagar trabalho não-mergeado.

## Não fazer

- `git push --force` em branch compartilhada
- `--no-verify` em hook (resolver a causa, não bypass)
- `--no-gpg-sign` ou alterar `gpg.sign` sem ordem
- `git reset --hard` em commit não-local
- `git rebase -i` (interativo, trava)
- Configurar `user.name` ou `user.email` global
