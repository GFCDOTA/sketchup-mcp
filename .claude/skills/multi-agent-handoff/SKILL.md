---
name: multi-agent-handoff
description: Use when work is shared across multiple agents (Claude / Codex / ChatGPT bridge / human) or sessions on the sketchup-mcp repo. Triggers on `git worktree`, ".ai_bridge", "HANDOFF", "handoff", "outro agente", "out-of-band commit", "branch que apareceu", or anything involving coordinating parallel work without overwriting another's.
---

# multi-agent-handoff

Skill pra coordenação quando há mais de um agente trabalhando no
repo.

## Quando usar

- Continuar trabalho de outra sessão / outro agente
- Detectar commit / branch / arquivo que apareceu sem ser sua
  ação
- Decidir entre worktrees paralelos vs check-in sequencial
- Atualizar `.ai_bridge/` (se ativo neste repo)
- Antes de qualquer push / merge quando há indício de
  paralelismo

## Princípio raiz

**Nunca assumir exclusividade sobre o repo.** Trabalho remoto
pode ter mudado entre dois comandos. Detalhe em
`memory/multi_agent_coordination.md`.

## Pre-flight (sempre antes de mutação remota)

```bash
git -C /e/Claude/sketchup-mcp fetch --all --prune
git -C /e/Claude/sketchup-mcp branch --show-current
git -C /e/Claude/sketchup-mcp rev-parse HEAD
git -C /e/Claude/sketchup-mcp rev-parse origin/develop
git -C /e/Claude/sketchup-mcp worktree list
```

Comparar HEAD local vs remoto da branch alvo. Se divergiu, parar.

**Importante:** sequencial — não rodar `git fetch` e
`rev-parse origin/*` em paralelo (rev-parse pode pegar stale).

## Worktree isolado

Quando há indicação de múltiplos agentes:

```bash
git -C /e/Claude/sketchup-mcp worktree add \
  ../sketchup-mcp-<agent-slug> \
  <branch>
```

- Cada agente opera dentro de sua worktree
- Não tocar working tree de outro agente
- Branch da worktree é dedicada (não usar `develop` direto)

## Detecção de mudança out-of-band

Se aparecer commit, branch ou PR que você NÃO criou:

1. **Parar mutação remota** (sem push, sem merge, sem delete)
2. **Registrar** (texto pro humano + linha em
   `plans/active_work.md` ou `memory/current_state.md`)
3. **Reconciliar**: ler o que apareceu, decidir aceitar / rebase
   / pedir review humano
4. Só voltar a operar após reconciliação

## Handoff explícito

Quando passar trabalho pra outra sessão / agente:

- Atualizar `plans/active_work.md` (branch, último commit,
  status, TODOs)
- Se `.ai_bridge/` ativo: `HANDOFF.md` + `CURRENT_STATE.md`
- Listar TODOs no PR body se PR estiver aberta
- Commit pequeno final ("wip: handoff" se necessário) pra evitar
  perda

## `.ai_bridge/` protocol (se ativo)

Estrutura observada em outros repos do humano:

```
.ai_bridge/
├── HANDOFF.md           ← fio da meada entre sessões
├── CURRENT_STATE.md     ← snapshot mais recente
├── GPT_REQUESTS/        ← pedidos pro GPT
├── GPT_RESPONSES/       ← respostas estruturadas
├── DECISIONS/           ← decisões versionadas
├── LESSONS/             ← aprendizados pontuais
└── TODO_NEXT/           ← próximos passos por agente
```

**TODO:** Confirmar se este repo (`sketchup-mcp`) usa
`.ai_bridge/`. Em snapshot 2026-05-27 não foi auditado.

## NUNCA fazer

- Force push em branch que outro agente pode ter pegado
- Reset --hard em commit que pode ter sido pushed
- Delete de branch remota sem confirmar status de outras
  sessões / agentes
- Sobrescrever working tree de worktree alheia

## Quando consultar humano

- Múltiplas worktrees na mesma branch
- Branches paralelas com objetivos potencialmente conflitantes
- Commit out-of-band com autoria desconhecida (Co-Authored-By
  diferente, autor email diferente)

## Skills relacionadas

- `repo-governance/` — PR / branch / merge mechanics
- `pdf-to-skp-pipeline/` — se handoff envolve build em curso
