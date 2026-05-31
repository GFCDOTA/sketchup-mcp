# `.claude/docs/index.md` — índice humano

Mapa pra navegar `.claude/` sem duplicar conteúdo. Cada link
aponta pra source-of-truth, não pra cópia.

## Onde começar

- **Constituição (load-bearing)**: [`constitution.md`](../constitution.md)
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
| [`specs/skp_proof_of_progress_gate.md`](../specs/skp_proof_of_progress_gate.md) | "No SKP, no progress" — toda PR de fidelidade gera SKP + comparação |
| [`specs/sdd_and_harness_engineering.md`](../specs/sdd_and_harness_engineering.md) | Spec → fixture → teste → artifact |
| [`specs/repository_hygiene.md`](../specs/repository_hygiene.md) | Triggers reais pra cleanup |

### Templates (usar ao criar nova feature/spec)

| Template | Quando |
|---|---|
| [`specs/templates/feature_spec_template.md`](../specs/templates/feature_spec_template.md) | Nova feature FP-NNN |
| [`specs/templates/fidelity_spec_template.md`](../specs/templates/fidelity_spec_template.md) | Documentar veredito de fidelidade de um build |
| [`specs/templates/artifact_contract_template.md`](../specs/templates/artifact_contract_template.md) | Documentar contrato de artifact (input/output/schema) |
| [`specs/templates/regression_summary_template.md`](../specs/templates/regression_summary_template.md) | Preencher `regression_summary.md` em `artifacts/review/<plant>/<cycle>/` |

## Evals — como medimos progresso

| Arquivo | Pra que serve |
|---|---|
| [`evals/eval_strategy.md`](../evals/eval_strategy.md) | 3 camadas: contract suite / gates_self_check / rubric humano |
| [`evals/fidelity_rubric.md`](../evals/fidelity_rubric.md) | Rubric A/B/C/D OK/WARN/FAIL pra Camada 3 |
| [`evals/regression_matrix.md`](../evals/regression_matrix.md) | Matriz feature × gate histórica |

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
| [`skills/generate-and-compare-skp-after-change`](../skills/generate-and-compare-skp-after-change/SKILL.md) | Gerar SKP novo + comparar before/after (Constitution #8) |
| [`skills/skp-visual-self-correction`](../skills/skp-visual-self-correction/SKILL.md) | Visual Oracle Gate (FP-030); deterministic findings + qualitative axes |
| [`skills/repo-governance`](../skills/repo-governance/SKILL.md) | PR / branch / merge / hygiene |
| [`skills/multi-agent-handoff`](../skills/multi-agent-handoff/SKILL.md) | Trabalho paralelo / handoff |

## Audits — histórico de revisões

| Arquivo | Tópico |
|---|---|
| [`docs/audits/2026-05-27_claude_structure_audit.md`](audits/2026-05-27_claude_structure_audit.md) | Audit da estrutura `.claude/` pós PR #194 + patch P1 |

## Pontos de saída pro resto do repo

- `../../README.md` — Quickstart, pipeline overview, schema
- `../../docs/specs/` — Specs históricos (FP-NNN), assets canônicos
  - `FP-030_visual_oracle_gate.md` — Visual Oracle Gate
- `../../artifacts/<plant>/` — Deliverables canônicos
- `../../artifacts/review/<plant>/<run_id>/final/` — Review artifacts pra PR
- `../../tests/` — Contract suite (`test_visual_oracle_contract.py` inclusive)
- `../../tools/run_skp_visual_review.py` — FP-030 runner
- `../../tools/prompts/visual_oracle_reviewer.md` — prompt pra agente de visão
- `../../schemas/visual_findings.schema.json` — JSON Schema v1
- `../../fixtures/visual_oracle_examples/` — 19 exemplos seed (good_real + bad_real + synthetic)
- `../../planta_74.pdf` — PDF source da planta real
