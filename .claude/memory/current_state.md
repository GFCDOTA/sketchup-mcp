# Current state — sketchup-mcp

> **Snapshot:** 2026-05-27. Verificar com `git`/`gh` antes de agir
> em decisões remotas — este arquivo decai rápido.

## Branch base

`develop` é a integration branch. `main` só recebe `develop` via merge.

- Working branch desta organização: `chore/organize-claude-knowledge-base`
- HEAD de `origin/develop` no snapshot: `2aafd04`

## PRs / commits recentes (origin/develop)

| # | Resumo | Status |
|---|---|---|
| #193 | feat(fp-026): residual wall stub elimination — spec + diagnostic + tests | Merged |
| #192 | fix(walls): junction-aware endpoint extension — trim LL-017 stubs | Merged |
| #191 | feat(artifacts): refresh planta_74 build + document room fidelity baseline | Merged |
| #189 | docs: document runs/ vs artifacts/ convention + rewrite quadrado spec | Merged |
| #187 | chore: drop 7 zero-ref fixture orphans + requirements.txt + clean.pdf | Merged |
| #186 | docs(claude): bake rule — never use --mode headless from a dev terminal | Merged |
| #185 | feat(artifacts): commit canonical planta_74 SKP + renders + report | Merged |
| #184 | chore: prune repo to minimal SKP-generation pipeline | Merged |

## Baselines considerados estáveis (não retrabalhar)

- **quadrado canonical**: render + shell polygon + geometry report
  pinados em `docs/specs/_assets/`. PR #189 reescreveu o spec.
- **planta_74 canonical artifact**: `artifacts/planta_74/*` é o
  deliverable atual (PR #185 / #191).
- **runs/ vs artifacts/ convention**: PR #189 documentou; PR #191
  reforçou. Não inverter.
- **`--mode headless` proibido em dev local**: PR #186 cravou; é
  YELLOW gate.
- **Junction-aware endpoint extension**: PR #192 + FP-026 (PR #193)
  resolvem residual wall stubs.

## Problemas reais ainda abertos

- **Room fidelity = WARN** para `planta_74`: 8 cells fechadas vs 11
  ambientes semânticos. Dois cells fundem ambientes open-plan
  (r001 = A.S./TERRACO SOCIAL/TERRACO TECNICO; r002 = SALA DE
  JANTAR/SALA DE ESTAR). Geometricamente honesto — não inventar
  paredes. Backlog: overlay `semantic_zones` separado.

## TODO — verificar live

- [ ] `gh pr list --repo GFCDOTA/sketchup-mcp --state open` pra
      ver se tem PR aberta não listada aqui
- [ ] Confirmar que não há working trees paralelos em outros agentes
      (`git worktree list`)
