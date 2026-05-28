# Active work — sketchup-mcp

Branch em curso, objetivo, escopo, validação.

> **Atualizar a cada session start / branch switch.** Se este
> arquivo estiver stale, qualquer agente deve reconciliar antes
> de operar.

## Branch atual

`feat/skp-proof-of-progress-gate`

- Base: `origin/develop` em `04cb25b` (post-merge PR #195)
- Criada em: 2026-05-28

## Objetivo

Cravar a regra permanente **No SKP, no progress** /
**SKP Proof-of-Progress Gate**: toda PR que afete fidelidade
arquitetônica precisa gerar SKP novo + renders + comparação
antes/depois em pasta human-facing (`artifacts/review/<plant>/<cycle>/`)
com `regression_summary.md`.

## Escopo permitido

- Spec canônica em `.claude/specs/skp_proof_of_progress_gate.md`
- Skill operacional `generate-and-compare-skp-after-change`
- Template `regression_summary_template.md`
- Adicionar princípio #8 na Constitution
- LL-021 / lição #12 em `memory/lessons_learned.md`
- Reforço em `memory/artifact_policy.md` (referência ao gate)
- Atualizar bootloader CLAUDE.md (@import novo spec)
- Atualizar README.md + docs/index.md (refletir novos arquivos)
- Atualizar plans/active_work + next_actions + memory/current_state
- Audit log em `docs/audits/2026-05-28_*.md`

## Fora de escopo

- Tocar `tools/`, `tests/`, `fixtures/`, `artifacts/<plant>/`
- Criar `tools/check_skp_proof_of_progress.py` (gate automatizado
  CI) — fica como follow-up TODO documentado na spec
- Aplicar a regra retroativamente a PRs anteriores
- Regenerar `.skp` de planta_74 nesta PR (regra é normativa, não
  exercitada aqui)

## Comandos de validação

```bash
# Gitignore não está ignorando os novos arquivos
git check-ignore -v \
  .claude/specs/skp_proof_of_progress_gate.md \
  .claude/skills/generate-and-compare-skp-after-change/SKILL.md \
  .claude/specs/templates/regression_summary_template.md \
  .claude/docs/audits/2026-05-28_skp_proof_of_progress_gate.md
# Esperado: tudo "not ignored"

# Imports do bootloader resolvem
cat .claude/CLAUDE.md CLAUDE.md | grep -oE '@\.claude/[a-zA-Z_/-]+\.md' | sed 's/@//' | sort -u | while read f; do test -f "$f" && echo OK $f || echo MISS $f; done
# Esperado: todos OK

# Contract suite ainda verde
.venv/Scripts/python.exe -m pytest tests/ -q
# Esperado: 89 passed, 5 skipped (sem mexer em código)
```

## Status

Em curso. Spec + skill + template + constitution + lessons +
artifact_policy + bootloader + README + index + plans atualizados.
Audit log a criar. Próximo: validar, commit, push, PR contra
`develop`.
