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
| Publisher indisponível | FEITO | outbox recuperável; reconciliação pelo marcador |
| PR protegido | BLOQUEADO | `auto_merge` só mescla com a proteção exigindo aprovação independente (lida, nunca alterada); a proteção é configuração do proprietário |
| Kill switch | EM PR | `AUTOMERGE_DISABLED` e `PR_LIFECYCLE_DISABLED` (#648/#665) |
| Reinício Windows | ABERTO | recuperação por morte/reinício de processos validada; reboot real depende de registrar a tarefa |
| Falha permanente | FEITO | DLQ + `JOB_FAILED` |

## 3. Critérios §12.1 (acionamento automático do Codex)

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
| A7 | reconciliação periódica recupera pedidos perdidos e PRs antigos | FEITO (execução real; ciclo de 60 s por causa da cota da API) |
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
