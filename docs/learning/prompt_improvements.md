# Prompt Improvements

> Patterns of session prompts that worked or didn't. Each entry has
> the symptom, the new prompt pattern, and a date.
> Use this when refining `.claude/commands/*.md` or when designing
> AFK loops.

## PI-001 — "Gigante prompt único" vs slash commands

**Date:** 2026-05-03
**Symptom:** A 200-line AFK prompt with rules for 6 phases worked
once but couldn't be reused. Half of it was repetition of git rules.
**New pattern:** Slash commands in `.claude/commands/` that act as
playbooks. The user just sends `/afk-maintain` and the agent
follows the documented sequence, reading rules from `CLAUDE.md`.
**Result:** Less context burned per request, easier to evolve the
playbooks via PR.

## PI-002 — "Não me faça perguntas" precisa de regras conservadoras explícitas

**Date:** 2026-05-03
**Symptom:** Telling Claude "don't ask, take conservative defaults"
without saying what conservative means caused over-cautious bail-outs
on every minor ambiguity.
**New pattern:** Combine "don't ask" with explicit fallback rules:
*"if ambiguous: pick the option that doesn't change algorithm code,
doesn't delete data, doesn't push to main, and documents the
decision in reports/."*
**Result:** Predictable behavior under autonomy. Documented in
`CLAUDE.md` §5.

## PI-003 — Pedindo ao agente pra "aprender" sem persistência

**Date:** 2026-05-03
**Symptom:** "Lembre-se disso" durante uma sessão é perdido na
próxima. Subagent calls inherit prompt only at invocation.
**New pattern:** Direct memorable observations to a write-to-disk
location (`docs/learning/`) and update `CLAUDE.md` if it's a rule.
The "memory" is git-versioned, not chat-bound.
**Result:** Knowledge survives compaction and session restarts.

## PI-004 — "Continue de onde parou" sem contexto

**Date:** 2026-05-03
**Symptom:** Saying "continue" after a break causes the agent to
guess. Sometimes resumes correctly, sometimes restarts a different
phase.
**New pattern:** Always include current state in the resume prompt:
- current branch
- last commit SHA
- pending todo from the previous session
- what NOT to do
Or use `/afk-maintain` which figures out state from `git status` +
`reports/repo_audit.md`.

## PI-005 — Permissões in-prompt vs `--dangerously-skip-permissions`

**Date:** 2026-05-03
**Symptom:** Approving every Bash call slows AFK loops to a crawl.
**New pattern:** Use the user-side bypass (`/permissions` →
"approve all") for fully-autonomous sessions. The `pre_bash_guard.py`
hook still blocks the truly destructive commands, so the bypass is
"trust the rules, not the user-per-call."
**Result:** AFK loops complete without 50 permission prompts.

## PI-006 — Pedindo um agente que faça tudo

**Date:** 2026-05-03
**Symptom:** Asking ONE agent to "review the PR, fix the issues, and
merge" produces low-quality reviews because the same model is biased
toward the fix it would write.
**New pattern:** Specialist agents (`.claude/agents/`) are scoped to
review-only. The fix is a separate task with its own PR. Coordinator
agent decides who reviews.
**Result:** Real review pressure. See `LL-007`, `DL-004`.

## PI-007 — "Pode commitar e push" deve ser explícito

**Date:** 2026-05-03
**Symptom:** Agente comitou trabalho intermediário porque interpretou
"pushar quando estiver pronto" liberalmente.
**New pattern:** "Comite SOMENTE quando todos os checks abaixo
passarem: pytest verde, ruff sem novas categorias, diff confina-se a
arquivos permitidos." Lista explícita de critérios.
**Result:** Sem commits surpresa. Conferência humana antes de cada
push (ou `/prepare-pr` que valida tudo antes).

## PI-008 — Subagents não herdam CLAUDE.md sempre

**Date:** 2026-05-03
**Symptom:** Subagents inicialmente não sabiam das regras do projeto
porque o CLAUDE.md não chegava no contexto deles.
**New pattern:** Cada `.claude/agents/<name>.md` repete as regras
críticas (allow/deny lists, never-do, output format) dentro do
próprio arquivo. Não confiar em herdar de CLAUDE.md.
**Result:** Agentes operam corretamente mesmo se chamados sem o
CLAUDE.md no contexto. Documentado em `LL-006`.

## PI-009 — Prompt Contract for autonomous tasks

**Date:** 2026-05-04
**Symptom:** Autonomous prompts to `/afk-maintain` and specialist agents
drifted scope, occasionally producing PRs that touched forbidden files
(Ruby/SU exporter, geometry thresholds, schema). Vague "fix the auditor
finding" prompts couldn't be retried deterministically because the goal,
allowed scope, and validation were under-specified.
**New pattern:** Every autonomous task instantiates the Prompt Contract
Template from `docs/learning/prompt_quality_rubric.md` before execution:
Context, Goal, Allowed files, Forbidden files, Steps, Validation, Stop
conditions, PR body, Final output. The `agent-coordinator` validates the
15 criteria + 8-item checklist before dispatching to specialists.
`/prepare-pr` runs the same gate before drafting the PR body.
**Result:** TBD — measure in next AFK runs (track halts due to
incomplete contract; count of PRs touching forbidden paths).

## Template para nova entrada

```markdown
## PI-NNN — <título curto>

**Date:** YYYY-MM-DD
**Symptom:** <o que estava ruim>
**New pattern:** <o prompt/regra/abordagem que resolveu>
**Result:** <o que melhorou empiricamente>
```
