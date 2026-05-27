# Active work — sketchup-mcp

Branch em curso, objetivo, escopo, validação.

> **Atualizar a cada session start / branch switch.** Se este
> arquivo estiver stale, qualquer agente deve reconciliar antes
> de operar.

## Branch atual

`chore/organize-claude-knowledge-base`

- Base: `origin/develop` em `2aafd04`
- Criada em: 2026-05-27

## Objetivo

Transformar `.claude/` numa base operacional do projeto:
contexto, regras, specs, skills, plans separados em arquivos
pequenos. `CLAUDE.md` raiz vira stub de auto-load; `.claude/CLAUDE.md`
vira bootloader curto com `@imports`.

Detalhe completo do plano em `specs/repository_hygiene.md` (não)
— este escopo é organização de conhecimento, não cleanup de
código.

## Escopo permitido

- Criar / atualizar arquivos sob `.claude/`
- Atualizar `.gitignore` pra liberar subdirs versionados
- Substituir `.claude/CLAUDE.md` por bootloader
- Stub em raiz `CLAUDE.md` → `@.claude/CLAUDE.md`

## Fora de escopo

- Tocar `tools/`, `tests/`, `fixtures/`, `artifacts/`
- Mudar comportamento do pipeline
- Refactor de código Python / Ruby
- Cleanup de `docs/` (separar em outra PR)

## Comandos de validação

```bash
# Gitignore não está ignorando os subdirs novos
git -C /e/Claude/sketchup-mcp check-ignore -v \
  .claude/CLAUDE.md \
  .claude/README.md \
  .claude/memory/project_context.md \
  .claude/specs/product_goal.md \
  .claude/plans/roadmap.md \
  .claude/skills/pdf-to-skp-pipeline/SKILL.md \
  .claude/docs/index.md
# Esperado: tudo sai "ok" (não ignorado) exceto scratch/

# Scratch continua ignorada
git -C /e/Claude/sketchup-mcp check-ignore -v .claude/scratch/x.md
# Esperado: scratch é ignored

# Contract suite ainda verde (não toquei código mas vale conferir)
python -m pytest tests/ -q
```

## Status

Em curso. Próximo passo: validar gates → commit único → push →
PR contra `develop`.
