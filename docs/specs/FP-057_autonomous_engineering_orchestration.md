# FP-057 — Autonomous Engineering Orchestration & Continuous Backlog Execution

```yaml
id: FP-057
versao: 1.0.0
status: EM_EXECUCAO            # aprovada pelo proprietario em 2026-10-24; P0 entregue por esta PR
prioridade: P0_CRITICAL
repositorio: GFCDOTA/sketchup-mcp
branch_base: develop
github_project: https://github.com/orgs/GFCDOTA/projects/1
dependencias: [FP-043, FP-054, FP-055, FP-056]
principios:
  backlog_as_source_of_truth: true
  continuous_execution: true
  automatic_issue_discovery: true
  automatic_impact_analysis: true
  no_false_pass: true
  no_unapproved_visual_changes: true
  preserve_official_artifacts: true
  fail_closed_on_missing_evidence: true
  independent_review_required_when_applicable: true
```

## 1. Problema
O executor conclui tarefas, entrega relatorio e para sem escolher a proxima; o proprietario acompanha o board, descobre tarefas
esquecidas, cobra SPEC/Project e relembra dependencias. Objetivo: **o backlog determina o que fazer, os criterios de aceite
determinam quando esta pronto e o Quality Guardian impede resultado invalido de ser dado como concluido.** O proprietario decide
so o que exige autoridade humana.

## 2. Arquitetura
```text
Issues/Project -> Backlog Discovery -> Dependency & Impact Analyzer -> Task Scheduler -> Executor
   -> Implementacao + testes -> PR -> Quality Guardian -> (FAIL: corrige e revalida | PASS: politica de revisao)
   -> (revisao exigida: GPT Review | dispensada: merge) -> Backlog Reconciliation -> proxima tarefa elegivel
```
Nenhuma transicao e inferida de mensagem de progresso: cada mudanca de estado exige fato verificavel.

## 3. Fonte unica de verdade
- **Issues** (Epic, Story, Bug, Task, Technical Debt, Human Decision): identificacao, prioridade, dependencias, criterios de aceite,
  SPEC, evidencia requerida. Nao existe segundo backlog manual.
- **Project** (`Backlog, Ready, In Progress, GPT Review, Blocked, Done`): interface visual; nao e autoridade exclusiva da conclusao tecnica.
- **SPECs** versionadas no repositorio; mudanca de contrato dispara analise dos consumidores; nao se incrementa versao de todas.
- Rastreabilidade: Issue -> SPEC -> componentes -> PR -> commit -> testes -> evidencia -> veredito.

## 4. Descoberta e elegibilidade (P1)
Tarefa elegivel: aberta; com criterios de aceite; dependencias obrigatorias satisfeitas; sem decisao humana pendente para a acao
pretendida; sem outra execucao ativa; arquivos sem conflito com outro trabalho; proximo passo seguro e autorizado. Se nao elegivel,
registrar a razao e avaliar a proxima.
Prioridade: P0 de integridade/seguranca de artefatos > falsos PASS e gates incorretos > bloqueios que travam varias tarefas >
regressoes recentes > integracao real FP-055/056 > correcoes funcionais > debito necessario > funcionalidades aprovadas > melhorias.
O scheduler pondera dependencias, impacto, risco e caminho critico; o objetivo e um pipeline funcional, nao Issues fechadas.

## 5. Grafo de dependencias
EPIC -> STORY -> TASK/BUG -> componente -> teste/prova. Validar: referencia inexistente, ciclo, dependencia ja resolvida ou
equivocada, **Epic aberta usada como bloqueio** (nao bloqueia filhas), tarefas paralelizaveis, bloqueio tecnico classificado como
decisao humana.

## 6. Bloqueios (taxonomia)
`TECHNICAL` (investigar e corrigir) · `DEPENDENCY` (resolver dependencia) · `EVIDENCE` (produzir prova) · `HUMAN_DECISION`
(alternativas verificadas, impactos, evidencias, recomendacao) · `EXTERNAL` (registrar requisito externo) · `ENVIRONMENT`
(recuperar ou escalar). Dependencia resolvida reavalia dependentes; falta de evidencia gera tarefa de validacao; falha temporaria
de API nao e defeito de negocio; bloqueio genuino nao some porque o agente continuou trabalhando.

## 7. Defeito novo
Reproduzir/registrar evidencia -> procurar Issue existente (sem duplicar) -> classificar -> causa-raiz ou hipotese -> componentes e
SPECs afetados -> dependencias -> criar/atualizar Issue com criterios de aceite e prioridade -> decidir se interrompe -> corrigir
quando elegivel -> revalidar consumidores. Critico que invalida a implementacao atual tem prioridade; independente e registrado sem
interromper. Defeito novo nao cria SPEC nova automaticamente.

## 8. Quality Guardian e integracao
Reusa `quality-guardian` e `audit-report` e os checks `qg: backlog, issues and specs`, `qg: PR policy`,
`qg: geometry, program and integration`, preservando os 5 checks do CI. Estados de integracao: `AVAILABLE -> INVOKED -> CONSUMED
-> REFLECTED_IN_MODEL -> VALIDATED`; capacidade existente e nao consumida nao e integrada. **Fail-closed:** prova nao executada,
nao coletada, de commit errado, runtime velho, artefato invalido ou que nao corresponde ao alegado => `BLOCKED`/`FAIL`/
`NOT_EXECUTED`, nunca `PASS` por ausencia de informacao.

## 9. Revisao independente GPT
Estados `GPT_REVIEW_REQUIRED | PENDING | APPROVED | CHANGES_REQUESTED`. O executor nao aprova o proprio trabalho. Exigida para:
contratos centrais, coordenadas/geometria, algoritmos de posicionamento, solver/regras rigidas, gates de seguranca, politicas de
aprovacao, evidencias L2, reducao de programa, estrutura do pipeline inteligente. Aprovacao verificavel identifica revisor
autorizado, PR, **SHA revisado**, veredito, evidencias e data; texto `GPT-REVIEW: APPROVED` do proprio executor nao basta; novo
commit invalida a aprovacao do SHA anterior. Sem API paga o GPT nao e acionado por evento: a tarefa fica aguardando e o scheduler
segue nas independentes.

## 10. Board
Transicoes: Backlog->Ready (dependencias satisfeitas); Ready->In Progress (execucao assumida); In Progress->GPT Review
(pronto para revisao independente); In Progress->Blocked (bloqueio real comprovado); GPT Review->In Progress (correcoes);
GPT Review->Done (revisao aprovada + demais criterios); In Progress->Done (sem revisao exigida + todos os gates); Blocked->Ready
(causa resolvida). Done exige fechamento tecnico verificavel. Project indisponivel/rate limit: dados canonicos ficam nas Issues,
registra o erro, repete apos o prazo, sem cartao duplicado e sem alterar o resultado tecnico. Sem `BACKLOG_PROJECT_TOKEN` (#508) a
automacao do Project e **parcial**; nunca pedir nem inventar o valor.

## 10b. Estado de execucao e recuperacao
Manifesto duravel (`schema_version`, `active_spec`, `active_phase`, `current_issue`, `current_branch`, `base_commit`,
`last_verified_commit`, `open_pull_requests`, `pending_reviews`, `blocked_issues`, `next_eligible_issues`, `last_successful_gate`,
`last_audit`, `recovery_instructions`): checkpoint operacional, nao segundo backlog; sem segredos. Ao iniciar: ler, reconciliar
com o GitHub, verificar branches/worktrees/commits/PRs/jobs, identificar interrompidas, nao repetir efeitos, retomar da ultima
operacao segura. Concorrencia: cada tarefa tem Issue, branch, agente, commit-base, componentes e estado; worktree por tarefa;
execucao morta nao deixa bloqueio permanente; nunca apagar worktree com alteracao nao integrada.

## 11. Modo de execucao
`CONTINUOUS_WITHIN_SESSION` e `DURABLE_RESUME` sao obrigatorios; `UNATTENDED_RUNNER` exige runner implantado e testado e **nao e
declarado operacional sem isso**. Sem loop infinito nem consulta agressiva a APIs. Durante a sessao: nao parar apos fase, merge,
atualizacao de Issue ou relatorio; nao pedir autorizacao tecnica ja concedida; nao abandonar independentes por decisao humana pendente.

## 12. Autonomia e limites
Autorizado: investigar, criar Issues, atualizar backlog, testes, correcoes tecnicas, PRs, reexecutar testes, atualizar SPECs, merge
que cumpra a politica, seguir para a proxima. **Nao autorizado:** alterar planta aprovada, reduzir mobiliario aprovado, inventar
fontes, aprovar a propria revisao GPT, manipular evidencias, relaxar gates, ignorar branch protection, sobrescrever `.skp`/PDF
oficiais, expor credenciais, fechar Issue sem criterio cumprido, mergear alteracao critica sem revisao independente obrigatoria.

## 13. Fases e gates
| Fase | Entrega | Gate |
|---|---|---|
| P0 | auditoria do que existe (Quality Guardian, `board_sync`, `audit-report`, Issues, protecao, marcadores GPT) | mapa do fluxo, lacunas comprovadas, responsabilidades |
| P1 | descoberta de tarefas e grafo de dependencias | agente identifica o proximo trabalho elegivel sem intervencao |
| P2 | scheduler e checkpoints | reiniciar nao duplica Issues/PRs/operacoes nem perde trabalho |
| P3 | defeito novo -> Issue/analise/correcao; analise de impacto | ciclo sem reorganizacao manual do backlog |
| P4 | Quality Guardian e politica de revisao reforcados | PR invalido bloqueado, marcador GPT forjado rejeitado, novo commit invalida aprovacao, protecao efetiva |
| P5 | reconciliacao do board | Issues e Project reconciliados, limites de autenticacao reportados |
| P6 | prova de recuperacao ponta a ponta no GitHub | tarefa sintetica, check reprovado de proposito, correcao, reinicio sem duplicar; revisao independente pendente nao paralisa |
| P7 | adocao nas FP-055/056 | ao concluir tarefa real, seleciona e comeca a proxima |

## 14. Casos reais obrigatorios
A (#484: decisao arquitetonica pendente, geometria preservada, investigacoes independentes) · B (#501/#502: medicoes ainda
executaveis, alternativas viaveis ou inviaveis, nenhum layout reprovado e aprovado) · C (#508: credencial externa detectada, nao
inventada, segue com a sincronizacao possivel) · D (apos merge: reconciliar, reavaliar dependencias, escolher outra Issue) ·
E (GPT Review: registrar PR e SHA, nao fingir aprovacao, merge bloqueado quando obrigatorio, continuar outras tarefas).

## 15. Relatorio e Definition of Done
Relatorio versionado `AUTONOMOUS ENGINEERING STATUS` (backlog por estado, bloqueios por causa, qualidade, integracao, execucao,
recuperacao) sem metrica inventada. Concluida quando: backlog consultado automaticamente; dependencias corretas; tarefas elegiveis
selecionadas sem instrucao; defeitos novos registrados; criterios de aceite verificados; Guardian bloqueia violacoes; revisao GPT
nao falsificavel; Project reconciliavel; interrupcoes recuperaveis; continua apos merges; bloqueadas nao paralisam independentes;
prova real ponta a ponta; nenhum arquivo oficial alterado; situacao inspecionavel; nada declarado 24/7 sem runner.

> Reaproveitamento (nao duplicar): `tools/validation/{backlog_gate, issue_integrity_gate, spec_integrity_gate, pr_policy_gate,
> quality_geometry_gate, board_sync, audit_report, known_gaps}.py`, `docs/governance/`, workflows `quality-guardian` e `audit-report`.
