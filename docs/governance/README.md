# Governança do backlog — Quality Guardian

Fonte oficial do backlog: Project <https://github.com/orgs/GFCDOTA/projects/1> + Issues. Nada é Done por inferência.

## Gates (todos stdlib + `gh`, sem OpenAI nem serviço pago)
| Gate | O que reprova | Onde roda |
|---|---|---|
| `tools.validation.backlog_gate` | Done sem Issue fechada, prova, evidência ou revisão independente (`review_policy.json`); status × label `blocked`; dependências | `qg: backlog, issues and specs` |
| `tools.validation.issue_integrity_gate` | Issue sem critérios de aceite; bloqueio sem causa; Epic bloqueada; decisão humana sem alternativas/recomendação; dependência obsoleta | idem |
| `tools.validation.spec_integrity_gate` | SPEC FP-055/056 citando Issue ou arquivo inexistente, ou "feita" com Issue aberta | idem |
| `tools.validation.pr_policy_gate` | PR sem `Refs #N`, com `Closes`, sem `SKP-proof`, que afeta o `.skp` sem prova, código sem teste, aparência "aprovada" sem prova | `qg: PR policy` |
| `tools.validation.quality_geometry_gate` | defeito geométrico novo/pior, pré-voo reprovado, perda de programa sem registro (`known_gaps.json`) | `qg: geometry, program and integration` |
| `tools.validation.consumption_baseline` | capacidade/módulo que deixa de ser invocado/consumido, ou melhoria não registrada | idem |
| `tools.rooms.capability_catalog` | `L2_PASS` sem evidência/digests | idem |

Veredito do gêmeo em caixas: `KNOWN` enquanto houver defeito conhecido ou perda de programa registrada — **nunca** aprovação
geométrica/funcional (`geometric_approved`/`functional_approved` = `false`). A prova SketchUp real não roda no CI; fica em
`artifacts/review/**` e é exigida pela política de PR (`.skp` em `final/`).

## Causas de bloqueio (`blocked` + exatamente um `bloqueio:<causa>`)
`technical` (agente corrige) · `dependency` (depende de trabalho anterior, com dependência aberta) · `evidence` (falta
validação/prova) · `human-decision` (decisão arquitetônica, visual ou de escopo do proprietário: exige `aprovação-humana-pendente`,
`Alternativas verificadas` e `Recomendação técnica`). Epic agregadora nunca é bloqueio individual.

## Fluxo PR ↔ Issue ↔ board
1. PR cita a Issue com `Refs #N` (nunca `Closes`: a Issue só fecha com comentário `**Evidência` conferido pelo gate).
2. `python -m tools.validation.board_sync --pr N` move a Issue: rascunho ou check pendente/reprovado → `In Progress`;
   pronto e verde → `GPT Review`. Issue em `Blocked` ou `Done` não é movida por PR.
3. Gate reprovado: o job publica o motivo no PR e o merge fica bloqueado pelo check obrigatório.
4. `Done` só com critérios de aceite, prova e evidência; Issues `prio:P0` ou `gpt-review-required` fechadas depois de
   `review_policy.json: effective_from` exigem um comentário `GPT-REVIEW: APPROVED` (revisão independente do ChatGPT conectado ao
   GitHub) e ficam em `GPT Review` até lá.

## Limites conhecidos (declarados)
- A branch padrão é `main`: eventos `issues`, `issue_comment`, `schedule` e `workflow_dispatch` só disparam a partir dela.
  Os checks de `pull_request`/`push` funcionam em `develop`; a rotina diária e o relatório semanal passam a rodar quando
  `develop` for promovida a `main`.
- Mover cartões no Project dentro do Actions exige o secret `BACKLOG_PROJECT_TOKEN` (PAT com `project`); sem ele, o gate roda
  sem Project (`--no-project`) e `board_sync` roda localmente.
- Visões Kanban/Tabela/Roadmap do Project não são criáveis por API.

## Relatório de auditoria
`python -m tools.validation.audit_report --out docs/reports/audit/audit_<data>.md --with-geometry`: PRs, bloqueios por causa,
defeitos e regressões, capacidades implementadas × invocadas × consumidas, provas reais disponíveis e decisões que dependem do
proprietário. Versionado em `docs/reports/audit/` para a revisão independente.
