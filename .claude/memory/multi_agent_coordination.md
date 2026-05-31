# Multi-agent coordination — sketchup-mcp

Regras pra quando mais de um agente (Claude / Codex / GPT-bridge /
humano + qualquer combinação) trabalha no repo em paralelo.

## Princípio raiz

**Nunca assumir exclusividade sobre o repo.** Trabalho remoto
pode ter mudado entre dois comandos.

## Antes de qualquer decisão remota

```bash
git -C <repo> fetch --all --prune
git -C <repo> branch --show-current
git -C <repo> rev-parse HEAD
git -C <repo> rev-parse origin/<branch-target>
```

Comparar HEAD local vs HEAD remoto da branch alvo. Se divergiu,
parar e reconciliar antes de commit/push/merge.

## Antes de commit

- `git status --short` mostra exatamente o que você está
  staging? Mudança out-of-band aparece como `??` ou ` M` não
  reconhecida.
- Diff revisado? Pelo menos `git diff --stat` + `git diff
  <arquivo-crítico>`.

## Depois de commit

```bash
git -C <repo> rev-parse HEAD     # confirmar o SHA do que acabou de gravar
git -C <repo> log -1 --oneline   # confirmar mensagem + autoria
```

Push rápido se commit for válido. Atraso aumenta janela de conflito.

## Worktrees isoladas

Se houver indicação de múltiplos agentes ativos:

```bash
git -C <repo> worktree list
git -C <repo> worktree add ../sketchup-mcp-<agent-slug> <branch>
```

Trabalhar dentro da worktree própria. Não tocar working tree de
outro agente.

## Handoff

Quando passar trabalho pra outra sessão / outro agente:

- Anotar branch atual + último commit em `plans/active_work.md`
- Se houver coordenação via `.ai_bridge/`, atualizar
  `HANDOFF.md` + `CURRENT_STATE.md` lá
- Listar TODOs explícitos no commit message ou no PR body

## Mudança out-of-band detectada

Se aparecer commit, branch, arquivo ou PR que você não criou:

1. **Parar mutação remota** (não push, não merge, não delete)
2. **Registrar** o achado (texto pro humano + nota em
   `current_state.md` ou `active_work.md`)
3. **Reconciliar**: ler o commit/PR, decidir se aceita / rebase /
   pede revisão humana
4. Só voltar a operar depois de reconciliado

## TODO — verificar live

- [ ] Confirmar se há `.ai_bridge/` ativo neste repo (no snapshot
      do dia desta organização, não foi auditado)
