# FP-060-A01 M1 — closed-loop minimo em laboratorio isolado

**Veredito: PASS** · modo `closed_loop` · lab `fp060_lab_618_7a8afa1c` · HEAD final `56bb00b15fda36127a01f09eeebec72cbe49208a`

| Criterio (derivado do SQLite/git) | Resultado |
|---|---|
| claude_cli_observed | PASS |
| codex_cli_observed | PASS |
| request_changes_then_correction | PASS |
| approved_after_correction | PASS |
| approval_bound_to_final_head | PASS |
| workflow_completed | PASS |
| no_pending_or_running_event | PASS |
| one_delivery_per_implement_event | PASS |
| survived_coordinator_restart | PASS |
| finished_cli_runs_job_contained | PASS |
| orphan_cli_tree_dead_after_coordinator_kill | PASS |
| coordinator_tests_ran_in_os_sandbox | PASS |
| verdicts_published_once_via_outbox | PASS |
| interrupted_publication_was_reconciled | PASS |

| Run | Evento | Agente | PID | Exit | s | Contencao | Binario |
|---|---|---|---|---|---|---|---|
| 1 | 1 | claude | 33632 | INTERROMPIDO | - | - | `claude.exe` |
| 2 | 1 | claude | 35208 | 0 | 9.4 | job_object | `claude.exe` |
| 3 | 3 | codex | 48008 | 0 | 31.2 | job_object | `codex.exe` |
| 4 | 5 | claude | 18496 | 0 | 14.5 | job_object | `claude.exe` |
| 5 | 7 | codex | 31344 | 0 | 35.9 | job_object | `codex.exe` |

| # | Evento | Estado | Tentativas | Pai |
|---|---|---|---|---|
| 1 | IMPLEMENT_REQUESTED | DONE | 2 |  |
| 2 | IMPLEMENT_COMPLETED | RECORDED | 0 | 1 |
| 3 | REVIEW_REQUESTED | DONE | 2 | 1 |
| 4 | REVIEW_CHANGES_REQUESTED | DONE | 1 | 3 |
| 5 | CORRECTION_REQUESTED | DONE | 1 | 4 |
| 6 | IMPLEMENT_COMPLETED | RECORDED | 0 | 5 |
| 7 | REVIEW_REQUESTED | DONE | 1 | 5 |
| 8 | REVIEW_APPROVED | RECORDED | 0 | 7 |
| 9 | WORKFLOW_COMPLETED | RECORDED | 0 | 7 |

Commits: `3883994dd985` lab: semente com defeito conhecido; `618fc164802f` lab: rodada 1 (IMPLEMENT_REQUESTED); `56bb00b15fda` lab: rodada 2 (CORRECTION_REQUESTED)
Coordenadores (processos distintos): lab-coordinator:13696, lab-coordinator:20036, lab-coordinator:20436, lab-coordinator:24704, lab-coordinator:34616, lab-coordinator:40180, lab-coordinator:6712
Leases retomados: reclaimed expired lease of lab-coordinator:20436; attempt 2; reclaimed expired lease of lab-coordinator:6712; attempt 2
Runs sem termino registrado (coordenador morreu com o CLI no ar): 1
Arvore dos CLIs interrompidos: run 1 (claude, pid 33632) apos 2.0s: nenhum processo vivo
Isolamento dos testes do coordenador (evidencia dos eventos concluidos): appcontainer_no_capabilities
Outbox: #1 `lab:slug:review:618fc164802fb36514b0339be4513336bd3bd324:REQUEST_CHANGES` DONE em 2 tentativa(s); #2 `lab:slug:review:56bb00b15fda36127a01f09eeebec72cbe49208a:APPROVE` DONE em 1 tentativa(s)
Ledger (o que o sistema externo recebeu): 2 linha(s), 2 chave(s) distinta(s)
Reviews bloqueados: nenhum
Motivos de falha gravados nos eventos: nenhum

Limites: testes em AppContainer sem capacidades: nega arquivos e credenciais do usuario e a rede, mas le o que a ACL abre a todo AppContainer (Windows, Program Files), e NAO garante a integridade do resultado (o codigo testado controla o exit code); APPROVE tecnico de laboratorio != review independente no GitHub (M2); sem GitHub, sem --execute; o alvo do outbox e um arquivo local que faz o papel de sistema externo; Job Object nao e sandbox: so prende a vida da arvore do CLI ao coordenador e ao lease
