# FP-060 — Event-Driven Agent Orchestration

> SketchUp MCP · Spec-Driven Development · Python · SQLite · Claude Code CLI · Codex CLI · GitHub
> Issue: #606 · Refs #601 (FP-059) · Status: RASCUNHO · versão 1.0.0

## 0. Reconciliação com o HEAD (2026-11-04)

Estado real conferido antes de qualquer código (BLOCO 13, passo 3):

| Item | Estado | Consequência para esta SPEC |
|---|---|---|
| PR #605 (PoC SQLite) | aberto, `poc/isolated-sqlite-event-bus`; 24 testes determinísticos reexecutados verdes | P0: PoC movida de `experiments/` (violava o guard FP-044 de raiz) para `docs/spikes/sqlite_event_bus_poc/` e registrada no FP-042 |
| PR #598 (executor delivery, #589) | aberto | P3 depende dele: o executor confiável que faz staging/commit/push é o de #598 |
| PR #602 (SPEC FP-059) | aberto | a máquina de estados de negócio citada em §4.2 ainda não está em `develop` |
| PR #603 (revisor Codex read-only, #601 F2) | aberto | P4 **estende** este revisor; não criar outro |
| PR #604 (reconciliador do ciclo de PRs, #601 F4) | aberto | P5 **reutiliza** este reconciliador; não criar outro polling |
| `tools/validation/{task_scheduler,task_readiness,execution_state,board_sync}.py`, `tools/orchestration/{event_bridge,event_executor,execution_guards}.py`, `agent_bar/` | existem em `develop` @ a2fdafd | são os contratos a estender em P1/P5/P7 |
| `tools/orchestration/executor_delivery.py` | **não existe** em `develop` (vem no PR #598) | P3 espera #598 |

Regra derivada: P1 só começa depois que #598/#603/#604 forem landados ou descartados, senão a FP-060 nasce com dois mecanismos de claim/lease concorrentes (proibido por §4.2).

## 1. Metadata

```yaml
feature: "FP-060 — Event-Driven Agent Orchestration"
contexto_delimitado: "Engineering Automation"
funcionalidade: "Durable Event Bus & Agent Workers"
repositório: "GFCDOTA/sketchup-mcp"
branch_base: "develop"
plataforma: "Windows 11"
runtime: "Python 3.12+"
broker: "SQLite"
executor: "Claude Code CLI"
revisor: "Codex CLI"
depende_de: ["FP-057 / #589", "FP-058 / #599", "FP-059 / #601", "PR #598", "PR #605"]
tipo_de_entrega: "Implementação faseada com E2E real"
```

## 2. Contexto

### 2.1 Problema
O ciclo backlog → execução → revisão → merge ainda depende de componentes parcialmente integrados e de intervenção humana para retomar tarefas. Eventos persistidos devem acionar consumidores especializados sem depender da sessão interativa de nenhum agente.

### 2.2 Evidência experimental (PR #605)
Claude Code CLI 2.1.158 (assinatura) e Codex CLI 0.164.0 (ChatGPT) reais; SQLite como persistência e comunicação; três workers Python; dois cenários E2E (incluindo correção após review); cinco subprocessos reais; dez eventos encadeados; 24 testes determinísticos; quatro testes de resiliência com CLIs reais. Commit do harness: `53efa09933d1968bbd715868300eb60831e3e953`, worktree limpa. Evidência em `docs/spikes/sqlite_event_bus_poc/evidence/2026-11-05_real_cli/`.

### 2.3 Defeitos descobertos pela PoC (obrigatório incorporar)
- **D-060-01** — Conexão SQLite no Windows precisa ser fechada explicitamente; o context manager de transação não fecha a conexão.
- **D-060-02** — Codex produziu JSON válido sem ter lido o código. Exigir prova de inspeção vinculada ao SHA e validação externa.
- **D-060-03** — Codex read-only não roda Python de forma confiável no host. Testes rodam num processo determinístico confiável; o revisor recebe código + resultados como evidência.
- **D-060-04** — Claude retornou `subtype: success` com `is_error: true` numa falha de auth. Exit code, subtype ou existência de arquivo nunca bastam como prova de sucesso.
- **D-060-05** — O Python do venv pode iniciar outro interpretador filho; cancelamento considera a árvore de processos inteira.
- **D-060-06** — Processo que perde o lease pode continuar rodando; bloquear a publicação não basta, é preciso interromper/isolar a capacidade de efeito externo.
- **D-060-07** — #605 falhou em inventário e PR policy; a integração respeita FP-042 e Quality Guardian sem exceções.

## 3. Objetivos

**Principal:** transformar a PoC em infraestrutura durável que coordene Claude Code, Codex CLI, GitHub e o backlog.

**Critérios de sucesso:** (1) processos residentes consomem eventos reais; (2) CLIs só sobem quando há trabalho; (3) eventos sobrevivem a reinício/falha; (4) um evento não gera publicação duplicada; (5) review vinculado ao HEAD correto; (6) correção gera nova revisão; (7) conclusão de PR libera a próxima tarefa elegível; (8) Agent Control Bar mostra o estado real; (9) ciclo completo sem mensagem intermediária do proprietário; (10) nenhuma política enfraquecida.

**Não objetivos:** Kafka/RabbitMQ/SQS; segundo scheduler; substituir GitHub Project ou Quality Guardian; agentes com privilégio irrestrito; decisões visuais automáticas; API paga obrigatória; mexer no pipeline geométrico.

## 4. Arquitetura

```text
GitHub → Event Bridge / Scheduler → SQLite Durable Event Bus
   (inbox · work queue · transactional outbox · lease/fencing · DLQ · audit log)
      ├─► Claude Worker → Claude Code CLI → Implementation Result
      ├─► Codex Worker  → Codex CLI       → Structured Review
      └─► Deterministic Coordinator → tests/guards · GitHub publisher · CI reconciliation · scheduler · project sync
                                        └─► Agent Control Bar
```

### 4.2 Reutilização obrigatória
`tools/orchestration/{event_bridge,event_executor,executor_delivery,execution_guards}.py`, `tools/orchestration/agent_bar/`, `tools/validation/{execution_state,board_sync}.py` e os módulos da PoC (`event_store.py`, `agents_cli.py`, `workers.py`, `run_real_e2e.py`, `live_resilience.py`). Confirmar caminhos no HEAD (ver §0).

- **Um único** mecanismo autoritativo de claim, lease e conclusão.
- SQLite = fonte de verdade operacional de entrega de jobs após a migração. GitHub = fonte de verdade de PRs, reviews, CI, merges e Issues.
- A máquina de estados da FP-059 continua dona das transições de negócio.

### 4.3 Responsabilidades
| Componente | Responsabilidade |
|---|---|
| Event Bridge | detectar e normalizar mudanças externas |
| SQLite | persistir eventos, jobs e resultados |
| Scheduler | identificar tarefas elegíveis |
| Claude Worker | invocar Claude e capturar resultado |
| Codex Worker | invocar Codex e capturar parecer |
| Coordinator | decidir transições e autorizar ações |
| Publisher | aplicar efeitos no GitHub |
| Quality Guardian | executar políticas de governança |
| Agent Bar | exibir estado e controles |

Workers não decidem merge nem contornam a máquina de estados.

## 5. Contrato de eventos

### 5.1 Envelope canônico
```json
{
  "schema_version": 1,
  "event_id": "uuid",
  "event_type": "REVIEW_REQUESTED",
  "aggregate_type": "pull_request",
  "aggregate_id": "GFCDOTA/sketchup-mcp#<pr>",
  "correlation_id": "uuid",
  "causation_id": "uuid",
  "idempotency_key": "repo:<pr>:<sha>:review",
  "producer": "coordinator",
  "occurred_at": "ISO-8601",
  "payload": {"repository": "GFCDOTA/sketchup-mcp", "issue": 0, "pr": 0, "head_sha": "SHA_COMPLETO", "policy_version": "POLICY_VERSION"}
}
```
IDs e SHAs vêm do contexto real; o exemplo não é um evento executado.

### 5.2 Eventos suportados
- **GitHub/backlog:** `ISSUE_READY`, `PR_OPENED`, `PR_HEAD_UPDATED`, `CI_PASSED`, `CI_FAILED`, `GITHUB_REVIEW_SUBMITTED`, `PR_MERGED`, `ISSUE_UNBLOCKED`
- **Claude:** `IMPLEMENT_REQUESTED`, `IMPLEMENT_STARTED`, `IMPLEMENT_COMPLETED`, `IMPLEMENT_FAILED`, `CORRECTION_REQUESTED`
- **Codex:** `REVIEW_REQUESTED`, `REVIEW_STARTED`, `REVIEW_APPROVED`, `REVIEW_CHANGES_REQUESTED`, `REVIEW_BLOCKED`
- **Orquestração:** `JOB_RETRY_SCHEDULED`, `JOB_SUPERSEDED`, `JOB_FAILED`, `JOB_DEAD_LETTERED`, `PUBLISH_REQUESTED`, `PUBLISH_COMPLETED`, `PUBLISH_FAILED`, `WORKFLOW_COMPLETED`

### 5.3 Semântica de entrega
At-least-once durável; dedup por idempotency key; claim transacional; exclusão mútua por agregado; lease renovável; fencing token por aquisição; retry com backoff+jitter; DLQ persistente; auditoria de transições; processamento seguro após reinício. **Não** prometer exactly-once para efeitos externos — no GitHub, idempotência + reconciliação + checagem de estado antes de repetir mutação.

## 6. Persistência SQLite

### 6.1 Entidades mínimas
`events(id, event_id, event_type, aggregate_id, correlation_id, causation_id, idempotency_key, payload_json, schema_version, occurred_at)` ·
`jobs(id, event_id, consumer, state, attempt, max_attempts, available_at, lease_owner, lease_token, lease_until, last_error)` ·
`outbox(id, event_id, target, operation, payload_json, idempotency_key, status, attempts)` ·
`dead_letters(id, job_id, reason, failed_at)` ·
`agent_runs(id, job_id, agent, process_id, process_group_id, started_at, finished_at, exit_code, result, artifact_hash)` ·
`state_transitions(id, aggregate_id, from_state, to_state, reason, occurred_at)`

### 6.2 Propriedades obrigatórias
WAL; `busy_timeout` configurável; conexões fechadas explicitamente (D-060-01); migrações versionadas; transações curtas para claim/update; escrita atômica de resultado + eventos subsequentes; retenção configurável; banco e logs fora do git; banco em caminho persistente fora de worktree descartável. **O LLM nunca recebe o SQLite como banco gravável.**

### 6.3 Migração dos estados FP-057
1. ler estado legado; 2. mapeamento documentado; 3. importação idempotente; 4. modo shadow; 5. cutover com executor pausado; 6. reconciliar leases/eventos; 7. verificar contagem e semântica; 8. rollback para DRY_RUN se falhar. Nunca dois executores escrevendo no mesmo ciclo.

## 7. Segurança dos agentes

### 7.1 Claude Worker
Worktree dedicada; só a tarefa autorizada; tools explicitamente permitidas; **sem token GitHub de publicação, sem `git push`/merge/aprovação**; não toca governança fora do escopo; orçamento, timeout, cancelamento; produz artefatos para validação determinística. Staging, testes, commit e push são do executor Python.

### 7.2 Codex Worker
Sandbox read-only; HEAD fixo; recebe diff, arquivos permitidos e evidências verificadas; sem credencial de publicação; não altera arquivos; JSON aderente ao schema; declara ausência de evidência. O coordenador roda os testes e repassa os resultados (D-060-03).

### 7.3 Prova de inspeção
```json
{
  "head_sha": "SHA_COMPLETO",
  "verdict": "REQUEST_CHANGES",
  "inspected": true,
  "files_reviewed": [{"path": "example.py", "sha256": "HASH_REAL", "code_excerpt": "linha exata do arquivo"}],
  "findings": [],
  "evidence": {"tests_passed": false, "source": "trusted_test_runner"}
}
```
Validar hashes e trechos — presença deles não prova qualidade. Código não inspecionado, conteúdo desatualizado ou afirmação incompatível com a evidência ⇒ `REVIEW_BLOCKED`, nunca aprovação.

### 7.4 Identidade independente
Auth do Codex via ChatGPT ≠ identidade GitHub independente. O publisher de review usa credencial separada e verificável; se o GitHub não reconhecer a separação autor×aprovador, a aprovação automática é bloqueada.

## 8. Fases

| Fase | Objetivo | Aceite (resumo) |
|---|---|---|
| **P0** | PoC #605 vira evidência reproduzível; gates corrigidos sem exceção | evidência E2E preservada; 24+ testes verdes; resiliência documentada; 8/8 checks; revisão independente; nada de produção alterado |
| **P1** | Durable Event Bus de produção (migrações, jobs, outbox, DLQ, claims, lease, fencing, observabilidade) | publicação persistente; claim transacional; dedup; retry+DLQ; recovery pós-restart; zero side effect duplicado; suíte sem LLM no CI |
| **P2** | Process Supervisor: árvore de processos Windows (Job Objects), processo↔lease↔fencing, cancelar na perda de titularidade | matar worker interrompe CLIs; lease perdido ⇒ cancelado/isolado; nenhum órfão apto a publicar; novo worker recupera; resultado antigo recusado; testado em Windows real |
| **P3** | Claude Worker ligado ao executor FP-057 (consome `IMPLEMENT_REQUESTED`/`CORRECTION_REQUESTED`, valida `is_error`, testes por runner confiável, guards, outbox) | Claude real iniciado por evento SQLite; sem push no filho; entrega pelo executor; E2E com PR descartável; CI no HEAD publicado |
| **P4** | Codex Worker + publisher independente (pacote de revisão imutável, schema + evidência, review ID e SHA registrados) | Codex real revisa PR descartável; evidência verificada; não altera arquivos; identidade independente; auth falha ⇒ bloqueio; review desatualizado não aprova |
| **P5** | Event Bridge GitHub (polling reutilizando #604): novo PR/commit, CI, review, merge, issue desbloqueada → evento idempotente | todos detectados; duplicado ignorado; GitHub fora não perde job; reconciliação pós-restart |
| **P6** | Closed loop E2E real (13 passos §8-P6 da versão original) + negativos: credencial inválida, CI vermelho, HEAD alterado, lease perdido, processo interrompido, review sem evidência | ambos CLIs reais; zero mensagem manual; tudo persistido; ≥1 correção pós-review; CI verde no HEAD final; review independente válido; relatório com PIDs, SHAs e eventos |
| **P7** | Operação contínua controlada: scheduler no bus, Project #1, pause/resume, fila/retries/DLQ na Agent Bar, autostart, limites de custo/tentativa/simultaneidade, rollback, soak supervisionado | 2 jobs em sequência; reboot recupera; Agent Bar fiel; DRY_RUN e SUPERVISED; kill switch; sem órfãos; **CONTINUOUS só com autorização explícita** |

## 9. Matriz de testes

| Teste | Evidência exigida |
|---|---|
| Dois workers disputam um job | um único claim |
| Evento duplicado | uma única execução |
| Worker encerrado | job recuperado |
| CLI perde lease | processo cancelado ou isolado |
| SQLite reiniciado | eventos preservados |
| GitHub indisponível | retry sem perda |
| HEAD mudou | review invalidado |
| Claude/Codex sem login | falha/DLQ |
| CLI retornou falso sucesso | falha reconhecida |
| Codex não inspecionou | `REVIEW_BLOCKED` |
| Codex alterou workspace | review invalidado |
| CI vermelho | sem aprovação |
| Publisher indisponível | outbox recuperável |
| PR protegido | merge bloqueado |
| Kill switch | nenhum job novo |
| Reinício Windows | retomada segura |
| Nenhuma tarefa | workers ociosos |
| Falha permanente | DLQ + diagnóstico |
| Duas tarefas Ready | ordem do scheduler |

Gates por fase: unit + integração; negativos de segurança; Quality Guardian; inventário FP-042; PR policy e branch protection; revisão independente; evidência operacional quando a fase exige Windows/CLIs reais. Mock só nas suítes determinísticas de isolamento e falha — nunca substitui o E2E real.

## 10. Observabilidade (FP-058)
A Agent Bar consome snapshots autoritativos do orquestrador: EVENT BUS (health, pending, running, retry, DLQ) · CLAUDE (state, job, PID, lease) · CODEX (state, job, PID, review SHA) · GITHUB (PR, CI, review, merge allowed) · ORCHESTRATOR (mode DRY_RUN/SUPERVISED/CONTINUOUS, last transition, last error). O painel não inicia agentes — envia comandos seguros ao coordenador. Banco ou GitHub indisponível **nunca** aparece como saudável.

## 11. Migração e rollback
Progressão: laboratório → extração → shadow → executor de 1 PR supervisionado → revisor de 1 PR supervisionado → closed loop → scheduler → habilitação controlada.
Rollback: para novos claims; cancela ou deixa terminar com segurança os jobs autorizados; preserva banco, logs e artefatos; impede workers antigos de publicar; reconcilia side effects pendentes; volta para DRY_RUN; não apaga histórico.

## 12. Definition of Done
PoC #605 reconciliada · Event Store integrado · estados legados migrados · Claude Worker · Codex Worker · publisher independente · SQLite com retry/outbox/DLQ · fencing e cancelamento comprovados · Event Bridge GitHub · reviews no HEAD certo · closed loop E2E · Agent Bar integrada · recuperação pós-reinício · Quality Guardian e CI verdes · zero violação de branch protection · execução contínua autorizada separadamente.

**Prova final:** um PR real e descartável recebe pedido de correção; Claude corrige e publica pelo executor confiável; Codex revisa o novo HEAD e, se preciso, pede outra alteração; Claude corrige; Codex aprova; tudo como eventos persistidos, sem mensagem manual intermediária e sem sessão de chat aberta.

## 13. Instruções de execução
1. Ler esta SPEC, a FP-059 e o relatório do #605. 2. PoC = aprovada experimentalmente, não infraestrutura de produção. 3. Reconciliar repo e PRs antes de codar (§0). 4. Issue #606 vinculada à FP-059; SPEC no inventário. 5. P0–P7 em PRs pequenos e rastreáveis. 6. Reutilizar módulos existentes, nunca outro orquestrador. 7. Contínuo desligado até E2E + autorização específica. 8. Resultados e bloqueios no GitHub com evidência verificável. 9. Não alterar políticas/guards para acelerar. 10. Não declarar conclusão com base só em teste simulado.

**Princípio:** o produto é um orquestrador orientado a eventos que coordena agentes reais com persistência, segurança e recuperação — não mais uma PoC, documentação ou interface.
