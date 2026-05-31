# Audit — `.claude/` structure (2026-05-27)

> Audit log da estrutura `.claude/` introduzida em PR #194 e
> patch P1 subsequente. Documenta achados, P1 fixes aplicados, e
> follow-ups deixados pra próximas iterações.

## Contexto

PR #194 (`chore: organize Claude project knowledge under
.claude/`) introduziu a estrutura inicial: `memory/`, `specs/`,
`plans/`, `skills/`, `docs/`, `scratch/`, com `.claude/CLAUDE.md`
como bootloader. A primeira iteração entregou 26 arquivos novos.

Esta auditoria avaliou se o resultado funciona como **sistema
moderno de IA/SDD** ou se ainda é "markdown bonito". Identificou
gaps em enforcement real, schema alignment, e risk de loops
infinitos.

## Veredito da auditoria

- **Nota geral**: 8/10
- **SDD**: 7/10
- **IA/agentes**: 6.5/10
- **Enforcement real**: 5.5/10

## P1 achados → fixes aplicados (este patch)

### P1 #1 — Metadata sidecar apontava pra `runs/`

**Achado**: `artifacts/planta_74/planta_74.skp.metadata.json`
tinha `skp_path` apontando pra `E:\Claude\sketchup-mcp\runs\
planta_74\planta_74.skp` — contradição com a regra "`runs/` é
scratch, `artifacts/` é deliverable".

**Fix**:
- `skp_path` agora aponta pra `artifacts/planta_74/planta_74.skp`
  (path canônico do artifact)
- Adicionado `source_run_path` pra preservar provenance do build
- Documentado em [`specs/skp_artifact_layout.md`](../../specs/skp_artifact_layout.md)
  o SOP de rewrite no promotion
- Skill [`skp-artifact-management`](../../skills/skp-artifact-management/SKILL.md)
  agora inclui o rewrite no flow

### P1 #2 — `.gitignore` ignorava `constitution.md` e `evals/`

**Achado**: o whitelist no `.gitignore` cobria `agents`,
`commands`, `hooks`, `skills`, `specs`, `memory`, `plans`,
`docs`, `settings.json`, `CLAUDE.md`, `README.md` — mas se Claude
criasse `.claude/constitution.md` ou `.claude/evals/...`, esses
arquivos ficariam silenciosamente ignorados.

**Fix**: `.gitignore` agora libera:
- `!.claude/constitution.md`
- `!.claude/evals/`

### P1 #3 — `fidelity_gate.md` não batia com o schema real

**Achado**: doc falava em `wall_fidelity` / `room_fidelity` /
`opening_fidelity` como se fossem campos do
`geometry_report.json`. Schema real tem `gates_self_check.{plan_shell_group_exists,
wall_shell_is_single_group, floors_separated_from_walls,
default_material_faces_zero}`.

**Fix**: [`specs/fidelity_gate.md`](../../specs/fidelity_gate.md)
reescrito com **dois eixos** explícitos:
- Eixo 1 (machine-readable) = 4 booleans do `gates_self_check`
- Eixo 2 (julgamento humano) = wall/room/opening fidelity como
  prose no `artifacts/<plant>/README.md`

Adicionado snapshot numérico de `planta_74` (2026-05-27) com
valores reais lidos do `geometry_report.json`.

### P1 #4 — Faltavam blocos modernos de SDD

**Achado**: nenhum `constitution.md`, `evals/`, `specs/templates/`
ou `docs/audits/`. Estrutura era "markdown bonito" sem
enforcement.

**Fix**: novos blocos criados:
- `.claude/constitution.md` — 7 princípios load-bearing
- `.claude/evals/eval_strategy.md` — 3 camadas (contract / gates /
  rubric)
- `.claude/evals/fidelity_rubric.md` — rubric A/B/C/D com
  OK/WARN/FAIL
- `.claude/evals/regression_matrix.md` — matriz feature × gate
- `.claude/specs/templates/feature_spec_template.md`
- `.claude/specs/templates/fidelity_spec_template.md`
- `.claude/specs/templates/artifact_contract_template.md`
- `.claude/docs/audits/` (este arquivo)

### P1 #5 — `DONE IS NOT STOP` absoluto = risco de loop

**Achado**: a regra "DONE IS NOT STOP. Parar somente nos
critérios RED" deixa o agente terminar uma organização e
inventar outra auditoria, depois outra doc, depois outra
limpeza. Audit recente do user reforçou esse fail-mode em PRs
#73 / 2026-05-08 / #108 (3 hygiene passes convergindo em
"preserve" = bikeshed).

**Fix**: [`memory/operational_rules.md`](../../memory/operational_rules.md)
§ "Continuar automaticamente vs parar" reescrito:
- "Natural slice complete IS a valid stop"
- Continuar automaticamente só com encaixe em 5 categorias:
  SKP fidelity / artifact quality / failing gate / active PR
  cleanup / user-requested milestone
- Verbal `NAO PARE` mode continua sendo override, mas ainda
  filtra por produto-ROI

Constitution #6 cravou o princípio. Memory global
`feedback_done_is_not_stop.md` também refinada.

## Coisas boas confirmadas

- **`.skp` policy** ficou bem defendida — regra no bootloader,
  em `artifact_policy.md`, em `skp_artifact_layout.md` e na
  skill `skp-artifact-management`.
- **`FP-026_residual_wall_stub_elimination.md`** segue sendo o
  melhor exemplo de SDD real no repo — usado como referência no
  novo `templates/feature_spec_template.md`.
- **`perfect_reference_strategy.md`** com os 4 tiers de verdade
  ficou load-bearing.

## Validation post-patch

```bash
# Constitution + evals trackáveis
git check-ignore -v .claude/constitution.md  # → not ignored
git check-ignore -v .claude/evals/eval_strategy.md  # → not ignored
git check-ignore -v .claude/scratch/test.md  # → still ignored

# Metadata sidecar aponta pra artifact, não pra runs/
grep skp_path artifacts/planta_74/planta_74.skp.metadata.json
# → "skp_path": "artifacts/planta_74/planta_74.skp"
# → "source_run_path": "runs/planta_74/planta_74.skp"

# Root CLAUDE.md continua stub
cat CLAUDE.md
# → @.claude/CLAUDE.md

# Nenhuma mudança em código (tools/, tests/, fixtures/, Ruby builder)
git diff --stat -- tools/ tests/ fixtures/ 'docs/specs/*.md'
# → empty
```

## Follow-ups (não bloqueiam este patch)

- [ ] **Builder produz schema 1.1.0 com `source_run_path`** — hoje
      o promotion rewrite é manual; ideal é `tools/promote_artifact.py`
      gerar o sidecar correto direto
- [ ] **CI rodando build canônico** — `gates_self_check` deveria
      falhar PR no GitHub Actions
- [ ] **Critério numérico pra rubric D1/D2** — hoje é qualitativo
- [ ] **Histórico de regressão**: completar `evals/regression_matrix.md`
      com linhas das PRs #185–#193
- [ ] **`.ai_bridge/` sketchup-mcp**: confirmar se é convenção
      adotada aqui (em outros repos do user existe)

## Audit metadata

- **Auditor**: humano (Felipe) + revisão crítica do conteúdo do
  archive
- **Data**: 2026-05-27
- **Branch da patch**: `chore/organize-claude-knowledge-base`
- **Commits**: PR #194 (estrutura inicial) + commits de P1 fix
  desta data
