# Active work — sketchup-mcp

Branch em curso, objetivo, escopo, validação.

> **Atualizar a cada session start / branch switch.** Se este
> arquivo estiver stale, qualquer agente deve reconciliar antes
> de operar.

> **Snapshot:** 2026-06-06.

## Contexto da sessão (2026-06-06)

Sessão de **higiene de repo + reconciliação**, sem tocar a superfície de
fidelidade do `.skp` (ambiente remoto sem SketchUp — geometria não valida
aqui). Foco: destravar o suite de testes e reconciliar branches/docs.

## Branches / PRs em voo

Todos **draft → `develop`** (Hard Rule #4):

| PR | Branch | O quê | Risco |
|---|---|---|---|
| #222 | `feat/noc-dispatcher` | atuador do NOC (dispatcher + worktree-lock) | MED — muda `:8765` vivo, bem-railed, não auto-merge |
| #223 | `chore/noc-t1` | doc `NOC_DISPATCHER.md` (output dogfooded da task T1) | baixo; mergear **depois** do #222 |
| #224 | `chore/refresh-nba-seed` | cura `_NBA_SEED` (remove 2 itens já feitos) | baixo, independente |
| #225 | `claude/repo-overview-NDPaj` | `fix(deps)` matplotlib+numpy | baixo; **destrava `pytest`** (coleção quebrava) |
| #226 | `fix/consult-path-resolution` | `fix(cockpit)` resolve consult paths em call-time | baixo; conserta 4 testes, prod byte-equivalente |

## Feito nesta sessão

- **`main` == `develop`** reconciliadas em `73eb9da` (FF limpo; `develop`
  estava 292 commits atrás).
- **Revisão das branches órfãs** → viraram PRs #222–224.
- **2 bugs reais** achados + corrigidos com prova em venv limpo (#225, #226):
  antes `Interrupted: 1 error during collection`; depois **467 passed, 5 skipped**.
- **Docs reconciliados** (este branch `chore/refresh-stale-docs`): `current_state.md`
  (folded do `chore/refresh-current-state`, atualizado p/ hoje), `active_work.md`,
  `next_actions.md`.

## Comandos de validação

```bash
# Suite verde (precisa do #225 mergeado OU matplotlib/numpy instalados)
python -m pytest tests/ -q          # esperado: 467 passed, 5 skipped

# main == develop
git rev-parse origin/main origin/develop   # mesmo SHA

# Bootloader @imports resolvem
cat .claude/CLAUDE.md CLAUDE.md | grep -oE '@\.claude/[a-zA-Z_/-]+\.md' \
  | sed 's/@//' | sort -u \
  | while read f; do test -f "$f" && echo OK $f || echo MISS $f; done
```

## Aguardando

- Review humano + merge dos PRs #222–226 (ordem sugerida: #225 → #226 → #222 → #223; #224 a qualquer hora).
- Decisão sobre fechar `chore/refresh-current-state` (conteúdo único folded aqui).
- `feat/mobiliar-bedroom-layout` é **WIP de peer vivo** — hands-off.
