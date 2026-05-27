# Claude Operating Instructions — sketchup-mcp

> Bootloader. Curto por design. Detalhes vivem nos arquivos
> importados abaixo + skills auto-discovered.

## Project mission

Gerar um `.skp` SketchUp fiel a uma planta arquitetônica de PDF.
Pipeline: `consensus.json → tools/build_plan_shell_skp.{py,rb} →
.skp + renders + report`.

`.skp` é o artefato humano mais importante. Tudo o mais (testes,
refactor, ADRs, cleanup) só conta se destravar esse objetivo.

Detalhe: `@.claude/specs/product_goal.md` e
`@.claude/memory/project_context.md`.

## Critical rules (Hard Rules)

1. **NEVER invent walls / rooms / openings.** A consensus é a
   fonte de verdade — se não está em `consensus.json`, não
   entra no `.skp`.
2. **NEVER carve windows full-height.** Windows preservam wall
   mass abaixo do peitoril e acima da verga (3D aperture path).
   Doors / passages / porta-vidro vão pelo path 2D full-height.
3. **NEVER mutate input fixtures** em `fixtures/quadrado/` ou
   `fixtures/planta_74/` sem aprovação humana explícita — a
   smoke suite pina contra elas.
4. **NEVER push direto em `main`.** PRs `feature/<x>` ou
   `chore/<x>` → `develop`; `main` só recebe `develop` via merge.

Quebrar uma dessas é RED. Ver `@.claude/memory/operational_rules.md`
§ GREEN / YELLOW / RED.

## Outras regras críticas

- **`--mode headless` é proibido em dev local.** Default
  `interactive` deixa SU aberto pra inspeção. `headless` é só pra
  CI (PR #186).
- **`/runs/` é scratch.** Não commitar. SKP de evidência precisa
  ser promovido pra `artifacts/<plant>/`. Ver
  `@.claude/memory/artifact_policy.md`.
- **Develop-first.** Branch nova a partir de `origin/develop`,
  fetch antes de decisões remotas, sequencial.
- **Multi-agent**: nunca assumir exclusividade do repo. Ver
  `@.claude/memory/multi_agent_coordination.md`.

## Load order

@.claude/constitution.md

@.claude/memory/project_context.md
@.claude/memory/current_state.md
@.claude/memory/operational_rules.md
@.claude/memory/git_workflow.md
@.claude/memory/multi_agent_coordination.md
@.claude/memory/artifact_policy.md
@.claude/memory/lessons_learned.md
@.claude/memory/deprecated_context.md

@.claude/specs/product_goal.md
@.claude/specs/fidelity_gate.md
@.claude/specs/skp_artifact_layout.md

@.claude/evals/eval_strategy.md
@.claude/evals/fidelity_rubric.md

@.claude/plans/active_work.md
@.claude/plans/next_actions.md

## Specs sob demanda (não auto-load)

Estes são consultados quando relevantes, não importados sempre:

- `.claude/specs/perfect_reference_strategy.md`
- `.claude/specs/sdd_and_harness_engineering.md`
- `.claude/specs/repository_hygiene.md`
- `.claude/specs/templates/*` (use ao criar nova feature/spec)
- `.claude/evals/regression_matrix.md`
- `.claude/plans/roadmap.md`
- `.claude/plans/stopped_work.md`
- `.claude/docs/index.md`
- `.claude/docs/audits/*` (histórico, não regra viva)

## Skills

Auto-discovered em `.claude/skills/*/SKILL.md`:

- `pdf-to-skp-pipeline` — build do `.skp` a partir de consensus
- `fidelity-review` — SKP vs PDF review checklist
- `skp-artifact-management` — promotion runs/ → artifacts/
- `repo-governance` — PR / branch / merge / hygiene
- `multi-agent-handoff` — coordenação multi-agent / worktrees

## Scratch

`.claude/scratch/` é local-only e ignorada pelo git. Rascunhos
descartáveis. Nada importante vive lá.
