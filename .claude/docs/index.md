# `.claude/docs/index.md` — índice humano

Mapa pra navegar `.claude/` sem duplicar conteúdo. Cada link
aponta pra source-of-truth, não pra cópia.

## Onde começar

- **Estrutura geral**: [`README.md`](../README.md)
- **Bootloader / load order**: [`CLAUDE.md`](../CLAUDE.md)

## Memory — contexto vivo

| Arquivo | Pra que serve |
|---|---|
| [`memory/project_context.md`](../memory/project_context.md) | Identidade + pipeline + fixtures canônicas |
| [`memory/current_state.md`](../memory/current_state.md) | Branch, PRs recentes, baselines (decai rápido) |
| [`memory/operational_rules.md`](../memory/operational_rules.md) | GREEN/YELLOW/RED, autonomia, consulta LLM |
| [`memory/git_workflow.md`](../memory/git_workflow.md) | develop-first, gh, branch naming |
| [`memory/multi_agent_coordination.md`](../memory/multi_agent_coordination.md) | Worktrees, out-of-band, fetch sequencial |
| [`memory/artifact_policy.md`](../memory/artifact_policy.md) | `.skp` como artefato humano principal |
| [`memory/lessons_learned.md`](../memory/lessons_learned.md) | Aprendizados permanentes |
| [`memory/deprecated_context.md`](../memory/deprecated_context.md) | Decisões superseded (não seguir) |

## Specs — contrato do produto

| Arquivo | Pra que serve |
|---|---|
| [`specs/product_goal.md`](../specs/product_goal.md) | O que é sucesso pro humano |
| [`specs/fidelity_gate.md`](../specs/fidelity_gate.md) | Dimensões de fidelidade |
| [`specs/perfect_reference_strategy.md`](../specs/perfect_reference_strategy.md) | Tiers de verdade, truth cards |
| [`specs/skp_artifact_layout.md`](../specs/skp_artifact_layout.md) | Paths, naming, metadata |
| [`specs/sdd_and_harness_engineering.md`](../specs/sdd_and_harness_engineering.md) | Spec → fixture → teste → artifact |
| [`specs/repository_hygiene.md`](../specs/repository_hygiene.md) | Triggers reais pra cleanup |

## Plans — estado curto

| Arquivo | Pra que serve |
|---|---|
| [`plans/roadmap.md`](../plans/roadmap.md) | Milestones M0–M4 |
| [`plans/next_actions.md`](../plans/next_actions.md) | Fila curta de próximas ações |
| [`plans/active_work.md`](../plans/active_work.md) | Branch + objetivo + escopo |
| [`plans/stopped_work.md`](../plans/stopped_work.md) | Pausados / encerrados |

## Skills — operação por área

| Skill | Quando dispara |
|---|---|
| [`skills/pdf-to-skp-pipeline`](../skills/pdf-to-skp-pipeline/SKILL.md) | Build do `.skp` a partir de consensus |
| [`skills/fidelity-review`](../skills/fidelity-review/SKILL.md) | Review SKP vs PDF |
| [`skills/skp-artifact-management`](../skills/skp-artifact-management/SKILL.md) | Promotion runs/ → artifacts/ |
| [`skills/repo-governance`](../skills/repo-governance/SKILL.md) | PR / branch / merge / hygiene |
| [`skills/multi-agent-handoff`](../skills/multi-agent-handoff/SKILL.md) | Trabalho paralelo / handoff |

## Pontos de saída pro resto do repo

- `../../README.md` — Quickstart, pipeline overview, schema
- `../../docs/specs/` — Specs históricos (FP-NNN), assets canônicos
- `../../artifacts/<plant>/` — Deliverables canônicos
- `../../tests/` — Contract suite
- `../../planta_74.pdf` — PDF source da planta real
