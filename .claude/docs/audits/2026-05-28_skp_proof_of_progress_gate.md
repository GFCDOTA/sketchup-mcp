# Audit — SKP Proof-of-Progress Gate introduction (2026-05-28)

Audit log da introdução da regra permanente "No SKP, no
progress" / SKP Proof-of-Progress Gate.

## Contexto

PR #194 cravou a estrutura `.claude/`. PR #195 pinou os
invariantes de opening routing após uma fidelity-review onde:

1. Visual inspection do iso render levantou hipótese: "estão
   aparecendo janelas a mais"
2. Data check (`window_apertures_3d == 4`, `count(kind=window) == 4`)
   dismissed a hipótese
3. Mas o exercício mostrou: `gates_self_check = true` machine-
   readable **não basta** pra prova de fidelidade. Humano olha
   o `.skp` no SU.

A regra **No SKP, no progress** vem responder esse gap.

## O que esta PR introduz

### Constitution

- **Princípio #8** adicionado em `.claude/constitution.md`:
  "Toda mudança que afete fidelidade arquitetônica deve gerar
  `.skp` novo em pasta human-facing com renders + report +
  regression_summary.md. Sem isso, a melhoria não está concluída."

### Spec canônica

- `.claude/specs/skp_proof_of_progress_gate.md` — spec completa
  com: problema, quando aplica, quando NÃO aplica, artefatos
  obrigatórios, separação de pastas, fluxo de 5 passos,
  critérios de bloqueio, regra pra agentes, follow-up spec do
  gate automático em `tools/`.

### Skill operacional

- `.claude/skills/generate-and-compare-skp-after-change/SKILL.md`
  — auto-trigger após mudança de fidelidade. Define o flow:
  baseline → build → comparar → summary → promote.

### Template

- `.claude/specs/templates/regression_summary_template.md` —
  template do `regression_summary.md` exigido em
  `artifacts/review/<plant>/<cycle>/`.

### Memory + policy

- `memory/lessons_learned.md` #12 (LL-021) — "No SKP, no
  progress" com referência ao caso 2026-05-27 que motivou.
- `memory/artifact_policy.md` — 6º requisito de sucesso pra PRs
  que tocam fidelidade.
- `memory/current_state.md` — atualizado (PR #195 merged, branch
  atual, baselines).

### Knowledge base

- Bootloader `CLAUDE.md` agora @imports o novo spec.
- `README.md` + `docs/index.md` listam novo spec/skill/template.
- `plans/active_work.md` + `plans/next_actions.md` atualizados.

## O que esta PR NÃO faz

- **NÃO** cria `tools/check_skp_proof_of_progress.py` — fica
  como follow-up TODO documentado no spec
- **NÃO** aplica retroativamente em PRs anteriores
- **NÃO** regenera `.skp` de planta_74 — regra é normativa,
  não dogfooded aqui (será dogfooded na próxima PR de builder)
- **NÃO** toca `tools/`, `tests/`, `fixtures/`, `artifacts/<plant>/`

## Por que separar gate textual de gate automatizado

O gate textual (esta PR) já dá:

1. Constitutional weight — reviewer humano cobra
2. Documentação rastreável — agente lê e segue
3. Skill com auto-trigger description — Claude Code carrega
4. Template pronto pra preencher

O gate automatizado (`tools/check_skp_proof_of_progress.py`,
próxima PR) adicionaria:

1. CI bloqueia PR não-conformante automaticamente
2. Detecção via `git diff --name-only`
3. Independente de reviewer humano lembrar

Separar permite landar a regra HOJE sem ficar bloqueado pela
implementação do tool. A regra textual já protege via review.

## Encaixe operacional

Esta PR é **categoria 5** (user-requested milestone) da
[`memory/operational_rules.md`](../../memory/operational_rules.md).
User pediu explicitamente "criar a regra permanente No SKP, No
Progress". Slice claro, escopo bounded.

Próximo trabalho legítimo (após merge): item #2 da fila
(`plans/next_actions.md`) — tool automatizado, mas **só** com OK
explícito do humano.

## Validation post-patch

```bash
# Gitignore deixa os novos arquivos visíveis
git -C /e/Claude/sketchup-mcp check-ignore -v \
  .claude/specs/skp_proof_of_progress_gate.md \
  .claude/skills/generate-and-compare-skp-after-change/SKILL.md \
  .claude/specs/templates/regression_summary_template.md \
  .claude/docs/audits/2026-05-28_skp_proof_of_progress_gate.md
# → todos "not ignored"

# Imports do bootloader resolvem
cat .claude/CLAUDE.md CLAUDE.md | grep -oE '@\.claude/[a-zA-Z_/-]+\.md' \
  | sed 's/@//' | sort -u \
  | while read f; do test -f "$f" && echo OK $f || echo MISS $f; done
# → todos OK (incluindo o novo spec)

# Contract suite ainda verde (sem mexer código)
.venv/Scripts/python.exe -m pytest tests/ -q
# → 89 passed, 5 skipped
```

## Audit metadata

- **Auditor**: humano (Felipe)
- **Data**: 2026-05-28
- **Branch**: `feat/skp-proof-of-progress-gate`
- **Base**: `origin/develop` em `04cb25b` (post-PR #195)
- **Relacionado**: PR #194 (estrutura inicial), PR #195
  (opening routing invariants), audit
  `2026-05-27_claude_structure_audit.md`
