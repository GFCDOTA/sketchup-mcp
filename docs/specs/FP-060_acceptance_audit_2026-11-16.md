# FP-060 — Auditoria dos critérios de aceite (2026-11-16)

Auditoria honesta da SPEC `FP-060_event_driven_agent_orchestration.md` (fases §8, matriz §9, DoD §12 e critérios §12.1). Estados: **FEITO** (em `develop`, com
prova), **EM PR** (implementado e testado, ainda não em `develop`), **PARCIAL**, **ABERTO**, **BLOQUEADO** (depende de decisão do proprietário). Nada aqui é
declarado concluído sem evidência verificável; a fonte de verdade do estado vivo é o GitHub (PRs/Issues) e o Project #1.

## 1. Fases (§8)

| Fase | Estado | Evidência / o que falta |
|---|---|---|
| P0 PoC #605 reconciliada | FEITO | evidência reproduzível preservada; gates e SPEC em `develop` (PRs #610–#616) |
| P1 Durable Event Bus | FEITO | `tools/orchestration/event_store.py` (claim transacional, lease, fencing, DLQ, outbox); recuperação com processos reais em `tests/test_event_store_processes.py` (#661, mergeado) |
| P2 Process Supervisor | FEITO | `process_supervisor.py` + check de CI `windows process supervisor`; sandbox de testes (#617, mergeado com autorização do proprietário para a mudança de CI) |
| P3 Claude Worker | PARCIAL | executor e entrega guardada em `develop`; confirmação do HEAD publicado / publicação pendente (#652), laço resiliente (#640), worker de implementação e intake (#646/#641/#636) estão em PR com achados do revisor independente em tratamento |
| P4 Codex Worker + publisher | EM PR | `codex_reviewer`, Outbox e destino GitHub (#630, #632, #618, #619); publicação como `fmmodesto` comprovada em revisões reais (ver §3); pilha depende da atualização com `develop` |
| P5 Event Bridge GitHub | PARCIAL | bridge em `develop`; durabilidade do estado e recuperação (#635), divergência JSON×SQLite (#634), reconciliação do store (#642) em PR |
| P6 Closed loop E2E real | PARCIAL | ver §3: ciclo real até o APPROVE comprovado; merge automático aguarda a proteção da branch |
| P7 Operação contínua | ABERTO | tarefa agendada (instalador pronto no #665), reboot real, soak de 2 jobs e Agent Bar com o store (#663) pendentes de merge/registro; **CONTINUOUS só com autorização explícita** |

## 2. Matriz de testes (§9)

| Teste | Estado | Prova |
|---|---|---|
| Dois workers disputam um job | FEITO | `test_event_store_processes.py` (5 processos disputando UM evento, o vencedor segura o claim) |
| Evento duplicado | FEITO | publicação duplicada por 6 processos reais; chave `review-request:<repo>#<PR>:<HEAD>` no ciclo de PR |
| Worker encerrado | FEITO | kill duro em processo real; recuperação uma única vez e resultado antigo recusado (EventStore e `pr_lifecycle`, #665) |
| CLI perde lease | FEITO | heartbeat/fencing do executor e do worker de revisão |
| SQLite reiniciado | FEITO | eventos e dedup atravessam a reabertura em outro processo |
| GitHub indisponível | PARCIAL | retry/backoff e cota da API tratados; recuperação após limite de requisições observada em execução real |
| HEAD mudou | FEITO | pedido do HEAD antigo descartado; novo HEAD gera nova revisão independente |
| Claude/Codex sem login | FEITO | `BLOCKED_*`/DLQ com diagnóstico |
| CLI retornou falso sucesso | FEITO | `is_error` e confirmação do HEAD publicado |
| Codex não inspecionou | FEITO | `REVIEW_BLOCKED` |
| CI vermelho | FEITO | pedido descartado; sem aprovação |
| Codex alterou o workspace | FEITO | veredito invalidado e revisão bloqueada: `tests/test_closed_loop_lab.py::test_reviewer_that_alters_the_workspace_invalidates_its_own_verdict` e `tests/test_codex_reviewer.py::test_check_untouched_blocks_on_dirty_tree_or_moved_head` (guarda de segurança; worktree de revisão separada, `read-only`) |
| Nenhuma tarefa (workers ociosos) | PARCIAL | sem pedido pronto o pool/laço ficam ociosos sem gastar cota: `test_an_event_waiting_for_checks_is_not_polled_again_inside_the_recheck_window` e `test_the_pool_default_idle_is_long_enough_not_to_burn_the_quota` (`tests/test_pr_lifecycle.py`, no #665); observado no laço real (ciclos sem evento). Falta o soak de 2 jobs sequenciais com a tarefa registrada |
| Duas tarefas Ready (ordem do scheduler) | FEITO | `test_the_oldest_ready_request_goes_first_and_a_waiting_one_does_not_block_the_queue` (fila de revisão, #665) e a ordem do agendador de tarefas (`test_decide_skips_tasks_claimed_by_another_execution_and_resumes_its_own_first`, `tests/test_fp057_p2_scheduler.py`) |
| Publisher indisponível | FEITO | outbox recuperável; reconciliação pelo marcador |
| PR protegido | BLOQUEADO | `auto_merge` só mescla com a proteção exigindo aprovação independente (lida, nunca alterada); a proteção é configuração do proprietário |
| Kill switch | EM PR | `AUTOMERGE_DISABLED` e `PR_LIFECYCLE_DISABLED` (#648/#665) |
| Reinício Windows | ABERTO | recuperação por morte/reinício de processos validada; reboot real depende de registrar a tarefa |
| Falha permanente | FEITO | DLQ + `JOB_FAILED` |

## 3. Critérios §12.1 (acionamento automático do Codex)

Fonte dos critérios A1–A11: `docs/specs/FP-060_event_driven_agent_orchestration.md` §12.1, que **ainda não está em `develop`**: a seção é adicionada pelo PR #665
(branch `feat/fp060-pr-lifecycle`, empilhado sobre o #648) e só passa a ser rastreável a partir do merge dele. Até lá, a numeração A1–A11 é a desta auditoria e do #665.

Prova real (PR descartável #667, Issue #666), sem intervenção humana entre as etapas: PR aberto em rascunho -> rascunho finalizado e `fmmodesto` solicitado pelo
`pr_lifecycle` -> `REVIEW_REQUESTED` no EventStore -> Codex real (`CHANGES_REQUESTED` no HEAD `c667f07`) -> executor com Claude real corrige e publica `0bfffe9` -> novo
HEAD revisado de forma independente (`APPROVED`) com 9/9 checks. A decisão do `auto_merge` para esse HEAD é WAIT **somente** pela proteção da `develop` (ver abaixo).

| # | Critério | Estado |
|---|---|---|
| A1 | PR pronto sai do rascunho e solicita o revisor | FEITO (execução real; módulo no #665) |
| A2 | `REVIEW_REQUESTED` no EventStore, dedup repo/PR/HEAD | FEITO (execução real) |
| A3 | worker espera checks e dispara sessão real do Codex | FEITO (execução real, até 3 em paralelo) |
| A4 | parecer publicado como `fmmodesto` via Outbox | FEITO (execução real) |
| A5 | REQUEST_CHANGES aciona o Claude; novo HEAD gera nova revisão | FEITO no #667 (PR `executor-ok` fora de caminho crítico); PRs do próprio FP-060 tocam caminhos críticos e são corrigidos na sessão do desenvolvedor, por desenho das guardas |
| A6 | APPROVE libera o merge automático protegido | BLOQUEADO: depende da proteção da `develop` exigir 1 aprovação, descartar aprovações antigas e resolver conversas (script `configure_branch_protection.ps1`, executado pelo proprietário) |
| A7 | reconciliação periódica recupera pedidos perdidos e PRs antigos | PARCIAL: a recuperação de pedidos perdidos e de PRs antigos foi comprovada em execução real, mas o critério exige ciclo de **30 s** e o laço roda a **60 s** (cota REST de 5000/h esgotada uma vez com 30 s e 3 listagens por ciclo). Pendência explícita: alinhar a frequência (cache da listagem por HEAD já reduz o custo; reavaliar 30 s com a tarefa registrada) ou alterar o critério na SPEC com aprovação |
| A8 | recuperação após reinício do computador | ABERTO (tarefa agendada ainda não registrada) |
| A9 | Project Board sincronizado | FEITO (`backlog_reconcile --apply`, 16 movimentos validados) |
| A10 | independente da tarefa agendada externa | FEITO (nenhum passo lê essa tarefa) |
| A11 | E2E real sem mocks | PARCIAL: ciclo comprovado até o APPROVE; falta o merge automático |

## 4. Definition of Done (§12)

PoC reconciliada FEITO · Event Store FEITO · estados legados migrados FEITO · Claude Worker PARCIAL · Codex Worker EM PR · publisher independente EM PR · SQLite com
retry/outbox/DLQ FEITO · fencing e cancelamento FEITO · Event Bridge FEITO/PARCIAL · reviews no HEAD certo FEITO · closed loop E2E PARCIAL · Agent Bar com o store EM PR (#663) ·
recuperação pós-reinício ABERTO · Quality Guardian e CI verdes FEITO nos PRs abertos · **zero violação de branch protection FEITO (nenhuma proteção foi alterada ou contornada)** ·
execução contínua autorizada separadamente ABERTO.

**A FP-060 NÃO está concluída.** Pendências que impedem a conclusão: (1) proteção da `develop` (proprietário); (2) merge automático do ciclo completo; (3) registro da
tarefa agendada e prova de reboot/soak; (4) drenagem dos PRs abertos até aprovação independente e merge.

## 5. Evidências de integração (atualizado após a proteção da `develop`)

| Item | Estado | Evidência verificável |
|---|---|---|
| Proteção da `develop` | FEITO (aplicada pelo proprietário) | leitura da API: 8 checks obrigatórios, `enforce_admins: true`, `required_approving_review_count: 1`, `dismiss_stale_reviews: true`, `required_conversation_resolution: true`, sem force-push nem exclusão |
| Merge automático protegido de ponta a ponta | FEITO | PR #667 (disposable, Issue #666): `REVIEW_REQUESTED` → Codex real `CHANGES_REQUESTED` → correção do Claude real → nova revisão `APPROVED` no HEAD exato `0bfffe9` (9/9 checks) → `auto_merge` decidiu MERGE e mesclou (commit `7ea99dae`), com a proteção exigindo aprovação (lida, nunca alterada) |
| Independência do revisor | FEITO | todas as revisões publicadas como `fmmodesto`, uma por HEAD; aprovações de SHAs antigos nunca reaproveitadas (`dismiss_stale_reviews`) |
| Revisão dos PRs que têm testes de processos reais | BLOQUEADO (ambiental, decisão do proprietário) | dentro do AppContainer do revisor os testes que criam processos filhos (`default_runner`, kill duro, dois processos disputando o item, `InstanceLock` entre processos, `main` recusando segunda instância) estouram o prazo (6 falhas: `tests/test_event_executor.py::test_default_runner_kills_a_live_process_tree_as_soon_as_cancel_is_set` e 5 em `tests/test_event_executor_recovery.py`); o veredito vira `NEEDS_HUMAN` (`tests_passed: false`, `findings: 0`) e não é publicado. Os mesmos testes passam localmente e no CI (`pytest (py3.11/3.12)` e `windows process supervisor`). Afeta #643, #652, #640, #642 |
| Tarefa agendada, reboot real, soak | ABERTO | dependem do #665 (empilhado no #648) |
