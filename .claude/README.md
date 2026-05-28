# `.claude/` — base operacional do projeto

Contexto vivo, regras, specs, planos e skills do `sketchup-mcp`.
Tudo aqui é versionado (subdirs whitelisted no `.gitignore` do
repo) exceto `scratch/`.

## Mapa

```
.claude/
├── CLAUDE.md              ← bootloader curto com @imports
├── constitution.md        ← 7 princípios load-bearing (vence sobre tudo)
├── README.md              ← este arquivo
├── memory/                ← contexto vivo do projeto
│   ├── project_context.md
│   ├── current_state.md
│   ├── operational_rules.md
│   ├── git_workflow.md
│   ├── multi_agent_coordination.md
│   ├── artifact_policy.md
│   ├── lessons_learned.md
│   └── deprecated_context.md
├── specs/                 ← contrato do produto
│   ├── product_goal.md
│   ├── fidelity_gate.md
│   ├── perfect_reference_strategy.md
│   ├── skp_artifact_layout.md
│   ├── skp_proof_of_progress_gate.md  ← "No SKP, no progress" (Constitution #8)
│   ├── sdd_and_harness_engineering.md
│   ├── repository_hygiene.md
│   └── templates/         ← templates pra novas features/specs
│       ├── feature_spec_template.md
│       ├── fidelity_spec_template.md
│       ├── artifact_contract_template.md
│       └── regression_summary_template.md  ← pro SKP Proof-of-Progress Gate
├── evals/                 ← como medimos progresso real
│   ├── eval_strategy.md
│   ├── fidelity_rubric.md
│   └── regression_matrix.md
├── plans/                 ← estado curto / próximos passos
│   ├── roadmap.md
│   ├── next_actions.md
│   ├── active_work.md
│   └── stopped_work.md
├── skills/                ← skills custom (auto-load pelo Claude Code)
│   ├── pdf-to-skp-pipeline/SKILL.md
│   ├── fidelity-review/SKILL.md
│   ├── skp-artifact-management/SKILL.md
│   ├── generate-and-compare-skp-after-change/SKILL.md
│   ├── repo-governance/SKILL.md
│   └── multi-agent-handoff/SKILL.md
├── docs/
│   ├── index.md           ← índice navegável
│   └── audits/            ← audit logs pontuais (histórico)
│       └── 2026-05-27_claude_structure_audit.md
└── scratch/               ← rascunhos locais, IGNORADA pelo git
```

## O que vai onde

| Pasta | Vai aqui | NÃO vai aqui |
|---|---|---|
| `constitution.md` | 7 princípios load-bearing. Vence sobre qualquer outro `.md` em conflito. | Regra operacional detalhada (vai em `memory/` ou `specs/`) |
| `memory/` | Regra viva permanente, contexto que decai (current_state), aprendizado durável | Tarefas atuais, planos próximos, logs de PR |
| `specs/` | Contrato de produto, fidelidade, layout, hygiene + `templates/` pra novas | Snapshot de PR / branch, estado-do-dia |
| `evals/` | Estratégia de medição, rubric, matriz feature × gate | Spec de produto (vai em `specs/`) |
| `plans/` | Roadmap, fila curta, branch em curso, work pausado | Specs longas, regra permanente |
| `skills/` | Operação por área com SKILL.md frontmatter | Especificação / regra geral |
| `docs/` | Índice + pointers humanos + `audits/` (histórico) | Cópia de conteúdo de outros `.md` |
| `scratch/` | Rascunhos, experimentos descartáveis | Qualquer coisa que vale a pena commitar |

## Política de atualização

- **Memory** atualiza quando regra muda ou decisão é cravada.
  Histórico vai pra `deprecated_context.md`, NÃO sumir.
- **Specs** versionar via novo arquivo (`<spec>-v2.md`) quando
  mudança é breaking; in-place se for refino.
- **Plans** especialmente `current_state.md` e `active_work.md`
  precisam atualizar a cada session start / branch switch.
- **Skills** atualizar quando comando / convenção do repo muda.

## Quando criar arquivo novo

Sim se:

- Cobre tópico que ainda não tem home clara em um existente
- Tem mais de ~1 página de conteúdo durável
- Outros agentes vão precisar referenciar isoladamente

Não se:

- É 3 linhas que cabem num arquivo existente
- É contexto efêmero (vai pra `scratch/`)
- Já está coberto e a diferença é só formatação

## Quando mover pra deprecated

- Decisão antiga foi superseded por nova
- Convenção mudou (ex.: "PR manual" → "gh CLI")
- Tooling sumiu (ex.: pipelines V3–V6.x)

Mover pra `memory/deprecated_context.md` com formato:

```md
## Deprecated: <nome>
Status: superseded
Replaced by: <arquivo / regra atual>
Reason: ...
Do not use for future decisions.
```

**Nunca apagar** sem rastro. Histórico em deprecated é parte do
contexto.

## Convenções

- **Nomes de arquivo**: snake_case (`current_state.md`,
  `project_context.md`) seguindo o que o user pediu no plano
- **Datas absolutas**: `2026-05-27`, nunca "hoje"
- **`scratch/` é descartável**: pode ser limpa sem aviso

## Como o Claude Code enxerga

Quando Claude Code roda em `E:\Claude\sketchup-mcp\` (ou subpasta):

1. Lê `sketchup-mcp/CLAUDE.md` (stub) → `@.claude/CLAUDE.md`
   (bootloader) → carrega `@imports` em cadeia
2. Lista skills de `.claude/skills/*/SKILL.md` na disponibilidade
3. **NÃO** auto-carrega `specs/`, `plans/`, `docs/` — Claude lê
   quando relevante

## Onde fica o resto (fora deste repo)

| Coisa | Caminho |
|---|---|
| Skills globais | `C:\Users\felip_local\.claude\skills\` |
| Auto-memory global | `C:\Users\felip_local\.claude\projects\E--Claude\memory\` |
| Instruções globais | `C:\Users\felip_local\.claude\CLAUDE.md` + `RTK.md` |
| Binário Claude Code | `C:\Users\felip_local\AppData\Roaming\Claude\claude-code\2.1.149\claude.exe` |
| Skills built-in (pptx, pdf, verify, code-review, etc.) | Dentro do `.exe` |
