# Git Workflow

> Effective from 2026-05-03. Replaces previous "branch direto pra main"
> flow with a develop-first integration model.

## Branches permanentes

| Branch | Papel | Quem mergeia |
|---|---|---|
| `main` | Branch estável/release. Sempre verde, sempre deployable. | Apenas via PR vindo de `develop` (ou hotfix emergencial). |
| `develop` | Branch de integração. Recebe todas as features. | Via PR vindo de feature branches. |

**Regras invioláveis:**
- Nunca delete `main`.
- Nunca delete `develop`.
- Nunca `git push --force` em `main` ou `develop`.
- Nunca commite direto em `main` ou `develop` (sempre via PR).

## Branches de trabalho

Nomeie pelo tipo:

| Prefixo | Quando usar |
|---|---|
| `feature/<slug>` | Funcionalidade nova |
| `fix/<slug>` | Bugfix não-emergencial |
| `chore/<slug>` | Manutenção, tooling, infra |
| `docs/<slug>` | Documentação |
| `perf/<slug>` | Performance / benchmarks |
| `refactor/<slug>` | Refatoração sem mudança funcional |
| `test/<slug>` | Adicionar/melhorar testes |
| `agents/<slug>` | Agentes especialistas (read-only ou scoped) |
| `hotfix/<slug>` | Correção urgente que vai direto pra `main` |

## Fluxo padrão (feature → develop → main)

```
1. git checkout develop
2. git pull origin develop
3. git checkout -b feature/<slug>
4. (commits pequenos, semânticos)
5. git push -u origin feature/<slug>
6. Abrir PR: feature/<slug> → develop
7. Aguardar CI verde + review (humano ou agentes)
8. Merge (squash recomendado) → develop
9. Deletar branch feature/<slug> (local + remoto)
```

Quando `develop` acumula mudanças validadas e estiver verde:

```
10. Abrir PR: develop → main
11. Confirmar CI verde
12. Merge — main fica atualizada
```

## Hotfix (exceção emergencial)

Para bugs em produção que precisam ir direto pra main:

```
1. git checkout main && git pull
2. git checkout -b hotfix/<slug>
3. (fix)
4. git push -u origin hotfix/<slug>
5. PR: hotfix/<slug> → main  (atalho do fluxo padrão)
6. Após merge em main: PR de main → develop pra sincronizar
```

Use raramente. A maioria dos "urgentes" cabe no fluxo padrão.

## CI

`.github/workflows/ci.yml` dispara em:
- `pull_request` (qualquer base — pega PR pra develop e pra main)
- `push: branches: [main, develop]` (após merges)
- `workflow_dispatch` (manual)

## Por que develop-first

- **Isolamento de risco**: se uma feature quebra algo, isolada em develop, não afeta main.
- **Janela de validação**: develop pode ser testada por ciclos antes de promover pra main.
- **Atomicidade da promoção**: 1 PR `develop → main` agrupa N PRs revisados, simplifica changelog.
- **Hotfix path claro**: bugs reais de produção têm caminho dedicado.

## Quando NÃO seguir esse fluxo

- **Hotfix verdadeiro** (rare) — caminho `hotfix/* → main` documentado acima.
- **Mudança em `.github/workflows/ci.yml` que afeta o próprio CI** — pode precisar iterar direto pra desbloquear, mas ainda assim via PR (não commit direto).

## Limpeza

Após PR mergeado:
- Delete a branch de feature local: `git branch -d feature/<slug>`
- Delete remota: `git push origin --delete feature/<slug>`
- Ou via GitHub: marcar "Delete branch" no PR mergeado

`develop` e `main` **nunca** são deletadas.

## Comandos úteis

```bash
# Atualizar develop antes de criar feature
git checkout develop && git pull origin develop

# Promover develop → main quando estiver pronto
gh pr create --base main --head develop \
    --title "Promote develop to main" \
    --body "Promotes accumulated changes from develop to main."

# Ver branches mergeadas em develop (candidatas a delete)
git branch --merged develop | grep -v "^\*\|main\|develop"

# Audit de branches divergentes
git for-each-ref refs/heads --format="%(refname:short) %(upstream:short)"
```

## Backup pré-cleanup

Quando precisar limpar branches em massa, sempre salvar backup em
`D:/Claude/scratch/sketchup-mcp-branch-cleanup-backup-<date>.txt` com:
- Nome da branch (local e/ou remota)
- SHA do último commit
- Subject do último commit
- Contagem de commits únicos vs `main`

Permite recuperação por `git fetch origin <sha>` se algum trabalho for
inadvertidamente apagado.
