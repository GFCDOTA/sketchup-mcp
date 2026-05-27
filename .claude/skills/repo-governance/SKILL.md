---
name: repo-governance
description: Use for any task touching PR creation, branch management, repo hygiene, merge strategy, or commit discipline. Triggers on `gh pr`, "abrir PR", "merge develop", "cleanup branch", "branch cleanup", "PR contra develop", ".gitignore", "develop-first", or any decision about how changes land in the repo.
---

# repo-governance

Skill operacional pra governança do repo: branch model, PRs,
hygiene, commit discipline.

## Quando usar

- Abrir PR pra `develop`
- Merge / fast-forward de PR mergeada
- Branch cleanup local + remoto
- Mudança em `.gitignore`
- Decisão sobre fazer cleanup pass ou não
- Audit de PRs abertas

## Branch model (develop-first)

```
main ← develop ← feature/<x> | chore/<x> | fix/<x> | docs/<x>
```

Hard Rule #4 (do `.claude/CLAUDE.md`): **nunca push direto em
main**. PRs vão pra `develop`; `main` só recebe `develop`.

Detalhes em `memory/git_workflow.md`.

## PR via gh (sempre)

```bash
"/c/Program Files/GitHub CLI/gh.exe" pr create \
  --repo fmodesto30/sketchup-mcp \
  --base develop \
  --head <branch> \
  --title "<title>" \
  --body-file - <<'EOF'
## Summary
...

## Test plan
- [ ] ...

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
```

- Sempre `--repo fmodesto30/sketchup-mcp`
- Sempre `--body-file -` com heredoc (escape hell se inline)
- Sempre `--base develop` (Hard Rule #4)

Auth status já configurado (account `fmodesto30`, scope `repo`,
keyring). Ver memory global `reference_gh_cli_absolute_path.md`.

## PR title convention

Prefixos do repo (observados nas PRs recentes):

| Prefixo | Quando |
|---|---|
| `feat:` ou `feat(<scope>):` | Funcionalidade nova / mudança de contrato |
| `fix:` ou `fix(<scope>):` | Bugfix |
| `chore:` | Refactor sem mudança comportamental, cleanup |
| `docs:` ou `docs(<scope>):` | Doc-only |

Scope opcional: `(walls)`, `(artifacts)`, `(claude)`, `(fp-026)`,
etc.

## Commit message style

Observado no log:

```
feat(fp-026): residual wall stub elimination — spec + diagnostic + tests (#193)
fix(walls): junction-aware endpoint extension — trim LL-017 stubs (#192)
docs: document runs/ vs artifacts/ convention + rewrite quadrado spec (#189)
chore: drop 7 zero-ref fixture orphans + requirements.txt + clean.pdf (#187)
```

Mesma forma do PR title. Co-author footer:

```
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

## Cleanup branch após merge

```bash
git -C /e/Claude/sketchup-mcp checkout develop
git -C /e/Claude/sketchup-mcp pull --ff-only
git -C /e/Claude/sketchup-mcp branch -d <branch-merged>
git -C /e/Claude/sketchup-mcp push origin --delete <branch-merged>
```

`branch -d` (lowercase) recusa apagar se não-mergeada — proteção.
NÃO usar `branch -D` sem autorização explícita.

## NUNCA fazer

- `git push --force` em branch compartilhada
- `--no-verify` pra bypass de hook
- PR direto pra `main`
- Configurar `user.name` ou `user.email` global
- Cleanup pass sem trigger real (ver
  `specs/repository_hygiene.md`)

## Quando consultar humano

- PR title / scope ambíguo
- Conflito de merge não-trivial
- Trigger de cleanup duvidoso (se já houve audit recente
  convergindo em "preserve", parar)
- Branch antiga sem PR mas com commits únicos não-mergeados

## Skills relacionadas

- `multi-agent-handoff/` — coordenação quando há agentes paralelos
- `skp-artifact-management/` — PR que commita artifact
