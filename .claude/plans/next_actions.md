# Next actions — sketchup-mcp

Fila curta. Máximo 5 itens. Adicionar novo só se houver espaço E
valor claro pro produto.

> **Snapshot:** 2026-05-27. Decai rápido.

## Fila atual

### 1. Concluir esta reorganização do `.claude/`

- **Objetivo:** Branch `chore/organize-claude-knowledge-base`
  mergeada em `develop`
- **Por quê:** Base operacional pra agentes futuros saberem onde
  achar regras vivas, specs, plans, skills. Sem isso, contexto
  fragmenta em CLAUDE.md gigantes.
- **Arquivos prováveis:** `.claude/` (este PR)
- **Validação:** README.md explica estrutura, `.claude/CLAUDE.md`
  vira bootloader, gitignore libera subdirs, `.skp` policy
  documentada, multi-agent rules cravadas
- **Critério de parada:** PR aberto contra `develop`

### 2. Auditar TODOs deixados nesta reorganização

- **Objetivo:** Cada `TODO` em `.claude/**/*.md` resolvido ou
  movido pra issue
- **Por quê:** TODOs são honest markers de "preciso validar
  contra repo real". Deixar eternos vira ruído.
- **Arquivos prováveis:** `.claude/memory/*.md`,
  `.claude/specs/*.md`, `.claude/skills/*/SKILL.md`
- **Validação:** `rg -n "TODO" .claude/` retorna lista vazia OU
  só TODOs com link pra issue
- **Critério de parada:** lista enxugada

### 3. (placeholder)

- TODO: definir próximo item de ROI quando #1 e #2 fecharem

### 4. (placeholder)

### 5. (placeholder)

## Regra de fila

Concluir a fila → escolher próximo item **só se houver valor
claro pro produto** (gerar/revisar `.skp` fiel). Não inventar
trabalho cosmético. Ver `specs/product_goal.md` § "Critérios de
avanço real".
